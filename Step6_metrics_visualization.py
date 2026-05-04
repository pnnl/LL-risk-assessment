"""
Step6_metrics_visualization.py
================================
Reads the metric CSVs, LDDL CSV, and timeseries JSON produced by Step5_analyzesim.py
and writes a single self-contained HTML dashboard with all data embedded.

Changes from previous version:
  - Parallel line section split into two panels: Flows and Swings
  - New LDDL section: P/OS-P, Q/OS-Q, and Bus Voltage time series
  - LDDL metrics added to KPI grid
  - Loads metrics_lddl.csv when present

Usage:
    python Step6_metrics_visualization.py
"""

import os, json
import pandas as pd
import numpy as np
from pathlib import Path

# ── CHANGE THESE BEFORE RUNNING ──────────────────────────────────────────

THRESHOLDS = dict(
    genmw      = 5.0,
    genpct     = 3.0,
    genmvar    = 5.0,
    genqpct    = 3.0,
    vtsw       = 0.05,
    freqband   = 0.036,
    freqsw     = 0.03,
    anglesw    = 10.0,
    linemw     = 20.0,
    linepct    = 10.0,
    vhi        = 1.10,
    vlo        = 0.90,
    vsw        = 0.05,
)


# ═══════════════════════════════════════════════════════════════════════════
# DATA LOADING
# ═══════════════════════════════════════════════════════════════════════════

def load_data(INPUT_DIR, run_tag):
    files = {
        "gen":  f"metrics_generators_{run_tag}.csv",
        "line": f"metrics_lines_{run_tag}.csv",
        "bus":  f"metrics_buses_{run_tag}.csv",
        "load": f"metrics_loads_{run_tag}.csv",
        "lddl": f"metrics_lddl_{run_tag}.csv",
        "ts":   f"timeseries_worst_{run_tag}.json",
    }
    data = {}
    for key, fname in files.items():
        path = os.path.join(INPUT_DIR, fname)
        if not os.path.exists(path):
            print(f"  [!] Missing: {fname} — {key} section will be empty")
            data[key] = [] if key != "ts" else {}
            continue
        if key == "ts":
            with open(path) as f:
                data[key] = json.load(f)
        else:
            df = pd.read_csv(path)
            df = df.replace([np.inf, -np.inf], np.nan)
            data[key] = json.loads(df.to_json(orient="records"))
        print(f"  Loaded {fname}: {len(data[key])} records")
    return data


# ═══════════════════════════════════════════════════════════════════════════
# HTML GENERATION
# ═══════════════════════════════════════════════════════════════════════════

def build_html(data, subtitle, thresholds):
    gen_json  = json.dumps(data["gen"],  indent=None)
    line_json = json.dumps(data["line"], indent=None)
    bus_json  = json.dumps(data["bus"],  indent=None)
    load_json = json.dumps(data["load"], indent=None)
    lddl_json = json.dumps(data["lddl"], indent=None)
    ts_json   = json.dumps(data["ts"],   indent=None)
    thr_json  = json.dumps(thresholds,   indent=None)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>Reliability Risk Assessment Dashboard</title>
<script src="https://cdn.plot.ly/plotly-2.27.0.min.js"></script>
<style>
*{{box-sizing:border-box;margin:0;padding:0}}
:root{{
  --bg:#0d1b2a;--fg:#cdd9e5;--hdr:#102030;--hdr-border:#1a6ea8;
  --sidebar:#0b1b2e;--sidebar-border:#1a3a5c;--card:#0f2236;--card-border:#1a3a5c;
  --kgroup:#071a2e;--kitem:#0b1c30;--plot-bg:#071520;
  --grid:#122540;--zero:#1a3a5c;--line-color:#1a3a5c;
  --accent:#4a9fd4;--accent2:#7aacbf;--accent3:#e8623a;--accent4:#4ab878;
  --th-bg:#0b1c30;--td-border:#0e2035;--tbody-hover:#102030;
  --grp-color:#4a8;--tbtn:#152c44;--tbtn-border:#2a5a8c;--tbtn-fg:#7aacbf;
  --tbtn-act:#1a6ea8;--tbtn-act-border:#3a9ed8;
}}
body.light{{
  --bg:#f0f4f8;--fg:#1a2a3a;--hdr:#d0e0f0;--hdr-border:#1a6ea8;
  --sidebar:#e0eaf4;--sidebar-border:#9ab;--card:#fff;--card-border:#b0c8e0;
  --kgroup:#e4eef8;--kitem:#f5f9ff;--plot-bg:#f8fafc;
  --grid:#d0dde8;--zero:#c0d0e0;--line-color:#c0d0e0;
  --accent:#1a6ea8;--accent2:#3a6080;--accent3:#c04010;--accent4:#287848;
  --th-bg:#d8e8f4;--td-border:#c8d8e8;--tbody-hover:#eaf2fa;
  --grp-color:#287848;--tbtn:#ccddf0;--tbtn-border:#8ab;--tbtn-fg:#1a4060;
  --tbtn-act:#1a6ea8;--tbtn-act-border:#1a6ea8;
}}
body{{font-family:'Segoe UI',Arial,sans-serif;background:var(--bg);color:var(--fg);font-size:13px;transition:background .2s,color .2s}}

.hdr{{padding:9px 16px;background:var(--hdr);border-bottom:2px solid var(--hdr-border);
      display:flex;align-items:center;gap:14px;flex-wrap:wrap}}
.hdr-title{{font-size:1.05rem}}
.hdr-title .sub{{font-size:0.75rem;color:var(--accent2);font-weight:normal}}
.mode-btn{{margin-left:auto;background:var(--tbtn);border:1px solid var(--tbtn-border);
  border-radius:4px;padding:4px 12px;color:var(--tbtn-fg);cursor:pointer;font-size:0.72rem;
  transition:background .2s}}
