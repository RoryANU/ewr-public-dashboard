"""Build index.html: Leaflet map of Basin Plan surface water SDL resource units.

Source: MDBA Library 'Surface Water SDL Resource Units' (CC BY 4.0).
Units that appear in the 2026 review EWR results are highlighted.
Rivers: HydroRIVERS v1.0 (HydroSHEDS) clipped to the basin.
Gauges: parameter sheet gauges located via BoM Water Data Online only (sheet coords ignored),
split by whether they appear in the model outputs.
"""
import json
import numpy as np
import pandas as pd
from flow_regime_mappings import regimes_for
from shapely.geometry import shape, mapping

HERE = __import__("pathlib").Path(__file__).resolve().parent.parent  # repo root
norm = lambda s: "".join(c for c in s.lower() if c.isalnum())

reviewed = pd.read_csv(HERE / "data/ewr_results/ecological_objective_frequency.csv",
                       usecols=["SWSDLName", "PlanningUnitName"])
in_review = {norm(n): sorted(g.PlanningUnitName.unique())
             for n, g in reviewed.groupby("SWSDLName")}

gj = json.load(open(HERE / "data/boundaries/sdl_resource_units.geojson"))
for f in gj["features"]:
    p = f["properties"]
    p["planning_units"] = in_review.get(norm(p["SWSDLName"]), [])
    p["in_review"] = bool(p["planning_units"])
    p.pop("FID", None)
    f["geometry"] = mapping(shape(f["geometry"]).simplify(0.005, preserve_topology=True))

# --- gauges: parameter sheet x BoM Water Data Online x model outputs -------------
param = pd.read_csv(HERE / "data/parameters/parameter_sheet.csv", dtype=str)
bom = pd.read_csv(HERE / "data/bom_gauges/bom_station_list.csv", dtype=str)
for c in ("station_latitude", "station_longitude"):
    bom[c] = pd.to_numeric(bom[c], errors="coerce")
bom = bom.dropna(subset=["station_latitude"]).drop_duplicates("station_no").set_index("station_no")
model_gauges = set()
for f in (HERE / "data/ewr_results").glob("*.csv"):
    cols = [c for c in ("Gauge", "Multigauge") if c in pd.read_csv(f, nrows=0).columns.str.strip()]
    for c in cols:
        model_gauges |= set(pd.read_csv(f, usecols=[c], dtype=str)[c].dropna())

# every gauge id the parameter sheet uses (primary, multigauge or weirpool), with the rows it appears in
rows = {}
for col in ("Gauge", "Multigauge", "WeirpoolGauge"):
    for gid, g in param.dropna(subset=[col]).groupby(col):
        rows[gid] = pd.concat([rows[gid], g]) if gid in rows else g

ref = pd.read_csv(HERE / "data/parameters/objective_reference.csv", dtype=str)
ref_pair = ref.drop_duplicates(["LTWPShortName", "EcoObj"]).set_index(["LTWPShortName", "EcoObj"])
ref_any = ref.drop_duplicates("EcoObj").set_index("EcoObj")


# Flow regimes: the MDBA EWR_analysis_pipeline mapping (flow_regime_mappings.py), keyed by State and matched on the EWR code.
UNMAPPED = "Unmapped"


def pipeline_regimes(code, state, fallback=()):
    """Flow regimes of an EWR by the MDBA EWR_analysis_pipeline rule (flow_regime_mappings.py); a list, since the pipeline
    puts some EWRs in several regimes. No match -> `fallback` (the pipeline's own output column) -> "Unmapped"."""
    return regimes_for(code, state) or list(fallback) or [UNMAPPED]


# Frequency ratio (FR = achieved / target frequency) per gauge, EWR code, policy and climate model, from the model outputs.
# The model outputs report the lake-level EWRs (CLLMM1c-4c) under A4260527 (Tauwitchere); the FIRM site list (MILANG, measurand 35),
# SiteID_MDBA and the parameter sheet put them on A4260524 (Milang). Re-key the results to A4260524.
REKEY = {"A4260527": "A4260524"}
fr_raw = pd.read_csv(HERE / "data/ewr_results/frequency_raw.csv", usecols=["Gauge", "EWR", "SWSDLName", "Policy", "ClimateModel", "FR"], dtype={"Gauge": str})
fr_raw["Gauge"] = fr_raw.Gauge.replace(REKEY)
POLICIES = ["Without Development", "Pre Basin Plan", "Basin plan 2024", "Basin plan full implementation"]
CLIMATES = ["Historical Climate", "Warmer and Wetter 1.5 C", "Warmer and Drier 1.5 C", "Warmer and Much Drier 1.5 C",
            "Hotter and Wetter 2.0 C", "Hotter and Drier 2.0 C", "Hotter and Much Drier 2.0 C"]
