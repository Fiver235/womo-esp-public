/*
 * womo-energy-card – Energieübersicht im Stil der Victron-Konsole GUI v2 („Übersicht").
 * Projekt C:\Code\Truma, liegt in HA unter /config/www/womo-energy-card.js (/local/womo-energy-card.js).
 *
 * Links: Landstrom, Lichtmaschine (DC/DC), Solar · Mitte: Wechselrichter/Lader, Batterie
 * Rechts: AC-Verbraucher, DC-Verbraucher. Linien mit laufenden Punkten zeigen die Flussrichtung.
 * Unter 640 px Breite schaltet die Karte auf ein Hochformat-Layout (layout: auto|landscape|portrait).
 *
 * Konfiguration: siehe docs/VICTRON.md, Abschnitt „Dashboard".
 */
const VERSION = "1.0.2";

const DE = {
  off: "Aus", on: "Ein", low_power: "Energiesparmodus", fault: "Fehler", bulk: "Bulk-Ladung",
  absorption: "Absorption", float: "Erhaltungsladung", storage: "Lagerung", equalize: "Ausgleichsladung",
  passthrough: "Durchleitung", inverting: "Wechselrichten", power_assist: "PowerAssist",
  power_supply: "Netzteilbetrieb", sustain: "Sustain", sustain_alt: "Sustain", starting_up: "Startet",
  repeated_absorption: "Wiederh. Absorption", auto_equalize: "Auto-Ausgleich", battery_safe: "BatterySafe",
  external_control: "Externe Steuerung", discharging: "Entladen", recharging: "Nachladen",
  scheduled_recharging: "Geplantes Nachladen", charger_only: "Nur Laden", inverter_only: "Nur Wechselrichter",
  grid: "Netz", generator: "Generator", shore_power: "Landstrom", not_connected: "Nicht verbunden",
  unknown: "Unbekannt", mppt_active: "MPPT aktiv", voltage_current_limited: "Begrenzt", not_available: "–",
};

const BOXES = {
  shore:    { title: "Landstrom", icon: "mdi:power-plug", ent: "shore_power" },
  dcdc:     { title: "Lichtmaschine", icon: "mdi:engine", ent: "dcdc_power" },
  solar:    { title: "Solar", icon: "mdi:solar-power-variant", ent: "solar_power" },
  inverter: { title: "Wechselrichter / Lader", icon: "mdi:sine-wave", ent: "inverter_state" },
  battery:  { title: "Batterie", icon: "mdi:battery", ent: "battery_soc" },
  acloads:  { title: "AC-Verbraucher", icon: "mdi:power-socket-eu", ent: "ac_power" },
  dcloads:  { title: "DC-Verbraucher", icon: "mdi:lightbulb-group", ent: "dc_power" },
};

// Koordinaten in Layout-Einheiten: Kästen [x, y, b, h], Linien [x1, y1, x2, y2] in positiver Flussrichtung.
const LAYOUTS = {
  landscape: {
    w: 1000, h: 580, ft: 15, ftc: 15, fb: 38, fbc: 38, fs: 15, compact: [],
    boxes: {
      shore: [10, 10, 240, 170], dcdc: [10, 205, 240, 170], solar: [10, 400, 240, 170],
      inverter: [380, 10, 240, 220], battery: [380, 310, 240, 260],
      acloads: [750, 10, 240, 220], dcloads: [750, 400, 240, 170],
    },
    lines: {
      shore: [250, 95, 380, 95], acloads: [620, 120, 750, 120], invbat: [500, 230, 500, 310],
      dcdc: [250, 340, 380, 340], solar: [250, 485, 380, 485], dcloads: [620, 485, 750, 485],
    },
  },
  portrait: {
    w: 600, h: 1060, ft: 21, ftc: 17, fb: 46, fbc: 34, fs: 19, compact: ["dcdc", "solar", "dcloads"],
    boxes: {
      shore: [10, 10, 270, 170], acloads: [320, 10, 270, 170], inverter: [10, 260, 580, 160],
      battery: [10, 500, 580, 230], dcdc: [10, 810, 185, 240], solar: [207, 810, 186, 240],
      dcloads: [405, 810, 185, 240],
    },
    lines: {
      shore: [145, 180, 145, 260], acloads: [455, 260, 455, 180], invbat: [300, 420, 300, 500],
      dcdc: [102, 810, 102, 730], solar: [300, 810, 300, 730], dcloads: [497, 730, 497, 810],
    },
  },
};

