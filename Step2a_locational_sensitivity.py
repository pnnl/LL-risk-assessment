# -*- coding: utf-8 -*-
'''
Compute voltage sensitivities deltaV/deltaP and deltaV/deltaQ 
        and angle sensitivities deltaTheta/deltaP  for generator units
Brute-force central-difference method
Buses considered:
  - Voltage sensitivity : PQ buses without switched shunts, 69 kV <= base kV <= 138 kV (user can change)
  - Angle sensitivity   : in-service generator buses with PMAX > min_mw (config-driven)
Voltage levels and area filter can be changed via configuration input
@author: bisw757
'''

from pathlib import Path
import os, sys, csv, time
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.cm as cm
import numpy as np
import pandas as pd

from psse_config import configure_psse
psse_version = 35
psspy_version = 311
psspy = configure_psse(psse_version, psspy_version)


# ---------------- SENSITIVITY STUDY SETTINGS ----------------
DELTA_Q = 1.0
DELTA_P = 1.0
LOAD_ID = 'ZZ'   # fictitious load ID used for perturbations
#-------------------------------------------------------------

def initialize_psse():
    psspy.psseinit(200000)
    psspy.progress_output(6, '', [0, 0]) # suppressing outputs in python console
    psspy.alert_output(6, '', [0, 0])
    psspy.prompt_output(6, '', [0, 0])

def load_case(case_file):
    ierr = psspy.case(str(case_file))
    if ierr != 0:
        raise Exception(f"Error loading case: {ierr}")
    print(f"Loaded case: {case_file}")

def solve_power_flow():
    ierr = psspy.fnsl([0, 0, 0, 1, 0, 0, 0, 0])
    # ierr = psspy.fdns([0, 0, 0, 1, 1, 0, 0, 0]) # uncomment if fast-decoupled N_R desired
    return ierr == 0

def solve_and_get_voltage(bus_num):
    if not solve_power_flow():
        return None, None
    return get_bus_voltage(bus_num)

def get_bus_voltage_from_csv(bus_num,base_voltage_lookup):
    """Get base case voltage from pre-computed CSV file"""
    if bus_num in base_voltage_lookup:
        data = base_voltage_lookup[bus_num]
        return data['VM_PU'], data['VA_DEG']
    return None, None

# time saving with power flow solution from base case 
# already stored in a csv (step1_extract_case_info.py)
def get_bus_voltage(bus_num):
    ierr1, vmag = psspy.busdat(bus_num, 'PU')
    ierr2, vang = psspy.busdat(bus_num, 'ANGLED') #angle in degrees
    if ierr1 != 0 or ierr2 != 0:
        return None, None
    return vmag, vang

def add_fictitious_load(bus_num, p_mw=0.0, q_mvar=0.0):
    val_i = psspy.getdefaultint()
    ierr = psspy.load_data_6(
        bus_num,
        LOAD_ID,
        [1, val_i, val_i, val_i, 1, 0, 0],
        [p_mw, q_mvar, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0]
    )
    return ierr == 0

def remove_fictitious_load(bus_num):
    psspy.purgload(bus_num, LOAD_ID)

# ----------BUS SELECTION FUNCTIONS---------------

