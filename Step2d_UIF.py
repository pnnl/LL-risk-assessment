# -*- coding: utf-8 -*-
"""
RATLLE — Risk Assessment Tool for Large Load Induced Events
To provide feedback or report bugs, please email shuchismita.biswas@pnnl.gov

Step 2d: Calculate fault current contribution based metrics to understand which generators
	are likely to pick up active power fluctuations induced by a data center load. 

	Unit Interaction Factor (UIF) screening (fault-simulation method)
	Current gain / load sharing metric screening (fault-simulation method)
Reference: R. Arritt et al, "Managing Oscillating Load Impacts from Data Centers on
Synchronous Machines" EPRI 2026.

Unit Interaction Factor:

    UIF_i = (S_LDDL / MBASE_i) * (1 - S_sc-i / S_sc) ** 2

Current Gain Based Load Sharing Metric:(1 - S_sc-i / S_sc)

where S_sc is the short-circuit MVA at the LDDL bus with the full system in
service and S_sc-i is the same with synchronous unit i out of service.
S_LDDL is considered 100 MVA for computation convenience.

How S_sc is measured in this implementation:
This implementation does not use the PSS/E fault analysis license. 
S_sc is measured from the base dynamics engine: initialize dynamics, apply a 
shunt fault at the LDDL bus with dist_bus_fault_3, read the faulted bus voltage at the subtransient instant
with chnval, and compute the Thevenin impedance. This method was validated
on the WECC 240-bus case.

SCALABILITY:
To keep the number of candidates small on a large system, generators are ranked 
by approximate electrical distance (impedance-weighted shortest path) from the 
LDDL bus and screened in expanding rings (10 closest electrical generators), 
stopping once two rings come back all clear (UIF<0.1 for all). 

Known limitations / assumptions:
  - Metrics are calculated from synchronous machines only (WMOD == 0).
  - UIF > 0.1 threshold is the classical subsynchronous interaction screening value.
  - LDDL nominal size S_LDDL is the module constant LDDL_MVA = 100, not read from config.
"""

import numpy as np
import pandas as pd
from pathlib import Path
from scipy.sparse import lil_matrix
from scipy.sparse.csgraph import dijkstra

from psse_config import configure_psse

psse_version = 35
psspy_version = 311
psspy = configure_psse(psse_version, psspy_version)

# --- Screening parameters ----------------------------------------------------
MIN_PGEN_MW = 10.0      # only screen synchronous units above this size
UIF_THRESHOLD = 0.1     # classical UIF threshold
LDDL_MVA = 100.0        # assumed prospective LDDL oscillation size (S_LDDL)
RING_SIZE = 10          # candidates evaluated per expanding ring
RESTRICT_TO_LDDL_AREA = False  # True: only screen units in the LDDL bus's own
                        # PSS/E area. False (default): rank all units by electrical
                        # distance and expand outward across area boundaries

# --- Fault-measurement parameters (validated in the diagnostic) --------------
FAULT_MVA = 12000.0     # shunt fault admittance (MVA)
DELTA_T = 0.0001        # integration step (s)
N_EARLY_POINTS = 4      # early post-fault points to fit for onset extrapolation
T_FLAT = 0.1            # flat settling run before applying the fault

# --- Ranking parameters ------------------------------------------------------
# Flat nominal reactance (pu, system base) for every transformer for shortest path search.
NOMINAL_XFMR_X_PU = 0.1

# ============================================================================
# Electrical-distance ranking (impedance-weighted shortest path)
# ============================================================================
# Ranks synchronous generators by accumulated series reactance along the
# shortest path from the LDDL bus -- an approximation of Thevenin impedance,
# used only to order candidates and decide when the expanding-ring search stops.