const CSS = `
:host { display: block; }
ha-card { background: var(--womo-bg, #000); overflow: hidden; padding: 8px; box-sizing: border-box; }
.title { color: #fff; font-size: 1.15em; padding: 4px 6px 10px; }
.wrap { position: relative; width: 100%; --s: 1; }
svg { position: absolute; inset: 0; width: 100%; height: 100%; overflow: visible; pointer-events: none; }
.ln { stroke: #3a3936; stroke-width: 3; stroke-linecap: round; transition: stroke .4s; }
.ln.on { stroke: #4d5560; }
.dot { fill: #387dc5; }
.box { position: absolute; box-sizing: border-box; background: #1c1b19; color: #fff; cursor: pointer;
  border-radius: calc(var(--s) * 10px); padding: calc(var(--s) * 12px) calc(var(--s) * 14px);
  overflow: hidden; display: flex; flex-direction: column; transition: opacity .4s, background .2s;
  font-family: var(--ha-font-family-body, Roboto, "Noto Sans", sans-serif); -webkit-tap-highlight-color: transparent; }
.box:hover { background: #262521; }
.box.dim { opacity: .45; }
.box.compact { padding: calc(var(--s) * 12px) calc(var(--s) * 10px); }
.hd { display: flex; flex-wrap: wrap; align-items: center; column-gap: calc(var(--s) * 6px); row-gap: calc(var(--s) * 2px);
  color: #969591; white-space: nowrap; font-size: calc(var(--s) * var(--ft) * 1px); position: relative; z-index: 1; min-width: 0; }
.compact .hd { font-size: calc(var(--s) * var(--ftc) * 1px); }
.hd ha-icon { --mdc-icon-size: 1.3em; color: #969591; flex: none; }
.hd .t { overflow: hidden; text-overflow: ellipsis; }
.hd .st { margin-left: auto; padding-left: calc(var(--s) * 6px); font-size: .9em; color: #c8c6c1; flex: none; }
.big { font-size: calc(var(--s) * var(--fb) * 1px); font-weight: 300; line-height: 1.15; white-space: nowrap;
  margin-top: calc(var(--s) * 8px); position: relative; z-index: 1; }
.compact .big { font-size: calc(var(--s) * var(--fbc) * 1px); }
.b-battery .big { font-size: calc(var(--s) * var(--fb) * 1.35px); }
.big .u { font-size: .55em; color: #969591; margin-left: .12em; }
.big.txt { font-size: calc(var(--s) * var(--fb) * .62px); font-weight: 400; white-space: normal; }
.sub { display: flex; flex-wrap: wrap; column-gap: calc(var(--s) * 14px); row-gap: calc(var(--s) * 2px);
  font-size: calc(var(--s) * var(--fs) * 1px); color: #c8c6c1; line-height: 1.4;
  margin-top: calc(var(--s) * 6px); position: relative; z-index: 1; }
.sub .it { white-space: nowrap; }
.sub .muted { color: #969591; }
.lnk { color: #5b9bd9; cursor: pointer; }
.fill { position: absolute; left: 0; right: 0; bottom: 0; height: 0; opacity: .28; z-index: 0;
  transition: height 1s, background .6s; }
`;

class WomoEnergyCard extends HTMLElement {
  setConfig(config) {
    if (!config || typeof config.entities !== "object") throw new Error("womo-energy-card: 'entities' fehlt");
    this._cfg = { threshold: 5, layout: "auto", ...config };
    this._layoutName = null;
    if (this._wrap) this._resize();
  }

  set hass(hass) {
    this._hass = hass;
    if (!this._wrap) this._init();
    this._update();
  }

  getCardSize() { return 9; }
  getGridOptions() { return { columns: "full", rows: "auto" }; }

  disconnectedCallback() { if (this._ro) this._ro.disconnect(); }
  connectedCallback() { if (this._ro && this._card) this._ro.observe(this._card); }

  _init() {
    const root = this.attachShadow({ mode: "open" });
    const t = this._cfg.title ? `<div class="title">${this._cfg.title}</div>` : "";
    root.innerHTML = `<style>${CSS}</style><ha-card>${t}<div class="wrap"></div></ha-card>`;
    this._card = root.querySelector("ha-card");
    this._wrap = root.querySelector(".wrap");
    this._wrap.addEventListener("click", (ev) => this._click(ev));
    this._ro = new ResizeObserver(() => this._resize());
    this._ro.observe(this._card);
    this._resize();
  }