def get_pq_buses_without_reactive_compensation(minkV=69, maxkV=138, area_filter=None):
    """
    Return PQ buses (type 1) with no switched shunt and base kV in [minkV, maxkV].
    If area_filter is provided (int or list/set of ints), only buses whose PSSE
    area number is in that set are included.  Pass None (or leave blank) to keep
    all areas (original behaviour).
    """
    ierr,  bus_numbers = psspy.abusint(-1, 1, 'NUMBER')
    ierr2, bus_types   = psspy.abusint(-1, 1, 'TYPE')
    ierr3, bus_kvs     = psspy.abusreal(-1, 1, 'BASE')
    ierr4, bus_areas   = psspy.abusint(-1, 1, 'AREA')

    bus_numbers = bus_numbers[0]
    bus_types   = bus_types[0]
    bus_kvs     = bus_kvs[0]
    bus_areas   = bus_areas[0]

    ierr, swsh_buses = psspy.aswshint(-1, 1, 'NUMBER')
    swsh_buses = swsh_buses[0] if ierr == 0 else []
    reactive_comp = set(swsh_buses)

    # Normalise area_filter to a set (None → no filtering)
    if area_filter is not None:
        if isinstance(area_filter, (int, float)):
            area_filter = {int(area_filter)}
        else:
            area_filter = {int(a) for a in area_filter}

    pq_buses = []
    for i, bus in enumerate(bus_numbers):
        if bus_types[i] != 1:
            continue
        if not (minkV <= bus_kvs[i] <= maxkV):
            continue
        if bus in reactive_comp:
            continue
        if area_filter is not None and bus_areas[i] not in area_filter:
            continue
        pq_buses.append({'bus_num': bus, 'kv': bus_kvs[i], 'area': bus_areas[i]})

    area_msg = (f"area(s) {sorted(area_filter)}" if area_filter else "all areas")
    print(f"Found {len(pq_buses)} PQ buses without switched shunts "
          f"({minkV:.0f} kV – {maxkV:.0f} kV, {area_msg})")
    return pq_buses

# ----------SENSITIVITY FUNCTIONS-----------------

def compute_voltage_sensitivities(pq_buses,sav_case,base_voltage_lookup,delta_P=1,delta_Q=1):
    """
    Compute dV/dP and dV/dQ for every bus in pq_buses 
    For each bus we apply three perturbations and solve power flow:
      +DELTA_P  →  v_p_plus
      -DELTA_P  →  v_p_minus
      +DELTA_Q  →  v_q_plus   (case is reloaded to base before each bus)
      -DELTA_Q  →  v_q_minus

    Central difference:
      dV/dP = (v_p_plus - v_p_minus) / (2 * DELTA_P)
      dV/dQ = (v_q_plus - v_q_minus) / (2 * DELTA_Q)
    """
    results = []

    load_case(sav_case)
    solve_power_flow()

    total = len(pq_buses)
    for idx, b in enumerate(pq_buses, 1):
        bus     = b['bus_num']
        v_base, _ = get_bus_voltage_from_csv(bus,base_voltage_lookup)

        # --- dV/dP ---
        add_fictitious_load(bus, delta_P, 0.0)
        v_p_plus, _ = solve_and_get_voltage(bus)
        remove_fictitious_load(bus)

        add_fictitious_load(bus, -delta_P, 0.0)
        v_p_minus, _ = solve_and_get_voltage(bus)
        remove_fictitious_load(bus)

        # --- dV/dQ ---
        add_fictitious_load(bus, 0.0, delta_Q)
        v_q_plus, _ = solve_and_get_voltage(bus)
        remove_fictitious_load(bus)

        add_fictitious_load(bus, 0.0, -delta_Q)
        v_q_minus, _ = solve_and_get_voltage(bus)
        remove_fictitious_load(bus)

        if all(v is not None for v in [v_p_plus, v_p_minus, v_q_plus, v_q_minus]):
            dv_dp = (v_p_plus - v_p_minus) / (2.0 * delta_P)
            dv_dq = (v_q_plus - v_q_minus) / (2.0 * delta_Q)
            results.append({
                'Bus'      : bus,
                'Area'     : b['area'],
                'kV'       : b['kv'],
                'V0_pu'    : v_base,
                'dV/dP'    : dv_dp,
                'dV/dQ'    : dv_dq,
                'vP_plus'  : v_p_plus,
                'vP_minus' : v_p_minus,
                'vQ_plus'  : v_q_plus,
                'vQ_minus' : v_q_minus,
            })

        if idx % 50 == 0 or idx == total:
            print(f"  Processed {idx}/{total} buses")

    return pd.DataFrame(results)