def assemble_edges_from_psse(bus_index, nominal_xfmr_x=NOMINAL_XFMR_X_PU):
    """
    Build the (from_bus, to_bus, x_pu) edge list for build_reactance_graph()
    from the loaded PSS/E case, without the transformer-impedance string codes.
    Lines: real series reactance from abrncplx
    Transformers: topology only (WIND1NUMBER/WIND2NUMBER) with a flat nominal reactance. 
    """
    edges = []

    ierr, br_from = psspy.abrnint(-1, 1, 1, 1, 1, 'FROMNUMBER')
    ierr, br_to = psspy.abrnint(-1, 1, 1, 1, 1, 'TONUMBER')
    ierr, br_stat = psspy.abrnint(-1, 1, 1, 1, 1, 'STATUS')
    ierr, br_rx = psspy.abrncplx(-1, 1, 1, 1, 1, 'RX')

    n_lines = 0
    for k in range(len(br_from[0])):
        if br_stat[0][k] != 1:
            continue
        x = br_rx[0][k].imag
        if x == 0:
            continue
        edges.append((br_from[0][k], br_to[0][k], abs(x)))
        n_lines += 1

    ierr, tr_from = psspy.atrnint(-1, 1, 1, 1, 1, 'WIND1NUMBER')
    ierr, tr_to = psspy.atrnint(-1, 1, 1, 1, 1, 'WIND2NUMBER')
    ierr, tr_stat = psspy.atrnint(-1, 1, 1, 1, 1, 'STATUS')

    n_xfmrs = 0
    if tr_from is not None and tr_from[0] is not None:
        for k in range(len(tr_from[0])):
            if tr_stat[0][k] != 1:
                continue
            edges.append((tr_from[0][k], tr_to[0][k], nominal_xfmr_x))
            n_xfmrs += 1
    else:
        print("  [!] atrnint('WIND1NUMBER') returned no transformer topology -- "
              "ranking graph will have NO transformer edges, which will strand "
              "generators that connect only through a transformer.")

    return edges, n_lines, n_xfmrs


def build_reactance_graph(edges, bus_index):
    """
    Symmetric sparse weighted adjacency, edge weight = |X| pu. Parallel
    elements between the same bus pair are combined in parallel.
    """
    n = len(bus_index)
    inv_x = {}
    for fb, tb, x in edges:
        if fb not in bus_index or tb not in bus_index:
            continue
        if fb == tb:
            continue
        x = abs(x)
        if x == 0:
            continue
        i, j = bus_index[fb], bus_index[tb]
        key = (i, j) if i < j else (j, i)
        inv_x[key] = inv_x.get(key, 0.0) + 1.0 / x

    graph = lil_matrix((n, n), dtype=float)
    for (i, j), inv in inv_x.items():
        x_combined = 1.0 / inv
        graph[i, j] = x_combined
        graph[j, i] = x_combined
    return graph.tocsr()

def rank_generators_by_reactance(graph, bus_index, lddl_bus, gen_buses):
    """
    Rank generator buses by accumulated path reactance from the LDDL bus,
    nearest first. 
    """
    src = bus_index[lddl_bus]
    dist = dijkstra(graph, directed=False, indices=src)
    ranked = []
    for gb in gen_buses:
        ranked.append((gb, dist[bus_index[gb]] if gb in bus_index else np.inf))
    ranked.sort(key=lambda t: t[1])
    return ranked

def init_psse():
    psspy.psseinit(200000)
    import redirect
    redirect.psse2py()

def load_case(sav_case):
    ierr = psspy.case(str(sav_case))
    if ierr != 0:
        raise RuntimeError(f"Could not load case (code {ierr}): {sav_case}")

def get_system_mva_base():
    sbase = psspy.sysmva()
    if not sbase:
        raise RuntimeError("Could not read system MVA base (psspy.sysmva).")
    return sbase

def get_bus_index_and_area():
    ierr, bus_num = psspy.abusint(-1, 1, 'NUMBER')
    ierr, bus_area = psspy.abusint(-1, 1, 'AREA')
    nums = bus_num[0]
    areas = bus_area[0]
    bus_index = {b: i for i, b in enumerate(nums)}
    area_of_bus = {b: a for b, a in zip(nums, areas)}
    return bus_index, area_of_bus