  _resize() {
    const w = this._wrap.clientWidth || this._card.clientWidth || 1000;
    const forced = this._cfg.layout && this._cfg.layout !== "auto" ? this._cfg.layout : null;
    const want = LAYOUTS[forced] ? forced : (w < 640 ? "portrait" : "landscape");
    if (want !== this._layoutName) { this._build(want); this._update(); }
    this._wrap.style.setProperty("--s", (w / LAYOUTS[want].w).toFixed(4));
  }

  _build(name) {
    const L = LAYOUTS[name];
    this._layoutName = name;
    const pct = (v, t) => `${((v / t) * 100).toFixed(3)}%`;
    let html = `<svg viewBox="0 0 ${L.w} ${L.h}" preserveAspectRatio="none">`;
    for (const [k, [x1, y1, x2, y2]] of Object.entries(L.lines)) {
      html += `<g data-line="${k}"><line class="ln" x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}"/><g class="dots"></g></g>`;
    }
    html += "</svg>";
    for (const [id, [x, y, w, h]] of Object.entries(L.boxes)) {
      const b = BOXES[id];
      const title = (this._cfg.names && this._cfg.names[id]) || b.title;
      const cls = `box b-${id}${L.compact.includes(id) ? " compact" : ""}`;
      html += `<div class="${cls}" data-box="${id}" style="left:${pct(x, L.w)};top:${pct(y, L.h)};width:${pct(w, L.w)};height:${pct(h, L.h)}">`
        + (id === "battery" ? `<div class="fill" data-f="bat_fill"></div>` : "")
        + `<div class="hd"><ha-icon data-f="${id}_icon" icon="${b.icon}"></ha-icon><span class="t">${title}</span><span class="st" data-f="${id}_st"></span></div>`
        + `<div class="big${id === "inverter" ? " txt" : ""}" data-f="${id}_big"></div>`
        + `<div class="sub" data-f="${id}_sub"></div></div>`;
    }
    const ws = this._wrap.style;
    ws.aspectRatio = `${L.w} / ${L.h}`;
    ws.setProperty("--ft", L.ft); ws.setProperty("--ftc", L.ftc); ws.setProperty("--fb", L.fb);
    ws.setProperty("--fbc", L.fbc); ws.setProperty("--fs", L.fs);
    this._wrap.innerHTML = html;
    this._f = {};
    this._wrap.querySelectorAll("[data-f]").forEach((e) => { this._f[e.dataset.f] = e; });
    this._boxEl = {};
    this._wrap.querySelectorAll("[data-box]").forEach((e) => { this._boxEl[e.dataset.box] = e; });
    this._lines = {};
    this._wrap.querySelectorAll("[data-line]").forEach((g) => {
      const k = g.dataset.line;
      this._lines[k] = { dots: g.querySelector(".dots"), ln: g.querySelector(".ln"), dir: 0, c: L.lines[k] };
    });
    this._cache = {};
  }

  // ---- Werte ---------------------------------------------------------------
  _st(k) { const id = this._cfg.entities[k]; return id && this._hass ? this._hass.states[id] : undefined; }
  _num(k) {
    const s = this._st(k);
    if (!s) return NaN;
    const v = parseFloat(s.state);
    return Number.isFinite(v) ? v : NaN;
  }
  _tr(k) {
    const s = this._st(k);
    if (!s || s.state === "unavailable" || s.state === "unknown") return "–";
    if (DE[s.state] !== undefined) return DE[s.state];
    return this._hass.formatEntityState ? this._hass.formatEntityState(s) : s.state;
  }
  _n(v, d) {
    if (!Number.isFinite(v)) return "–";
    const lang = (this._hass && (this._hass.locale?.language || this._hass.language)) || "de";
    this._nf = this._nf || {};
    const key = `${lang}|${d}`;
    if (!this._nf[key]) this._nf[key] = new Intl.NumberFormat(lang, { minimumFractionDigits: d, maximumFractionDigits: d });
    return this._nf[key].format(Math.abs(v) < 0.5 * 10 ** -d ? 0 : v);
  }
  _w(v) { return !Number.isFinite(v) ? "– W" : Math.abs(v) >= 1000 ? `${this._n(v / 1000, 2)} kW` : `${this._n(v, 0)} W`; }
  _wBig(v) {
    if (!Number.isFinite(v)) return `–<span class="u">W</span>`;
    return Math.abs(v) >= 1000 ? `${this._n(v / 1000, 2)}<span class="u">kW</span>` : `${this._n(v, 0)}<span class="u">W</span>`;
  }
  // Dauer-Sensor in Sekunden umrechnen; HA liefert ihn in der eingestellten Anzeigeeinheit.
  _secs(k) {
    const v = this._num(k);
    const u = this._st(k)?.attributes?.unit_of_measurement;
    const f = { s: 1, min: 60, h: 3600, d: 86400 }[u] ?? 1;
    return v * f;
  }
  _dur(sec) {
    if (!Number.isFinite(sec) || sec <= 0) return null;
    const m = Math.round(sec / 60), h = Math.floor(m / 60), d = Math.floor(h / 24);
    if (d >= 2) return `${d} d ${h % 24} h`;
    if (h >= 1) return `${h} h ${m % 60} min`;
    return `${m} min`;
  }
  _items(list) { return list.filter(Boolean).map((x) => `<span class="it">${x}</span>`).join(""); }

