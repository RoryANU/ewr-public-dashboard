# ewr-public-dashboard

Builds `basin_plan_review_2026/sdl_units_map.html`, a self-contained Leaflet map of Basin Plan surface water SDL resource units. A pre-built copy of the HTML is already included in the repo.

## How to generate the HTML

### 1. Requirements

- Python 3.9 or later
- `pandas`, `numpy` and `shapely`

### 2. Get the repo and install dependencies

```bash
git clone https://github.com/RoryANU/ewr-public-dashboard.git
cd ewr-public-dashboard
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install pandas numpy shapely
```

### 3. Run the build script

Run it from inside `basin_plan_review_2026/`, because the script finds its inputs relative to its own location:

```bash
cd basin_plan_review_2026
python3 build_sdl_map.py
```

It prints a short summary (gauges plotted, planning units, output size) and overwrites `sdl_units_map.html` in the same folder.

### 4. Open the map

```bash
open sdl_units_map.html            # macOS; on Linux use xdg-open, on Windows use start
```

The file is self-contained (data, rivers and boundaries are embedded), so it can be opened directly or hosted on any static web server.

## What goes into the build

`build_sdl_map.py` fills `sdl_units_map.template.html` with:

| Input | Location |
| --- | --- |
| EWR comparison results (frequency, inter-event, connectivity) | `basin_plan_review_2026/all_*.csv` |
| SDL resource unit boundaries and rivers | `basin_plan_review_2026/sdl_resource_units/*.geojson` |
| MDBA grades and moderation notes | `basin_plan_review_2026/mdba_grades/*.json` |
| BoM gauge locations | `basin_plan_review_2026/bom_gauges/bom_wdo_station_list.csv` |
| EWR parameter sheet, objective reference and calc config | `py_ewr/parameter_metadata/` |

To change the map's layout or styling, edit `sdl_units_map.template.html` and re-run the script. To change its data, edit the inputs above and re-run.
