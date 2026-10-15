# ewr-public-dashboard

An interactive map of Basin Plan surface water SDL resource units. **Open [`index.html`](index.html)** to view it. The file is self-contained (data, rivers and boundaries are embedded), so it can be opened directly or hosted on any static web server.

## Repository layout

```
index.html                  The built map (output of the build script)
requirements.txt            Python dependencies for the build
scripts/
  build_map.py              Builds index.html from the template and data
  flow_regime_mappings.py   EWR code -> flow regime mapping used by the build
templates/
  map_template.html         HTML/JS template the build fills with data
data/
  ewr_results/              EWR comparison results (frequency, inter-event, connectivity)
  boundaries/               SDL resource unit and river GeoJSON
  mdba_grades/              MDBA grades and moderation notes (JSON)
  bom_gauges/               BoM gauge station locations
  parameters/               EWR parameter sheet, objective reference, calc config
```

## How to regenerate `index.html`

Requires Python 3.9 or later.

```bash
git clone https://github.com/RoryANU/ewr-public-dashboard.git
cd ewr-public-dashboard
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python3 scripts/build_map.py
```

The script reads everything under `data/`, fills `templates/map_template.html`, prints a short summary (gauges plotted, planning units, output size) and overwrites `index.html`. It can be run from any directory.

To change the map's layout or styling, edit `templates/map_template.html`; to change its data, edit the files under `data/`; then re-run the script.