  // ---- DOM-Aktualisierung ohne Neuaufbau (Animationen laufen weiter) --------
  _html(key, html) {
    const e = this._f[key];
    if (!e || this._cache[key] === html) return;
    this._cache[key] = html;
    e.innerHTML = html;
  }
  _set(key, prop, val) {
    const e = this._f[key], ck = `${key}@${prop}`;
    if (!e || this._cache[ck] === val) return;
    this._cache[ck] = val;
    if (prop === "icon") e.setAttribute("icon", val); else e.style[prop] = val;
  }
  _dim(id, on) { const e = this._boxEl[id]; if (e) e.classList.toggle("dim", !!on); }
  _flow(name, v) {
    const l = this._lines[name];
    if (!l) return;
    const dir = Number.isFinite(v) && Math.abs(v) >= this._cfg.threshold ? Math.sign(v) : 0;
    if (dir === l.dir) return;
    l.dir = dir;
    l.ln.classList.toggle("on", dir !== 0);
    if (!dir) { l.dots.innerHTML = ""; return; }
    let [x1, y1, x2, y2] = l.c;
    if (dir < 0) [x1, y1, x2, y2] = [x2, y2, x1, y1];
    const dur = 1.8, n = 3;
    let s = "";
    for (let i = 0; i < n; i++) {
      s += `<circle class="dot" r="5"><animateMotion dur="${dur}s" repeatCount="indefinite" begin="${(-i * dur / n).toFixed(2)}s" path="M${x1},${y1} L${x2},${y2}"/></circle>`;
    }
    l.dots.innerHTML = s;
  }