assert set(fr_raw.Policy) == set(POLICIES) and set(fr_raw.ClimateModel) == set(CLIMATES)
fr_raw["scn"] = fr_raw.Policy.map(POLICIES.index) * len(CLIMATES) + fr_raw.ClimateModel.map(CLIMATES.index)
FR = {k: dict(v.groupby("scn").FR.mean().round(3))   # mean where a gauge/code sits in several planning units
      for k, v in fr_raw.groupby(["Gauge", "EWR"])}
FR_S = {k: dict(v.groupby("scn").FR.mean().round(3))  # same, restricted to one SDL unit (gauges that serve several SDL units)
        for k, v in fr_raw.groupby(["Gauge", "EWR", "SWSDLName"])}

# MRIP exceedance time proportion (ETP) per gauge, EWR code, policy and climate model. The EWR-level rating
# (Rating_ETP, vs historical Pre Basin Plan / Without Development) is recomputed here with the MDBA's intended rules (Figure 3 /
# MDBAuth/EWR_analysis_pipeline, scenario_comparison_MRIP). The pipeline's own function calls its first rule with its arguments in the
# wrong order (wod, pbp, buffer instead of pbp, scenario, buffer), so the published Rating_ETP column does not follow the rules as written.
# Set FIX_ETP_RULE = False to use the published column as is.
FIX_ETP_RULE = True


def etp_rating(wod, pbp, scn, B=0.01):
    """Rating_ETP as the pipeline's rules are written: (1) PBP and scenario both under B -> 0; (2) PBP and WoD both under B -> B - scenario;
    (3) WoD too close to PBP (WoD > PBP(1-B)) or scenario worse than PBP, with PBP > 0 -> (PBP - scenario) / PBP; (4) otherwise (PBP - scenario) / |PBP - WoD|."""
    wod, pbp, scn = (np.asarray(x, dtype=float) for x in (wod, pbp, scn))
    with np.errstate(all="ignore"):
        return np.select([(pbp < B) & (scn < B), (pbp < B) & (wod < B), ((wod > pbp * (1 - B)) | (scn > pbp)) & (pbp != 0)],
                         [0.0, B - scn, (pbp - scn) / pbp], default=(pbp - scn) / np.abs(pbp - wod))


etp_raw = pd.read_csv(HERE / "data/ewr_results/interevent_ewr.csv", dtype={"Gauge": str},
                      usecols=lambda c: c.strip() in {"PlanningUnitName", "SWSDLName", "Gauge", "EWR", "Policy", "ClimateModel",
                                                      "ETP", "ETP_PBP_Hist", "ETP_WOD_Hist", "Rating_ETP"})
etp_raw.columns = etp_raw.columns.str.strip()
etp_raw["Gauge"] = etp_raw.Gauge.replace(REKEY)
if FIX_ETP_RULE:
    etp_raw["Rating_ETP"] = etp_rating(etp_raw.ETP_WOD_Hist, etp_raw.ETP_PBP_Hist, etp_raw.ETP)
etp_raw = etp_raw.drop_duplicates(["PlanningUnitName", "SWSDLName", "Gauge", "EWR", "Policy", "ClimateModel"])   # rows repeat per ecological objective
etp_raw["scn"] = etp_raw.Policy.map(POLICIES.index) * len(CLIMATES) + etp_raw.ClimateModel.map(CLIMATES.index)
ETP = {k: ({i: (e, r) for i, e, r in v.groupby("scn")[["ETP", "Rating_ETP"]].mean().round(4).itertuples()},
           round(v.ETP_PBP_Hist.mean(), 4), round(v.ETP_WOD_Hist.mean(), 4))
       for k, v in etp_raw.groupby(["Gauge", "EWR"])}
ETP_S = {k: ({i: (e, r) for i, e, r in v.groupby("scn")[["ETP", "Rating_ETP"]].mean().round(4).itertuples()},
             round(v.ETP_PBP_Hist.mean(), 4), round(v.ETP_WOD_Hist.mean(), 4))
         for k, v in etp_raw.groupby(["Gauge", "EWR", "SWSDLName"])}