def get_synchronous_units(area_of_bus, min_pgen_mw=MIN_PGEN_MW):
    """
    Return in-service synchronous (WMOD == 0) generator units above the MW
    threshold, as a list of dicts:
        {bus, id, pgen_mw, mbase, area}
    These are both the screening candidates and the units eligible to be
    switched out of service for S_sc-i.
    """
    ierr, mac_bus = psspy.amachint(-1, 4, 'NUMBER')
    ierr, mac_stat = psspy.amachint(-1, 4, 'STATUS')
    ierr, mac_wmod = psspy.amachint(-1, 4, 'WMOD')
    ierr, mac_id = psspy.amachchar(-1, 4, 'ID')
    ierr, mac_pgen = psspy.amachreal(-1, 4, 'PGEN')
    ierr, mac_mbase = psspy.amachreal(-1, 4, 'MBASE')

    units = []
    n_nonsync = 0
    for k in range(len(mac_bus[0])):
        if mac_stat[0][k] != 1:
            continue
        if mac_wmod[0][k] != 0:
            n_nonsync += 1
            continue
        if mac_pgen[0][k] <= min_pgen_mw:
            continue
        if mac_mbase[0][k] == 0:
            continue
        bus = mac_bus[0][k]
        units.append({
            'bus': bus,
            'id': mac_id[0][k].strip(),
            'pgen_mw': mac_pgen[0][k],
            'mbase': mac_mbase[0][k],
            'area': area_of_bus.get(bus),
        })
    if n_nonsync:
        print(f"  ({n_nonsync} non-synchronous machines excluded from candidacy)")
    return units

def initialize_dynamic_simulation():
    """Convert/order/factor/solve sequence"""
    psspy.fnsl([0, 0, 0, 1, 0, 0, 0, 0])
    psspy.cong(0)
    psspy.conl(0, 1, 1, [0, 0], [0.0, 0.0, 0.0, 0.0])
    psspy.conl(0, 1, 2, [0, 0], [0.0, 0.0, 0.0, 0.0])
    psspy.conl(0, 1, 3, [0, 0], [0.0, 0.0, 0.0, 0.0])
    psspy.ordr()
    psspy.fact()
    psspy.tysl(0)

def measure_scc(sav_case, dyr_case, fault_bus, sys_mva, out_file,
                machine_out=None):
    """
    Measure short-circuit MVA at fault_bus by fault simulation, optionally
    with one machine taken out of service first.

    Parameters
    ----------
    machine_out : (bus, id) or None
        If given, that machine is set STAT=0 before initialization, so the
        measured S_sc reflects the system with that unit removed (S_sc-i).

    Returns
    -------
    s_sc : float, short-circuit MVA at fault_bus
    v_pre, v_onset : the prefault and extrapolated-onset voltages (for logging)
    """
    load_case(sav_case)

    if machine_out is not None:
        mbus, mid = machine_out
        # Set only the STATUS field of the machine to 0 (out of service),
        # leaving all other machine data unchanged. psspy._i is PSS/E's
        # "leave unchanged" integer sentinel; psspy._f the real one.
        intgar = [0, psspy._i, psspy._i, psspy._i, psspy._i, psspy._i]
        realgar = [psspy._f] * 17
        ierr = psspy.machine_chng_2(mbus, mid, intgar, realgar)
        if ierr != 0:
            raise RuntimeError(
                f"Could not set machine {mbus} '{mid}' out of service "
                f"(ierr={ierr}). Check the machine_chng_2 argument counts "
                f"(intgar/realgar lengths) against your PSS/E version."
            )

    dyr_loaded = psspy.dyre_new([1, 1, 1, 1], str(dyr_case), "", "", "")
    initialize_dynamic_simulation()

    psspy.delete_all_plot_channels()
    psspy.voltage_and_angle_channel([-1, -1, -1, fault_bus])
    v_channel = 1

    val_i = psspy.getdefaultint()
    _f = psspy.getdefaultreal()
    psspy.dynamics_solution_params(
        [99, val_i, val_i, val_i, val_i, val_i, val_i, val_i],
        [1.0, _f, DELTA_T, 0.016, _f, _f, _f, _f], ''
    )
    psspy.strt_2([0, 0], out_file)

    psspy.run(0, T_FLAT, 0, 0, 0)
    ierr, v_pre = psspy.chnval(v_channel)
    if ierr != 0:
        raise RuntimeError(f"chnval prefault failed (ierr={ierr}).")

    options = [1, 1, fault_bus, 0, 1]
    values = [0.0, -FAULT_MVA, 0.0, 0.0, 0.0, 0.0]
    ierr = psspy.dist_bus_fault_3(1, 0.0, options, values)
    if ierr != 0:
        raise RuntimeError(f"dist_bus_fault_3 failed (ierr={ierr}) at bus "
                           f"{fault_bus}.")

    times, volts = [], []
    for m in range(1, N_EARLY_POINTS + 1):
        psspy.run(0, T_FLAT + m * DELTA_T, 0, 0, 0)
        ierr, v = psspy.chnval(v_channel)
        if ierr != 0:
            raise RuntimeError(f"chnval failed mid-fault (ierr={ierr}).")
        times.append(m * DELTA_T)
        volts.append(v)

    coeffs = np.polyfit(times, volts, 1)
    v_onset = coeffs[1]

    psspy.dist_clear_fault(1)

    y_fault_pu = FAULT_MVA / sys_mva
    z_th_pu = (v_pre / v_onset - 1.0) / y_fault_pu
    s_sc = sys_mva / abs(z_th_pu)
    return s_sc, v_pre, v_onset


