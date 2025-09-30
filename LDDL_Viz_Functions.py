from __future__ import annotations
import re
import numpy as np
import pandas as pd
import matplotlib
# matplotlib.use("TkAgg")                      # always open a GUI window
matplotlib.use("QtAgg")
import matplotlib.pyplot as plt
from matplotlib import cm, colors            # cm & colors both needed
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from cartopy.mpl.ticker import LongitudeFormatter, LatitudeFormatter
import matplotlib as mpl
import os

import matplotlib.lines as mlines
import matplotlib.patches as mpatches

# os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["MPLBACKEND"] = "QtAgg" 
# ───────────────────────────────────────────────────────────────
# 1)  Location & file names
# ───────────────────────────────────────────────────────────────


# DATA_FILE = f"MiniWECC240_SquareWave_load_Var_{location}.csv"
# BUS_FILE  = "MiniWECC_240bus_Buses_Areas_Zones.csv"       # use .xlsx if you want




    
    

def Read_System_Bus_Lat_Long(BUS_FILE):
    CWD = os.getcwd() ## current working directory
    bus_info = pd.read_csv(CWD + '/'+ BUS_FILE)            # or read_excel
    bus_info = bus_info.rename(
        columns=lambda c: (
            c.strip()           # remove leading/trailing blanks
             .replace("  ", "") # drop double-space
             .replace(" ", "")  # drop single space
        )
    )
    # Expect headers BusNumber, BusName, ZoneNum, Latitude, Longitude, … now
    def _clean_numeric(col: pd.Series, negate=False) -> pd.Series:
        ser = (
            col.astype(str)
               .str.replace(r"[^\d.\-]", "", regex=True)
               .astype(float)
        )
        return -ser if negate else ser
    
    bus_info["Lat"] = _clean_numeric(bus_info.iloc[:, 7]) ## cleaned Lat saved in 10th col
    bus_info["Lon"] = _clean_numeric(bus_info.iloc[:, 8], True) ## cleaned Longitude saved in 11th col
    
    return(bus_info)


# ───────────────────────────────────────────────────────────────
# 3)  Read oscillation data & tidy headers
# ───────────────────────────────────────────────────────────────

def Process_LDDL_out_for_Viz(df):
    df.columns = df.columns.str.strip()         # trim trailing blanks
    
    time         = df.iloc[:, 0].to_numpy()
    signal_names = df.columns[1:]               # skip time
    signal_vals  = df.iloc[:, 1:].to_numpy()
    
    
    # masks with whitespace-tolerant regex
    is_line = [bool(re.match(r"POWR\s*\d+\s*TO\s*\d+", n)) for n in signal_names]
    is_gen  = [bool(re.match(r"POWR\s*\d+", n)) and not l
               for n, l in zip(signal_names, is_line)]
    is_load = [bool(re.match(r"PLOD\s*\d+", n)) for n in signal_names]
    
    # tie-line values already in MW
    vals_line  = signal_vals[:, is_line]
    
    # generator & load injections are in per-unit, convert → MW
    vals_gen   = 100 * signal_vals[:, is_gen]
    vals_load  = 100 * signal_vals[:, is_load]
    
    osc_line = vals_line[time > 2].max(0) - vals_line[time > 2].min(0)
    osc_gen  = vals_gen [time > 2].max(0) - vals_gen [time > 2].min(0)
    osc_load = vals_load[time > 2].max(0) - vals_load[time > 2].min(0)
    
    names_line = signal_names[is_line]
    names_gen  = signal_names[is_gen]
    names_load = signal_names[is_load]
    
    # ───────────────────────────────────────────────────────────────
    # 4)  Parse bus numbers (skip if fails → -1)
    # ───────────────────────────────────────────────────────────────
    def _bus(regex: str, txt: str) -> int:
        m = re.search(regex, txt)
        return int(m.group(1)) if m else -1
    
    gen_buses  = np.array([_bus(r"POWR\s*(\d+)", n) for n in names_gen])
    load_buses = np.array([_bus(r"PLOD\s*(\d+)", n) for n in names_load])
    
    # keep only valid generator/load entries
    mask = gen_buses != -1
    gen_buses, osc_gen, names_gen = gen_buses[mask], osc_gen[mask], names_gen[mask]
    
    mask = load_buses != -1
    load_buses, osc_load, names_load = load_buses[mask], osc_load[mask], names_load[mask]
    
    
    return(osc_line, names_line, osc_gen, gen_buses, osc_load, load_buses)