NS = len(POLICIES) * len(CLIMATES)


def _ok(v):
    """JSON-safe number: NaN / inf (e.g. a rating with a zero baseline) become None."""
    return None if v is None or v != v or v in (float("inf"), float("-inf")) else v


def etp_for(gid, code, sdl=None):
    scn, pbp, wod = (ETP_S if sdl else ETP).get((gid, code, sdl) if sdl else (gid, code), ({}, None, None))
    return ([_ok(scn[i][0]) if i in scn else None for i in range(NS)], [_ok(scn[i][1]) if i in scn else None for i in range(NS)], _ok(pbp), _ok(wod))


# EWRs actually assessed in the initial SDL assessment = (gauge, EWR) pairs in the model outputs, with the objective,
# ecological theme and flow regime the MDBA pipeline attached to them.
assessed = pd.read_csv(HERE / "data/ewr_results/frequency_raw.csv", dtype=str,
                       usecols=["Gauge", "EWR", "EcoObj", "Target", "FlowRegime", "SWSDLName"]).drop_duplicates(["Gauge", "EWR", "EcoObj", "SWSDLName"])
assessed["Gauge"] = assessed.Gauge.replace(REKEY)
ASSESSED = {g: v for g, v in assessed.groupby("Gauge")}
for gid in ASSESSED.keys() - rows.keys():       # in the model outputs but absent from the parameter sheet: plot anyway
    rows[gid] = param.iloc[0:0]
rows.setdefault("A4260527", param.iloc[0:0])     # Tauwitchere Barrage: BoM station, no EWRs of its own

# Only EWRs evaluated by these handlers in data/parameters/ewr_calc_config.json go in the diagram.
HANDLERS = {"flow_handle", "lowflow_handle"}
calc_config = json.load(open(HERE / "data/parameters/ewr_calc_config.json"))
key_handler = {k: h for h, keys in calc_config.items() for k in keys}


def handler_of(r):
    """Same key py_ewr builds: {Code}-{single|multigauge}-{FlowLevelVolume}."""
    kind = "multigauge" if isinstance(r.Multigauge, str) and r.Multigauge else "single"
    return key_handler.get(f"{r.Code}-{kind}-{r.FlowLevelVolume}", "unknown")


def _info_for(eo, ltwp, theme_hint=None):
    key = (ltwp, eo)
    ent = ref_pair.loc[key] if key in ref_pair.index else (ref_any.loc[eo] if eo in ref_any.index else None)
    theme = theme_hint if isinstance(theme_hint, str) else (ent.Target if ent is not None and isinstance(ent.Target, str) else "Unclassified")
    return [ent.Objective if ent is not None else "", theme.replace("Other species", "Other Species")]


def _fr_for(gid, code, sdl=None):
    return (FR_S if sdl else FR).get((gid, code, sdl) if sdl else (gid, code), {})


def _pack(gid, total, codes, by_code, info, reg, hand, sdl=None):
    count = {eo: sum(eo in v for v in by_code.values()) for eo in info}
    objs = sorted(info, key=lambda e: (-count[e], e))
    idx = {e: i for i, e in enumerate(objs)}
    return {"total": total, "codes": codes, "reg": reg, "h": hand, "objs": objs, "info": [info[e] for e in objs],
            "cells": [sorted(idx[e] for e in by_code[c]) for c in codes],
            "fr": [[_fr_for(gid, c, sdl).get(i) for i in range(NS)] for c in codes],
            "etp": [etp_for(gid, c, sdl)[0] for c in codes], "er": [etp_for(gid, c, sdl)[1] for c in codes],
            "ep": [etp_for(gid, c, sdl)[2] for c in codes], "ew": [etp_for(gid, c, sdl)[3] for c in codes]}


def objective_matrix(g, gid, sdl=None):
    """EWR codes (columns) x ecological objectives (rows) for one gauge from its parameter-sheet rows
    (gauges with no model results). All EWRs are kept; handler / _S filtering happens in the browser."""
    codes, by_code, info, hand, state_of = [], {}, {}, {}, {}
    for r in g.itertuples():
        if r.Code not in by_code:
            codes.append(r.Code)
            by_code[r.Code] = set()
            hand[r.Code] = handler_of(r)
            state_of[r.Code] = r.State
        if isinstance(r.EcoObj, str):
            for eo in r.EcoObj.split("+"):
                by_code[r.Code].add(eo)
                info.setdefault(eo, _info_for(eo, r.LTWPShortName))
    return _pack(gid, len(codes), codes, by_code, info, [pipeline_regimes(c, state_of.get(c)) for c in codes], [hand[c] for c in codes], sdl)


