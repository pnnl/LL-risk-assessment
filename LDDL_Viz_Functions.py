# from __future__ import annotations
import re
import numpy as np
import pandas as pd
import matplotlib as mpl
mpl.use("QtAgg")
import matplotlib.pyplot as plt
import cartopy.crs as ccrs
from matplotlib import cm, colors            # cm & colors both needed
import cartopy.feature as cfeature
import os
import matplotlib.lines as mlines

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

# ───────────────────────────────────────────────────────────────
# 1)  some computation functions
# ───────────────────────────────────────────────────────────────

def max_peak_to_peak_per_cycle(y, t, f):
    """
    Compute the maximum peak-to-peak per cycle for multiple periodic time series.

    Parameters
    ----------
    y : array_like, shape (n_samples, n_signals)
        Time series data. Each column is a separate signal.
    t : array_like, shape (n_samples,)
        Time vector corresponding to the rows of y.
    f : float
        Frequency of the periodic signals in Hz.

    Returns
    -------
    ptp_max_all : ndarray, shape (n_signals,)
        Maximum peak-to-peak per cycle for each column/time series.
    """
    y = np.asarray(y)
    t = np.asarray(t)

    if y.ndim == 1:
        # Convert single vector to 2D column
        y = y[:, np.newaxis]

    dt = t[2] - t[1]
    T = 1 / f
    samples_per_cycle = int(T / dt)

    num_cycles = y.shape[0] // samples_per_cycle
    if num_cycles == 0:
        raise ValueError("Not enough samples for even one full cycle.")

    # Truncate to full cycles
    y_trunc = y[:num_cycles*samples_per_cycle, :]

    # Reshape into (num_cycles, samples_per_cycle, n_signals)
    y_cycles = y_trunc.reshape(num_cycles, samples_per_cycle, y.shape[1])

    # Compute max and min per cycle for each signal
    max_per_cycle = y_cycles.max(axis=1)
    min_per_cycle = y_cycles.min(axis=1)

    # Compute peak-to-peak per cycle
    ptp_per_cycle = max_per_cycle - min_per_cycle

    # Return maximum peak-to-peak per signal
    ptp_max_all = np.max(ptp_per_cycle,axis=0)
    return ptp_max_all

# ───────────────────────────────────────────────────────────────
# 2)  Reading location & file names
# ───────────────────────────────────────────────────────────────

def _clean_numeric(col: pd.Series, negate=False) -> pd.Series:
    ser = (
        col.astype(str)
           .str.replace(r"[^\d.\-]", "", regex=True)
           .astype(float)
    )
    return -ser if negate else ser

def Read_System_Bus_Lat_Long(BUS_FILE, cfg):
    bus_info = pd.read_csv(BUS_FILE)            # or read_excel
    bus_info = bus_info.rename(
        columns=lambda c: (
            c.strip()           # remove leading/trailing blanks
             .replace("  ", "") # drop double-space
             .replace(" ", "")  # drop single space
        )
    )
    # drop duplicate 
    bus_with_name =bus_info.loc[bus_info["BUS_NAME"].notna(), "BUS_NUMBER"].unique()
    bus_info = bus_info[~((bus_info["BUS_NAME"].isna()) & (bus_info["BUS_NUMBER"].isin(bus_with_name)))]
    if 'Latitude' in bus_info.columns or 'LATITUDE' in bus_info.columns or 'Lat' in bus_info.columns or 'LAT' in bus_info.columns:
        bus_info["Lat"] = _clean_numeric(bus_info.iloc[:, 7]) ## cleaned Lat saved in 10th col
        bus_info["Lon"] = _clean_numeric(bus_info.iloc[:, 8], True) ## cleaned Longitude saved in 11th col
    return(bus_info)


# ───────────────────────────────────────────────────────────────
# 3)  Read system data
# ───────────────────────────────────────────────────────────────