.mode-btn:hover{{background:var(--tbtn-act);color:#fff}}

.layout{{display:flex;height:calc(100vh - 46px);overflow:hidden}}

/* sidebar */
.sidebar{{width:240px;min-width:240px;background:var(--sidebar);padding:10px 9px;
          overflow-y:auto;border-right:1px solid var(--sidebar-border);flex-shrink:0}}
.sidebar>h2{{font-size:0.63rem;text-transform:uppercase;letter-spacing:2px;
             color:var(--accent);margin-bottom:6px}}
/* sidebar threshold groups — mirror KPI nesting */
.thr-group{{background:var(--kgroup);border:1px solid var(--card-border);border-radius:4px;
            padding:5px 8px;margin-bottom:5px}}
.thr-group-hdr{{font-size:0.60rem;text-transform:uppercase;letter-spacing:1.8px;
                color:var(--accent);font-weight:700;margin-bottom:4px;padding-bottom:3px;
                border-bottom:2px solid var(--hdr-border)}}
.thr-subgroup{{margin-bottom:4px;padding-left:6px;border-left:2px solid var(--card-border)}}
.thr-subgroup-hdr{{font-size:0.55rem;text-transform:uppercase;letter-spacing:1.5px;
                   color:var(--accent2);margin:4px 0 3px;padding-bottom:1px;
                   border-bottom:1px solid var(--card-border)}}
.ctrl{{margin-bottom:6px}}
.ctrl label{{display:flex;justify-content:space-between;align-items:baseline;
             color:var(--accent2);font-size:0.68rem;margin-bottom:2px;gap:4px}}
.ctrl label .lbl{{flex:1;line-height:1.3}}
.ctrl label .val{{color:var(--fg);font-weight:bold;white-space:nowrap;font-size:0.72rem}}
input[type=range]{{width:100%;height:4px;accent-color:#1a6ea8;cursor:pointer}}

/* main */
.main{{flex:1;overflow-y:auto;padding:8px;display:flex;flex-direction:column;gap:8px}}
.card{{background:var(--card);border:1px solid var(--card-border);border-radius:5px;padding:8px 10px}}
.card>h3{{font-size:0.64rem;text-transform:uppercase;letter-spacing:1.5px;
          color:var(--accent);margin-bottom:6px}}
/* collapsible sections */
.sec-hdr{{font-size:0.64rem;text-transform:uppercase;letter-spacing:2px;
          color:var(--accent);padding:4px 2px 1px;border-top:1px solid var(--card-border);
          display:flex;align-items:center;gap:6px;cursor:pointer;user-select:none}}
.sec-hdr:hover{{color:var(--fg)}}
.collapse-btn{{margin-left:auto;background:none;border:none;color:inherit;
  cursor:pointer;font-size:1rem;line-height:1;padding:0 2px;opacity:0.7}}
.collapse-btn:hover{{opacity:1}}
.sec-body{{display:flex;flex-direction:column;gap:8px}}
.sec-body.hidden{{display:none}}
/* collapsible card */
.card-collapse-btn{{margin-left:auto;background:none;border:none;color:var(--accent2);
  cursor:pointer;font-size:0.85rem;line-height:1;padding:0 2px;opacity:0.7;flex-shrink:0}}
.card-collapse-btn:hover{{opacity:1;color:var(--accent)}}
.card>h3{{display:flex;align-items:center}}
.card-body.hidden{{display:none}}

/* KPI grid — grouped */
.kgrid{{display:flex;flex-direction:column;gap:5px}}
.kgroup{{background:var(--kgroup);border:1px solid var(--card-border);border-radius:4px;padding:5px 8px}}
.kgroup-hdr{{font-size:0.60rem;text-transform:uppercase;letter-spacing:1.8px;color:var(--accent);
             margin-bottom:5px;padding-bottom:3px;border-bottom:2px solid var(--hdr-border);font-weight:700}}
.ksubgroup{{margin-bottom:5px;padding-left:6px;border-left:2px solid var(--card-border)}}
.ksubgroup-hdr{{font-size:0.55rem;text-transform:uppercase;letter-spacing:1.5px;color:var(--accent2);
                margin-bottom:3px;padding-bottom:1px;border-bottom:1px solid var(--card-border)}}
.kgroup-items{{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:3px}}
.kitem{{background:var(--kitem);border:1px solid var(--card-border);border-radius:3px;padding:4px 8px;display:flex;align-items:center;gap:8px}}
.kitem .klbl{{color:var(--accent2);font-size:0.66rem;line-height:1.3;flex:1}}
.kitem .kval{{font-size:0.92rem;font-weight:bold;color:var(--accent);white-space:nowrap}}
.kval.warn{{color:var(--accent3)!important}}.kval.ok{{color:var(--accent4)!important}}.kval.info{{color:#e8c030!important}}

/* two/three col */
.two-col{{display:grid;grid-template-columns:1fr 1fr;gap:8px}}
.three-col{{display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px}}

/* chart divs */
.plt{{width:100%;height:260px;resize:vertical;overflow:hidden;min-height:100px}}
.plt-sm{{width:100%;height:210px;resize:vertical;overflow:hidden;min-height:80px}}
.plt-xs{{width:100%;height:175px;resize:vertical;overflow:hidden;min-height:80px}}

/* sidebar resize handle */
.sidebar{{position:relative}}
.sidebar-resizer{{
  position:absolute;top:0;right:0;width:5px;height:100%;
  cursor:col-resize;background:transparent;z-index:10;
  border-right:2px solid var(--sidebar-border);
  transition:border-color .15s;
}}
.sidebar-resizer:hover,.sidebar-resizer.dragging{{border-right-color:var(--accent)}}

/* panel resize hint */
.resize-hint{{font-size:0.58rem;color:var(--accent2);opacity:0.5;
  text-align:right;margin-top:2px;letter-spacing:0.5px;user-select:none}}

/* tabs */
.trow{{display:flex;gap:5px;margin-bottom:7px;flex-wrap:wrap}}
.tbtn{{background:var(--tbtn);border:1px solid var(--tbtn-border);border-radius:3px;
       padding:3px 10px;color:var(--tbtn-fg);cursor:pointer;font-size:0.7rem}}
.tbtn.act{{background:var(--tbtn-act);border-color:var(--tbtn-act-border);color:#eef4ff}}

/* tables */
.tbl-wrap{{overflow-x:auto;max-height:270px;overflow-y:auto}}
table{{width:100%;border-collapse:collapse;font-size:0.7rem}}
th{{background:var(--th-bg);padding:5px 7px;text-align:left;color:var(--accent);
    font-weight:600;position:sticky;top:0;white-space:nowrap;
    cursor:pointer;user-select:none}}
th:hover{{color:var(--fg)}}
td{{padding:4px 7px;border-bottom:1px solid var(--td-border);white-space:nowrap}}
tr:hover td{{background:var(--tbody-hover)}}
.hi{{color:var(--accent3);font-weight:bold}}.okc{{color:var(--accent4)}}

/* parallel chips */
.par-chips{{display:flex;flex-wrap:wrap;gap:4px;margin-top:7px}}
.pchip{{display:inline-flex;align-items:center;gap:6px;background:#0b1c30;
        border:1px solid #1a3a5c;border-radius:3px;padding:3px 9px;font-size:0.68rem}}
.pchip .pkey{{color:#e89030;font-weight:bold}}
.pchip .pfl{{color:#7aacbf}}
.par-note{{font-size:0.7rem;color:#7aacbf;font-weight:normal;
           text-transform:none;letter-spacing:0;margin-left:8px}}
.sublbl{{font-size:0.7rem;color:#e8623a;font-weight:bold;margin-bottom:3px}}

/* LDDL panel accent */
.sec-hdr.lddl-hdr{{color:#d4a017;border-top-color:#3a4a1c}}
.card.lddl-card{{border-color:#2a3a1c}}
.card.lddl-card>h3{{color:#d4a017}}
</style>
</head>
<body>

<div class="hdr">
  <!-- PNNL logo (embedded image) -->
  <img src="data:image/jpeg;base64,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AABDbnRDYm9vbAAAAAAATGJsc2Jvb2wAAAAAAE5ndHZib29sAAAAAABFbWxEYm9vbAAAAAAASW50cmJvb2wAAAAAAEJja2dPYmpjAAAAAQAAAAAAAFJHQkMAAAADAAAAAFJkICBkb3ViQG/gAAAAAAAAAAAAR3JuIGRvdWJAb+AAAAAAAAAAAABCbCAgZG91YkBv4AAAAAAAAAAAAEJyZFRVbnRGI1JsdAAAAAAAAAAAAAAAAEJsZCBVbnRGI1JsdAAAAAAAAAAAAAAAAFJzbHRVbnRGI1B4bEBywAAAAAAAAAAACnZlY3RvckRhdGFib29sAQAAAABQZ1BzZW51bQAAAABQZ1BzAAAAAFBnUEMAAAAATGVmdFVudEYjUmx0AAAAAAAAAAAAAAAAVG9wIFVudEYjUmx0AAAAAAAAAAAAAAAAU2NsIFVudEYjUHJjQFkAAAAAAAAAAAAQY3JvcFdoZW5QcmludGluZ2Jvb2wAAAAADmNyb3BSZWN0Qm90dG9tbG9uZwAAAAAAAAAMY3JvcFJlY3RMZWZ0bG9uZwAAAAAAAAANY3JvcFJlY3RSaWdodGxvbmcAAAAAAAAAC2Nyb3BSZWN0VG9wbG9uZwAAAAAAOEJJTQPtAAAAAAAQASwAAAABAAEBLAAAAAEAAThCSU0EJgAAAAAADgAAAAAAAAAAAAA/gAAAOEJJTQQNAAAAAAAEAAAAHjhCSU0EGQAAAAAABAAAAB44QklNA/MAAAAAAAkAAAAAAAAAAAEAOEJJTScQAAAAAAAKAAEAAAAAAAAAAThCSU0D9QAAAAAASAAvZmYAAQBsZmYABgAAAAAAAQAvZmYAAQChmZoABgAAAAAAAQAyAAAAAQBaAAAABgAAAAAAAQA1AAAAAQAtAAAABgAAAAAAAThCSU0D+AAAAAAAcAAA/////////////////////////////wPoAAAAAP////////////////////////////8D6AAAAAD/////////////////////////////A+gAAAAA/////////////////////////////wPoAAA4QklNBAgAAAAAABAAAAABAAACQAAAAkAAAAAAOEJJTQQeAAAAAAAEAAAAADhCSU0EGgAAAAADXwAAAAYAAAAAAAAAAAAAAUgAAAK0AAAAFQBQAE4ATgBMAF8AQwBF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W2AuY6OdpfU5jnN/rJn/AFZ6C/p7emuwqvsjHb21gEEPP0rRYD6vqu/Ps371ppIKczp/1a6H00WjExGM9dhrtLi6wuYfpV7rnWfo3fnsT9L+rvRukW2XdPx/RsuaGPdve+Wg7mt/SvetJJJT/9k4QklNBCEAAAAAAF0AAAABAQAAAA8AQQBkAG8AYgBlACAAUABoAG8AdABvAHMAaABvAHAAAAAXAEEAZABvAGIAZQAgAFAAaABvAHQAbwBzAGgAbwBwACAAQwBDACAAMgAwADEAOAAAAAEAOEJJTQQGAAAAAAAHAAUAAAABAQD/4RGEaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wLwA8P3hwYWNrZXQgYmVnaW49Iu+7vyIgaWQ9Ilc1TTBNcENlaGlIenJlU3pOVGN6a2M5ZCI/PiA8eDp4bXBtZXRhIHhtbG5zOng9ImFkb2JlOm5zOm1ldGEvIiB4OnhtcHRrPSJBZG9iZSBYTVAgQ29yZSA1LjYtYzE0MCA3OS4xNjA0NTEsIDIwMTcvMDUvMDYtMDE6MDg6MjEgICAgICAgICI+IDxyZGY6UkRGIHhtbG5zOnJkZj0iaHR0cDovL3d3dy53My5vcmcvMTk5OS8wMi8yMi1yZGYtc3ludGF4LW5zIyI+IDxyZGY6RGVzY3JpcHRpb24gcmRmOmFib3V0PSIiIHhtbG5zOnhtcD0iaHR0cDovL25zLmFkb2JlLmNvbS94YXAvMS4wLyIgeG1sbnM6eG1wTU09Imh0dHA6Ly9ucy5hZG9iZS5jb20veGFwLzEuMC9tbS8iIHhtbG5zOnN0RXZ0PSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvc1R5cGUvUmVzb3VyY2VFdmVudCMiIHhtbG5zOnN0UmVmPSJodHRwOi8vbnMuYWRvYmUuY29tL3hhcC8xLjAvc1R5cGUvUmVzb3VyY2VSZWYjIiB4bWxuczpkYz0iaHR0cDovL3B1cmwub3JnL2RjL2VsZW1lbnRzLzEuMS8iIHhtbG5zOnBob3Rvc2hvcD0iaHR0cDovL25zLmFkb2JlLmNvbS9waG90b3Nob3AvMS4wLyIgeG1wOkNyZWF0b3JUb29sPSJBZG9iZSBQaG90b3Nob3AgQ0MgMjAxOCAoTWFjaW50b3NoKSIgeG1wOkNyZWF0ZURhdGU9IjIwMTgtMDUtMDRUMDg6MjA6NTUtMDc6MDAiIHhtcDpNZXRhZGF0YURhdGU9IjIwMTgtMDgtMDZUMDc6NDc6MjAtMDc6MDAiIHhtcDpNb2RpZnlEYXRlPSIyMDE4LTA4LTA2VDA3OjQ3OjIwLTA3OjAwIiB4bXBNTTpJbnN0YW5jZUlEPSJ4bXAuaWlkOjQ3OGI5NjdmLTAwNzEtNDUyMi1hYzQ0LTc5NzZjMGRjNjk4MSIgeG1wTU06RG9jdW1lbnRJRD0iYWRvYmU6ZG9jaWQ6cGhvdG9zaG9wOjgzMGE3ZTRlLWNmZjItNmU0Mi05NjM4LWViN2VlZDk1NDk1MyIgeG1wTU06T3JpZ2luYWxEb2N1bWVudElEPSJ4bXAuZGlkOjY1MjZhNTFlLWY4YWQtNDJmMS1hNjVlLWJiZDhhMGI0ZGRjNCIgZGM6Zm9ybWF0PSJpbWFnZS9qcGVnIiBwaG90b3Nob3A6Q29sb3JNb2RlPSIzIiBwaG90b3Nob3A6SUNDUHJvZmlsZT0ic1JHQiBJRUM2MTk2Ni0yLjEiPiA8eG1wTU06SGlzdG9yeT4gPHJkZjpTZXE+IDxyZGY6bGkgc3RFdnQ6YWN0aW9uPSJjcmVhdGVkIiBzdEV2dDppbnN0YW5jZUlEPSJ4bXAuaWlkOjY1MjZhNTFlLWY4YWQtNDJmMS1hNjVlLWJiZDhhMGI0ZGRjNCIgc3RFdnQ6d2hlbj0iMjAxOC0wNS0wNFQwODoyMDo1NS0wNzowMCIgc3RFdnQ6c29mdHdhcmVBZ2VudD0iQWRvYmUgUGhvdG9zaG9wIENDIDIwMTggKE1hY2ludG9zaCkiLz4gPHJkZjpsaSBzdEV2dDphY3Rpb249InNhdmVkIiBzdEV2dDppbnN0YW5jZUlEPSJ4bXAuaWlkOjRjMTk0ZTU2LWNlOGUtNGQxNy1iNDZkLWVkNmQ0Yzk0NTYzYyIgc3RFdnQ6d2hlbj0iMjAxOC0wNS0wNFQwODoyMDo1NS0wNzowMCIgc3RFdnQ6c29mdHdhcmVBZ2VudD0iQWRvYmUgUGhvdG9zaG9wIENDIDIwMTggKE1hY2ludG9zaCkiIHN0RXZ0OmNoYW5nZWQ9Ii8iLz4gPHJkZjpsaSBzdEV2dDphY3Rpb249InNhdmVkIiBzdEV2dDppbnN0YW5jZUlEPSJ4bXAuaWlkOjJlNWU4ODU4LWE5YWEtNDRjOS04MTFkLTY0MDFkOWRiNTBlMCIgc3RFdnQ6d2hlbj0iMjAxOC0wOC0wNlQwNzo0NzoyMC0wNzowMCIgc3RFdnQ6c29mdHdhcmVBZ2VudD0iQWRvYmUgUGhvdG9zaG9wIENDIDIwMTggKE1hY2ludG9zaCkiIHN0RXZ0OmNoYW5nZWQ9Ii8iLz4gPHJkZjpsaSBzdEV2dDphY3Rpb249ImNvbnZlcnRlZCIgc3RFdnQ6cGFyYW1ldGVycz0iZnJvbSBpbWFnZS9wbmcgdG8gaW1hZ2UvanBlZyIvPiA8cmRmOmxpIHN0RXZ0OmFjdGlvbj0iZGVyaXZlZCIgc3RFdnQ6cGFyYW1ldGVycz0iY29udmVydGVkIGZyb20gaW1hZ2UvcG5nIHRvIGltYWdlL2pwZWciLz4gPHJkZjpsaSBzdEV2dDphY3Rpb249InNhdmVkIiBzdEV2dDppbnN0YW5jZUlEPSJ4bXAuaWlkOjQ3OGI5NjdmLTAwNzEtNDUyMi1hYzQ0LTc5NzZjMGRjNjk4MSIgc3RFdnQ6d2hlbj0iMjAxOC0wOC0wNlQwNzo0NzoyMC0wNzowMCIgc3RFdnQ6c29mdHdhcmVBZ2VudD0iQWRvYmUgUGhvdG9zaG9wIENDIDIwMTggKE1hY2ludG9zaCkiIHN0RXZ0OmNoYW5nZWQ9Ii8iLz4gPC9yZGY6U2VxPiA8L3htcE1NOkhpc3Rvcnk+IDx4bXBNTTpEZXJpdmVkRnJvbSBzdFJlZjppbnN0YW5jZUlEPSJ4bXAuaWlkOjJlNWU4ODU4LWE5YWEtNDRjOS04MTFkLTY0MDFkOWRiNTBlMCIgc3RSZWY6ZG9jdW1lbnRJRD0iYWRvYmU6ZG9jaWQ6cGhvdG9zaG9wOjEzNDBlNTlkLTdkNjctMTk0Mi04N2Y5LTY1ZTA2NDkyYmJhNiIgc3RSZWY6b3JpZ2luYWxEb2N1bWVudElEPSJ4bXAuZGlkOjY1MjZhNTFlLWY4YWQtNDJmMS1hNjVlLWJiZDhhMGI0ZGRjNCIvPiA8L3JkZjpEZXNjcmlwdGlvbj4gPC9yZGY6UkRGPiA8L3g6eG1wbWV0YT4gICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAg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" alt="PNNL" style="height:38px;width:auto;flex-shrink:0;background:#fff;border-radius:3px;padding:2px 4px;">
  <div class="hdr-title">Reliability Risk Assessment Dashboard
    <span class="sub">&mdash; {subtitle}</span>
  </div>
  <button class="mode-btn" onclick="toggleMode()" id="mode-btn">☀ Light Mode</button>
</div>

<div class="layout">

<!-- ══ SIDEBAR ═══════════════════════════════════════ -->
<aside class="sidebar" id="sidebar">
  <div class="sidebar-resizer" id="sidebar-resizer" title="Drag to resize sidebar"></div>
  <h2>Thresholds</h2>
  <p style="font-size:0.64rem;color:var(--accent2);line-height:1.5;margin-bottom:8px;padding:6px 8px;background:var(--kgroup);border:1px solid var(--card-border);border-radius:4px;">
    Set your thresholds below. If the observed oscillation amplitudes cross these thresholds, elements are flagged as <span style="color:var(--accent3);font-weight:bold">violations</span> and highlighted throughout the dashboard.
  </p>

  <!-- Generator group -->
  <div class="thr-group">
    <div class="thr-group-hdr">Generator</div>

    <div class="thr-subgroup">
      <div class="thr-subgroup-hdr">Active Power</div>
      <div class="ctrl"><label><span class="lbl">P swing amplitude</span><span class="val" id="v-genmw"></span></label>
        <input type="range" id="s-genmw" min="0" max="50" step="0.5" oninput="update()"></div>
      <div class="ctrl"><label><span class="lbl">P swing % Mbase</span><span class="val" id="v-genpct"></span></label>
        <input type="range" id="s-genpct" min="0" max="20" step="0.25" oninput="update()"></div>
    </div>

    <div class="thr-subgroup">
      <div class="thr-subgroup-hdr">Reactive Power</div>
      <div class="ctrl"><label><span class="lbl">Q swing amplitude</span><span class="val" id="v-genmvar"></span></label>
        <input type="range" id="s-genmvar" min="0" max="50" step="0.5" oninput="update()"></div>
      <div class="ctrl"><label><span class="lbl">Q swing % Mbase</span><span class="val" id="v-genqpct"></span></label>
        <input type="range" id="s-genqpct" min="0" max="20" step="0.25" oninput="update()"></div>
    </div>

    <div class="thr-subgroup">
      <div class="thr-subgroup-hdr">Dynamics</div>
      <div class="ctrl"><label><span class="lbl">Vt swing (pu)</span><span class="val" id="v-vtsw"></span></label>
        <input type="range" id="s-vtsw" min="0" max="0.2" step="0.005" oninput="update()"></div>
      <div class="ctrl"><label><span class="lbl">Freq band &plusmn;(Hz)</span><span class="val" id="v-freqband"></span></label>
        <input type="range" id="s-freqband" min="0.005" max="0.1" step="0.001" oninput="update()"></div>
      <div class="ctrl"><label><span class="lbl">Freq swing (Hz)</span><span class="val" id="v-freqsw"></span></label>
        <input type="range" id="s-freqsw" min="0.005" max="0.1" step="0.001" oninput="update()"></div>
      <div class="ctrl"><label><span class="lbl">Angle swing (&deg;)</span><span class="val" id="v-anglesw"></span></label>
        <input type="range" id="s-anglesw" min="0" max="30" step="0.5" oninput="update()"></div>
    </div>
  </div>

  <!-- Lines group -->
  <div class="thr-group">
    <div class="thr-group-hdr">Lines</div>
    <div class="ctrl"><label><span class="lbl">P swing amplitude (MW)</span><span class="val" id="v-linemw"></span></label>
      <input type="range" id="s-linemw" min="0" max="200" step="1" oninput="update()"></div>
    <div class="ctrl"><label><span class="lbl">P swing % rating</span><span class="val" id="v-linepct"></span></label>
      <input type="range" id="s-linepct" min="0" max="50" step="1" oninput="update()"></div>
  </div>

  <!-- HV Buses group -->
  <div class="thr-group">
    <div class="thr-group-hdr">HV Buses</div>
    <div class="ctrl"><label><span class="lbl">V upper limit (pu)</span><span class="val" id="v-vhi"></span></label>
      <input type="range" id="s-vhi" min="1.0" max="1.15" step="0.005" oninput="update()"></div>
    <div class="ctrl"><label><span class="lbl">V lower limit (pu)</span><span class="val" id="v-vlo"></span></label>
      <input type="range" id="s-vlo" min="0.85" max="1.0" step="0.005" oninput="update()"></div>
    <div class="ctrl"><label><span class="lbl">V swing amplitude (pu)</span><span class="val" id="v-vsw"></span></label>
      <input type="range" id="s-vsw" min="0" max="0.2" step="0.005" oninput="update()"></div>
  </div>
</aside>

<!-- ══ MAIN ══════════════════════════════════════════ -->
<main class="main">

  <!-- KPI summary -->
  <div class="sec-hdr" id="sec-kpi" onclick="toggleSec('sec-kpi','body-kpi')">&#9660; Risk Metrics Summary <button class="collapse-btn">&#8211;</button></div>
  <div id="body-kpi" class="sec-body">
    <div class="card"><div class="kgrid" id="kgrid"></div></div>
  </div>

  <!-- Generator section -->
  <div class="sec-hdr" id="sec-gen" onclick="toggleSec('sec-gen','body-gen')">&#9660; Generator Metrics <button class="collapse-btn">&#8211;</button></div>
  <div id="body-gen" class="sec-body">
  <div class="two-col">
    <div class="card"><h3>P Swing Amplitude Distribution</h3><div class="plt" id="gen-p-hist"></div></div>
    <div class="card"><h3>Q Swing Amplitude Distribution</h3><div class="plt" id="gen-q-hist"></div></div>
  </div>
  <div class="two-col">
    <div class="card"><h3>Frequency Swing Amplitude Distribution</h3><div class="plt" id="gen-freq-hist"></div></div>
    <div class="card"><h3>Rotor Angle Swing Amplitude Distribution</h3><div class="plt" id="gen-angle-hist"></div></div>
  </div>
  <div class="two-col">
    <div class="card"><h3>Top 30 Generators &mdash; Highest P Swing Amplitude</h3><div class="plt" id="gen-top-p"></div></div>
    <div class="card"><h3>Top 30 Generators &mdash; Highest Q Swing Amplitude</h3><div class="plt" id="gen-top-q"></div></div>
  </div>
  <div class="card">
    <h3>Generator Detail</h3>
    <div class="tbl-wrap" id="gen-tbl"></div>
  </div>

  </div><!-- /body-gen -->

  <!-- Line section -->
  <div class="sec-hdr" id="sec-line" onclick="toggleSec('sec-line','body-line')">&#9660; Line Metrics <button class="collapse-btn">&#8211;</button></div>
  <div id="body-line" class="sec-body">
  <div class="two-col">
    <div class="card"><h3>P Swing Amplitude Distribution</h3><div class="plt" id="line-hist"></div></div>
    <div class="card"><h3>Top 30 Lines by P Swing Amplitude</h3><div class="plt" id="line-top"></div></div>
  </div>

  </div><!-- /body-line -->

  <!-- Parallel circuits -->
  <div class="sec-hdr" id="sec-par" onclick="toggleSec('sec-par','body-par')">&#9660; Parallel Circuit Analysis <span class="par-note" id="par-note"></span> <button class="collapse-btn">&#8211;</button></div>
  <div id="body-par" class="sec-body">
  <div class="two-col">

    <!-- Panel 1: Flows -->
    <div class="card">
      <h3>Parallel Circuit Flows (MW)</h3>
      <div style="font-size:0.67rem;color:#7aacbf;margin-bottom:4px">
        Initial P flow per circuit &mdash; grouped by bus pair
      </div>
      <div class="plt" id="par-flows-circuit"></div>
      <div style="font-size:0.67rem;color:#7aacbf;margin:8px 0 4px">
        &Sigma; Initial P flow per bus pair
      </div>
      <div class="plt-sm" id="par-flows-pair"></div>
    </div>

    <!-- Panel 2: Swings -->
    <div class="card">
      <h3>Parallel Circuit Swings (MW)</h3>
      <div style="font-size:0.67rem;color:#7aacbf;margin-bottom:4px">
        P swing amplitude per circuit &mdash; coloured by threshold
      </div>
      <div class="plt" id="par-swings-circuit"></div>
      <div style="font-size:0.67rem;color:#7aacbf;margin:8px 0 4px">
        &Sigma; P swing amplitude per bus pair &mdash; annotated with circuit count
      </div>
      <div class="plt-sm" id="par-swings-pair"></div>
    </div>

  </div>
  <!-- Summary chips span full width below both panels -->
  <div class="card" style="padding:8px 10px">
    <div class="par-chips" id="par-chips"></div>
  </div>

  </div><!-- /body-par -->

  <!-- HV Bus section -->
  <div class="sec-hdr" id="sec-bus" onclick="toggleSec('sec-bus','body-bus')">&#9660; HV Bus Metrics <button class="collapse-btn">&#8211;</button></div>
  <div id="body-bus" class="sec-body">
  <div class="two-col">
    <div class="card"><h3>Voltage Swing Amplitude &mdash; Top 50 Buses</h3><div class="plt" id="bus-swing"></div></div>
    <div class="card"><h3>V<sub>min</sub> &amp; V<sub>max</sub> Envelope</h3><div class="plt" id="bus-venv"></div></div>
  </div>

  </div><!-- /body-bus -->

  <!-- Most Impacted Elements Time Series -->
  <div class="sec-hdr" id="sec-ts" onclick="toggleSec('sec-ts','body-ts')">&#9660; Most Impacted Elements <button class="collapse-btn">&#8211;</button></div>
  <div id="body-ts" class="sec-body">
  <div class="two-col">
    <div class="card">
      <div class="sublbl" id="ts-lbl-gen"></div>
      <h3>Generator P &amp; Q</h3><div class="plt" id="ts-gen-pq"></div>
    </div>
    <div class="card">
      <div class="sublbl" id="ts-lbl-gen2"></div>
      <h3>Terminal Voltage &amp; Frequency</h3><div class="plt" id="ts-gen-vf"></div>
    </div>
  </div>
  <div class="two-col">
    <div class="card">
      <div class="sublbl" id="ts-lbl-gen3"></div>
      <h3>Rotor Angle</h3><div class="plt" id="ts-gen-ang"></div>
    </div>
    <div class="card">
      <div class="sublbl" id="ts-lbl-line"></div>
      <h3>Line P &amp; Q Flow</h3><div class="plt" id="ts-line"></div>
    </div>
  </div>
  <div class="two-col">
    <div class="card">
      <div class="sublbl" id="ts-lbl-bus"></div>
      <h3>HV Bus Voltage &amp; Angle</h3><div class="plt" id="ts-bus"></div>
    </div>
  </div>
  </div><!-- /body-ts -->

  <!-- LDDL Bus Response -->
  <div class="sec-hdr lddl-hdr" id="sec-lddl" onclick="toggleSec('sec-lddl','body-lddl')">&#9660; LDDL Bus Response <button class="collapse-btn">&#8211;</button></div>
  <div id="body-lddl" class="sec-body">
  <div class="two-col">
    <div class="card lddl-card">
      <h3>LDDL Active Power</h3>
      <div style="font-size:0.67rem;color:#7aacbf;margin-bottom:4px">
        P &amp; OS P (MW) &mdash; oscillation-source active power vs measured
      </div>
      <div class="plt" id="lddl-p"></div>
    </div>
    <div class="card lddl-card">
      <h3>LDDL Reactive Power</h3>
      <div style="font-size:0.67rem;color:#7aacbf;margin-bottom:4px">
        Q &amp; OS Q (MVar) &mdash; oscillation-source reactive power vs measured
      </div>
      <div class="plt" id="lddl-q"></div>
    </div>
  </div>
  <div class="two-col">
    <div class="card lddl-card">
      <h3>LDDL Bus Voltage</h3>
      <div style="font-size:0.67rem;color:#7aacbf;margin-bottom:4px">
        Bus voltage (pu) at LDDL connection point
      </div>
      <div class="plt" id="lddl-v"></div>
    </div>
  </div>
  </div><!-- /body-lddl -->

</main>
</div>

<script>
// ── Embedded data ────────────────────────────────────────────────────────
const GEN  = {gen_json};
const LINE = {line_json};
const BUS  = {bus_json};
const LOAD = {load_json};
const LDDL = {lddl_json};
const TS   = {ts_json};
const DEFS = {thr_json};

// ── State ────────────────────────────────────────────────────────────────
let GEN_VIEW = 'unit';
let genSortCol = 'pg_swing', genSortAsc = false;
let lineSortCol = 'pbr_swing', lineSortAsc = false;

// ── Plotly config / layout factory ───────────────────────────────────────
const CFG = {{responsive:true, displayModeBar:false}};

function lay(xt, yt, y2t) {{
  const light = document.body.classList.contains('light');
  const gridC  = light ? '#d0dde8' : '#122540';
  const zeroC  = light ? '#c0d0e0' : '#1a3a5c';
  const fontC  = light ? '#3a6080' : '#8aacbf';
  const plotBg = light ? '#f8fafc' : '#071520';
  const l = {{
    paper_bgcolor:'transparent', plot_bgcolor:plotBg,
    margin:{{l:52,r:14,t:6,b:56}},
    font:{{color:fontC,size:11}},
    xaxis:{{title:{{text:xt,font:{{size:10}}}},gridcolor:gridC,
            linecolor:zeroC,zerolinecolor:zeroC,tickfont:{{size:10}}}},
    yaxis:{{title:{{text:yt,font:{{size:10}}}},gridcolor:gridC,
            linecolor:zeroC,zerolinecolor:zeroC,tickfont:{{size:10}}}},
    legend:{{bgcolor:'transparent',font:{{size:10}}}},
    showlegend:false,
  }};
  if (y2t) {{
    l.yaxis2 = {{title:{{text:y2t,font:{{size:10}}}},overlaying:'y',side:'right',
                gridcolor:gridC,zerolinecolor:zeroC,tickfont:{{size:10}}}};
    l.showlegend = true;
  }}
  return l;
}}

// ── Slider init ───────────────────────────────────────────────────────────
function initSliders() {{
  for (const [k, v] of Object.entries(DEFS)) {{
    const el = document.getElementById('s-' + k);
    if (el) el.value = v;
  }}
}}

function T(k) {{
  const el = document.getElementById('s-' + k);
  return el ? parseFloat(el.value) : DEFS[k];
}}

function refreshLabels() {{
  const set = (k, dec, unit) => {{
    const v = document.getElementById('v-'+k);
    const s = document.getElementById('s-'+k);
    if (v && s) v.textContent = parseFloat(s.value).toFixed(dec) + unit;
  }};
  set('genmw',1,' MW');    set('genpct',2,'%');
  set('genmvar',1,' MVar'); set('genqpct',2,'%');
  set('vtsw',3,' pu');     set('freqband',3,' Hz');
  set('freqsw',3,' Hz');   set('anglesw',1,'°');
  set('linemw',0,' MW');   set('linepct',0,'%');
  set('vhi',3,' pu');      set('vlo',3,' pu');   set('vsw',3,' pu');
}}

// ── Numeric helpers ───────────────────────────────────────────────────────
const nv  = (r, k) => {{ const x = parseFloat(r[k]); return isNaN(x) ? 0 : x; }};
const pct = (r, num, base) => nv(r,base) > 0 ? nv(r,num)/nv(r,base)*100 : 0;
const cnt = (arr, fn) => arr.filter(fn).length;
const maxOf = (arr, k) => arr.length ? Math.max(...arr.map(r=>nv(r,k))) : 0;

function fmt(x, d=2) {{
  if (x===null||x===undefined) return '–';
  const f = parseFloat(x); if (isNaN(f)) return x;
  return f.toFixed(d);
}}

function hiClass(val, thresh, inverse=false) {{
  if (val===null||val===undefined) return '';
  return (inverse ? val < thresh : val > thresh) ? 'hi' : 'okc';
}}

// ── KPI summary ───────────────────────────────────────────────────────────
function drawKPIs() {{
  const tGM=T('genmw'),tGP=T('genpct'),tGV=T('genmvar'),tGQ=T('genqpct');
  const tVT=T('vtsw'),tFB=T('freqband'),tFS=T('freqsw'),tAS=T('anglesw');
  const tLM=T('linemw'),tLP=T('linepct');
  const tVH=T('vhi'),tVL=T('vlo'),tVS=T('vsw');

  // Highest observed values
  const maxGenP  = maxOf(GEN,  'pg_swing');
  const maxGenQ  = maxOf(GEN,  'qg_swing');
  const maxLineP = maxOf(LINE, 'pbr_swing');
  const maxLineQ = maxOf(LINE, 'qbr_swing');

  // Top generator names
  const topGenP  = GEN.length  ? ([...GEN ].sort((a,b)=>nv(b,'pg_swing') -nv(a,'pg_swing') )[0].NAME||'—') : '—';
  const topGenQ  = GEN.length  ? ([...GEN ].sort((a,b)=>nv(b,'qg_swing') -nv(a,'qg_swing') )[0].NAME||'—') : '—';
  const topLineP = LINE.length ? ([...LINE].sort((a,b)=>nv(b,'pbr_swing')-nv(a,'pbr_swing'))[0]||{{}}) : {{}};
  const topLinePLbl = topLineP.from_bus ? `${{topLineP.from_bus}}→${{topLineP.to_bus}}` : '—';
  const topLineQ = LINE.length ? ([...LINE].sort((a,b)=>nv(b,'qbr_swing')-nv(a,'qbr_swing'))[0]||{{}}) : {{}};
  const topLineQLbl = topLineQ.from_bus ? `${{topLineQ.from_bus}}→${{topLineQ.to_bus}}` : '—';

  // Nested group renderer
  const renderGroup = (g) => {{
    const renderItems = (items) => items.map(k => {{
      const cls = k.cls || (typeof k.v==='number' ? (k.v>0?'warn':'ok') : 'info');
      return `<div class="kitem">
        <div class="klbl">${{k.l}}</div>
        <div class="kval ${{cls}}">${{typeof k.v==='number'&&!Number.isInteger(k.v) ? k.v.toFixed(2) : k.v}}</div>
      </div>`;
    }}).join('');

    if (g.subgroups) {{
      const subs = g.subgroups.map(sg => `
        <div class="ksubgroup">
          <div class="ksubgroup-hdr">${{sg.title}}</div>
          <div class="kgroup-items">${{renderItems(sg.items)}}</div>
        </div>`).join('');
      return `<div class="kgroup">
        <div class="kgroup-hdr">${{g.title}}</div>
        ${{subs}}
      </div>`;
    }}
    return `<div class="kgroup">
      <div class="kgroup-hdr">${{g.title}}</div>
      <div class="kgroup-items">${{renderItems(g.items)}}</div>
    </div>`;
  }};

  const groups = [
    {{
      title: 'Generator',
      subgroups: [
        {{
          title: 'Active Power',
          items: [
            {{l:`# P swing &gt; ${{tGM.toFixed(1)}} MW`,            v: cnt(GEN, r=>nv(r,'pg_swing')>tGM)}},
            {{l:`# P swing &gt; ${{tGP.toFixed(2)}}% Mbase`,        v: cnt(GEN, r=>pct(r,'pg_swing','MBASE_MVA')>tGP)}},
            {{l:'# P<sub>max</sub> violations',                      v: cnt(GEN, r=>nv(r,'pg_max')>nv(r,'PMAX_MW'))}},
            {{l:'# P<sub>min</sub> violations',                      v: cnt(GEN, r=>nv(r,'pg_min')<nv(r,'PMIN_MW'))}},
            {{l:`Highest P swing observed`,                          v: maxGenP.toFixed(2)+' MW', cls:'info'}},
            {{l:`At generator`,                                      v: topGenP,                  cls:'info'}},
          ]
        }},
        {{
          title: 'Reactive Power',
          items: [
            {{l:`# Q swing &gt; ${{tGV.toFixed(1)}} MVar`,          v: cnt(GEN, r=>nv(r,'qg_swing')>tGV)}},
            {{l:`# Q swing &gt; ${{tGQ.toFixed(2)}}% Mbase`,        v: cnt(GEN, r=>pct(r,'qg_swing','MBASE_MVA')>tGQ)}},
            {{l:'# Q<sub>max</sub> violations',                      v: cnt(GEN, r=>nv(r,'qg_max')>nv(r,'QMAX_MVAR'))}},
            {{l:'# Q<sub>min</sub> violations',                      v: cnt(GEN, r=>nv(r,'qg_min')<nv(r,'QMIN_MVAR'))}},
            {{l:`Highest Q swing observed`,                          v: maxGenQ.toFixed(2)+' MVar', cls:'info'}},
            {{l:`At generator`,                                      v: topGenQ,                    cls:'info'}},
          ]
        }},
        {{
          title: 'Dynamics',
          items: [
            {{l:`# V<sub>t</sub> swing &gt; ${{tVT.toFixed(3)}} pu`, v: cnt(GEN, r=>nv(r,'vt_swing')>tVT)}},
            {{l:`# Freq outside ±${{tFB.toFixed(3)}} Hz`,            v: cnt(GEN, r=>nv(r,'freq_swing')/2>tFB)}},
            {{l:`# Freq swing &gt; ${{tFS.toFixed(3)}} Hz`,           v: cnt(GEN, r=>nv(r,'freq_swing')>tFS)}},
            {{l:`# Angle swing &gt; ${{tAS.toFixed(1)}}°`,            v: cnt(GEN, r=>nv(r,'angle_swing')>tAS)}},
          ]
        }},
      ]
    }},
    {{
      title: 'Lines',
      items: [
        {{l:`# P swing &gt; ${{tLM.toFixed(0)}} MW`,                v: cnt(LINE, r=>nv(r,'pbr_swing')>tLM)}},
        {{l:`# P swing &gt; ${{tLP.toFixed(0)}}% rating`,            v: cnt(LINE, r=>pct(r,'pbr_swing','RATE_A_MVA')>tLP)}},
        {{l:`Highest P swing observed`,                              v: maxLineP.toFixed(2)+' MW',   cls:'info'}},
        {{l:`On line`,                                               v: topLinePLbl,                 cls:'info'}},
        {{l:`Highest Q swing observed`,                              v: maxLineQ.toFixed(2)+' MVar', cls:'info'}},
        {{l:`On line`,                                               v: topLineQLbl,                 cls:'info'}},
      ]
    }},
    {{
      title: 'HV Buses',
      items: [
        {{l:`# V outside ${{tVL.toFixed(2)}}–${{tVH.toFixed(2)}} pu`, v: cnt(BUS, r=>nv(r,'v_min')<tVL||nv(r,'v_max')>tVH)}},
        {{l:`# V swing &gt; ${{tVS.toFixed(3)}} pu`,                  v: cnt(BUS, r=>nv(r,'v_swing')>tVS)}},
      ]
    }},
  ];

  document.getElementById('kgrid').innerHTML = groups.map(renderGroup).join('');
}}

// ── Generator histograms ──────────────────────────────────────────────────
function drawGenHists() {{
  if (!GEN.length) return;
  const hist = (id, vals, col, thresh, xlabel) => Plotly.react(id, [
    {{x:vals, type:'histogram', nbinsx:40, marker:{{color:col,opacity:0.85}}}},
    {{x:[thresh,thresh], y:[0, vals.length/4||10], type:'scatter', mode:'lines',
      line:{{color:'#e8623a',dash:'dash',width:1.5}}}},
  ], lay(xlabel||'','Count'), CFG);

  hist('gen-p-hist',    GEN.map(r=>nv(r,'pg_swing')),    '#2080c0', T('genmw'),   'P swing amplitude (MW)');
  hist('gen-q-hist',    GEN.map(r=>nv(r,'qg_swing')),    '#9060d0', T('genmvar'), 'Q swing amplitude (MVar)');
  hist('gen-freq-hist', GEN.map(r=>nv(r,'freq_swing')),  '#e89030', T('freqsw'),  'Freq swing amplitude (Hz)');
  hist('gen-angle-hist',GEN.map(r=>nv(r,'angle_swing')), '#e06858', T('anglesw'), 'Angle swing amplitude (°)');

  // ── Top 30 by swing amplitude ─────────────────────────────────────────
  const tGM2 = T('genmw'), tGV2 = T('genmvar');
  const topP = [...GEN].sort((a,b)=>nv(b,'pg_swing')-nv(a,'pg_swing')).slice(0,30);
  const topQ = [...GEN].sort((a,b)=>nv(b,'qg_swing')-nv(a,'qg_swing')).slice(0,30);

  const barTop = (id, rows, field, thresh, color, colorOver) => {{
    const labels = rows.map(r => r.NAME || String(r.bus_num));
    const vals   = rows.map(r => nv(r, field));
    const cols   = vals.map(v => v > thresh ? colorOver : color);
    const l = lay('', field==='pg_swing' ? 'P swing (MW)' : 'Q swing (MVar)');
    l.xaxis.tickangle = -45; l.xaxis.tickfont = {{size:9}};
    l.shapes = [{{type:'line',xref:'paper',x0:0,x1:1,yref:'y',y0:thresh,y1:thresh,
      line:{{color:colorOver,width:1.5,dash:'dash'}}}}];
    Plotly.react(id, [{{x:labels, y:vals, type:'bar', marker:{{color:cols}}}}], l, CFG);
  }};
  barTop('gen-top-p', topP, 'pg_swing', tGM2, '#2080c0', '#e8623a');
  barTop('gen-top-q', topQ, 'qg_swing', tGV2, '#9060d0', '#e8623a');
}}

// ── Generator table ───────────────────────────────────────────────────────
function drawGenTable() {{
  const wrap = document.getElementById('gen-tbl'); if (!GEN.length) return;

  const sorted = [...GEN].sort((a,b) =>
    genSortAsc ? nv(a,genSortCol)-nv(b,genSortCol) : nv(b,genSortCol)-nv(a,genSortCol));

  const th = (k, label) => {{
    const arrow = genSortCol===k ? (genSortAsc?' \u25b2':' \u25bc') : '';
    return `<th onclick="sortGen('${{k}}')">${{label}}${{arrow}}</th>`;
  }};

  const tGM=T('genmw'), tGV=T('genmvar'), tFS=T('freqsw'), tAS=T('anglesw'), tVT=T('vtsw');

  const hdr = `<tr>
    ${{th('NAME','Bus Name')}}
    ${{th('bus_num','Bus #')}}
    <th>Area</th><th>Zone</th>
    <th>Mbase (MVA)</th>
    ${{th('pg_init','P<sub>init</sub> (MW)')}}
    ${{th('qg_init','Q<sub>init</sub> (MVar)')}}
    ${{th('pg_swing','P swing (MW)')}}
    ${{th('qg_swing','Q swing (MVar)')}}
    ${{th('vt_swing','V<sub>t</sub> swing (pu)')}}
    ${{th('freq_swing','Freq swing (Hz)')}}
    ${{th('angle_swing','Angle swing (\u00b0)')}}
  </tr>`;

  const icBadge = '<span style="font-size:0.6rem;background:#5a1a0a;color:#e8823a;border-radius:2px;padding:1px 4px;margin-left:4px" title="Initial condition violation">IC</span>';

  const bodyRows = sorted.map(r => {{
    const pViol    = nv(r,'pg_max')>nv(r,'PMAX_MW') || nv(r,'pg_min')<nv(r,'PMIN_MW');
    const qmaxV    = nv(r,'qg_max')>nv(r,'QMAX_MVAR');
    const qminV    = nv(r,'qg_min')<nv(r,'QMIN_MVAR');
    const pInitViol = nv(r,'pg_init')>nv(r,'PMAX_MW') || nv(r,'pg_init')<nv(r,'PMIN_MW');
    const qInitMaxV = nv(r,'qg_init')>nv(r,'QMAX_MVAR');
    const qInitMinV = nv(r,'qg_init')<nv(r,'QMIN_MVAR');
    return `<tr>
      <td>${{r.NAME||'\u2013'}}</td>
      <td>${{r.bus_num}}</td>
      <td>${{r.AREA||'\u2013'}}</td><td>${{r.ZONE||'\u2013'}}</td>
      <td>${{fmt(r.MBASE_MVA,1)}}</td>
      <td class="${{pInitViol?'hi':''}}">${{fmt(r.pg_init,2)}}${{pInitViol?icBadge:''}}</td>
      <td class="${{(qInitMaxV||qInitMinV)?'hi':''}}">${{fmt(r.qg_init,2)}}${{(qInitMaxV||qInitMinV)?icBadge:''}}</td>
      <td class="${{nv(r,'pg_swing')>tGM?'hi':''}}">${{fmt(r.pg_swing,2)}}</td>
      <td class="${{nv(r,'qg_swing')>tGV?'hi':''}}">${{fmt(r.qg_swing,2)}}</td>
      <td class="${{nv(r,'vt_swing')>tVT?'hi':''}}">${{fmt(r.vt_swing,4)}}</td>
      <td class="${{nv(r,'freq_swing')>tFS?'hi':''}}">${{fmt(r.freq_swing,4)}}</td>
      <td class="${{nv(r,'angle_swing')>tAS?'hi':''}}">${{fmt(r.angle_swing,2)}}</td>
    </tr>`;
  }}).join('');

  wrap.innerHTML = `<table><thead>${{hdr}}</thead><tbody>${{bodyRows}}</tbody></table>`;
}}

function setGenView(v) {{ drawGenTable(); }}

function sortGen(col) {{
  if (genSortCol===col) genSortAsc=!genSortAsc; else {{ genSortCol=col; genSortAsc=false; }}
  drawGenTable();
}}

// ── Line charts ───────────────────────────────────────────────────────────
function drawLineCharts() {{
  if (!LINE.length) return;
  const tLM = T('linemw');

  Plotly.react('line-hist', [
    {{x:LINE.map(r=>nv(r,'pbr_swing')), type:'histogram', nbinsx:40, marker:{{color:'#20a090',opacity:0.85}}}},
    {{x:[tLM,tLM], y:[0,LINE.length/4||10], type:'scatter', mode:'lines', line:{{color:'#e8623a',dash:'dash',width:1.5}}}},
  ], lay('P swing (MW)','Count'), CFG);

  const top = [...LINE].sort((a,b)=>nv(b,'pbr_swing')-nv(a,'pbr_swing')).slice(0,30);
  const labels = top.map(r => `${{r.from_bus||'?'}}→${{r.to_bus||'?'}}`);
  const vals   = top.map(r => nv(r,'pbr_swing'));
  const colors = vals.map(v => v>tLM ? '#e8623a' : '#20a090');
  const tl = lay('','P swing (MW)');
  tl.xaxis.tickangle = -45; tl.xaxis.tickfont = {{size:9}};
  Plotly.react('line-top', [{{x:labels,y:vals,type:'bar',marker:{{color:colors}}}}], tl, CFG);
}}

// ── Parallel circuits — split into flows panel and swings panel ───────────
function drawParallel() {{
  if (!LINE.length) return;
  const par    = LINE.filter(r => nv(r,'is_parallel')===1 || r.is_parallel===true || r.is_parallel==='1');
  const tLM    = T('linemw');
  const noteEl = document.getElementById('par-note');

  const empty = (id) => Plotly.react(id, [], lay('',''), CFG);

  if (!par.length) {{
    noteEl.textContent = '— none detected';
    document.getElementById('par-chips').innerHTML = '';
    ['par-flows-circuit','par-flows-pair','par-swings-circuit','par-swings-pair'].forEach(empty);
    return;
  }}

  // Group by bus pair
  const grouped = {{}};
  par.forEach(r => {{
    const k = `${{r.from_bus||'?'}}→${{r.to_bus||'?'}}`;
    if (!grouped[k]) grouped[k] = [];
    grouped[k].push(r);
  }});
  const pairKeys = Object.keys(grouped);
  const nPairs   = pairKeys.length;
  noteEl.textContent = `— ${{par.length}} circuits across ${{nPairs}} bus pairs`;

  // ── Single base colour; circuit slots distinguished by opacity ───────────
  // Multi-ckt pairs show clearly in stacked charts: ckt1=full, ckt2=mid, ckt3=light
  const BASE_FLOW  = '#4a9fd4';   // blue for flows
  const BASE_SWING = '#20a090';   // teal for swings
  // Opacity steps per circuit slot (up to 5 deep)
  const CKT_OPAC = [0.90, 0.55, 0.75, 0.40, 0.65];

  // ── Find maximum circuit count across all pairs ───────────────────────
  const maxCkts = Math.max(...pairKeys.map(k => grouped[k].length));

  // ── Panel 1: Flows — one trace per circuit-index slot ────────────────
  const pairKeysByInit = [...pairKeys].sort((a,b)=>
    grouped[b].reduce((s,r)=>s+nv(r,'pbr_init'),0) -
    grouped[a].reduce((s,r)=>s+nv(r,'pbr_init'),0));

  const flowTraces = [];
  for (let ci = 0; ci < maxCkts; ci++) {{
    const xs = [], ys = [];
    pairKeysByInit.forEach(pair => {{
      const ckts = grouped[pair];
      if (ckts[ci] !== undefined) {{
        xs.push(pair);
        ys.push(nv(ckts[ci],'pbr_init'));
      }}
    }});
    if (xs.length) flowTraces.push({{
      name: `Circuit ${{ci+1}}`, x:xs, y:ys, type:'bar',
      marker:{{color:BASE_FLOW, opacity: CKT_OPAC[ci] ?? 0.5}},
      text: xs.map((_,i) => `Ckt ${{ci+1}}: ${{ys[i].toFixed(1)}} MW`),
      hovertemplate:'%{{x}}<br>%{{text}}<extra></extra>',
    }});
  }}
  const lFlowPair = lay('','P init (MW)');
  lFlowPair.barmode = 'stack';
  lFlowPair.xaxis.tickangle=-35; lFlowPair.xaxis.tickfont={{size:9}};
  lFlowPair.showlegend = maxCkts > 1;
  lFlowPair.annotations = pairKeysByInit.map((k)=>{{
    const tot = grouped[k].reduce((s,r)=>s+nv(r,'pbr_init'),0);
    return {{x:k,y:tot,text:`${{grouped[k].length}}ckt`,showarrow:false,
             yanchor:'bottom',font:{{size:9,color:'#7aacbf'}}}};
  }});
  Plotly.react('par-flows-pair', flowTraces, lFlowPair, CFG);

  // Circuit-level flow bars — all same colour; multi-ckt pairs get
  // alternating opacity so adjacent bars from the same pair stand apart
  const sortedBySwing = [...par].sort((a,b)=>nv(b,'pbr_swing')-nv(a,'pbr_swing'));
  const circLbls  = sortedBySwing.map(r=>`${{r.from_bus}}→${{r.to_bus}}`);
  const circPairs = sortedBySwing.map(r=>`${{r.from_bus||'?'}}→${{r.to_bus||'?'}}`);
  const inits     = sortedBySwing.map(r=>nv(r,'pbr_init'));
  const swings    = sortedBySwing.map(r=>nv(r,'pbr_swing'));

  // Track how many times we've seen each pair to assign circuit index
  const _seenFlow = {{}};
  const flowOpac = circPairs.map(p => {{
    _seenFlow[p] = (_seenFlow[p] ?? -1) + 1;
    return CKT_OPAC[_seenFlow[p]] ?? 0.5;
  }});

  const lFlowCkt = lay('','P init (MW)');
  lFlowCkt.xaxis.tickangle=-40; lFlowCkt.xaxis.tickfont={{size:9}};
  lFlowCkt.showlegend = false;
  Plotly.react('par-flows-circuit', [
    {{x:circLbls, y:inits, type:'bar',
      marker:{{color:BASE_FLOW, opacity:flowOpac}},
      hovertemplate:'%{{x}}<br>P init: %{{y:.1f}} MW<extra></extra>'}},
  ], lFlowCkt, CFG);

  // ── Panel 2: Swings — stacked per circuit index ───────────────────────
  const pairKeysBySwing = [...pairKeys].sort((a,b)=>
    grouped[b].reduce((s,r)=>s+nv(r,'pbr_swing'),0) -
    grouped[a].reduce((s,r)=>s+nv(r,'pbr_swing'),0));

  const swingTraces = [];
  for (let ci = 0; ci < maxCkts; ci++) {{
    const xs = [], ys = [];
    pairKeysBySwing.forEach(pair => {{
      const ckts = grouped[pair];
      if (ckts[ci] !== undefined) {{
        xs.push(pair);
        ys.push(nv(ckts[ci],'pbr_swing'));
      }}
    }});
    if (xs.length) swingTraces.push({{
      name:`Circuit ${{ci+1}}`, x:xs, y:ys, type:'bar',
      marker:{{color:BASE_SWING, opacity: CKT_OPAC[ci] ?? 0.5}},
      text: xs.map((_,i) => `Ckt ${{ci+1}}: ${{ys[i].toFixed(1)}} MW`),
      hovertemplate:'%{{x}}<br>%{{text}}<extra></extra>',
    }});
  }}
  const lSwingPair = lay('','P swing (MW)');
  lSwingPair.barmode = 'stack';
  lSwingPair.xaxis.tickangle=-35; lSwingPair.xaxis.tickfont={{size:9}};
  lSwingPair.showlegend = maxCkts > 1;
  lSwingPair.shapes = [{{type:'line',xref:'paper',x0:0,x1:1,yref:'y',
    y0:tLM,y1:tLM,line:{{color:'#e8623a',dash:'dash',width:1.5}}}}];
  lSwingPair.annotations = pairKeysBySwing.map((k)=>{{
    const tot = grouped[k].reduce((s,r)=>s+nv(r,'pbr_swing'),0);
    return {{x:k,y:tot,text:`${{grouped[k].length}}ckt`,showarrow:false,
             yanchor:'bottom',font:{{size:9,color:'#7aacbf'}}}};
  }});
  Plotly.react('par-swings-pair', swingTraces, lSwingPair, CFG);

  // Circuit-level swing bars — threshold violations red, others teal with
  // alternating opacity to distinguish multi-ckt pairs
  const _seenSwing = {{}};
  const swingOpac = circPairs.map(p => {{
    _seenSwing[p] = (_seenSwing[p] ?? -1) + 1;
    return CKT_OPAC[_seenSwing[p]] ?? 0.5;
  }});
  const swCols = swings.map(v => v > tLM ? '#e8623a' : BASE_SWING);

  const lSwingCkt = lay('','P swing (MW)');
  lSwingCkt.xaxis.tickangle=-40; lSwingCkt.xaxis.tickfont={{size:9}};
  lSwingCkt.showlegend = false;
  Plotly.react('par-swings-circuit', [
    {{x:circLbls, y:swings, type:'bar',
      marker:{{color:swCols, opacity:swingOpac}},
      hovertemplate:'%{{x}}<br>P swing: %{{y:.1f}} MW<extra></extra>'}},
    {{x:circLbls, y:circLbls.map(()=>tLM), type:'scatter', mode:'lines',
      line:{{color:'#e8623a',dash:'dash',width:1.5}}, showlegend:false, hoverinfo:'skip'}},
  ], lSwingCkt, CFG);

  // ── Summary chips ─────────────────────────────────────────────────────
  document.getElementById('par-chips').innerHTML = pairKeysBySwing.map(pair => {{
    const ckts     = grouped[pair];
    const n        = ckts.length;
    const sumInit  = ckts.reduce((s,r)=>s+nv(r,'pbr_init'),0);
    const sumSwing = ckts.reduce((s,r)=>s+nv(r,'pbr_swing'),0);
    const maxSwing = Math.max(...ckts.map(r=>nv(r,'pbr_swing')));
    const multiTag = n > 1 ? `<span style="font-size:0.6rem;background:#1a3a5c;color:#7aacbf;border-radius:2px;padding:1px 5px;margin-left:2px">${{n}} ckts</span>` : '';
    return `<div class="pchip">
      <span class="pkey">${{pair}}</span>${{multiTag}}
      <span class="pfl">Σ P<sub>init</sub>=${{sumInit.toFixed(1)}} MW</span>
      <span class="pfl">Σ swing=${{sumSwing.toFixed(1)}} MW</span>
      <span class="pfl">max ckt=${{maxSwing.toFixed(1)}} MW</span>
    </div>`;
  }}).join('');
}}

// ── HV Bus charts ─────────────────────────────────────────────────────────
function drawBusCharts() {{
  if (!BUS.length) return;
  const tVS=T('vsw'), tVH=T('vhi'), tVL=T('vlo');

  const sorted = [...BUS].sort((a,b)=>nv(b,'v_swing')-nv(a,'v_swing')).slice(0,50);
  const labels = sorted.map(r => String(r.NAME||r.bus_num));
  const swings = sorted.map(r => nv(r,'v_swing'));
  const cols   = swings.map(v => v>tVS ? '#e8623a' : '#40b878');
  const tl = lay('','V swing (pu)'); tl.xaxis.tickangle=-45; tl.xaxis.tickfont={{size:9}};
  Plotly.react('bus-swing', [
    {{x:labels,y:swings,type:'bar',marker:{{color:cols}}}},
    {{x:labels,y:labels.map(()=>tVS),type:'scatter',mode:'lines',line:{{color:'#e8623a',dash:'dash',width:1.5}}}},
  ], tl, CFG);

  const vmin = sorted.map(r=>nv(r,'v_min')), vmax = sorted.map(r=>nv(r,'v_max'));
  const te = lay('','Voltage (pu)'); te.xaxis.tickangle=-45; te.xaxis.tickfont={{size:9}};
  te.shapes = [
    {{type:'line',xref:'paper',x0:0,x1:1,yref:'y',y0:tVH,y1:tVH,
      line:{{color:'#e8623a',width:1,dash:'dash'}}}},
    {{type:'line',xref:'paper',x0:0,x1:1,yref:'y',y0:tVL,y1:tVL,
      line:{{color:'#e8623a',width:1,dash:'dash'}}}},
  ];
  te.showlegend = true;
  Plotly.react('bus-venv', [
    {{x:labels,y:vmax,type:'scatter',mode:'markers',name:'V max',
      marker:{{color:'#e89030',size:5,symbol:'triangle-up'}}}},
    {{x:labels,y:vmin,type:'scatter',mode:'markers',name:'V min',
      marker:{{color:'#4a9fd4',size:5,symbol:'triangle-down'}}}},
  ], te, CFG);
}}

// ── Time series ───────────────────────────────────────────────────────────
function drawTimeSeries() {{
  if (!TS || !Object.keys(TS).length) return;

  const linePlot = (id, t, traces, layout) => Plotly.react(id, traces, layout, CFG);

  // Generator
  const g = TS.gen;
  if (g) {{
    ['ts-lbl-gen','ts-lbl-gen2','ts-lbl-gen3'].forEach(id => {{
      const el=document.getElementById(id); if(el) el.textContent=g.label||'';
    }});
    const lpq = lay('Time (s)','P (MW)','Q (MVar)'); lpq.showlegend=true;
    linePlot('ts-gen-pq', null, [
      {{x:g.t,y:g.pg,name:'P (MW)',mode:'lines',line:{{color:'#2080c0',width:1.5}},yaxis:'y'}},
      {{x:g.t,y:g.qg,name:'Q (MVar)',mode:'lines',line:{{color:'#9060d0',width:1.5}},yaxis:'y2'}},
    ], lpq);
    const lvf = lay('Time (s)','Vt (pu)','Freq (Hz)'); lvf.showlegend=true;
    linePlot('ts-gen-vf', null, [
      {{x:g.t,y:g.vt,name:'Vt (pu)',mode:'lines',line:{{color:'#40c898',width:1.5}},yaxis:'y'}},
      {{x:g.t,y:g.freq,name:'Freq (Hz)',mode:'lines',line:{{color:'#e89030',width:1.5}},yaxis:'y2'}},
    ], lvf);
    linePlot('ts-gen-ang', null, [
      {{x:g.t,y:g.abus,name:'Angle (°)',mode:'lines',line:{{color:'#e06858',width:1.5}}}},
    ], lay('Time (s)','Angle (°)'));
  }}

  // Line — P and Q on dual axis
  const l = TS.line;
  if (l) {{
    const el=document.getElementById('ts-lbl-line'); if(el) el.textContent=l.label||'';
    const lln = lay('Time (s)','P flow (MW)', l.qbr ? 'Q flow (MVar)' : undefined);
    const traces = [
      {{x:l.t,y:l.pbr,name:'P flow (MW)',mode:'lines',line:{{color:'#20a090',width:1.5}},yaxis:'y'}},
    ];
    if (l.qbr) traces.push(
      {{x:l.t,y:l.qbr,name:'Q flow (MVar)',mode:'lines',line:{{color:'#a070e0',width:1.5}},yaxis:'y2'}}
    );
    linePlot('ts-line', null, traces, lln);
  }}

  // Bus
  const b = TS.bus;
  if (b) {{
    const el=document.getElementById('ts-lbl-bus'); if(el) el.textContent=b.label||'';
    const lbv = lay('Time (s)','V (pu)','Angle (°)'); lbv.showlegend=true;
    linePlot('ts-bus', null, [
      {{x:b.t,y:b.vbus,name:'V (pu)',mode:'lines',line:{{color:'#40b878',width:1.5}},yaxis:'y'}},
      {{x:b.t,y:b.abus,name:'Angle (°)',mode:'lines',line:{{color:'#a070e0',width:1.5}},yaxis:'y2'}},
    ], lbv);
  }}
}}

// ── LDDL time series ──────────────────────────────────────────────────────
function drawLDDL() {{
  const lddl = TS.lddl;
  if (!lddl || !lddl.t) return;

  const t = lddl.t;

  // ── Active power: P and OS P ──────────────────────────────────────────
  const hasP   = Array.isArray(lddl.P);
  const hasOSP = Array.isArray(lddl.OS_P);
  if (hasP || hasOSP) {{
    const tracesP = [];
    if (hasP)   tracesP.push({{x:t,y:lddl.P,   name:'LDDL P (MW)',   mode:'lines',line:{{color:'#d4a017',width:1.8}}}});
    if (hasOSP) tracesP.push({{x:t,y:lddl.OS_P,name:'LDDL OS P (MW)',mode:'lines',line:{{color:'#e86030',width:1.5,dash:'dash'}}}});
    const lp = lay('Time (s)','MW'); lp.showlegend=true;
    Plotly.react('lddl-p', tracesP, lp, CFG);
  }}

  // ── Reactive power: Q and OS Q ────────────────────────────────────────
  const hasQ   = Array.isArray(lddl.Q);
  const hasOSQ = Array.isArray(lddl.OS_Q);
  if (hasQ || hasOSQ) {{
    const tracesQ = [];
    if (hasQ)   tracesQ.push({{x:t,y:lddl.Q,   name:'LDDL Q (MVar)',   mode:'lines',line:{{color:'#6090d0',width:1.8}}}});
    if (hasOSQ) tracesQ.push({{x:t,y:lddl.OS_Q,name:'LDDL OS Q (MVar)',mode:'lines',line:{{color:'#a050c0',width:1.5,dash:'dash'}}}});
    const lq = lay('Time (s)','MVar'); lq.showlegend=true;
    Plotly.react('lddl-q', tracesQ, lq, CFG);
  }}

  // ── Bus voltage ───────────────────────────────────────────────────────
  const hasV = Array.isArray(lddl.BUS_VOLTAGE);
  if (hasV) {{
    Plotly.react('lddl-v', [
      {{x:t,y:lddl.BUS_VOLTAGE,name:'LDDL Bus V (pu)',mode:'lines',
        line:{{color:'#40c898',width:1.8}}}},
    ], lay('Time (s)','Voltage (pu)'), CFG);
  }}
}}

// ── Main update (called by all sliders) ───────────────────────────────────
function update() {{
  refreshLabels();
  drawKPIs();
  drawGenHists();
  drawGenTable();
  drawLineCharts();
  drawParallel();
  drawBusCharts();
}}

// ── Collapsible sections ──────────────────────────────────────────────────
function toggleSec(hdrId, bodyId) {{
  const body = document.getElementById(bodyId);
  const hdr  = document.getElementById(hdrId);
  if (!body) return;
  const collapsed = body.classList.toggle('hidden');
  // Update the arrow glyph on the section header
  const btn = hdr ? hdr.querySelector('.collapse-btn') : null;
  if (btn) btn.textContent = collapsed ? '+' : '–';
  // Update triangle on sec-hdr text node (first text node)
  if (hdr) {{
    const tn = [...hdr.childNodes].find(n=>n.nodeType===3&&n.textContent.trim());
    if (tn) tn.textContent = tn.textContent.replace(/[▼▶]/,'').replace(/^\s*/,
      (collapsed ? '▶ ' : '▼ '));
  }}
  // Reflow plots if expanding
  if (!collapsed) setTimeout(()=>document.querySelectorAll('.plt,.plt-sm,.plt-xs').forEach(el=>{{
    if (el.data||el.layout) Plotly.Plots.resize(el);
  }}),80);
}}

// Wire all sec-hdr elements that don't already have onclick
document.querySelectorAll('.sec-hdr').forEach(hdr => {{
  if (!hdr.id) return;
  const bodyId = hdr.id.replace('sec-','body-');
  if (!hdr.getAttribute('onclick')) {{
    hdr.addEventListener('click', () => toggleSec(hdr.id, bodyId));
  }}
}});

// ── Dark/light mode ──────────────────────────────────────────────────────
function toggleMode() {{
  const isLight = document.body.classList.toggle('light');
  document.getElementById('mode-btn').textContent = isLight ? '🌙 Dark Mode' : '☀ Light Mode';
  update(); drawTimeSeries(); drawLDDL();
}}

// ── Resizable plots (drag bottom edge to resize height) ───────────────────
const _ro = new ResizeObserver(entries => {{
  for (const entry of entries) {{
    const el = entry.target;
    if (el._rrDebounce) clearTimeout(el._rrDebounce);
    el._rrDebounce = setTimeout(() => {{
      if (el.data || el.layout) Plotly.Plots.resize(el);
    }}, 60);
  }}
}});
document.querySelectorAll('.plt,.plt-sm,.plt-xs').forEach(el => _ro.observe(el));

// ── Resizable sidebar (drag right edge) ───────────────────────────────────
(function() {{
  const sidebarEl = document.getElementById('sidebar');
  const resizerEl = document.getElementById('sidebar-resizer');
  if (!sidebarEl || !resizerEl) return;
  let _x0 = 0, _w0 = 0, _dragging = false;

  resizerEl.addEventListener('mousedown', e => {{
    _dragging = true; _x0 = e.clientX; _w0 = sidebarEl.offsetWidth;
    resizerEl.classList.add('dragging');
    document.body.style.cursor = 'col-resize';
    document.body.style.userSelect = 'none';
    e.preventDefault();
  }});
  document.addEventListener('mousemove', e => {{
    if (!_dragging) return;
    const newW = Math.max(160, Math.min(480, _w0 + (e.clientX - _x0)));
    sidebarEl.style.width = newW + 'px';
    sidebarEl.style.minWidth = newW + 'px';
  }});
  document.addEventListener('mouseup', () => {{
    if (!_dragging) return;
    _dragging = false;
    resizerEl.classList.remove('dragging');
    document.body.style.cursor = '';
    document.body.style.userSelect = '';
    // Reflow Plotly charts after sidebar resize
    setTimeout(() => document.querySelectorAll('.plt,.plt-sm,.plt-xs').forEach(el => {{
      if (el.data || el.layout) Plotly.Plots.resize(el);
    }}), 80);
  }});
}})();

// ── Boot ─────────────────────────────────────────────────────────────────
initSliders();
update();
drawTimeSeries();
drawLDDL();
</script>
</body>
</html>"""


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    root = Path.cwd()

    config = pd.read_csv(root / "simulation_config.csv")

    def _cfg(var, cast=str, default=None):
        row = config[config.Variable == var]
        if row.empty:
            return default
        v = row['Value'].iloc[0]
        return default if (str(v).strip().lower() == 'nan' or str(v).strip() == '') else cast(v)

    case_name  = _cfg('case_name',            str)
    bus_number = _cfg('bus_number',            int)
    osc_freq   = _cfg('oscillation_frequency', float)
    osc_amp    = _cfg('oscillation_amplitude', float)

    OUTPUT_DIR = str(root / "results")
    INPUT_DIR  = OUTPUT_DIR

    DASH_SUBTITLE = (f"{case_name}  —  Bus {bus_number}  —  {osc_freq} Hz")

    # Reconstruct run_tag to match Step5 output filenames exactly
    freq_str = str(osc_freq).rstrip('0').rstrip('.')
    amp_str  = str(int(osc_amp)) if osc_amp == int(osc_amp) else str(osc_amp)
    run_tag  = f"bus{bus_number}_{freq_str}Hz_{amp_str}MW"

    HTML_OUT = os.path.join(OUTPUT_DIR, f"risk_visualization_{run_tag}.html")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print(f"Run tag      : {run_tag}")
    print("Loading metric files...")
    data = load_data(INPUT_DIR, run_tag)

    print("Building dashboard HTML...")
    html = build_html(data, DASH_SUBTITLE, THRESHOLDS)

    with open(HTML_OUT, "w", encoding="utf-8") as f:
        f.write(html)

    size_kb = os.path.getsize(HTML_OUT) / 1024
    print(f"\n✓ Dashboard written: {HTML_OUT}  ({size_kb:.0f} KB)")
    print("  Open in any modern browser — no server required.")


if __name__ == "__main__":
    main()