"""Plausibilitaetsfilter fuer den LevelControl-Fuellstand (reines Python, ohne HA-Abhaengigkeiten).

Hintergrund (Messdaten 27.10.-3.11.2026, siehe docs/LEVELCONTROL.md):
* Im Stand liefert der Sensor alle 10 min einen Wert mit +-1 % Rauschen (75 <-> 76 ueber Stunden).
* Waehrend der Fahrt oder bei schlechter Ankopplung kommt "0 % / Qualitaet 0" (kein Echo),
  obwohl die Flasche eben noch 100 % hatte.
* Bei fast leerer Flasche (<= ~8 %) ist die Qualitaet meist 0, der Prozentwert aber richtig.
  Dazwischen kommen Fehlmessungen mit Qualitaet 3 (40, 35, 62, 52 % bei real 7 %), auch mehrere
  passende in Folge. Die Qualitaet taugt also nicht als Kriterium und wird nicht ausgewertet.

Physik: eine Flasche kann zwischen zwei Messungen nur um den Verbrauch sinken (Alde-Gasbrenner
~0,4 kg/h = ~4 %/h bei 11 kg) und nie steigen - ausser beim Flaschenwechsel. Daraus der Filter:

1. Korridor: Werte zwischen (letzter Wert - MAX_RATE*dt - TOL) und (letzter Wert + TOL) werden
   direkt uebernommen.
2. Ausserhalb des Korridors: letzten Wert halten. Ein neuer Pegel gilt erst, wenn die Messungen
   der letzten WINDOW_S ihn tragen. Gezaehlt wird die groesste Gruppe von Werten innerhalb +-TOL,
   sie muss mindestens MIN_SPAN_S ueberdecken und:
   * Anstieg (nur durch Flaschenwechsel moeglich, der saubere Werte liefert): RISE_SHARE,
   * Rueckgang (korrigiert auch einen falsch uebernommenen Wert): mehr als FALL_SHARE.
3. Start: Median der ersten START_SAMPLES Messungen. Waehrenddessen bleibt ein aus aelterem
   Filterzustand wiederhergestellter Anzeigewert stehen.
4. Glaettung der uebernommenen Werte: Median aus 3, dann exponentielle Glaettung, dann 1 %-Hysterese
   fuer die Anzeige, damit 75/76-Flackern verschwindet.

Waehrend der Fahrt (Erkennung von aussen) zaehlt keine Messung, siehe LevelFilter.update().
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import median

# Maximal plausibler Verbrauch in Prozentpunkten pro Stunde (11-kg-Flasche, Heizung + Kocher,
# mit Reserve). 6 %/h entsprechen ca. 0,66 kg/h.
MAX_RATE_PCT_PER_H = 6.0
# Toleranz fuer Messrauschen; zugleich halbe Breite einer Gruppe gleicher Werte (Prozentpunkte).
TOLERANCE_PCT = 3.0
# Zeitraum, ueber den Messungen fuer einen neuen Pegel ausgewertet werden.
WINDOW_S = 2 * 3600
# So lange muss eine Gruppe mindestens anhalten, bevor sie den Wert aendern darf.
MIN_SPAN_S = 90 * 60
# Anteil der Messungen im Zeitraum, den ein Anstieg mindestens braucht.
RISE_SHARE = 0.75
# Anteil der Messungen im Zeitraum, den ein Rueckgang ueberschreiten muss.
FALL_SHARE = 0.5
# Startwert = Median aus so vielen Messungen.
START_SAMPLES = 5
# Gewicht der neuesten Messung in der exponentiellen Glaettung.
EMA_ALPHA = 0.4
# Anzeige aendert sich erst, wenn der geglaettete Wert um so viel vom angezeigten abweicht.
DISPLAY_HYSTERESIS_PCT = 1.0
MEDIAN_WINDOW = 3
# Version des gesicherten Zustands. Aeltere Zustaende enthalten eventuell einen falschen Pegel
# und liefern deshalb nur noch den Anzeigewert, bis neu gestartet ist.
STATE_VERSION = 2


@dataclass
class FilterState:
    """Zustand des Filters (wird von Home Assistant ueber Neustarts gesichert)."""

    accepted: float | None = None       # letzter plausibler Rohwert (%)
    accepted_at: float | None = None    # Unix-Sekunden
    smoothed: float | None = None       # EMA ueber die uebernommenen Werte
    display: int | None = None          # angezeigter Fuellstand (%)
    capacity_g: int | None = None       # Flaschengroesse aus grams/percent (fuer kg-Anzeige)
    recent: list[float] = field(default_factory=list)   # letzte uebernommene Werte (Median)
    votes: list[tuple[float, float]] = field(default_factory=list)  # (Zeit, Rohwert) im Zeitraum
    candidate: float | None = None      # groesste abweichende Gruppe (nur Anzeige)
    candidate_share: float | None = None
    driving: bool = False               # letzte Messung waehrend der Fahrt (nicht gesichert)
    status: str = "init"

    def as_dict(self) -> dict:
        return {
            "version": STATE_VERSION,
            "accepted": self.accepted,
            "accepted_at": self.accepted_at,
            "smoothed": self.smoothed,
            "display": self.display,
            "capacity_g": self.capacity_g,
            "recent": list(self.recent),
            "votes": [list(v) for v in self.votes],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "FilterState":
        s = cls()
        try:
            s.display = None if d.get("display") is None else int(d["display"])
            s.capacity_g = None if d.get("capacity_g") is None else int(d["capacity_g"])
            if d.get("version") != STATE_VERSION:
                s.status = "alter Zustand verworfen, sammle Startwerte"
                return s
            s.accepted = None if d.get("accepted") is None else float(d["accepted"])
            s.accepted_at = None if d.get("accepted_at") is None else float(d["accepted_at"])
            s.smoothed = None if d.get("smoothed") is None else float(d["smoothed"])
            s.recent = [float(x) for x in d.get("recent", [])][-MEDIAN_WINDOW:]
            s.votes = [(float(t), float(v)) for t, v in d.get("votes", [])]
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
        s.recent.append(value)
        del s.recent[:-MEDIAN_WINDOW]
        med = median(s.recent)
        s.smoothed = med if s.smoothed is None else s.smoothed + EMA_ALPHA * (med - s.smoothed)
        if s.display is None or abs(s.smoothed - s.display) >= DISPLAY_HYSTERESIS_PCT:
            s.display = int(round(s.smoothed))

    def _reset_to(self, value: float, now: float, status: str) -> None:
        """Neuer Pegel: Glaettung verwerfen, sofort anzeigen."""
        s = self.state
        s.recent.clear()
        s.smoothed = None
        s.display = None
        s.candidate = None
        s.candidate_share = None
        self._accept(value, now)
        s.status = status

    def _largest_group(self) -> tuple[float, float, float] | None:
        """Groesste Gruppe von Werten innerhalb +-TOL: (Median, Anteil, Zeitspanne in s)."""
        votes = self.state.votes
        if not votes:
            return None
        best: list[tuple[float, float]] = []
        for _, center in votes:
            group = [v for v in votes if abs(v[1] - center) <= TOLERANCE_PCT]
            if len(group) > len(best):
                best = group
        times = [t for t, _ in best]
        return median(v for _, v in best), len(best) / len(votes), max(times) - min(times)

    # ------------------------------------------------------------------ Kern
    def update(
        self, percent: int, grams: int, quality: int, now: float, driving: bool = False
    ) -> int | None:
        """Eine Messung verarbeiten. Gibt den anzuzeigenden Fuellstand (%) zurueck.

        driving=True (Fahrterkennung von aussen, z. B. Starterbatterie > 13 V): die Messung wird
        komplett ignoriert und zaehlt auch nicht fuer einen neuen Pegel. Der Zeitbezug (accepted_at)
        bleibt unveraendert, sodass der Korridor nach der Fahrt den Verbrauch waehrend der Fahrt
        abdeckt.

        Die Qualitaet wird bewusst nicht ausgewertet (siehe Modulbeschreibung), sie dient nur dem
        Statustext.
        """
        s = self.state
        s.driving = driving
        if driving:
            s.status = "Fahrt erkannt, halte letzten Wert"
            return s.display

        value = float(percent)
        if percent > 0 and grams > 0:
            s.capacity_g = int(round(grams * 100.0 / percent))

        s.votes.append((now, value))
        s.votes = [v for v in s.votes if now - v[0] <= WINDOW_S]

        if s.accepted is None:
            if len(s.votes) >= START_SAMPLES:
                self._reset_to(median(v for _, v in s.votes), now, "Startwert uebernommen")
            else:
                s.status = f"sammle Startwerte {len(s.votes)}/{START_SAMPLES}"
            return s.display

        dt_h = max(0.0, (now - (s.accepted_at or now)) / 3600.0)
        lower = s.accepted - MAX_RATE_PCT_PER_H * dt_h - TOLERANCE_PCT
        upper = s.accepted + TOLERANCE_PCT

        if lower <= value <= upper:
            self._accept(value, now)
            s.candidate = None
            s.candidate_share = None
            s.status = "ok" if quality > 0 else "ok (schwaches Echo)"
            return s.display

        group = self._largest_group()
        if group is not None:
            level, share, span = group
            if abs(level - s.accepted) > TOLERANCE_PCT:
                s.candidate = level
                s.candidate_share = share
                enough = share >= RISE_SHARE if level > s.accepted else share > FALL_SHARE
                if enough and span >= MIN_SPAN_S:
                    self._reset_to(level, now, "neuer Pegel uebernommen")
                    return s.display
        s.status = "unplausibel, halte letzten Wert"
        return s.display

    def attributes(self) -> dict:
        s = self.state
        return {
            "status": s.status,
            "fahrt": s.driving,
            "letzter_plausibler_rohwert": s.accepted,
            "geglaettet": None if s.smoothed is None else round(s.smoothed, 2),
            "kandidat": s.candidate,
            "kandidat_anteil": None if s.candidate_share is None else round(s.candidate_share, 2),
            "messungen_im_zeitraum": len(s.votes),
            "flaschengroesse_kg": None if not s.capacity_g else round(s.capacity_g / 1000.0, 1),
        }
