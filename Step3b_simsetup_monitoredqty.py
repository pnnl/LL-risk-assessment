"""
Step before starting simulation - shortlisting which channels to log during simulation
Value thresholds can be edited

  monitored_loads.csv       - In-service loads > 50 MW in the source area
  monitored_buses.csv       - In-service buses > 100 kV in the source area
  monitored_generators.csv  - In-service generator buses with aggregated Pgen > 50 MW
                              in the source area
  monitored_lines.csv       - In-service lines > 100 kV in the source area
                              + all in-service inter-area tie lines

All filters consider only in-service elements.
"""

import csv
import os
from pathlib import Path
from collections import defaultdict

# Helper functions
def read_csv(path):
    """Read a CSV into a list of dicts with auto-typed numeric fields."""
    rows = []
    with open(path, newline='') as f:
        for row in csv.DictReader(f):
            typed = {}
            for k, v in row.items():
                v = v.strip()
                try:
                    typed[k] = int(v)
                except ValueError:
                    try:
                        typed[k] = float(v)
                    except ValueError:
                        typed[k] = v
            rows.append(typed)
    return rows


def write_csv(path, rows, headers):
    """Write a list of dicts to CSV using the given column order."""
    with open(path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=headers, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(rows)
    print(f"  {path.name}: {len(rows)} rows")


# ---------------------------------------------------------------------------
# Parallel circuit detection
# ---------------------------------------------------------------------------

def build_parallel_lookup(branches):
    """
    Return a set of bus pairs that have more than one circuit.

    Returns
    -------
    set of frozenset({from_bus, to_bus}) where circuit count > 1
    """
    circuit_count = defaultdict(int)
    for row in branches:
        pair = frozenset({row['FROM_BUS'], row['TO_BUS']})
        circuit_count[pair] += 1

    return {pair for pair, count in circuit_count.items() if count > 1}

#  identify the source bus area
def get_source_area(buses, source_bus):
    """Return the area number of the source bus."""
    for b in buses:
        if b['BUS_NUM'] == source_bus:
            return b['AREA']
    raise ValueError(f"Source bus {source_bus} not found in buses CSV.")

# build lookup: bus_num -> area  (needed for tie-line detection)
def build_bus_area_lookup(buses):
    return {b['BUS_NUM']: b['AREA'] for b in buses}

# ---------------------------------------------------------------------------
# Filter 1 — monitored loads
#   Criteria:
#     - STAT == 1          (in-service)
#     - PTOTAL_MW > 50     
# ---------------------------------------------------------------------------

def filter_loads(loads, source_area):
    result = []
    for row in loads:
        if (row['STAT'] == 1
                and row['PTOTAL_MW'] > 50.0):
            result.append(row)
    return result


LOAD_HEADERS = [
    'BUS_NUM', 'ID', 'STAT', 'AREA', 'ZONE', 'OWNER',
    'PL_MW', 'QL_MVAR',
    'IP_MW', 'IQ_MVAR',
    'YP_MW', 'YQ_MVAR',
    'PTOTAL_MW', 'QTOTAL_MVAR',
    'BUS_KV', 'VM_PU', 'VA_DEG'
]


# ---------------------------------------------------------------------------
# Filter 2 — monitored buses
#   Criteria:
#     - TYPE != 4          (type 4 = isolated / out-of-service)
#     - AREA == source_area
#     - BASKV > 100        (nominal voltage > 100 kV)
# ---------------------------------------------------------------------------

def filter_buses(buses, source_area):
    result = []
    for row in buses:
        if (row['TYPE'] != 4
                and row['AREA'] == source_area
                and row['BASKV'] > 100.0):
            result.append(row)
    return result


BUS_HEADERS = [
    'BUS_NUM', 'NAME', 'BASKV', 'TYPE', 'AREA', 'ZONE', 'OWNER',
    'VM_PU', 'VA_DEG',
    'NVHI', 'NVLO', 'EVHI', 'EVLO',
    'PGEN_MW', 'QGEN_MVAR', 'PLOAD_MW', 'QLOAD_MVAR',
    'PINJ_MW', 'QINJ_MVAR'
]


# ---------------------------------------------------------------------------
# Filter 3 — monitored generator buses
#   Criteria (applied to individual machine rows first):
#     - STAT == 1          (machine in-service)
#   Then aggregate per bus:
#     - sum(PGEN_MW) > 50  (total dispatched generation at the bus)
#
#   Output is one row per qualifying BUS_NUM with aggregated totals.
#   Capability limits (Pmax, Qmax etc.) are summed across machines at the bus.
# ---------------------------------------------------------------------------

def filter_generators(generators, source_area):
    # Accumulate per-bus aggregates for in-service machines in the source area
    agg = defaultdict(lambda: {
        'PGEN_MW': 0.0, 'QGEN_MVAR': 0.0,
        'PMAX_MW': 0.0, 'PMIN_MW': 0.0,
        'QMAX_MVAR': 0.0, 'QMIN_MVAR': 0.0,
        'MBASE_MVA': 0.0,
        'MACHINE_COUNT': 0,
        # Keep bus-level info from the first machine seen (same for all at a bus)
        'AREA': 0, 'ZONE': 0, 'BUS_KV': 0.0, 'VM_PU': 0.0, 'VA_DEG': 0.0
    })

    for row in generators:
        if row['STAT'] != 1:
            continue
        bus = row['BUS_NUM']
        a = agg[bus]
        a['PGEN_MW']    += row['PGEN_MW']
        a['QGEN_MVAR']  += row['QGEN_MVAR']
        a['PMAX_MW']    += row['PMAX_MW']
        a['PMIN_MW']    += row['PMIN_MW']
        a['QMAX_MVAR']  += row['QMAX_MVAR']
        a['QMIN_MVAR']  += row['QMIN_MVAR']
        a['MBASE_MVA']  += row['MBASE_MVA']
        a['MACHINE_COUNT'] += 1
        # Overwrite bus-level fields each time (identical for same bus)
        a['AREA']    = row['AREA']
        a['ZONE']    = row['ZONE']
        a['BUS_KV']  = row['BUS_KV']
        a['VM_PU']   = row['VM_PU']
        a['VA_DEG']  = row['VA_DEG']

    # Keep only buses where total dispatch exceeds threshold
    result = []
    for bus_num, a in agg.items():
        if a['PGEN_MW'] > 50.0:
            result.append({'BUS_NUM': bus_num, **a})

    result.sort(key=lambda r: r['BUS_NUM'])
    return result


GEN_HEADERS = [
    'BUS_NUM', 'MACHINE_COUNT', 'AREA', 'ZONE',
    'PGEN_MW', 'QGEN_MVAR',
    'PMAX_MW', 'PMIN_MW', 'QMAX_MVAR', 'QMIN_MVAR',
    'MBASE_MVA',
    'BUS_KV', 'VM_PU', 'VA_DEG'
]


# ---------------------------------------------------------------------------
# Filter 4 — monitored lines
#   Two inclusion criteria:
#
#   A. In-area high-voltage line:
#      - STAT == 1
#      - FROM_KV > 100 AND TO_KV > 100   (both ends are HV)
#      - from_bus area == source_area AND to_bus area == source_area
#
#   B. Inter-area tie line:
#      - STAT == 1
#      - from_bus area != to_bus area     (crosses an area boundary)
#        NOTE: one end may still be in the source area; we include ALL ties
#        so the full picture of power flowing in/out is visible.
#
#   A 'TIE_LINE' flag column is added so the two categories are distinguishable.
# ---------------------------------------------------------------------------

def filter_lines(branches, bus_area_lu, source_area, parallel_pairs):
    """
    parallel_pairs : set of frozenset({from_bus, to_bus}) with >1 circuit.

    Adds two columns to every output row:
      PARALLEL       - 1 if another circuit exists between the same bus pair
                       (in any status / area), 0 otherwise
      PARALLEL_COUNT - total number of circuits between that bus pair
                       (includes out-of-service siblings)
    """
    # Pre-build a count dict for the PARALLEL_COUNT column
    circuit_count = defaultdict(int)
    for row in branches:
        circuit_count[frozenset({row['FROM_BUS'], row['TO_BUS']})] += 1

    result = []
    for row in branches:
        if row['STAT'] != 1:
            continue

        from_area = bus_area_lu.get(row['FROM_BUS'], -1)
        to_area   = bus_area_lu.get(row['TO_BUS'],   -1)

        is_tie       = (from_area != to_area)
        is_inarea_hv = (
            from_area == source_area
            and to_area == source_area
            and row['FROM_KV'] > 100.0
            and row['TO_KV']   > 100.0
        )

        if is_inarea_hv or is_tie:
            pair                 = frozenset({row['FROM_BUS'], row['TO_BUS']})
            row['TIE_LINE']      = 1 if is_tie          else 0
            row['FROM_AREA']     = from_area
            row['TO_AREA']       = to_area
            row['PARALLEL']      = 1 if pair in parallel_pairs else 0
            row['PARALLEL_COUNT']= circuit_count[pair]
            result.append(row)

    return result


LINE_HEADERS = [
    'FROM_BUS', 'TO_BUS', 'CKT', 'STAT',
    'FROM_KV', 'TO_KV', 'FROM_AREA', 'TO_AREA', 'TIE_LINE',
    'PARALLEL', 'PARALLEL_COUNT',
    'R_PU', 'X_PU', 'B_PU',
    'RATE_A_MVA', 'RATE_B_MVA', 'RATE_C_MVA',
    'LENGTH',
    'P_FROM_MW', 'Q_FROM_MVAR', 'P_TO_MW', 'Q_TO_MVAR',
    'MVA', 'LOADING_PCT', 'PLOSS_MW', 'QLOSS_MVAR'
]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def channels(source_bus, data_dir, case_stem):
    data_dir = Path(data_dir)

    # --- load input CSVs ---
    print(f"\nReading CSVs from: {data_dir}")
    buses      = read_csv(data_dir / f"{case_stem}_buses.csv")
    branches   = read_csv(data_dir / f"{case_stem}_branches.csv")
    generators = read_csv(data_dir / f"{case_stem}_generators.csv")
    loads      = read_csv(data_dir / f"{case_stem}_loads.csv")
    print(f"  Loaded {len(buses)} buses, {len(branches)} branches, "
          f"{len(generators)} generators, {len(loads)} loads")

    # --- identify source area ---
    source_area   = get_source_area(buses, source_bus)
    bus_area_lu   = build_bus_area_lookup(buses)
    parallel_pairs = build_parallel_lookup(branches)
    print(f"\nSource bus : {source_bus}")
    print(f"Source area: {source_area}")
    print(f"Bus pairs with parallel circuits: {len(parallel_pairs)}")

    # --- apply filters ---
    print("\nBuilding monitored sets:")
    monitored_loads = filter_loads(loads, source_area)
    monitored_buses = filter_buses(buses, source_area)
    monitored_gens  = filter_generators(generators, source_area)
    monitored_lines = filter_lines(branches, bus_area_lu, source_area, parallel_pairs)

    # --- write outputs ---
    print("\nWriting monitored CSVs:")
    write_csv(data_dir / "monitored_loads.csv",      monitored_loads, LOAD_HEADERS)
    write_csv(data_dir / "monitored_buses.csv",      monitored_buses, BUS_HEADERS)
    write_csv(data_dir / "monitored_generators.csv", monitored_gens,  GEN_HEADERS)
    write_csv(data_dir / "monitored_lines.csv",      monitored_lines, LINE_HEADERS)

    # --- console summary ---
    in_area_lines = sum(1 for r in monitored_lines if r['TIE_LINE'] == 0)
    tie_lines     = sum(1 for r in monitored_lines if r['TIE_LINE'] == 1)
    parallel_lines= sum(1 for r in monitored_lines if r['PARALLEL'] == 1)

    print(f"""
Summary for source bus {source_bus} (area {source_area}):
  Monitored loads       : {len(monitored_loads):>5}  (in-service, >50 MW, in area)
  Monitored buses       : {len(monitored_buses):>5}  (in-service, >100 kV, in area)
  Monitored gen buses   : {len(monitored_gens):>5}  (in-service, aggregated >50 MW, in area)
  Monitored lines       : {len(monitored_lines):>5}  total
    - In-area HV lines  : {in_area_lines:>5}  (>100 kV, both ends in area)
    - Inter-area ties   : {tie_lines:>5}  (crosses area boundary)
    - With parallel ckt : {parallel_lines:>5}  (PARALLEL=1, any status sibling)
""")


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import pandas as pd 
    root = Path.cwd()
    data_dir = root/"Processing"
    config_params = pd.read_csv(root/"simulation_config.csv")
    source_bus = int(config_params[config_params.Variable=='bus_number']['Value'].iloc[0])
    case_stem = config_params[config_params.Variable=='case_name']['Value'][0]
    channels(source_bus, data_dir, case_stem)