def compute_uif_csm(sav_case, dyr_case, lddl_bus, out_dir):
    sys_mva = get_system_mva_base_from_case(sav_case)
    out_file = str(Path(out_dir) / f"uif_fault_{lddl_bus}.out")

    # --- Baseline S_sc (measured once, reused for every candidate) ----------
    print("Measuring baseline short-circuit capacity at LDDL bus...")
    s_sc, v_pre, v_onset = measure_scc(sav_case, dyr_case, lddl_bus, sys_mva,
                                       out_file)
    print(f"  S_sc at bus {lddl_bus} = {s_sc:.1f} MVA "
          f"(V {v_pre:.4f} -> {v_onset:.4f} pu under fault)")

    # --- Build candidate list + ranking (needs a loaded case) ---------------
    load_case(sav_case)
    bus_index, area_of_bus = get_bus_index_and_area()
    if lddl_bus not in bus_index:
        raise ValueError(f"LDDL bus {lddl_bus} not in case.")
    load_area = area_of_bus[lddl_bus]

    units = get_synchronous_units(area_of_bus)
    if RESTRICT_TO_LDDL_AREA:
        units = [u for u in units if u['area'] == load_area]
        print(f"{len(units)} synchronous candidate unit(s) in LDDL area "
              f"{load_area} (RESTRICT_TO_LDDL_AREA=True).")
    else:
        print(f"{len(units)} synchronous candidate unit(s) system-wide "
              f"(ranked by electrical distance; area filter off).")

    if not units:
        return pd.DataFrame(), s_sc

    edges, n_lines, n_xfmrs = assemble_edges_from_psse(bus_index)
    print(f"  Ranking graph: {n_lines} lines, {n_xfmrs} transformers.")
    graph = build_reactance_graph(edges, bus_index)
    gen_buses = [u['bus'] for u in units]
    ranked = rank_generators_by_reactance(graph, bus_index, lddl_bus, gen_buses)
    # Order the unit dicts by the ranked bus order (stable: keep unit objects,
    # not just buses, so multi-unit buses are all screened).
    rank_pos = {gb: pos for pos, (gb, _d) in enumerate(ranked)}
    units_ranked = sorted(units, key=lambda u: rank_pos.get(u['bus'], 1e9))

    # --- Expanding-ring screening -------------------------------------------
    results = []
    clear_rings_seen = 0   # consecutive all-clear rings; stop after 2 (guard)
    n = len(units_ranked)
    ring_start = 0
    ring_idx = 0
    while ring_start < n:
        ring = units_ranked[ring_start:ring_start + RING_SIZE]
        ring_idx += 1
        print(f"\n--- Ring {ring_idx}: candidates {ring_start + 1}"
              f"-{ring_start + len(ring)} of {n} ---")
        ring_had_flag = False

        for u in ring:
            s_sc_minus_i, _, _ = measure_scc(
                sav_case, dyr_case, lddl_bus, sys_mva, out_file,
                machine_out=(u['bus'], u['id'])
            )
            uif = (LDDL_MVA / u['mbase']) * (1 - s_sc_minus_i / s_sc) ** 2
            csm = (1 - s_sc_minus_i / s_sc)

            # Sanity invariants (removing a source cannot strengthen the grid;
            # UIF cannot exceed its S_LDDL/MBASE ceiling)
            ordering_ok = s_sc_minus_i <= s_sc * (1 + 1e-6)
            ceiling_ok = uif <= (LDDL_MVA / u['mbase']) * (1 + 1e-6)
            invariants_ok = ordering_ok and ceiling_ok and uif >= -1e-6

            above = uif > UIF_THRESHOLD
            if above:
                ring_had_flag = True

            results.append({
                'BUS_NUM': u['bus'], 'ID': u['id'],
                'PGEN_MW': u['pgen_mw'], 'MBASE_MVA': u['mbase'],
                'S_SC_MINUS_I_MVA': s_sc_minus_i, 'S_SC_MVA': s_sc,
                'UIF': uif, 'Load_sharing_metric':csm,'ABOVE_THRESHOLD': above,
                'INVARIANTS_OK': invariants_ok,
                'RING': ring_idx,
            })
            flag = "  <-- ABOVE 0.1" if above else ""
            inv = "" if invariants_ok else "  [!] INVARIANT FAIL"
            print(f"    bus {u['bus']:<7} id {u['id']:<3} "
                  f"UIF={uif:.4f}{flag}{inv}")

        ring_start += RING_SIZE

        if ring_had_flag:
            clear_rings_seen = 0
        else:
            clear_rings_seen += 1
            print(f"    (ring all-clear; {clear_rings_seen} consecutive)")
            if clear_rings_seen >= 2:
                print("\nTwo consecutive all-clear rings -- stopping search. "
                      "Remaining, more-distant units are assumed below threshold "
                      "(guard ring already confirmed).")
                break

    df = pd.DataFrame(results).sort_values('UIF', ascending=False).reset_index(drop=True)
    return df, s_sc