def assessed_matrix(gid, g, sdl=None):
    """Same, but from the EWRs and objective mapping actually used in the model outputs for this gauge."""
    sub = ASSESSED[gid] if sdl is None else ASSESSED[gid][ASSESSED[gid].SWSDLName == sdl]
    prow = {c: x.iloc[0] for c, x in g.groupby("Code")}
    codes = list(dict.fromkeys(sub.EWR))
    by_code, info, reg, hand = {c: set() for c in codes}, {}, [], []
    for r in sub.itertuples():
        if isinstance(r.EcoObj, str):
            by_code[r.EWR].add(r.EcoObj)
            ltwp = prow[r.EWR].LTWPShortName if r.EWR in prow else None
            info.setdefault(r.EcoObj, _info_for(r.EcoObj, ltwp, r.Target))
    for c in codes:
        fr_names = sub[(sub.EWR == c)].FlowRegime.dropna()
        # pipeline rule from the code's State; a code absent from the parameter sheet has no State, so use the pipeline's own output
        reg.append(pipeline_regimes(c, prow[c].State if c in prow else None, sorted(set(fr_names))))
        hand.append(handler_of(prow[c]) if c in prow else "unknown")
    return _pack(gid, g.Code.nunique(), codes, by_code, info, reg, hand, sdl)


# A4261002 (BARRAGE) is the total barrage flow, "Barrages near the Murray Mouth": no BoM station. SiteID_MDBA lists TAUWDS and MOUTH
# under the same description (A4260527), so it is shown beside Tauwitchere Barrage, nudged so both markers can be clicked.
PROXY_LOC = {"A4261002": ("A4260527", 0.012, -0.012)}
PROXY_NAME = {"A4261002": "Barrages near the Murray Mouth (total barrage flow, virtual gauge; position approximate)"}
has_results = set(fr_raw.Gauge) | set(etp_raw.Gauge)      # gauges with their own FR or ETP rows (Multigauge partners alone don't count)
DEDUP = ["Code", "EcoObj", "LTWPShortName", "Multigauge", "FlowLevelVolume"]


def sdls_of(gid, g):
    """SDL units a gauge serves: from the model outputs when it has them, otherwise from the parameter sheet rows."""
    names = ASSESSED[gid].SWSDLName if gid in ASSESSED else g.SWSDLName
    return sorted(set(names.dropna()))


def _state_of(g, sdl):
    """State of the parameter-sheet rows this gauge has in one SDL unit (e.g. 409025: NSW Murray -> NSW, Victorian Murray -> VIC)."""
    st = g[g.SWSDLName == sdl].State.dropna()
    return st.mode().iat[0] if len(st) else ""


def mx_for(gid, g, sdl):
    """EWR x objective matrix for a gauge; with `sdl` only the EWRs, objectives and results of that SDL unit."""
    gs = g if sdl is None else g[g.SWSDLName == sdl]
    return (assessed_matrix if gid in ASSESSED else objective_matrix)(gid=gid, g=gs.drop_duplicates(DEDUP, keep="first"), sdl=sdl)