# ----------PLOTTING FUNCTION---------------------
def plot_sensitivities(df, output_path, minkV, maxkV, area_filter=None):
    """
    Scatterplot of dV/dQ (x) vs dV/dP (y) for all buses in df.
    Points are color-coded by nominal voltage level (kV).
    """
    kv_levels  = sorted(df['kV'].unique())
    n_levels   = len(kv_levels)
    palette    = cm.get_cmap('tab10', n_levels)
    kv_to_color = {kv: palette(i) for i, kv in enumerate(kv_levels)}

    fig, ax = plt.subplots(figsize=(9, 7))

    for kv in kv_levels:
        subset = df[df['kV'] == kv]
        ax.scatter(
            subset['dV/dQ'],
            subset['dV/dP'],
            c=[kv_to_color[kv]],
            label=f'{kv:.0f} kV  (n={len(subset)})',
            alpha=0.75,
            edgecolors='white',
            linewidths=0.4,
            s=55
        )

    # Reference lines at zero
    ax.axhline(0, color='grey', linewidth=0.7, linestyle='--', zorder=0)
    ax.axvline(0, color='grey', linewidth=0.7, linestyle='--', zorder=0)

    ax.set_xlabel('dV/dQ  (pu / Mvar)', fontsize=12)
    ax.set_ylabel('dV/dP  (pu / MW)',   fontsize=12)
    area_label = (f"Areas {sorted(area_filter)}" if area_filter else "All Areas")
    ax.set_title(
        f'Voltage Sensitivities — PQ Buses {minkV:.0f}–{maxkV:.0f} kV  |  {area_label}\n'
        f'(n = {len(df)} buses, central difference, Δ = {DELTA_P} MW / {DELTA_Q} Mvar)',
        fontsize=11
    )
    ax.legend(title='Nominal kV', fontsize=9, title_fontsize=9,
              loc='best', framealpha=0.85)
    ax.grid(True, linestyle=':', linewidth=0.5, alpha=0.6)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  Plot saved: {output_path}")


# ----------GENERATOR BUS SELECTION---------------

def get_generator_buses(min_mw=10.0, area_filter=None):
    """
    Return in-service generator buses with PMAX > min_mw.
    One entry per unique bus (multiple machines on the same bus are aggregated:
    the bus appears once with total_pmax = sum of PMAX across all machines).
    If area_filter is provided (int or list/set of ints), only generators in
    those PSSE area numbers are included.
    """
    ierr,  mach_buses  = psspy.amachint(-1, 1, 'NUMBER')
    ierr2, mach_status = psspy.amachint(-1, 1, 'STATUS')
    ierr3, mach_pmax   = psspy.amachreal(-1, 1, 'PMAX')

    mach_buses  = mach_buses[0]
    mach_status = mach_status[0]
    mach_pmax   = mach_pmax[0]

    # Build bus-level lookup for kV and area
    ierr,  bus_numbers = psspy.abusint(-1, 1, 'NUMBER')
    ierr2, bus_kvs     = psspy.abusreal(-1, 1, 'BASE')
    ierr3, bus_areas   = psspy.abusint(-1, 1, 'AREA')
    bus_kv_map   = dict(zip(bus_numbers[0], bus_kvs[0]))
    bus_area_map = dict(zip(bus_numbers[0], bus_areas[0]))

    # Normalise area_filter to a set (None → no filtering)
    if area_filter is not None:
        if isinstance(area_filter, (int, float)):
            area_filter = {int(area_filter)}
        else:
            area_filter = {int(a) for a in area_filter}

    # Aggregate PMAX per bus (sum in-service machines)
    bus_pmax = {}
    for bus, status, pmax in zip(mach_buses, mach_status, mach_pmax):
        if status != 1:
            continue
        bus_pmax[bus] = bus_pmax.get(bus, 0.0) + pmax

    gen_buses = []
    for bus, total_pmax in bus_pmax.items():
        if total_pmax <= min_mw:
            continue
        area = bus_area_map.get(bus, -1)
        if area_filter is not None and area not in area_filter:
            continue
        gen_buses.append({
            'bus_num'   : bus,
            'kv'        : bus_kv_map.get(bus, 0.0),
            'area'      : area,
            'total_pmax': total_pmax,
        })

    area_msg = (f"area(s) {sorted(area_filter)}" if area_filter else "all areas")
    print(f"Found {len(gen_buses)} generator buses with PMAX > {min_mw:.0f} MW "
          f"({area_msg})")
    return gen_buses