def get_system_mva_base_from_case(sav_case):
    """Load the case once just to read the system base (measure_scc reloads it)."""
    load_case(sav_case)
    return get_system_mva_base()

def main():
    root = Path.cwd()
    case_dir = root / "PSSE_Cases"
    out_dir = root / "Processing"
    out_dir.mkdir(exist_ok=True)

    config = pd.read_csv(root / 'modal_analysis_config.csv')

    def _cfg(var, cast=str):
        row = config[config.Variable == var]
        if row.empty:
            raise ValueError(f"'{var}' not found in modal_analysis_config.csv.")
        return cast(row['Value'].iloc[0])

    case_name = _cfg('case_name')
    dyr_name = _cfg('dyr_name')
    lddl_bus = _cfg('bus_number', int)
    sav_case = case_dir / f"{case_name}.sav"
    dyr_case = case_dir / f"{dyr_name}.dyr"

    init_psse()
    df, s_sc = compute_uif_csm(sav_case, dyr_case, lddl_bus, out_dir)

    out_csv = out_dir / f"UIF_{lddl_bus}.csv"
    df.to_csv(out_csv, index=False)

    print("\n" + "=" * 60)
    print(f"UIF screening complete. Baseline S_sc = {s_sc:.1f} MVA")
    print(f"{len(df)} unit(s) evaluated; "
          f"{int(df['ABOVE_THRESHOLD'].sum()) if not df.empty else 0} above {UIF_THRESHOLD}.")
    print(f"Saved: {out_csv}")


if __name__ == "__main__":
    main()