# ewr-public-dashboard

Builds `basin_plan_review_2026/sdl_units_map.html`, a Leaflet map of Basin Plan surface water SDL resource units.

```bash
pip install pandas numpy shapely
cd basin_plan_review_2026
python3 build_sdl_map.py
```

The script fills `sdl_units_map.template.html` with the CSV/JSON/GeoJSON inputs in this repo and writes `sdl_units_map.html`. The built HTML is included.