# ----------ANGLE SENSITIVITY FUNCTION------------

def compute_angle_sensitivities(gen_buses, sav_case, base_voltage_lookup, delta_P=1.0):
    """
    Compute dTheta/dP for every bus in gen_buses.
    For each bus two perturbations are applied:
      +delta_P  →  theta_plus
      -delta_P  →  theta_minus

    Central difference:
      dTheta/dP = (theta_plus - theta_minus) / (2 * delta_P)   [deg / MW]
    """
    results = []

    load_case(sav_case)
    solve_power_flow()

    total = len(gen_buses)
    for idx, b in enumerate(gen_buses, 1):
        bus = b['bus_num']
        _, theta_base = get_bus_voltage_from_csv(bus, base_voltage_lookup)

        # --- dTheta/dP ---
        add_fictitious_load(bus, delta_P, 0.0)
        _, theta_plus = solve_and_get_voltage(bus)
        remove_fictitious_load(bus)

        add_fictitious_load(bus, -delta_P, 0.0)
        _, theta_minus = solve_and_get_voltage(bus)
        remove_fictitious_load(bus)

        if theta_plus is not None and theta_minus is not None:
            dtheta_dp = (theta_plus - theta_minus) / (2.0 * delta_P)
            results.append({
                'Bus'          : bus,
                'Area'         : b['area'],
                'kV'           : b['kv'],
                'Total_PMAX_MW': b['total_pmax'],
                'Theta0_deg'   : theta_base,
                'dTheta/dP'    : dtheta_dp,
                'theta_plus'   : theta_plus,
                'theta_minus'  : theta_minus,
            })

        if idx % 50 == 0 or idx == total:
            print(f"  Processed {idx}/{total} generator buses")

    return pd.DataFrame(results)


# ----------ANGLE SENSITIVITY PLOT----------------

def plot_angle_sensitivities(df, output_path, min_mw, area_filter=None):
    """
    Scatterplot of dTheta/dP (y) vs Total PMAX (x) for all generator buses.
    Points are color-coded by nominal voltage level (kV).
    """
    kv_levels   = sorted(df['kV'].unique())
    n_levels    = len(kv_levels)
    palette     = cm.get_cmap('tab10', n_levels)
    kv_to_color = {kv: palette(i) for i, kv in enumerate(kv_levels)}

    fig, ax = plt.subplots(figsize=(9, 7))

    for kv in kv_levels:
        subset = df[df['kV'] == kv]
        ax.scatter(
            subset['Total_PMAX_MW'],
            subset['dTheta/dP'],
            c=[kv_to_color[kv]],
            label=f'{kv:.0f} kV  (n={len(subset)})',
            alpha=0.75,
            edgecolors='white',
            linewidths=0.4,
            s=55,
        )

    ax.axhline(0, color='grey', linewidth=0.7, linestyle='--', zorder=0)

    ax.set_xlabel('Total PMAX  (MW)',         fontsize=12)
    ax.set_ylabel('dθ/dP  (deg / MW)',        fontsize=12)
    area_label = (f"Areas {sorted(area_filter)}" if area_filter else "All Areas")
    ax.set_title(
        f'Angle Sensitivities — Generator Buses PMAX > {min_mw:.0f} MW  |  {area_label}\n'
        f'(n = {len(df)} buses, central difference, Δ = {DELTA_P} MW)',
        fontsize=11,
    )
    ax.legend(title='Nominal kV', fontsize=9, title_fontsize=9,
              loc='best', framealpha=0.85)
    ax.grid(True, linestyle=':', linewidth=0.5, alpha=0.6)

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    plt.close()
    print(f"  Plot saved: {output_path}")

