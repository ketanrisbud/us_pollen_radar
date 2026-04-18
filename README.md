# US Pollen Radar — Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-orange.svg)](https://github.com/hacs/integration)

A Home Assistant custom integration that fetches **US pollen data from [kleenex.com](https://www.kleenex.com/en-us/pollen-count)** and exposes it as sensors.

> ⚠️ **Disclaimer:** This integration uses an unofficial, reverse-engineered API from kleenex.com. It is not affiliated with or endorsed by Kleenex/Kimberly-Clark. The API may change without notice.

---

## Features

- 🌳 **Tree pollen** — PPM count + level (Low / Moderate / High / Very High)
- 🌾 **Grass pollen** — PPM count + level
- 🌿 **Weed pollen** — PPM count + level
- 🔬 **Per-species sensors** — e.g. `Oak 391 PPM`, `Ragweed Low` (enabled by default)
- 📅 **5-day forecast** as sensor attributes
- ⏱️ **Strict 1-hour rate limiting** — never floods the Kleenex API

---

## Installation via HACS

1. Open **HACS** → **Integrations** → ⋮ menu → **Custom repositories**
2. Add this repo URL, category: **Integration**
3. Search for **US Pollen Radar** and install
4. Restart Home Assistant

---

## Setup

1. Go to **Settings → Devices & Services → Add Integration**
2. Search for **US Pollen Radar**
3. Enter your **city name** (e.g. `Milford, CT`) and a display name
4. Click Submit — sensors appear immediately

---

## Sensors Created

| Sensor | Description | Unit |
|--------|-------------|------|
| `sensor.us_pollen_radar_trees` | Tree pollen PPM | ppm |
| `sensor.us_pollen_radar_trees_level` | Tree pollen level | enum |
| `sensor.us_pollen_radar_grass` | Grass pollen PPM | ppm |
| `sensor.us_pollen_radar_grass_level` | Grass pollen level | enum |
| `sensor.us_pollen_radar_weeds` | Weed pollen PPM | ppm |
| `sensor.us_pollen_radar_weeds_level` | Weed pollen level | enum |
| `sensor.us_pollen_radar_<species>` | Per-species PPM (e.g. Oak) | ppm |
| `sensor.us_pollen_radar_<species>_level` | Per-species level | enum |
| `sensor.us_pollen_radar_date` | Date of current data | date |
| `sensor.us_pollen_radar_last_updated` | Last API fetch time | timestamp |

### Sensor Attributes (trees / grass / weeds)

```yaml
level: high
species: Oak
details:
  - name: Oak
    value: 391
    level: high
forecast:
  - date: "2026-04-19"
    value: 1052
    level: high
    details: [...]
  - date: "2026-04-20"
    ...
```

---

## Rate Limiting

Data is fetched **once per hour** maximum. Kleenex only updates their source data every ~3 hours, so hourly polling is more than sufficient. The integration will **never** make more than one API request per hour, even on HA restart or manual refresh.

---

## Supported Cities

Any US city served by [kleenex.com/en-us/pollen-count](https://www.kleenex.com/en-us/pollen-count). Try your city name first; if it returns no data, try a nearby larger city.

---

## Troubleshooting

- **No data / invalid city**: Check [kleenex.com/en-us/pollen-count](https://www.kleenex.com/en-us/pollen-count) directly with your city name
- **403 errors**: Kleenex may be blocking requests — wait an hour and retry
- **Missing species sensors**: The US API only reports the top allergen species per category (e.g. just Oak for trees). This is a Kleenex data limitation, not an integration bug.

