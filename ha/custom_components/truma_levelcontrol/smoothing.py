"""Plausibilitaetsfilter fuer den LevelControl-Fuellstand (reines Python, ohne HA-Abhaengigkeiten).

Hintergrund (Messdaten 27.-31.10.2026, siehe docs/LEVELCONTROL.md):
* Im Stand liefert der Sensor alle 10 min einen Wert mit +-1 % Rauschen (75 <-> 76 ueber Stunden).
* Waehrend der Fahrt oder bei schlechter Ankopplung kommt "0 % / Qualitaet 0" (kein Echo),
  obwohl die Flasche eben noch 100 % hatte.
* Einzelne Ausreisser mit Qualitaet 3 kommen ebenfalls vor (99 % zwischen lauter 12 %).
* Bei fast leerer Flasche (<= ~8 %) ist die Qualitaet oft 0, der Prozentwert aber noch brauchbar.
  Qualitaet 0 heisst also "schwaches/kein Echo", nicht "Flasche leer" - und auch nicht "Messung falsch".

Physik: eine Flasche kann zwischen zwei Messungen nur um den Verbrauch sinken (Alde-Gasbrenner
~0,4 kg/h = ~4 %/h bei 11 kg) und nie steigen - ausser beim Flaschenwechsel. Daraus der Filter:

1. Korridor: Werte zwischen (letzter Wert - MAX_RATE*dt - TOL) und (letzter Wert + TOL) werden
   direkt uebernommen, unabhaengig von der Qualitaet.
2. Ausserhalb des Korridors mit Qualitaet >= 1 (echtes Echo): Kandidat. Erst wenn CONFIRM_SAMPLES
   aufeinanderfolgende Messungen den Kandidaten bestaetigen (Flaschenwechsel, Sensor neu platziert),
   wird er uebernommen.
3. Ausserhalb des Korridors mit Qualitaet 0 (kein Echo): letzten Wert halten. Da der Korridor mit
   der Zeit nach unten waechst, wird eine echte Leerung (langsam auf wenige Prozent, dann 0) trotzdem
   angezeigt - eine Vollflasche kann so aber nicht in 30 Minuten auf 0 fallen.
4. Glaettung der uebernommenen Werte: Median aus 3, dann exponentielle Glaettung, dann 1 %-Hysterese
   fuer die Anzeige, damit 75/76-Flackern verschwindet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median

# Maximal plausibler Verbrauch in Prozentpunkten pro Stunde (11-kg-Flasche, Heizung + Kocher,
# mit Reserve). 6 %/h entsprechen ca. 0,66 kg/h.
MAX_RATE_PCT_PER_H = 6.0
# Toleranz fuer Messrauschen nach oben und zusaetzlich nach unten (Prozentpunkte).
TOLERANCE_PCT = 3.0
# So viele aufeinanderfolgende, untereinander konsistente Messungen ausserhalb des Korridors
# braucht ein neuer Pegel (Flaschenwechsel), bevor er uebernommen wird. Bei 10-min-Intervall = 30 min.
CONFIRM_SAMPLES = 3
# Gewicht der neuesten Messung in der exponentiellen Glaettung.
EMA_ALPHA = 0.4
# Anzeige aendert sich erst, wenn der geglaettete Wert um so viel vom angezeigten abweicht.
DISPLAY_HYSTERESIS_PCT = 1.0
MEDIAN_WINDOW = 3


@dataclass
class FilterState:
    """Zustand des Filters (wird von Home Assistant ueber Neustarts gesichert)."""

    accepted: float | None = None       # letzter plausibler Rohwert (%)
    accepted_at: float | None = None    # Unix-Sekunden
    smoothed: float | None = None       # EMA ueber die uebernommenen Werte
    display: int | None = None          # angezeigter Fuellstand (%)
    capacity_g: int | None = None       # Flaschengroesse aus grams/percent (fuer kg-Anzeige)
    recent: list[float] = field(default_factory=list)   # letzte uebernommene Werte (Median)
    candidate: float | None = None      # Kandidat fuer neuen Pegel
    candidate_count: int = 0
    candidate_since: float | None = None
    hold_since: float | None = None     # seit wann "kein Echo" gehalten wird
    status: str = "init"

    def as_dict(self) -> dict:
        return {
            "accepted": self.accepted,
            "accepted_at": self.accepted_at,
            "smoothed": self.smoothed,
            "display": self.display,
            "capacity_g": self.capacity_g,
            "recent": list(self.recent),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FilterState":
        s = cls()
        try:
            s.accepted = None if d.get("accepted") is None else float(d["accepted"])
            s.accepted_at = None if d.get("accepted_at") is None else float(d["accepted_at"])
            s.smoothed = None if d.get("smoothed") is None else float(d["smoothed"])
            s.display = None if d.get("display") is None else int(d["display"])
            s.capacity_g = None if d.get("capacity_g") is None else int(d["capacity_g"])
            s.recent = [float(x) for x in d.get("recent", [])][-MEDIAN_WINDOW:]
            s.status = "wiederhergestellt"
        except (TypeError, ValueError):
            return cls()
        return s


class LevelFilter:
    """Nimmt Rohmessungen (percent, grams, quality, Zeitstempel) an und liefert den geglaetteten Wert."""

    def __init__(self, state: FilterState | None = None) -> None:
        self.state = state or FilterState()

    # ----------------------------------------------------------------- Hilfen
    @property
    def display_percent(self) -> int | None:
        return self.state.display

    @property
    def display_kg(self) -> float | None:
        s = self.state
        if s.display is None or not s.capacity_g:
            return None
        return round(s.display / 100.0 * s.capacity_g / 1000.0, 1)

    def _accept(self, value: float, now: float) -> None:
        s = self.state
        s.accepted = value
        s.accepted_at = now
        s.candidate = None
        s.candidate_count = 0
        s.candidate_since = None
        s.hold_since = None
        s.recent.append(value)
        del s.recent[:-MEDIAN_WINDOW]
        med = median(s.recent)
        s.smoothed = med if s.smoothed is None else s.smoothed + EMA_ALPHA * (med - s.smoothed)
        if s.display is None or abs(s.smoothed - s.display) >= DISPLAY_HYSTERESIS_PCT:
            s.display = int(round(s.smoothed))

    def _reset_to(self, value: float, now: float, status: str) -> None:
        """Neuer Pegel (Flaschenwechsel): Glaettung verwerfen, sofort anzeigen."""
        s = self.state
        s.recent.clear()
        s.smoothed = None
        s.display = None
        self._accept(value, now)
        s.status = status

    # ------------------------------------------------------------------ Kern
    def update(self, percent: int, grams: int, quality: int, now: float) -> int | None:
        """Eine Messung verarbeiten. Gibt den anzuzeigenden Fuellstand (%) zurueck."""
        s = self.state
        value = float(percent)
        if percent > 0 and grams > 0:
            s.capacity_g = int(round(grams * 100.0 / percent))

        # Erste Messung: alles mit echtem Echo oder Inhalt uebernehmen; 0 %/Q0 erst nach Bestaetigung.
        if s.accepted is None:
            if quality > 0 or percent > 0:
                self._reset_to(value, now, "erster Wert")
            else:
                self._track_candidate(value, now)
                if s.candidate_count >= CONFIRM_SAMPLES:
                    self._reset_to(value, now, "erster Wert (leer bestaetigt)")
                else:
                    s.status = "warte auf erste brauchbare Messung"
            return s.display

        dt_h = max(0.0, (now - (s.accepted_at or now)) / 3600.0)
        lower = s.accepted - MAX_RATE_PCT_PER_H * dt_h - TOLERANCE_PCT
        upper = s.accepted + TOLERANCE_PCT

        if lower <= value <= upper:
            self._accept(value, now)
            s.status = "ok" if quality > 0 else "ok (schwaches Echo)"
            return s.display

        if quality == 0:
            # Kein Echo (Fahrt, Sensor verrutscht, Flasche abgehoben): letzten Wert halten.
            # Ein laufender Kandidat bleibt stehen (wird weder bestaetigt noch verworfen).
            if s.hold_since is None:
                s.hold_since = now
            s.status = "kein Echo, halte letzten Wert"
            return s.display

        # Echtes Echo, aber ausserhalb des Korridors: Kandidat fuer Flaschenwechsel / Neuplatzierung.
        self._track_candidate(value, now)
        if s.candidate_count >= CONFIRM_SAMPLES:
            self._reset_to(value, now, "neuer Pegel uebernommen")
        else:
            s.status = f"unplausibel, Kandidat {s.candidate_count}/{CONFIRM_SAMPLES}"
        return s.display

    def _track_candidate(self, value: float, now: float) -> None:
        s = self.state
        if s.candidate is not None and abs(value - s.candidate) <= TOLERANCE_PCT:
            s.candidate_count += 1
        else:
            s.candidate_count = 1
            s.candidate_since = now
        s.candidate = value

    def attributes(self) -> dict:
        s = self.state
        return {
            "status": s.status,
            "letzter_plausibler_rohwert": s.accepted,
            "geglaettet": None if s.smoothed is None else round(s.smoothed, 2),
            "kandidat": s.candidate,
            "kandidat_bestaetigungen": s.candidate_count,
            "flaschengroesse_kg": None if not s.capacity_g else round(s.capacity_g / 1000.0, 1),
        }