# ------------------------------------------------
# MAIN
# ------------------------------------------------
def main():
    
    # dV/dP and dV/dQ  : PQ buses without switched shunts, minkV <= kV <= maxkV
    # dTheta/dP        : in-service generator buses with PMAX > min_mw
    start = time.time() 
    # pointing to case location and output directory
    root = Path.cwd()
    case_dir = root/"PSSE_Cases"
    meta_dir = root/"Processing"

    config_name = 'Pre_Screening_config.csv'
    config = pd.read_csv(root/config_name)
    case_name = config[config.Variable == 'case_name']['Value'][0]
    temp = case_name+'_buses.csv'
    case_name = case_name+'.sav'
    sav_case = case_dir / case_name
    
    min_kv = int(config[config.Variable == 'voltage_sensitivity_minKV']['Value'].iloc[0])
    max_kv = int(config[config.Variable == 'voltage_sensitivity_maxKV']['Value'].iloc[0])

    # Optional area filter — comma-separated PSSE area numbers, e.g. "3,7,12"
    # Leave the cell blank (or omit the row entirely) to study all areas.
    area_row = config[config.Variable == 'area']
    if not area_row.empty and str(area_row['Value'].iloc[0]).strip()!='nan':
        area_filter = [int(a) for a in str(area_row['Value'].iloc[0]).split(',')]
        print(f"Area filter applied: {area_filter}")
    else:
        area_filter = None
        print("No area filter — studying all areas")

    base_voltage_df = pd.read_csv(meta_dir/temp)
    base_voltage_lookup = base_voltage_df.set_index('BUS_NUM')[['VM_PU', 'VA_DEG']].to_dict('index') 

    initialize_psse()
    load_case(str(sav_case))

    pq_buses = get_pq_buses_without_reactive_compensation(min_kv, max_kv, area_filter)

    print(f"\nComputing dV/dP and dV/dQ for {len(pq_buses)} buses...")
    df = compute_voltage_sensitivities(pq_buses,sav_case,base_voltage_lookup,delta_P=1,delta_Q=1)

    # --- single combined CSV ---
    csv_path  = meta_dir / 'voltage_sensitivities.csv'
    plot_path = meta_dir /'voltage_sensitivities_scatter.png'

    df.to_csv(csv_path, index=False)
    print(f"\nSensitivities saved: {csv_path}")
    print(df[['Bus', 'Area', 'kV', 'V0_pu', 'dV/dP', 'dV/dQ']].to_string(index=False))

    # --- scatterplot ---
    print("\nGenerating scatter plot...")
    plot_sensitivities(df, plot_path, min_kv, max_kv, area_filter)

    # ── ANGLE SENSITIVITY BLOCK ──────────────────────────────────────────────
    min_mw_row = config[config.Variable == 'angle_sensitivity_minMW']
    min_mw = float(min_mw_row['Value'].iloc[0]) if not min_mw_row.empty else 10.0
    print(f"\nAngle sensitivity threshold: PMAX > {min_mw:.0f} MW")

    gen_buses = get_generator_buses(min_mw, area_filter)
    
    print(f"\nComputing dTheta/dP for {len(gen_buses)} generator buses...")
    df_ang = compute_angle_sensitivities(gen_buses, sav_case, base_voltage_lookup, delta_P=DELTA_P)

    ang_csv_path  = meta_dir / 'angle_sensitivities.csv'
    ang_plot_path = meta_dir / 'angle_sensitivities_scatter.png'

    df_ang.to_csv(ang_csv_path, index=False)
    print(f"\nAngle sensitivities saved: {ang_csv_path}")
    print(df_ang[['Bus', 'Area', 'kV', 'Total_PMAX_MW', 'Theta0_deg', 'dTheta/dP']].to_string(index=False))

    print("\nGenerating angle sensitivity scatter plot...")
    plot_angle_sensitivities(df_ang, ang_plot_path, min_mw, area_filter)
    # ── END ANGLE SENSITIVITY BLOCK ──────────────────────────────────────────

    print(f"\nTotal runtime: {time.time() - start:.2f} seconds")


if __name__ == "__main__":
    main()