def LDDL_OscAna_Viz(location, MW_THRESHOLD, CMAX , osc_line, names_line, osc_gen, gen_buses, osc_load, load_buses, bus_info, Output_Folder):
    # ───────────────────────────────────────────────────────────────
    # 5)  Figure & map
    # ───────────────────────────────────────────────────────────────
    
    
    cmap = plt.get_cmap("jet", 64)   # modern, no deprecation
    norm = colors.Normalize(vmin=MW_THRESHOLD, vmax=CMAX)
    
    # --- performance settings ---
    mpl.rcParams.update({
        "figure.dpi": 110,
        "path.simplify": True,
        "path.simplify_threshold": 0.5,
        "agg.path.chunksize": 20000,
        "font.size": 8,
    })
    
    # --- figure and axis ---
    fig = plt.figure(figsize=(12, 9))
    
    ax = plt.axes(projection=ccrs.PlateCarree())
    # ax.set_extent([-122, -107, 30, 52], crs=ccrs.PlateCarree())
    ax.set_extent([-125, -106.7, 29.7, 54], crs=ccrs.PlateCarree())
    
    
    ax.add_feature(cfeature.LAND.with_scale("50m"),   facecolor="lightgray") ## 110m for faster, 10m for high quality
    ax.add_feature(cfeature.OCEAN.with_scale("50m"),  facecolor="whitesmoke")
    ax.add_feature(cfeature.BORDERS.with_scale("50m"), linewidth=0.6)
    ax.add_feature(cfeature.STATES.with_scale("50m"),  linewidth=0.4)
    
    
    plt.tight_layout()
    plt.show() # plt.show(block=True)
    # fig.savefig("map.png", dpi=300, bbox_inches="tight")
    
    
    # grid with lat/lon labels
    gl = ax.gridlines(draw_labels=True, linewidth=0.3, color="gray",
                      alpha=0.7, linestyle="--")
    gl.top_labels   = False
    gl.right_labels = False
    gl.xlabel_style = {"size": 8}
    gl.ylabel_style = {"size": 8}
    
    
    
    # ───────────────────────────────────────────────────────────────
    # 6)  Plot tie-lines
    # ───────────────────────────────────────────────────────────────
    for mag, sig in zip(osc_line, names_line):
        if mag <= MW_THRESHOLD:
            continue
        m = re.match(r"POWR\s*(\d+)\s*TO\s*(\d+)", sig)
        if not m:
            continue
        b1, b2 = map(int, m.groups())
        try:
            lat_pair = bus_info.loc[bus_info.BusNumber == b1, "Lat"].iat[0], \
                       bus_info.loc[bus_info.BusNumber == b2, "Lat"].iat[0]
            lon_pair = bus_info.loc[bus_info.BusNumber == b1, "Lon"].iat[0], \
                       bus_info.loc[bus_info.BusNumber == b2, "Lon"].iat[0]
        except IndexError:
            continue
        ax.plot(lon_pair, lat_pair, transform=ccrs.Geodetic(),
                lw=3.5, alpha = 0.8, zorder = 2, c=cmap(norm(min(mag, CMAX))))
        ax.scatter(lon_pair, lat_pair, s=25, c="k", transform=ccrs.Geodetic())
    
    
    
    
    # ───────────────────────────────────────────────────────────────
    # 7)  Plot generators (triangles, labels)
    # ───────────────────────────────────────────────────────────────
    for mag, bus in zip(osc_gen, gen_buses):
        if mag <= MW_THRESHOLD:
            continue
        row = bus_info.loc[bus_info.BusNumber == bus]
        if row.empty:
            continue
        ax.scatter(row.Lon, row.Lat, marker="^", s=500,
                   edgecolors="k", linewidth=0.4, zorder = 3,
                   c=[cmap(norm(min(mag, CMAX)))], transform=ccrs.Geodetic())
        # text label
        ax.text(row.Lon.values[0] + 0.15,
                row.Lat.values[0] + 0.15,
                row.BusName.values[0],
                fontsize=8, weight="bold", transform=ccrs.PlateCarree())
    
    
    # ───────────────────────────────────────────────────────────────
    # 8)  Plot loads (squares)
    # ───────────────────────────────────────────────────────────────
    for mag, bus in zip(osc_load, load_buses):
        if mag <= MW_THRESHOLD:
            continue
        row = bus_info.loc[bus_info.BusNumber == bus]
        if row.empty:
            continue
        ax.scatter(row.Lon, row.Lat, marker="s", s=600,
                   edgecolors="k", linewidth=0.4, 
                   c=[cmap(norm(min(mag, CMAX)))], transform=ccrs.Geodetic())
    
     
    # ───────────────────────────────────────────────────────────────
    # 9)  Perturbation (big empty square)
    # ───────────────────────────────────────────────────────────────
    perturb_bus = int(re.match(r"^(\d+)", location).group(1))
    row = bus_info.loc[bus_info.BusNumber == perturb_bus]
    ax.scatter(row.Lon, row.Lat, marker="s", s=300,
               facecolors="none", edgecolors="k", linewidth=1.4,
               transform=ccrs.Geodetic())
    
    # ----- Custom legend handles -----
    gen_handle = mlines.Line2D([], [], color="k", marker="^", linestyle="None",
                               markersize=10, label="Generator")
    load_handle = mlines.Line2D([], [], color="k", marker="s", linestyle="None",
                                markersize=10, label="Load")
    line_handle = mlines.Line2D([], [], color="k", linewidth=2, label="Line")
     
    # Add legend
    ax.legend(handles=[gen_handle, load_handle, line_handle],
              loc="lower left", fontsize=10, frameon=True)

    
    # colour-bar
    sm = cm.ScalarMappable(norm=norm, cmap=cmap)
    cbar = plt.colorbar(sm, ax=ax, pad=0.02, aspect=25)
    cbar.set_label("Oscillation Magnitude (ΔMW)", fontsize=12, weight="bold")
    cbar.ax.tick_params(labelsize=10)
    
    plt.title(f"Oscillation >{MW_THRESHOLD} MW for {location.replace('_', ' ')}",
        fontsize=14, weight="bold")
    plt.tight_layout(rect=[0, 0, 1, 0.95])
    # # save instead of show
    plt.savefig(
        "LDDL_risk_eval_viz_"+str(perturb_bus)+".png",
        dpi=300,                # resolution
        bbox_inches="tight",    # trim whitespace
        pad_inches=0.2          # add a bit of breathing room
        )
    plt.show()
    
    