gauges, unplotted = [], []
for gid, g in rows.items():
    row = g.iloc[0] if len(g) else pd.Series(index=param.columns, dtype=object)
    lat = lon = None
    if gid in bom.index:
        lat, lon = bom.at[gid, "station_latitude"], bom.at[gid, "station_longitude"]
        src, name = "BoM WDO", bom.at[gid, "station_name"]
    elif gid in PROXY_LOC:                                 # virtual gauge: no station, plotted next to a real one
        ref_id, dlat, dlon = PROXY_LOC[gid]
        lat, lon = bom.at[ref_id, "station_latitude"] + dlat, bom.at[ref_id, "station_longitude"] + dlon
        src, name = "proxy: near " + bom.at[ref_id, "station_name"], PROXY_NAME[gid]
    else:                                                  # parameter-sheet coordinates are deliberately ignored
        unplotted.append(gid)
        continue
    if lat is None or pd.isna(lat) or not (-45 < lat < -9 and 110 < lon < 155):
        unplotted.append(gid)
        continue
    sdls = sdls_of(gid, g)
    gauges.append({"id": gid, "name": name, "lat": round(float(lat), 5), "lon": round(float(lon), 5),
                   "state": row.State if isinstance(row.State, str) else "",
                   "sdl": sdls[0] if sdls else "", "sdls": sdls if len(sdls) > 1 else [],
                   "sdlState": {x: _state_of(g, x) for x in sdls} if len(sdls) > 1 else {},
                   "ewrs": int(g.Code.nunique()) or len(ASSESSED.get(gid, [])) and int(ASSESSED[gid].EWR.nunique()), "model": gid in has_results, "src": src,
                   "mx": mx_for(gid, g, sdls[0] if len(sdls) > 1 else None),
                   **({"mxs": {x: mx_for(gid, g, x) for x in sdls}} if len(sdls) > 1 else {})})
print(len(gauges), "gauges plotted,", sum(x["model"] for x in gauges), "in model outputs; unplotted:", unplotted)
print("model-output gauges not in parameter sheet:", sorted(model_gauges - set(rows)))
no_bom = sorted(g for g in ASSESSED if g not in bom.index)      # model results but no BoM station: should be matched to something
if no_bom:
    print("*** FLAG: gauges with model outputs but NO BoM data (need matching to a station):", no_bom,
          "| proxy-placed:", sorted(set(no_bom) & set(PROXY_LOC)))

# --- SDL-unit view: the MDBA pipeline's own planning-unit x objective ratings (FRsp rating and mean ETP rating) --------------
pu_fr = pd.read_csv(HERE / "data/ewr_results/ecological_objective_frequency.csv",
                    usecols=["PlanningUnitName", "SWSDLName", "EcoObj", "Target", "Policy", "ClimateModel", "Rating_Frsp"])
pu_et = pd.read_csv(HERE / "data/ewr_results/interevent_ecological_objective.csv",
                    usecols=["PlanningUnitName", "SWSDLName", "EcoObj", "Target", "Policy", "ClimateModel", "Rating_ETP_mean"])
if FIX_ETP_RULE:   # planning unit x objective mean ETP rating = mean of the EWR ratings (as the pipeline's notebook 11 does), with the corrected rule
    _ew = pd.read_csv(HERE / "data/ewr_results/interevent_ewr.csv", dtype={"Gauge": str},
                      usecols=lambda c: c.strip() in {"PlanningUnitName", "SWSDLName", "EcoObj", "Target", "Policy", "ClimateModel", "EWR", "Gauge", "ETP", "ETP_PBP_Hist", "ETP_WOD_Hist"})
    _ew.columns = _ew.columns.str.strip()
    _ew["Rating_ETP_mean"] = etp_rating(_ew.ETP_WOD_Hist, _ew.ETP_PBP_Hist, _ew.ETP)
    _k = ["PlanningUnitName", "SWSDLName", "EcoObj", "Target", "Policy", "ClimateModel"]
    pu_et = _ew.groupby(_k, as_index=False).Rating_ETP_mean.mean()
for d_ in (pu_fr, pu_et):
    d_["scn"] = d_.Policy.map(POLICIES.index) * len(CLIMATES) + d_.ClimateModel.map(CLIMATES.index)
# Flows & Connectivity theme: the MDBA's planning-unit x flow-regime FRsp rating (FR only; its ETP is not published as a rating)
pu_fc = pd.read_csv(HERE / "data/ewr_results/flows_connectivity_frequency.csv",
                    usecols=["PlanningUnitName", "SWSDLName", "FlowRegime", "Policy", "ClimateModel", "Rating_FRsp"]).rename(
    columns={"FlowRegime": "EcoObj", "Rating_FRsp": "Rating_Frsp"})
pu_fc["Target"] = "Flows & Connectivity"
pu_fr = pd.concat([pu_fr, pu_fc], ignore_index=True)
for d_ in (pu_fc,):
    d_["scn"] = d_.Policy.map(POLICIES.index) * len(CLIMATES) + d_.ClimateModel.map(CLIMATES.index)