def Process_LDDL_out_for_Viz(df, cfg):
    # df is the dataframe of PSSE output, cfg has configuration parameters
    # if for some reason the visualization and analysis code needs to be debugged, df can read the PSSE simulation output. 
    # PSSE simulation need not be rerun
    df = df.drop_duplicates(subset='time', keep='first') # PSSE may report duplicate values for the same timestamp when simulation is stopped and re-ran
    df.columns = df.columns.str.strip()         # trim trailing blanks
    LDDL_bus_number = cfg.load_model.load_bus_number
    loads = pd.read_csv('Results_'+str(LDDL_bus_number)+'\\filtered_load.csv')
    
    time         = df.iloc[:, 0].to_numpy()
    signal_names = df.columns[1:]               # skip time
    signal_vals  = df.iloc[:, 1:].to_numpy()
    
    # Divvying up PSSE output to generator, load, and line values. Currently not logging outputs from other elements
    # masks with whitespace-tolerant regex
    is_line = [bool(re.match(r"POWR\s*\d+\s*TO\s*\d+", n)) for n in signal_names]
    is_gen  = [bool(re.match(r"POWR\s*\d+", n)) and not l
               for n, l in zip(signal_names, is_line)]
    is_load = []
    for n in signal_names:
        m = re.match(r"PLOD\s*(\d+)", n)
        if m:
            num = int(m.group(1))
            if num in np.array(loads.BUS_NUMBER) or num==LDDL_bus_number:
                is_load.append(True)
            else:
                is_load.append(False)
        else:
            is_load.append(False)
    is_v = [x for x in signal_names if 'VOLT' in x]
    
    # visually inspecting voltage deviations. Future plans to automate extracting elements where limit violations are observed
    plt.figure()
    plt.plot(df.time,df[is_v]-df[is_v].iloc[0])
    plt.title ('Voltage deviations (p.u.)')
    plt.xlabel('Time (s)')
    plt.grid()
    plt.tight_layout()
    plt.savefig('Results_'+str(LDDL_bus_number)+"\\voltage_deviations_"+str(LDDL_bus_number)+".png",)
    
    # tie-line values already in MW
    vals_line  = signal_vals[:, is_line]
    
    # generator & load injections are in per-unit, convert → MW
    vals_gen   = 100 * signal_vals[:, is_gen]
    vals_load  = 100 * signal_vals[:, is_load]
    
    if len(vals_line)>0:
        osc_line = max_peak_to_peak_per_cycle(vals_line[time > cfg.load_variation.start_time_s], time[time > cfg.load_variation.start_time_s], cfg.load_variation.freq_primary_hz)
        names_line = signal_names[is_line]
    else:
        osc_line = None
        names_line = None
    if len(vals_gen)>0:
        osc_gen = max_peak_to_peak_per_cycle(vals_gen[time > cfg.load_variation.start_time_s], time[time > cfg.load_variation.start_time_s], cfg.load_variation.freq_primary_hz)
        names_gen  = signal_names[is_gen]
    else:
        osc_gen = None
        names_gen = None
    if len(vals_load)>0:
        osc_load = max_peak_to_peak_per_cycle(vals_load[time > cfg.load_variation.start_time_s], time[time > cfg.load_variation.start_time_s], cfg.load_variation.freq_primary_hz)
        names_load = signal_names[is_load]
    else:
        osc_load = None
        names_load = None
    
    # we are computing peak-to-peak amplitudes per cycle. If on the other hand, absolute max-min is required, following snippet can be uncommented
    # osc_line = vals_line[time > cfg.load_variation.start_time_s].max(0) - vals_line[time > cfg.load_variation.start_time_s].min(0)
    # osc_gen  = vals_gen [time > cfg.load_variation.start_time_s].max(0) - vals_gen [time > cfg.load_variation.start_time_s].min(0)
    # osc_load = vals_load[time > cfg.load_variation.start_time_s].max(0) - vals_load[time > cfg.load_variation.start_time_s].min(0)

    lddl_idx = [i for i, x in enumerate(names_load) if str(LDDL_bus_number) in x and 'LL' in x]
    lddl_idx = lddl_idx[-1]
    
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
    
    # plotting most impacted elements
    fig, axs = plt.subplots(4,1)
    axs[0].plot(time,vals_load[:,lddl_idx])
    axs[0].set_title('Source: '+names_load[lddl_idx])
    axs[0].set_ylabel('MW')
    axs[0].set_xlabel('Time(s)')
    axs[0].grid()
    
    if len(osc_gen)>0:
        axs[1].plot(time,vals_gen[:,np.argmax(osc_gen)])
        axs[1].set_title('Most impacted Gen: '+names_gen[np.argmax(osc_gen)])
        axs[1].set_ylabel('MW')
        axs[1].set_xlabel('Time(s)')
        axs[1].grid()
    if len(osc_load)>0:
        axs[2].plot(time,vals_load[:,np.argmax(osc_load)])
        axs[2].set_title('Most impacted Load: '+names_load[np.argmax(osc_load)])
        axs[2].set_ylabel('MW')
        axs[2].set_xlabel('Time(s)')
        axs[2].grid()
    if len(osc_line)>0:
        axs[3].plot(time,vals_line[:,np.argmax(osc_line)])
        axs[3].set_title('Most impacted Line: '+names_line[np.argmax(osc_line)])
        axs[3].set_ylabel('MW')
        axs[3].set_xlabel('Time(s)')
        axs[3].grid()
    plt.tight_layout()
    
    plt.savefig(
        'Results_'+str(LDDL_bus_number)+"\\LDDL_timeseries_"+str(LDDL_bus_number)+".png",
        dpi=300,                # resolution
        bbox_inches="tight",    # trim whitespace
        pad_inches=0.2          # add a bit of breathing room
        )
    
    return(osc_line, names_line, osc_gen, gen_buses, osc_load, load_buses)

