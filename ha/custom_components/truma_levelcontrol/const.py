"""Constants for the Truma LevelControl integration."""

DOMAIN = "truma_levelcontrol"

CONF_POLL_INTERVAL = "poll_interval"
DEFAULT_POLL_INTERVAL = 600  # seconds (10 minutes)

# Fahrterkennung fuer den Plausibilitaetsfilter (smoothing.py): solange der Wert dieser
# Entitaet ueber der Schwelle liegt, faehrt das Wohnmobil und es werden keine Messwerte
# uebernommen. Vorgabe: Eingangsspannung des Orion XS (Starterbatterie/Lichtmaschine)
# ueber den Victron-GX im Womo. Leere Entitaet = Fahrterkennung aus.
CONF_DRIVE_ENTITY = "drive_entity"
CONF_DRIVE_MIN_VOLTAGE = "drive_min_voltage"
DEFAULT_DRIVE_ENTITY = "sensor.orion_xs_hq242394e7e_eingangsspannung"
DEFAULT_DRIVE_MIN_VOLTAGE = 13.0

# Advertising manufacturer ID the sensor uses (0x5000). HA discovery matches on
# this; see manifest.json "bluetooth".
MANUFACTURER_ID = 0x5000

# --- BLE protocol (reverse-engineered from LevelControl 2.2.1) -------------
_BASE = "-6afe-4cc5-b3ff-3e140baedeb6"
UUID_SERVICE      = "22bfa601" + _BASE
UUID_MEASUREMENT  = "22bfa610" + _BASE   # read / write / notify
UUID_PASSWORD     = "22bfa619" + _BASE   # read -> 5 bytes
UUID_STORE_NV     = "22bfa617" + _BASE   # write trigger

TRIGGER_INIT = 0x03
TRIGGER_GO = 0x02

MEASURE_WAIT_S = 3.0