pu_fr["scn"] = pu_fr.Policy.map(POLICIES.index) * len(CLIMATES) + pu_fr.ClimateModel.map(CLIMATES.index)
csv_name = {norm(n): n for n in pu_fr.SWSDLName.unique()}
# MDBA assessment units: SS7 (Campaspe / Coliban) and SS11 (SA Murray: channel + floodplain / Coorong, Lower Lakes & Murray Mouth) are assessed in two parts
PROC = json.load(open(HERE / "data/mdba_grades/process_data.json"))
MODN = json.load(open(HERE / "data/mdba_grades/moderation_notes.json"))
def assessment_units(code, pus):
    if code == "SS11":
        return [("SS11a", [i for i, p in enumerate(pus) if "Coorong" not in p]), ("SS11b", [i for i, p in enumerate(pus) if "Coorong" in p])]
    if code == "SS7":
        return [("SS7a", [i for i, p in enumerate(pus) if "Coliban" not in p]), ("SS7b", [i for i, p in enumerate(pus) if "Coliban" in p])]
    return [(code, list(range(len(pus))))]


SDLD = {}
for f in gj["features"]:
    nm = f["properties"]["SWSDLName"]
    cn = csv_name.get(norm(nm))
    if cn is None:
        continue
    a, b = pu_fr[pu_fr.SWSDLName == cn], pu_et[pu_et.SWSDLName == cn]
    pus = sorted(set(a.PlanningUnitName) | set(b.PlanningUnitName))
    theme = {**b.groupby("EcoObj").Target.agg(lambda x: x.mode().iat[0]).to_dict(), **a.groupby("EcoObj").Target.agg(lambda x: x.mode().iat[0]).to_dict()}
    objs = sorted(theme)

    def table(df, col):
        piv = {k: v for k, v in df.groupby(["EcoObj", "PlanningUnitName", "scn"])[col].mean().items()}
        return [[[(None if (v := piv.get((o, p, i))) is None or v != v or abs(v) == float("inf") else round(float(v), 3))
                  for i in range(NS)] for p in pus] for o in objs]
    code = f["properties"]["SWSDLID"]
    ASS_LABEL = {"SS11a": "SA Murray", "SS11b": "CLLMM"}
    ass = [{"code": c, "name": ASS_LABEL.get(c) or (PROC[c]["name"] if c in PROC else c), "pus": ix} for c, ix in assessment_units(code, pus) if ix]
    desc = [str(ref_any.at[o, "Objective"]) if o in ref_any.index and isinstance(ref_any.at[o, "Objective"], str) else "" for o in objs]   # objective text for tooltips / level 3
    SDLD[nm] = {"code": code, "ass": ass, "pus": pus, "objs": objs, "desc": desc, "theme": [str(theme[o]).replace("Other species", "Other Species") for o in objs],
                "fr": table(a, "Rating_Frsp"), "et": table(b, "Rating_ETP_mean")}
pu_raw = pd.read_csv(HERE / "data/ewr_results/frequency_raw.csv", dtype=str, usecols=["PlanningUnitName", "Gauge", "EWR", "SWSDLName"]).drop_duplicates()
pu_raw["Gauge"] = pu_raw.Gauge.replace(REKEY)
PUINFO = {pu: {"g": sorted(set(v.Gauge)), "n": len(v), "s": v.SWSDLName.iat[0]} for pu, v in pu_raw.groupby("PlanningUnitName")}
print(len(SDLD), "SDL units with planning-unit ratings;", sum(len(v["pus"]) for v in SDLD.values()), "planning units")

html = open(HERE / "templates/map_template.html").read().replace(
    "__DATA__", json.dumps(gj, separators=(",", ":"))).replace(
    "__GAUGES__", json.dumps(gauges, separators=(",", ":"))).replace(
    "__SDLD__", json.dumps(SDLD, separators=(",", ":"))).replace(
    "__PUINFO__", json.dumps(PUINFO, separators=(",", ":"))).replace(
    "__PROC__", json.dumps(PROC, separators=(",", ":"))).replace(
    "__MODN__", json.dumps(MODN, separators=(",", ":"))).replace(
    "__SCEN__", json.dumps({"policies": POLICIES, "climates": CLIMATES})).replace(
    "__RIVERS__", (HERE / "data/boundaries/rivers.geojson").read_text())
open(HERE / "index.html", "w").write(html)
print(len(html) // 1024, "KB;", sum(f["properties"]["in_review"] for f in gj["features"]), "units in review data")