def LDDL_OscAna_Viz(location, MW_THRESHOLD, osc_line, names_line, osc_gen, gen_buses, osc_load, load_buses, bus_info, Output_Folder):
    
    # List impacted elements - four outputs obtained - csvs of impacted generators, lines, and laods whose p-p amplitudes exceed MW_THRESHOLD
    # and a csv summarizing how many elements within/outside source zone are impacted
    
    gen_list = []
    load_list = []
    line_list = []
    for mag, bus in zip(osc_gen, gen_buses):
        if mag > MW_THRESHOLD:
            gen_list.append([bus,mag])
    gen_list = np.array(gen_list)
    if len(gen_list)>0:
        gen_list = pd.DataFrame(columns = ['Gen Number', "Oscillation amplitude (MW)"], data = gen_list)
    else: 
        gen_list = pd.DataFrame(columns = ['Gen Number', "Oscillation amplitude (MW)"])
    gen_list.to_csv('Results_'+str(location)+'\\Impacted_generators.csv')
    for mag, bus in zip(osc_load, load_buses):
        if mag > MW_THRESHOLD:
            load_list.append([bus,mag])
    load_list = np.array(load_list)
    if len(load_list)>0:
        load_list = pd.DataFrame(columns = ['Load Number', "Oscillation amplitude (MW)"], data = load_list)
    else:
        load_list = pd.DataFrame(columns = ['Load Number', "Oscillation amplitude (MW)"])
    load_list.to_csv('Results_'+str(location)+'\\Impacted_loads.csv')
    for mag, sig in zip(osc_line, names_line):
        if mag > MW_THRESHOLD:
            line_list.append([sig,mag])
    line_list = np.array(line_list)
    if len(line_list)>0:
        line_list = pd.DataFrame(columns = ['Line Number', "Oscillation amplitude (MW)"], data = line_list)
    else:
        line_list = pd.DataFrame(columns = ['Line Number', "Oscillation amplitude (MW)"])
    line_list.to_csv('Results_'+str(location)+'\\Impacted_lines.csv')
    
    #summary 
    source_zone = int(bus_info.loc[bus_info['BUS_NUMBER'] == int(location), "ZONE"].iloc[0])
    source_area = int(bus_info.loc[bus_info['BUS_NUMBER'] == int(location), "AREA"].iloc[0])
    
    summary = {
        "Category": ["Generator Injections", "Load Injections", "Tie-line flows"],
        "Instances >20 MW": [0, 0, 0],
        "Instances in Source Zone": [0, 0, 0],
        "Instances Outside Source Zone": [0, 0, 0],
        "Max Osc. in Source Zone (MW)": [0., 0., 0.],
        "Max Osc. outside Source Zone (MW)": [0., 0., 0.],
        "Max Loc. in Source Zone": ["None", "None", "None"],
        "Max Loc. outside Source Zone": ["None", "None", "None"],
    }
    
    summary["Instances >20 MW"][0] = len(gen_list)
    placeholder = pd.DataFrame()
    if len(gen_list)>0:   
        for x in gen_list.index:
            if bus_info[bus_info.BUS_NUMBER==gen_list.iloc[x]['Gen Number']]["ZONE"].iloc[0]==source_zone and bus_info[bus_info.BUS_NUMBER==gen_list.iloc[x]['Gen Number']]["AREA"].iloc[0]==source_area:
               placeholder =  pd.concat([placeholder,gen_list.iloc[x]],axis=1);
        summary["Instances in Source Zone"][0] = len(placeholder.T)
        summary["Instances Outside Source Zone"][0] = summary["Instances >20 MW"][0]-summary["Instances in Source Zone"][0]
        idx = np.argmax(np.array(placeholder.T["Oscillation amplitude (MW)"]))
        summary["Max Osc. in Source Zone (MW)"][0] = placeholder.T.iloc[idx]["Oscillation amplitude (MW)"]
        summary["Max Loc. in Source Zone"][0] = placeholder.T.iloc[idx]["Gen Number"]
        if summary["Instances >20 MW"][0]-summary["Instances in Source Zone"][0] > 0:
            outside = gen_list[~gen_list['Gen Number'].isin(placeholder.T['Gen Number'])]
            idx = np.argmax(np.array(outside["Oscillation amplitude (MW)"]))
            summary["Max Osc. outside Source Zone (MW)"][0] = outside.iloc[idx]["Oscillation amplitude (MW)"]
            summary["Max Loc. outside Source Zone"][0] = outside.iloc[idx]["Gen Number"]
    
    summary["Instances >20 MW"][1] = len(load_list)
    placeholder = pd.DataFrame()
    if len(load_list)>0: 
        for x in load_list.index:
            if bus_info[bus_info.BUS_NUMBER==load_list.iloc[x]['Load Number']]["ZONE"].iloc[0]==source_zone and bus_info[bus_info.BUS_NUMBER==load_list.iloc[x]['Load Number']]["AREA"].iloc[0]==source_area:
               placeholder =  pd.concat([placeholder,load_list.iloc[x]],axis=1);
        summary["Instances in Source Zone"][1] = len(placeholder.T)
        summary["Instances Outside Source Zone"][1] = summary["Instances >20 MW"][1]-summary["Instances in Source Zone"][1]
        idx = np.argmax(np.array(placeholder.T["Oscillation amplitude (MW)"]))
        summary["Max Osc. in Source Zone (MW)"][1] = placeholder.T.iloc[idx]["Oscillation amplitude (MW)"]
        summary["Max Loc. in Source Zone"][1] = placeholder.T.iloc[idx]["Load Number"]
        if summary["Instances >20 MW"][1]-summary["Instances in Source Zone"][1] > 0:
            outside = load_list[~load_list['Load Number'].isin(placeholder.T['Load Number'])]
            idx = np.argmax(np.array(outside["Oscillation amplitude (MW)"]))
            summary["Max Osc. outside Source Zone (MW)"][1] = outside.iloc[idx]["Oscillation amplitude (MW)"]
            summary["Max Loc. outside Source Zone"][1] = outside.iloc[idx]["Load Number"]
       
    summary["Instances >20 MW"][2] = len(line_list)
    placeholder = pd.DataFrame()
    if len(line_list)>0: 
        for x in line_list.index:
            frombus = int(line_list.iloc[x]['Line Number'].split()[1])
            tobus = int(line_list.iloc[x]['Line Number'].split()[3])
            if (bus_info[bus_info.BUS_NUMBER==frombus]["AREA"].iloc[0]==source_area and bus_info[bus_info.BUS_NUMBER==frombus]["ZONE"].iloc[0]==source_zone)  or (bus_info[bus_info.BUS_NUMBER==tobus]["AREA"].iloc[0]==source_area and bus_info[bus_info.BUS_NUMBER==tobus]["ZONE"].iloc[0]==source_zone):       
               placeholder =  pd.concat([placeholder,line_list.iloc[x]],axis=1);
        summary["Instances in Source Zone"][2] = len(placeholder.T)
        summary["Instances Outside Source Zone"][2] = summary["Instances >20 MW"][2]-summary["Instances in Source Zone"][2]
        idx = np.argmax(np.array(placeholder.T["Oscillation amplitude (MW)"].astype(float)))
        summary["Max Osc. in Source Zone (MW)"][2] = placeholder.T.iloc[idx]["Oscillation amplitude (MW)"]
        summary["Max Loc. in Source Zone"][2] = placeholder.T.iloc[idx]["Line Number"]
        if summary["Instances >20 MW"][2]-summary["Instances in Source Zone"][2] > 0:
            outside = line_list[~line_list['Line Number'].isin(placeholder.T['Line Number'])]
            idx = np.argmax(np.array(outside["Oscillation amplitude (MW)"].astype(float)))
            summary["Max Osc. outside Source Zone (MW)"][2] = outside.iloc[idx]["Oscillation amplitude (MW)"]
            summary["Max Loc. outside Source Zone"][2] = outside.iloc[idx]["Line Number"]
            
    summary_df = pd.DataFrame(summary)
    print(f"\nSummary of Oscillation Violations (>{MW_THRESHOLD} MW) "
           f"for {location.replace('_',' ')}\n")
    print(summary_df.to_string(index=False))
     
    summary_df.to_csv('Results_'+str(location)+'\\LDDL_summary_'+str(location)+'.csv')
    
    #visualization if latitude and longitude information provided
    
    if "Lat" not in bus_info.columns: 
        return
    
    # ───────────────────────────────────────────────────────────────
    # 5)  Figure & map - only if latitude and longitude information provided
    # ───────────────────────────────────────────────────────────────
    cmap = plt.get_cmap("jet", 64)   # modern, no deprecation
    max1 = max(osc_gen)
    max2 = max(osc_line)
    max3 = max(osc_load)
    CMAX = max(max1,max2,max3)
    norm = colors.Normalize(vmin=MW_THRESHOLD,vmax=CMAX)
    
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
    #ax.set_extent([-125, -106.7, 29.7, 54], crs=ccrs.PlateCarree())
        
    ax.add_feature(cfeature.LAND.with_scale("50m"),   facecolor="lightgray") ## 110m for faster, 10m for high quality
    ax.add_feature(cfeature.OCEAN.with_scale("50m"),  facecolor="whitesmoke")
    ax.add_feature(cfeature.BORDERS.with_scale("50m"), linewidth=0.6)
    ax.add_feature(cfeature.STATES.with_scale("50m"),  linewidth=0.4)
    plt.tight_layout()
    plt.show() 
    
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
            lat_pair = bus_info.loc[bus_info['BUS_NUMBER'] == b1, "Lat"].iat[0], \
                       bus_info.loc[bus_info['BUS_NUMBER'] == b2, "Lat"].iat[0]
            lon_pair = bus_info.loc[bus_info['BUS_NUMBER'] == b1, "Lon"].iat[0], \
                       bus_info.loc[bus_info['BUS_NUMBER'] == b2, "Lon"].iat[0]
        except IndexError:
            continue
        ax.plot(lon_pair, lat_pair, transform=ccrs.Geodetic(),
                lw=3.5, alpha = 0.8, zorder = 2,c=cmap(norm(min(mag, CMAX))))
        ax.scatter(lon_pair, lat_pair, s=25, c="k", transform=ccrs.Geodetic())
    
    # ───────────────────────────────────────────────────────────────
    # 7)  Plot generators (triangles, labels)
    # ───────────────────────────────────────────────────────────────
     
    for mag, bus in zip(osc_gen, gen_buses):
        if mag <= MW_THRESHOLD:
            continue
        row = bus_info.loc[bus_info['BUS_NUMBER'] == bus]
        if row.empty:
            continue
        ax.scatter(row.Lon, row.Lat, marker="^", s=500,
                   edgecolors="k", linewidth=0.4, zorder = 3, transform=ccrs.Geodetic(),c=cmap(norm(min(mag, CMAX)))    )
        # text label
        ax.text(row.Lon.values[0] + 0.15,
                row.Lat.values[0] + 0.15,
                row['BUS_NAME'].values[0],
                fontsize=8, weight="bold", transform=ccrs.PlateCarree(),c=cmap(norm(min(mag, CMAX))))
        
    # ───────────────────────────────────────────────────────────────
    # 8)  Plot loads (squares)
    # ───────────────────────────────────────────────────────────────
    for mag, bus in zip(osc_load, load_buses):
        if mag <= MW_THRESHOLD:
            continue
        row = bus_info.loc[bus_info['BUS_NUMBER'] == bus]
        if row.empty:
            continue
        ax.scatter(row.Lon, row.Lat, marker="s", s=600,
                   edgecolors="k", linewidth=0.4, transform=ccrs.Geodetic(),c=cmap(norm(min(mag, CMAX))))
       
    # ───────────────────────────────────────────────────────────────
    # 9)  Perturbation (big empty square)
    # ───────────────────────────────────────────────────────────────
    perturb_bus = int(re.match(r"^(\d+)", location).group(1))
    row = bus_info.loc[bus_info['BUS_NUMBER'] == perturb_bus]
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
    
    plt.title(f"Locations where amplitudes >{MW_THRESHOLD} MW are observed for source at {location.replace('_', ' ')}",
        fontsize=14, weight="bold")
    plt.tight_layout(rect=[0, 0, 1, 0.95])
    # # save instead of show
    plt.savefig(
        'Results_'+str(perturb_bus)+"\\LDDL_risk_eval_viz_"+str(perturb_bus)+".png",
        dpi=300,                # resolution
        bbox_inches="tight",    # trim whitespace
        pad_inches=0.2          # add a bit of breathing room
        )


    
   
    