  _update() {
    if (!this._hass || !this._f) return;
    const th = this._cfg.threshold;

    // Landstrom (AC-Eingang des MultiPlus)
    const sp = this._num("shore_power"), su = this._num("shore_voltage");
    const act = this._st("shore_active")?.state;
    const shoreOn = act !== "not_connected" && !(su < 50);
    this._html("shore_st", shoreOn ? (act && act !== "unknown" ? this._tr("shore_active") : "") : "Nicht verbunden");
    this._html("shore_big", this._wBig(shoreOn ? sp : 0));
    this._html("shore_sub", this._items([
      `${this._n(su, 0)} V`, `${this._n(this._num("shore_current"), 1)} A`, `${this._n(this._num("shore_frequency"), 1)} Hz`,
    ]));
    this._dim("shore", !shoreOn);
    this._flow("shore", shoreOn ? sp : 0);

    // Wechselrichter / Lader
    const dcp = this._num("inverter_dc_power");
    this._html("inverter_big", this._tr("inverter_state"));
    this._html("inverter_sub", this._items([
      this._cfg.entities.inverter_mode ? `<span class="lnk" data-more="inverter_mode">Modus: ${this._tr("inverter_mode")} ›</span>` : null,
      `Eingangslimit ${this._n(this._num("inverter_limit"), 1)} A`,
      `DC ${this._w(dcp)}`,
      Number.isFinite(this._num("inverter_temp")) ? `${this._n(this._num("inverter_temp"), 0)} °C` : null,
    ]));
    this._dim("inverter", this._st("inverter_state")?.state === "off");
    this._flow("invbat", dcp);

    // AC-Verbraucher (Ausgang des MultiPlus)
    const ap = this._num("ac_power"), au = this._num("ac_voltage");
    this._html("acloads_big", this._wBig(ap));
    this._html("acloads_sub", this._items([
      `${this._n(au, 0)} V`, `${this._n(this._num("ac_current"), 1)} A`, `${this._n(this._num("ac_frequency"), 1)} Hz`,
    ]));
    this._dim("acloads", !(au >= 50));
    this._flow("acloads", ap);

    // Batterie
    const soc = this._num("battery_soc"), bp = this._num("battery_power"), bu = this._num("battery_voltage");
    const charging = bp >= th, discharging = bp <= -th;
    const lvl = Number.isFinite(soc) ? Math.min(100, Math.max(10, Math.round(soc / 10) * 10)) : null;
    const icon = lvl === null ? "mdi:battery-unknown"
      : charging ? `mdi:battery-charging-${lvl}` : lvl === 100 ? "mdi:battery" : `mdi:battery-${lvl}`;
    this._set("battery_icon", "icon", icon);
    this._html("battery_st", charging ? "Lädt" : discharging ? "Entlädt" : "Ruhe");
    this._html("battery_big", `${this._n(soc, 0)}<span class="u">%</span>`);
    const ttg = this._dur(this._secs("battery_ttg"));
    this._html("battery_sub", this._items([
      `${this._n(bu, 2)} V`, `${this._n(this._num("battery_current"), 1)} A`, this._w(bp),
      ttg ? `Restlaufzeit ${ttg}` : null,
      Number.isFinite(this._num("battery_consumed")) ? `<span class="muted">Verbraucht ${this._n(this._num("battery_consumed"), 1)} Ah</span>` : null,
    ]));
    this._set("bat_fill", "height", Number.isFinite(soc) ? `${Math.max(0, Math.min(100, soc))}%` : "0%");
    this._set("bat_fill", "background", soc >= 50 ? "#72b84c" : soc >= 20 ? "#f0962e" : "#f35c58");

    // Lichtmaschine / DC-DC-Lader
    const dp = this._num("dcdc_power");
    this._html("dcdc_big", this._wBig(dp));
    this._html("dcdc_sub", this._items([
      `${this._n(this._num("dcdc_current"), 1)} A`,
      Number.isFinite(this._num("dcdc_input_voltage")) ? `Eingang ${this._n(this._num("dcdc_input_voltage"), 2)} V` : null,
      this._cfg.entities.dcdc_state ? `<span class="muted">${this._tr("dcdc_state")}</span>` : null,
    ]));
    this._dim("dcdc", this._st("dcdc_state")?.state === "off" && !(dp >= th));
    this._flow("dcdc", dp);

    // Solar
    const pp = this._num("solar_power");
    this._html("solar_big", this._wBig(pp));
    this._html("solar_sub", this._items([
      `${this._n(this._num("solar_voltage"), 1)} V`, `${this._n(this._num("solar_current"), 1)} A`,
      Number.isFinite(this._num("solar_today")) ? `Heute ${this._n(this._num("solar_today"), 2)} kWh` : null,
      this._cfg.entities.solar_state ? `<span class="muted">${this._tr("solar_state")}</span>` : null,
    ]));
    this._dim("solar", !(pp >= th));
    this._flow("solar", pp);

    // DC-Verbraucher
    const lp = this._num("dc_power");
    this._html("dcloads_big", this._wBig(lp));
    this._html("dcloads_sub", this._items([
      Number.isFinite(lp) && bu > 5 ? `≈ ${this._n(lp / bu, 1)} A` : null,
    ]));
    this._flow("dcloads", lp);
  }

  _click(ev) {
    const m = ev.target.closest("[data-more]");
    let key;
    if (m) { ev.stopPropagation(); key = m.dataset.more; }
    else {
      const b = ev.target.closest("[data-box]");
      if (!b) return;
      key = BOXES[b.dataset.box].ent;
    }
    const entityId = this._cfg.entities[key];
    if (!entityId) return;
    this.dispatchEvent(new CustomEvent("hass-more-info", { detail: { entityId }, bubbles: true, composed: true }));
  }
}

if (!customElements.get("womo-energy-card")) {
  customElements.define("womo-energy-card", WomoEnergyCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "womo-energy-card",
    name: "Womo-Energieübersicht",
    description: "Energiefluss im Stil der Victron GUI v2 (Landstrom, Lichtmaschine, Solar, MultiPlus, Batterie, Verbraucher)",
  });
  console.info(`%c WOMO-ENERGY-CARD %c ${VERSION} `, "background:#387dc5;color:#fff", "background:#1c1b19;color:#fff");
}