def Print_Summary_Osc_Violation(location, MW_THRESHOLD, CMAX , osc_line, names_line, osc_gen, gen_buses, osc_load, load_buses, bus_info, Output_Folder ):
    perturb_bus = int(re.match(r"^(\d+)", location).group(1))
    # ───────────────────────────────────────────────────────────────
    # 10)  Summary table (unchanged logic, uses .iloc[0])
    # ───────────────────────────────────────────────────────────────
    source_zone = int(
        bus_info.loc[bus_info.BusNumber == perturb_bus, "ZoneNum"].iloc[0]
    )
    
    summary = {
        "Category": ["Generator Injections", "Tie-line Flows", "Load Injections"],
        "Instances >20 MW": [0, 0, 0],
        "Instances in Source Zone": [0, 0, 0],
        "Instances Outside Source Zone": [0, 0, 0],
        "Max Osc. in Source Zone (MW)": [0., 0., 0.],
        "Max Osc. outside Source Zone (MW)": [0., 0., 0.],
        "Max Loc. in Source Zone": ["None", "None", "None"],
        "Max Loc. outside Source Zone": ["None", "None", "None"],
    }
    
    # >>> generator counts / max
    zone_gen = bus_info.set_index("BusNumber").loc[gen_buses, "ZoneNum"].to_numpy()
    gt = osc_gen > MW_THRESHOLD
    summary["Instances >20 MW"][0]              = int(gt.sum())
    summary["Instances in Source Zone"][0]      = int((gt & (zone_gen == source_zone)).sum())
    summary["Instances Outside Source Zone"][0] = int((gt & (zone_gen != source_zone)).sum())
    
    if (zone_gen == source_zone).any():
        idx = np.argmax(np.where(zone_gen == source_zone, osc_gen, -1))
        summary["Max Osc. in Source Zone (MW)"][0] = float(osc_gen[idx])
        summary["Max Loc. in Source Zone"][0] = bus_info.loc[
            bus_info.BusNumber == gen_buses[idx], "BusName"
        ].iat[0]
    
    if (zone_gen != source_zone).any():
        idx = np.argmax(np.where(zone_gen != source_zone, osc_gen, -1))
        summary["Max Osc. outside Source Zone (MW)"][0] = float(osc_gen[idx])
        summary["Max Loc. outside Source Zone"][0] = bus_info.loc[
            bus_info.BusNumber == gen_buses[idx], "BusName"
        ].iat[0]
    
    # >>> tie-lines
    cnt_in = cnt_out = 0
    max_in_mag = max_out_mag = 0.
    max_in_name = max_out_name = "None"
    
    for mag, sig in zip(osc_line, names_line):
        if mag <= MW_THRESHOLD:
            continue
        b1, b2 = map(int, re.match(r"POWR\s*(\d+)\s*TO\s*(\d+)", sig).groups())
        z1 = int(bus_info.loc[bus_info.BusNumber == b1, "ZoneNum"].iat[0])
        z2 = int(bus_info.loc[bus_info.BusNumber == b2, "ZoneNum"].iat[0])
        name = f"{bus_info.loc[bus_info.BusNumber==b1,'BusName'].iat[0]} --- " \
               f"{bus_info.loc[bus_info.BusNumber==b2,'BusName'].iat[0]}"
        if z1 == source_zone or z2 == source_zone:
            cnt_in += 1
            if mag > max_in_mag:
                max_in_mag, max_in_name = mag, name
        else:
            cnt_out += 1
            if mag > max_out_mag:
                max_out_mag, max_out_name = mag, name
    
    summary["Instances >20 MW"][1]              = cnt_in + cnt_out
    summary["Instances in Source Zone"][1]      = cnt_in
    summary["Instances Outside Source Zone"][1] = cnt_out
    summary["Max Osc. in Source Zone (MW)"][1]  = max_in_mag
    summary["Max Osc. outside Source Zone (MW)"][1] = max_out_mag
    summary["Max Loc. in Source Zone"][1]       = max_in_name
    summary["Max Loc. outside Source Zone"][1]  = max_out_name
    
    # >>> loads
    zone_load = bus_info.set_index("BusNumber").loc[load_buses, "ZoneNum"].to_numpy()
    gt = osc_load > MW_THRESHOLD
    summary["Instances >20 MW"][2] = int(gt.sum())
    summary["Instances in Source Zone"][2] = int((gt & (zone_load == source_zone)).sum())
    summary["Instances Outside Source Zone"][2] = int((gt & (zone_load != source_zone)).sum())
    
    if (zone_load == source_zone).any():
        idx = np.argmax(np.where(zone_load == source_zone, osc_load, -1))
        summary["Max Osc. in Source Zone (MW)"][2] = float(osc_load[idx])
        summary["Max Loc. in Source Zone"][2] = bus_info.loc[
            bus_info.BusNumber == load_buses[idx], "BusName"
        ].iat[0]
    
    if (zone_load != source_zone).any():
        idx = np.argmax(np.where(zone_load != source_zone, osc_load, -1))
        summary["Max Osc. outside Source Zone (MW)"][2] = float(osc_load[idx])
        summary["Max Loc. outside Source Zone"][2] = bus_info.loc[
            bus_info.BusNumber == load_buses[idx], "BusName"
        ].iat[0]
    
    summary_df = pd.DataFrame(summary)
    print(f"\nSummary of Oscillation Violations (>{MW_THRESHOLD} MW) "
          f"for {location.replace('_',' ')}\n")
    print(summary_df.to_string(index=False))
    
    summary_df.to_csv('LDDL_summary'+str(perturb_bus)+'.csv')
    
