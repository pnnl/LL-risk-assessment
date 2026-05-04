# -*- coding: utf-8 -*-
"""
Created on Tue Mar 17 22:48:05 2026

@author: bisw757
"""

"""
Step5_analyzesim.py
====================
Analyses simulation output and writes metric CSVs
plus a worst-offender time-series JSON for subsequent visualization.

Updated for unified temp.csv input with new column naming conventions:

  Generators : POWR <bus>[<name> <kv>]<ckt>   — active power   (was pg)
               VARS <bus>[<name> <kv>]<ckt>   — reactive power  (was qg)
               ETRM <bus>[<name> <kv>]<ckt>   — terminal volt   (was vt)
               ANGL <bus>[<name> <kv>]<ckt>   — voltage angle   (was abus)
  Buses      : VOLT <bus> [<name> <kv>]        — voltage mag     (was vbus)
               ANGL <bus> [<name> <kv>]        — voltage angle   (was abus)
  Loads      : PLOD <bus>[<name> <kv>]<id>    — active power    (was pld)
               VOLT <bus> [<name> <kv>]        — bus voltage     (was vbul, shared with buses)
  Lines      : LINE_<from>_<to>_<ckt>_P / _Q  (was pbr / qbr)
  LDDL       : LDDL P  |  LDDL Q  |  LDDL OS P  |  LDDL OS Q  |  LDDL BUS VOLTAGE

Generator vs bus disambiguation for shared ANGL/VOLT prefix:
  Bus numbers appearing in POWR columns are treated as generator buses.
  Their ANGL columns are gen angles; all others are bus angles.
  VOLT columns are treated as bus voltages for all buses (loads included).
"""

import os, re, json
import numpy as np
import pandas as pd
from pathlib import Path

# ── RARELY NEED CHANGING ──────────────────────────────────────────────────
HV_THRESHOLD_KV       = 10.0      # kV  — minimum base kV for "HV bus"
F_NOM                 = 60.0      # Hz  — nominal system frequency
TIMESERIES_MAX_POINTS = 3000      # max points per downsampled time series

# Simulator outputs power in per-unit on a 100 MVA system base.
# Multiplying by POWER_SCALE converts to MW / MVar.
# Applied to: POWR, VARS (generators), PLOD (loads),
#             LDDL P / Q / OS P / OS Q (NOT LDDL BUS VOLTAGE).
# Voltage, angle, and frequency signals are left unscaled.
POWER_SCALE = 100.0

# These are populated at runtime by main() from simulation_config.csv.
# Do not edit here — edit simulation_config.csv instead.
OSCILLATION_FREQ_HZ = None   # Hz  — oscillation frequency (defines cycle length)
START_TIME_SEC      = 1.0    # sec — discard simulation startup transient

# ── Resolved at runtime by main() ────────────────────────────────────────
SIM_FILE   = None   # path to the simulation CSV (results/<bus>_sim.csv)
META_DIR   = None   # Processing/ folder
OUTPUT_DIR = None   # results/ folder
META_FILES = {}     # populated once case_name is known

# LDDL column names — exact match against sim CSV headers
LDDL_COLS = {
    "P":           "LDDL P",
    "Q":           "LDDL Q",
    "OS_P":        "LDDL OS P",
    "OS_Q":        "LDDL OS Q",
    "BUS_VOLTAGE": "LDDL BUS VOLTAGE",
}

# ── Risk thresholds used for flagging in the summary CSV ─────────────────
# These mirror the THRESHOLDS dict in Step6 — edit both together if changed.
RISK_THRESHOLDS = dict(
    gen_pg_swing_mw     = 5.0,    # MW   — generator active power swing
    gen_qg_swing_mvar   = 5.0,    # MVar — generator reactive power swing
    gen_vt_swing_pu     = 0.05,   # pu   — generator terminal voltage swing
    gen_freq_swing_hz   = 0.03,   # Hz   — generator frequency swing
    gen_angle_swing_deg = 10.0,   # deg  — generator angle swing
    line_pbr_swing_mw   = 20.0,   # MW   — line active power swing
    line_pbr_swing_pct  = 10.0,   # %    — line P swing as % of thermal rating
    bus_v_swing_pu      = 0.05,   # pu   — HV bus voltage swing
    bus_v_hi_pu         = 1.10,   # pu   — HV bus voltage upper envelope
    bus_v_lo_pu         = 0.90,   # pu   — HV bus voltage lower envelope
    load_pld_swing_mw   = 5.0,    # MW   — load active power swing
    lddl_p_swing_mw     = 5.0,    # MW   — LDDL P swing
    lddl_q_swing_mvar   = 5.0,    # MVar — LDDL Q swing
    lddl_v_swing_pu     = 0.05,   # pu   — LDDL bus voltage swing
)


# ═══════════════════════════════════════════════════════════════════════════
# PEAK-TO-PEAK SWING
# ═══════════════════════════════════════════════════════════════════════════

def max_peak_to_peak_per_cycle(y, t, f):
    y = np.asarray(y)
    t = np.asarray(t)
    # print(f)
    if y.ndim == 1:
        y = y[:, np.newaxis]

    dt = t[2] - t[1]
    # print(dt)
    T  = 1 / f
    samples_per_cycle = int(T / dt)

    num_cycles = y.shape[0] // samples_per_cycle
    if num_cycles == 0:
        raise ValueError("Not enough samples for even one full cycle.")

    y_trunc  = y[:num_cycles * samples_per_cycle, :]
    y_cycles = y_trunc.reshape(num_cycles, samples_per_cycle, y.shape[1])

    ptp_per_cycle = y_cycles.max(axis=1) - y_cycles.min(axis=1)
    return np.max(ptp_per_cycle, axis=0)


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def load_sim():
    """Load the unified simulation CSV; trim startup transient; return (t, df).
    Used for metric computation — excludes the flat pre-oscillation period."""
    df       = pd.read_csv(str(SIM_FILE))
    df = df.drop_duplicates(subset=df.columns[0]) # drop duplicate time steps, right now keeps the first row
    time_col = df.columns[0]
    df       = df[df[time_col] > START_TIME_SEC].reset_index(drop=True)
    t        = df[time_col].to_numpy()
    return t, df


def load_sim_full():
    """Load the full simulation CSV without trimming; return (t, df).
    Used for time-series plots so the complete waveform is shown from t=0."""
    df       = pd.read_csv(str(SIM_FILE))
    time_col = df.columns[0]
    t        = df[time_col].to_numpy()
    t        = t - t[0]          # shift so axis always starts at 0
    return t, df


def load_meta(key):
    """Load a metadata CSV."""
    return pd.read_csv(os.path.join(str(META_DIR), META_FILES[key]))


def extract_bus_nums(col):
    """Return list of all 4-6 digit integers found in a column name."""
    return [int(x) for x in re.findall(r'\b(\d{4,6})\b', col)]


def prefix_of(col):
    """Return the first whitespace-delimited token of a column name (lowercase)."""
    return col.split()[0].lower()


def cols_by_prefix(df, prefix):
    """Return all columns whose first token matches prefix (case-insensitive)."""
    return [c for c in df.columns if prefix_of(c) == prefix.lower()]


def line_cols(df):
    """
    Parse all LINE_<from>_<to>_<ckt>_P/Q columns.
    Returns list of (col_name, from_bus, to_bus, ckt, 'P'|'Q').
    """
    pattern = re.compile(r'^LINE_(\d+)_(\d+)_(\d+)_(P|Q)$', re.IGNORECASE)
    result  = []
    for col in df.columns:
        m = pattern.match(col)
        if m:
            result.append((col, int(m.group(1)), int(m.group(2)),
                           int(m.group(3)), m.group(4).upper()))
    return result


def ptp(arr2d, t):
    """Convenience wrapper; arr2d shape is (samples,) or (samples, signals)."""
    return max_peak_to_peak_per_cycle(arr2d, t, OSCILLATION_FREQ_HZ)


def derive_freq(abus_arr, t):
    """Compute instantaneous frequency (Hz) from bus angle (degrees) array."""
    dt_scalar = float(np.median(np.diff(t)))
    if dt_scalar <= 0:
        raise ValueError(f"derive_freq: non-positive median dt={dt_scalar}. Check time column.")
    d_angle = np.diff(abus_arr, prepend=abus_arr[0])
    return F_NOM + d_angle / (360.0 * dt_scalar)


def round6(lst):
    return [round(float(v), 6) for v in lst]


def gen_bus_set(df):
    """Return set of bus numbers identified as generator buses (appear in POWR columns)."""
    nums = set()
    for col in cols_by_prefix(df, "powr"):
        n = extract_bus_nums(col)
        if n:
            nums.add(n[0])
    return nums


def build_vbus_lookup(t, df):
    """
    Build {bus_num: {vbus_init, vbus_swing, vbus_max, vbus_min}} from all VOLT columns.
    VOLT columns cover both regular and load buses; the lookup is used by all processors.
    """
    lookup = {}
    for col in cols_by_prefix(df, "volt"):
        nums = extract_bus_nums(col)
        if not nums:
            continue
        bus_num = nums[0]
        arr     = df[col].to_numpy()
        lookup[bus_num] = {
            "vbus_init":  arr[0],
            "vbus_swing": ptp(arr, t)[0],
            "vbus_max":   arr.max(),
            "vbus_min":   arr.min(),
        }
    print(f"-> Bus voltage lookup built: {len(lookup)} buses")
    return lookup


# ═══════════════════════════════════════════════════════════════════════════
# GENERATORS
# ═══════════════════════════════════════════════════════════════════════════

def process_generators(t, df, meta_gen, meta_bus, vbus_lookup):
    """
    Columns used:
      POWR  → active power  (pg)
      VARS  → reactive power (qg)
      ETRM  → terminal voltage (vt)
      ANGL  → voltage angle for gen buses (abus)
    """
    powr_cols = cols_by_prefix(df, "powr")
    rows = []

    for powr_col in powr_cols:
        bus = extract_bus_nums(powr_col)
        if not bus:
            continue
        bus_num = bus[0]

        def match(pfx):
            cands = [c for c in cols_by_prefix(df, pfx)
                     if extract_bus_nums(c) and extract_bus_nums(c)[0] == bus_num]
            return cands[0] if cands else None

        vars_col = match("vars")
        etrm_col = match("etrm")
        angl_col = match("angl")   # bus_num guaranteed to be gen bus

        pg_arr   = df[powr_col].to_numpy() * POWER_SCALE
        qg_arr   = df[vars_col].to_numpy() * POWER_SCALE if vars_col else np.zeros_like(pg_arr)
        vt_arr   = df[etrm_col].to_numpy()               if etrm_col else np.zeros_like(pg_arr)
        abus_arr = df[angl_col].to_numpy()               if angl_col else np.zeros_like(pg_arr)
        freq_arr = derive_freq(abus_arr, t)

        mat    = np.column_stack([pg_arr, qg_arr, vt_arr, abus_arr, freq_arr])
        swings = ptp(mat, t)

        vb = vbus_lookup.get(bus_num, {})

        rows.append({
            "bus_num":     bus_num,
            "pg_init":     pg_arr[0],
            "qg_init":     qg_arr[0],
            "vbus_init":   vb.get("vbus_init"),
            "vbus_swing":  vb.get("vbus_swing"),
            "vbus_max":    vb.get("vbus_max"),
            "vbus_min":    vb.get("vbus_min"),
            "pg_swing":    swings[0],
            "qg_swing":    swings[1],
            "vt_swing":    swings[2],
            "angle_swing": swings[3],
            "freq_swing":  swings[4],
            "pg_max":      pg_arr.max(),
            "pg_min":      pg_arr.min(),
            "qg_max":      qg_arr.max(),
            "qg_min":      qg_arr.min(),
        })

    df_out = pd.DataFrame(rows)

    agg = meta_gen.groupby("BUS_NUM", as_index=False).agg(
        PMAX_MW   =("PMAX_MW",   "sum"),
        PMIN_MW   =("PMIN_MW",   "sum"),
        QMAX_MVAR =("QMAX_MVAR", "sum"),
        QMIN_MVAR =("QMIN_MVAR", "sum"),
        MBASE_MVA =("MBASE_MVA", "sum"),
    )
    df_out = df_out.merge(agg, left_on="bus_num", right_on="BUS_NUM", how="left").drop(columns="BUS_NUM")

    bus_info = meta_bus[["BUS_NUM", "NAME", "AREA", "ZONE"]].drop_duplicates("BUS_NUM")
    df_out   = df_out.merge(bus_info, left_on="bus_num", right_on="BUS_NUM", how="left").drop(columns="BUS_NUM")

    print(f"-> {len(df_out)} generators processed")
    return df_out


# ═══════════════════════════════════════════════════════════════════════════
# LINES
# ═══════════════════════════════════════════════════════════════════════════

def process_lines(t, df, meta_branch, meta_bus):
    """
    Columns used:
      LINE_<from>_<to>_<ckt>_P  → active power flow  (pbr)
      LINE_<from>_<to>_<ckt>_Q  → reactive power flow (qbr)
    """
    # Group by (from_bus, to_bus, ckt) → {P: col, Q: col}
    line_lookup = {}
    for col, fb, tb, ckt, pq in line_cols(df):
        key = (fb, tb, ckt)
        line_lookup.setdefault(key, {})[pq] = col

    rows = []
    for (from_bus, to_bus, ckt), pq_dict in line_lookup.items():
        p_col = pq_dict.get("P")
        q_col = pq_dict.get("Q")
        if p_col is None:
            continue

        pbr_arr = df[p_col].to_numpy()
        qbr_arr = df[q_col].to_numpy() if q_col else np.zeros_like(pbr_arr)

        mat    = np.column_stack([pbr_arr, qbr_arr])
        swings = ptp(mat, t)

        rows.append({
            "from_bus":  from_bus,
            "to_bus":    to_bus,
            "ckt":       ckt,
            "pbr_init":  pbr_arr[0],
            "qbr_init":  qbr_arr[0],
            "pbr_swing": swings[0],
            "qbr_swing": swings[1],
        })

    df_out = pd.DataFrame(rows)

    # Parallel circuit detection
    counts = df_out.groupby(["from_bus", "to_bus"]).size().rename("n_ckt").reset_index()
    df_out = df_out.merge(counts, on=["from_bus", "to_bus"])
    df_out["is_parallel"] = (df_out["n_ckt"] > 1).astype(int)

    # Merge thermal rating
    rating = meta_branch.groupby(["FROM_BUS", "TO_BUS"], as_index=False)["RATE_A_MVA"].mean()
    df_out = df_out.merge(rating, left_on=["from_bus", "to_bus"],
                          right_on=["FROM_BUS", "TO_BUS"], how="left") \
                   .drop(columns=["FROM_BUS", "TO_BUS"])

    # Merge bus names
    bus_info = meta_bus[["BUS_NUM", "NAME", "AREA", "ZONE"]].drop_duplicates("BUS_NUM")
    df_out = df_out.merge(
        bus_info.rename(columns={"BUS_NUM": "from_bus", "NAME": "from_name",
                                 "AREA": "from_area", "ZONE": "from_zone"}),
        on="from_bus", how="left")
    df_out = df_out.merge(
        bus_info.rename(columns={"BUS_NUM": "to_bus", "NAME": "to_name"}),
        on="to_bus", how="left")

    print(f"-> {len(df_out)} lines processed")
    return df_out


# ═══════════════════════════════════════════════════════════════════════════
# HV BUSES
# ═══════════════════════════════════════════════════════════════════════════

def process_buses(t, df, meta_bus):
    """
    Columns used:
      VOLT <bus> [<name> <kv>]  → voltage magnitude (vbus)
    Only buses at or above HV_THRESHOLD_KV are included.
    """
    hv_buses  = set(meta_bus.loc[meta_bus["BASKV"] >= HV_THRESHOLD_KV, "BUS_NUM"].astype(int))
    bus_attrs = meta_bus.set_index("BUS_NUM")[["BASKV", "NAME", "AREA", "ZONE"]].to_dict("index")

    rows = []
    for col in cols_by_prefix(df, "volt"):
        nums = extract_bus_nums(col)
        if not nums or nums[0] not in hv_buses:
            continue
        bus_num = nums[0]
        attrs   = bus_attrs.get(bus_num, {})
        arr     = df[col].to_numpy()
        swing   = ptp(arr, t)[0]
        rows.append({
            "bus_num": bus_num,
            "NAME":    attrs.get("NAME"),
            "AREA":    attrs.get("AREA"),
            "ZONE":    attrs.get("ZONE"),
            "BASKV":   attrs.get("BASKV", np.nan),
            "v_swing": swing,
            "v_max":   arr.max(),
            "v_min":   arr.min(),
        })

    df_out = pd.DataFrame(rows)
    print(f"-> {len(df_out)} HV buses processed")
    return df_out


# ═══════════════════════════════════════════════════════════════════════════
# LOADS
# ═══════════════════════════════════════════════════════════════════════════

def process_loads(t, df, meta_load, meta_bus, vbus_lookup):
    """
    Columns used:
      PLOD <bus>[<name> <kv>]<id>  → active power (pld)
      VOLT <bus> [<name> <kv>]     → bus voltage at load terminal (vbul)
    """
    plod_cols = cols_by_prefix(df, "plod")
    rows = []

    for plod_col in plod_cols:
        nums = extract_bus_nums(plod_col)
        if not nums:
            continue
        bus_num = nums[0]

        # Load voltage = bus VOLT at the same bus number
        volt_col = next(
            (c for c in cols_by_prefix(df, "volt")
             if extract_bus_nums(c) and extract_bus_nums(c)[0] == bus_num),
            None
        )

        pld_arr  = df[plod_col].to_numpy() * POWER_SCALE
        vbul_arr = df[volt_col].to_numpy() if volt_col else np.zeros_like(pld_arr)

        mat    = np.column_stack([pld_arr, vbul_arr])
        swings = ptp(mat, t)

        vb = vbus_lookup.get(bus_num, {})

        rows.append({
            "bus_num":    bus_num,
            "pld_init":   pld_arr[0],
            "vbus_init":  vb.get("vbus_init"),
            "vbus_swing": vb.get("vbus_swing"),
            "vbus_max":   vb.get("vbus_max"),
            "vbus_min":   vb.get("vbus_min"),
            "pld_swing":  swings[0],
            "vbul_swing": swings[1],
            "pld_max":    pld_arr.max(),
            "vbul_max":   vbul_arr.max(),
            "vbul_min":   vbul_arr.min(),
        })

    df_out = pd.DataFrame(rows)

    ptot     = meta_load.groupby("BUS_NUM", as_index=False)["PTOTAL_MW"].sum()
    df_out   = df_out.merge(ptot, left_on="bus_num", right_on="BUS_NUM", how="left").drop(columns="BUS_NUM")

    bus_info = meta_bus[["BUS_NUM", "NAME", "AREA", "ZONE"]].drop_duplicates("BUS_NUM")
    df_out   = df_out.merge(bus_info, left_on="bus_num", right_on="BUS_NUM", how="left").drop(columns="BUS_NUM")

    print(f"-> {len(df_out)} load buses processed")
    return df_out


# ═══════════════════════════════════════════════════════════════════════════
# LDDL
# ═══════════════════════════════════════════════════════════════════════════

def process_lddl(t, df):
    """
    Compute swing metrics for all LDDL signals defined in LDDL_COLS.
    Missing columns are skipped with a warning.
    Returns a DataFrame with one row per signal.
    """
    present = [(key, col) for key, col in LDDL_COLS.items() if col in df.columns]
    missing = [col for _, col in LDDL_COLS.items() if col not in df.columns]

    for col in missing:
        print(f"   [LDDL] Column not found, skipping: '{col}'")

    if not present:
        print("-> No LDDL columns found")
        return pd.DataFrame()

    # Power signals are scaled; BUS_VOLTAGE is left in pu
    LDDL_POWER_KEYS = {"P", "Q", "OS_P", "OS_Q"}

    keys, col_names = zip(*present)
    arrays = []
    for key, col in present:
        arr = df[col].to_numpy()
        if key in LDDL_POWER_KEYS:
            arr = arr * POWER_SCALE
        arrays.append(arr)

    mat    = np.column_stack(arrays)
    swings = ptp(mat, t)

    rows = []
    for i, (key, col_name) in enumerate(present):
        arr = arrays[i]
        rows.append({
            "signal":  key,
            "column":  col_name,
            "init":    arr[0],
            "swing":   swings[i],
            "max":     arr.max(),
            "min":     arr.min(),
        })

    df_out = pd.DataFrame(rows)
    print(f"-> {len(df_out)} LDDL signals processed: {list(keys)}")
    return df_out


# ═══════════════════════════════════════════════════════════════════════════
# SUMMARY RISK CSV
# ═══════════════════════════════════════════════════════════════════════════

def write_summary_risk_csv(metrics_gen, metrics_line, metrics_bus,
                           metrics_load, metrics_lddl, output_dir, run_tag):
    """
    Writes two CSVs:

    1. violation_counts_<run_tag>.csv
       One row per risk check. Columns:
         section | metric | unit | threshold | n_total | n_violations |
         pct_violations | worst_value | worst_element | worst_pct_threshold

    2. violation_detail_<run_tag>.csv
       One row per element that violated at least one threshold. Columns:
         section | element | metric | value | unit | threshold |
         pct_threshold | margin
    """
    T = RISK_THRESHOLDS

    def _label(row_s, bus_col="bus_num", name_col="NAME", kv_col=None):
        bus  = int(row_s[bus_col]) if bus_col in row_s.index else "?"
        name = row_s.get(name_col, "")
        lbl  = f"Bus {bus}" + (f" ({name})" if name and str(name) != "nan" else "")
        if kv_col:
            kv = row_s.get(kv_col, "")
            lbl += f" {kv:.0f} kV" if kv and str(kv) != "nan" else ""
        return lbl

    # ── Build violation counts table ──────────────────────────────────────
    count_rows  = []
    detail_rows = []

    def _pct(val, thresh, lower=False):
        """Percentage of threshold consumed (>100% = violation)."""
        if thresh == 0:
            return None
        return round(100.0 * val / thresh, 2) if not lower else round(100.0 * (1 - val / thresh + 1), 2)

    def _margin(val, thresh, lower=False):
        return round(float(thresh - val if lower else val - thresh), 4)

    def add_count(section, metric, unit, thresh, values_series, labels_series,
                  lower=False):
        """Register one risk check into count_rows and detail_rows."""
        valid = values_series.dropna()
        n_total = len(valid)
        if n_total == 0:
            return

        if lower:
            mask = valid < thresh
            worst_idx = valid.idxmin()
        else:
            mask = valid > thresh
            worst_idx = valid.idxmax()

        n_viol      = int(mask.sum())
        worst_val   = float(valid.loc[worst_idx])
        worst_label = labels_series.loc[worst_idx]
        worst_pct   = _pct(worst_val, thresh, lower)

        count_rows.append({
            "section":           section,
            "metric":            metric,
            "unit":              unit,
            "threshold":         thresh,
            "n_total":           n_total,
            "n_violations":      n_viol,
            "pct_violations":    round(100.0 * n_viol / n_total, 1) if n_total else 0,
            "worst_value":       round(worst_val, 4),
            "worst_element":     worst_label,
            "worst_pct_threshold": worst_pct,
        })

        # Detail rows — one per violating element
        viol_idx = valid[mask].index
        for idx in viol_idx:
            val = float(valid.loc[idx])
            detail_rows.append({
                "section":       section,
                "element":       labels_series.loc[idx],
                "metric":        metric,
                "value":         round(val, 4),
                "unit":          unit,
                "threshold":     thresh,
                "pct_threshold": _pct(val, thresh, lower),
                "margin":        _margin(val, thresh, lower),
            })

    # ── Generators ───────────────────────────────────────────────────────
    if not metrics_gen.empty:
        g = metrics_gen.copy()
        labels = g.apply(lambda r: _label(r), axis=1)

        # Swing checks
        for col, metric, unit, thresh in [
            ("pg_swing",    "P swing amplitude",  "MW",   T["gen_pg_swing_mw"]),
            ("qg_swing",    "Q swing amplitude",  "MVar", T["gen_qg_swing_mvar"]),
            ("vt_swing",    "Vt swing amplitude", "pu",   T["gen_vt_swing_pu"]),
            ("freq_swing",  "Freq swing",         "Hz",   T["gen_freq_swing_hz"]),
            ("angle_swing", "Angle swing",        "deg",  T["gen_angle_swing_deg"]),
        ]:
            if col in g.columns:
                add_count("Generator", metric, unit, thresh, g[col], labels)

        # P vs Pmax / Pmin capacity checks (pg_max must not exceed Pmax)
        if "pg_max" in g.columns and "PMAX_MW" in g.columns:
            pmax_ratio = (g["pg_max"] / g["PMAX_MW"].replace(0, np.nan)) * 100
            pmax_labels = labels
            n_total = len(pmax_ratio.dropna())
            n_viol  = int((pmax_ratio > 100).sum())
            worst_idx = pmax_ratio.idxmax() if n_total else None
            count_rows.append({
                "section":           "Generator",
                "metric":            "Pmax violation (pg_max > Pmax)",
                "unit":              "%Pmax",
                "threshold":         100.0,
                "n_total":           n_total,
                "n_violations":      n_viol,
                "pct_violations":    round(100.0 * n_viol / n_total, 1) if n_total else 0,
                "worst_value":       round(float(pmax_ratio.loc[worst_idx]), 2) if worst_idx is not None else None,
                "worst_element":     pmax_labels.loc[worst_idx] if worst_idx is not None else "",
                "worst_pct_threshold": round(float(pmax_ratio.loc[worst_idx]), 2) if worst_idx is not None else None,
            })
            for idx in pmax_ratio[pmax_ratio > 100].dropna().index:
                detail_rows.append({
                    "section":       "Generator",
                    "element":       labels.loc[idx],
                    "metric":        "Pmax violation (pg_max > Pmax)",
                    "value":         round(float(g.loc[idx, "pg_max"]), 2),
                    "unit":          "MW",
                    "threshold":     round(float(g.loc[idx, "PMAX_MW"]), 2),
                    "pct_threshold": round(float(pmax_ratio.loc[idx]), 2),
                    "margin":        round(float(g.loc[idx, "pg_max"] - g.loc[idx, "PMAX_MW"]), 2),
                })

        # Q vs Qmax / Qmin
        if "qg_max" in g.columns and "QMAX_MVAR" in g.columns:
            qmax_mask = g["qg_max"] > g["QMAX_MVAR"]
            n_viol = int(qmax_mask.sum())
            n_total = len(g)
            worst_idx = (g["qg_max"] - g["QMAX_MVAR"]).idxmax() if n_total else None
            count_rows.append({
                "section":           "Generator",
                "metric":            "Qmax violation (qg_max > Qmax)",
                "unit":              "MVar",
                "threshold":         None,
                "n_total":           n_total,
                "n_violations":      n_viol,
                "pct_violations":    round(100.0 * n_viol / n_total, 1) if n_total else 0,
                "worst_value":       round(float(g.loc[worst_idx, "qg_max"]), 2) if worst_idx is not None else None,
                "worst_element":     labels.loc[worst_idx] if worst_idx is not None else "",
                "worst_pct_threshold": None,
            })
            for idx in g[qmax_mask].index:
                detail_rows.append({
                    "section":       "Generator",
                    "element":       labels.loc[idx],
                    "metric":        "Qmax violation (qg_max > Qmax)",
                    "value":         round(float(g.loc[idx, "qg_max"]), 2),
                    "unit":          "MVar",
                    "threshold":     round(float(g.loc[idx, "QMAX_MVAR"]), 2),
                    "pct_threshold": None,
                    "margin":        round(float(g.loc[idx, "qg_max"] - g.loc[idx, "QMAX_MVAR"]), 2),
                })

        if "qg_min" in g.columns and "QMIN_MVAR" in g.columns:
            qmin_mask = g["qg_min"] < g["QMIN_MVAR"]
            n_viol = int(qmin_mask.sum())
            n_total = len(g)
            worst_idx = (g["QMIN_MVAR"] - g["qg_min"]).idxmax() if n_total else None
            count_rows.append({
                "section":           "Generator",
                "metric":            "Qmin violation (qg_min < Qmin)",
                "unit":              "MVar",
                "threshold":         None,
                "n_total":           n_total,
                "n_violations":      n_viol,
                "pct_violations":    round(100.0 * n_viol / n_total, 1) if n_total else 0,
                "worst_value":       round(float(g.loc[worst_idx, "qg_min"]), 2) if worst_idx is not None else None,
                "worst_element":     labels.loc[worst_idx] if worst_idx is not None else "",
                "worst_pct_threshold": None,
            })
            for idx in g[qmin_mask].index:
                detail_rows.append({
                    "section":       "Generator",
                    "element":       labels.loc[idx],
                    "metric":        "Qmin violation (qg_min < Qmin)",
                    "value":         round(float(g.loc[idx, "qg_min"]), 2),
                    "unit":          "MVar",
                    "threshold":     round(float(g.loc[idx, "QMIN_MVAR"]), 2),
                    "pct_threshold": None,
                    "margin":        round(float(g.loc[idx, "QMIN_MVAR"] - g.loc[idx, "qg_min"]), 2),
                })

        # Vt swing % Mbase
        if "vt_swing" in g.columns and "MBASE_MVA" in g.columns:
            vt_pct = (g["pg_swing"] / g["MBASE_MVA"].replace(0, np.nan)) * 100
            add_count("Generator", "P swing % Mbase", "%Mbase",
                      T["gen_pg_swing_mw"], vt_pct, labels)

    # ── Lines ────────────────────────────────────────────────────────────
    if not metrics_line.empty:
        ln = metrics_line.copy()
        ln_labels = ln.apply(
            lambda r: f"{int(r['from_bus'])} → {int(r['to_bus'])} (ckt {int(r['ckt'])})",
            axis=1)

        add_count("Line", "P swing amplitude", "MW",
                  T["line_pbr_swing_mw"], ln["pbr_swing"], ln_labels)

        # Thermal loading: pbr_swing as % of RATE_A_MVA
        if "RATE_A_MVA" in ln.columns:
            rated = ln["RATE_A_MVA"].replace(0, np.nan)
            swing_pct = (ln["pbr_swing"] / rated) * 100
            add_count("Line", "P swing % thermal rating", "%rating",
                      T["line_pbr_swing_pct"], swing_pct, ln_labels)

    # ── HV Buses ─────────────────────────────────────────────────────────
    if not metrics_bus.empty:
        b = metrics_bus.copy()
        b_labels = b.apply(lambda r: _label(r, kv_col="BASKV"), axis=1)

        add_count("HV Bus", "V swing amplitude",  "pu", T["bus_v_swing_pu"],  b["v_swing"], b_labels)
        add_count("HV Bus", "V max envelope",      "pu", T["bus_v_hi_pu"],     b["v_max"],   b_labels)
        add_count("HV Bus", "V min envelope",      "pu", T["bus_v_lo_pu"],     b["v_min"],   b_labels, lower=True)

    # ── Loads ────────────────────────────────────────────────────────────
    if not metrics_load.empty and "pld_swing" in metrics_load.columns:
        ld = metrics_load.copy()
        ld_labels = ld.apply(lambda r: _label(r), axis=1)
        add_count("Load", "P swing amplitude", "MW",
                  T["load_pld_swing_mw"], ld["pld_swing"], ld_labels)

    # ── LDDL ─────────────────────────────────────────────────────────────
    if not metrics_lddl.empty:
        lddl_map = {
            "P":           ("LDDL P swing",     "MW",   T["lddl_p_swing_mw"]),
            "Q":           ("LDDL Q swing",     "MVar", T["lddl_q_swing_mvar"]),
            "OS_P":        ("LDDL OS P swing",  "MW",   T["lddl_p_swing_mw"]),
            "OS_Q":        ("LDDL OS Q swing",  "MVar", T["lddl_q_swing_mvar"]),
            "BUS_VOLTAGE": ("LDDL Bus V swing", "pu",   T["lddl_v_swing_pu"]),
        }
        for _, lrow in metrics_lddl.iterrows():
            key = lrow.get("signal", "")
            if key not in lddl_map:
                continue
            metric, unit, thresh = lddl_map[key]
            val = lrow["swing"]
            flagged = val > thresh
            lbl = lrow.get("column", key)
            count_rows.append({
                "section": "LDDL", "metric": metric, "unit": unit,
                "threshold": thresh, "n_total": 1,
                "n_violations": int(flagged),
                "pct_violations": 100.0 if flagged else 0.0,
                "worst_value": round(float(val), 4), "worst_element": lbl,
                "worst_pct_threshold": _pct(val, thresh),
            })
            if flagged:
                detail_rows.append({
                    "section": "LDDL", "element": lbl, "metric": metric,
                    "value": round(float(val), 4), "unit": unit,
                    "threshold": thresh,
                    "pct_threshold": _pct(val, thresh),
                    "margin": _margin(val, thresh),
                })

    # ── Write ─────────────────────────────────────────────────────────────
    count_cols  = ["section","metric","unit","threshold","n_total",
                   "n_violations","pct_violations","worst_value",
                   "worst_element","worst_pct_threshold"]
    detail_cols = ["section","element","metric","value","unit",
                   "threshold","pct_threshold","margin"]

    df_counts  = pd.DataFrame(count_rows,  columns=count_cols)
    df_details = pd.DataFrame(detail_rows, columns=detail_cols)

    counts_path  = os.path.join(output_dir, f"violation_counts_{run_tag}.csv")
    details_path = os.path.join(output_dir, f"violation_detail_{run_tag}.csv")

    df_counts.to_csv(counts_path,  index=False)
    df_details.to_csv(details_path, index=False)

    total_checks = len(df_counts)
    total_viols  = int((df_counts["n_violations"] > 0).sum())
    total_els    = len(df_details)

    print(f"-> Violation counts : {counts_path}  ({total_checks} checks, {total_viols} with violations)")
    print(f"-> Violation detail : {details_path}  ({total_els} violating elements)")
    return df_counts, df_details


# ═══════════════════════════════════════════════════════════════════════════
# VIOLATION COUNTS TABLE
# ═══════════════════════════════════════════════════════════════════════════

def write_violation_counts_csv(metrics_gen, metrics_line, metrics_bus,
                               metrics_load, metrics_lddl, output_dir, run_tag):
    """
    Produce a violation-counts CSV — one row per risk check — showing:
      n_monitored   : total elements checked
      n_violations  : elements that breached the threshold
      violation_pct : n_violations / n_monitored * 100
      worst_element : label of the worst offender
      worst_value   : its metric value

    Covers both oscillation-swing thresholds and static capacity limits
    (P > Pmax, Q > Qmax/Qmin, V > Vhi, V < Vlo, P swing > % rating).

    Output: results/violation_counts_<run_tag>.csv
    """
    T    = RISK_THRESHOLDS
    rows = []

    def _name(row, bus_col="bus_num"):
        bus  = int(row[bus_col])
        name = row.get("NAME", "")
        return f"Bus {bus}" + (f" ({name})" if name and str(name) != "nan" else "")

    def vrow(section, metric, threshold, thresh_label, unit,
             n_mon, n_viol, worst_label, worst_val):
        rows.append({
            "section":        section,
            "metric":         metric,
            "threshold":      thresh_label,
            "unit":           unit,
            "n_monitored":    n_mon,
            "n_violations":   n_viol,
            "violation_pct":  round(100.0 * n_viol / n_mon, 1) if n_mon else None,
            "worst_element":  worst_label,
            "worst_value":    round(float(worst_val), 4) if worst_val is not None else None,
        })

    # ── Generators ───────────────────────────────────────────────────────
    if not metrics_gen.empty:
        mg  = metrics_gen
        n   = len(mg)

        # Helper: worst element for a column (highest value unless ascending)
        def gen_worst(col, ascending=False):
            idx = mg[col].idxmin() if ascending else mg[col].idxmax()
            return _name(mg.loc[idx]), mg.loc[idx, col]

        # Swing thresholds
        for col, metric, unit, thresh in [
            ("pg_swing",    "P swing amplitude",   "MW",  T["gen_pg_swing_mw"]),
            ("qg_swing",    "Q swing amplitude",   "MVar",T["gen_qg_swing_mvar"]),
            ("vt_swing",    "Vt swing amplitude",  "pu",  T["gen_vt_swing_pu"]),
            ("freq_swing",  "Freq swing amplitude","Hz",  T["gen_freq_swing_hz"]),
            ("angle_swing", "Angle swing amplitude","deg",T["gen_angle_swing_deg"]),
        ]:
            if col not in mg.columns:
                continue
            mask  = mg[col] > thresh
            wlbl, wval = gen_worst(col)
            vrow("Generator", metric, thresh, f"> {thresh}", unit,
                 n, int(mask.sum()), wlbl, wval)

        # Capacity limit violations
        if "pg_max" in mg.columns and "PMAX_MW" in mg.columns:
            valid = mg.dropna(subset=["PMAX_MW"])
            if not valid.empty:
                mask  = valid["pg_max"] > valid["PMAX_MW"]
                if mask.any():
                    idx   = (valid["pg_max"] - valid["PMAX_MW"]).idxmax()
                    wlbl  = _name(valid.loc[idx])
                    wval  = valid.loc[idx, "pg_max"]
                else:
                    wlbl, wval = "—", 0.0
                vrow("Generator", "P > Pmax (capacity)", "Pmax", "> Pmax", "MW",
                     len(valid), int(mask.sum()), wlbl, wval)

        if "pg_min" in mg.columns and "PMIN_MW" in mg.columns:
            valid = mg.dropna(subset=["PMIN_MW"])
            if not valid.empty:
                mask  = valid["pg_min"] < valid["PMIN_MW"]
                if mask.any():
                    idx   = (valid["PMIN_MW"] - valid["pg_min"]).idxmax()
                    wlbl  = _name(valid.loc[idx])
                    wval  = valid.loc[idx, "pg_min"]
                else:
                    wlbl, wval = "—", 0.0
                vrow("Generator", "P < Pmin (capacity)", "Pmin", "< Pmin", "MW",
                     len(valid), int(mask.sum()), wlbl, wval)

        if "qg_max" in mg.columns and "QMAX_MVAR" in mg.columns:
            valid = mg.dropna(subset=["QMAX_MVAR"])
            if not valid.empty:
                mask  = valid["qg_max"] > valid["QMAX_MVAR"]
                if mask.any():
                    idx   = (valid["qg_max"] - valid["QMAX_MVAR"]).idxmax()
                    wlbl  = _name(valid.loc[idx])
                    wval  = valid.loc[idx, "qg_max"]
                else:
                    wlbl, wval = "—", 0.0
                vrow("Generator", "Q > Qmax (capacity)", "Qmax", "> Qmax", "MVar",
                     len(valid), int(mask.sum()), wlbl, wval)

        if "qg_min" in mg.columns and "QMIN_MVAR" in mg.columns:
            valid = mg.dropna(subset=["QMIN_MVAR"])
            if not valid.empty:
                mask  = valid["qg_min"] < valid["QMIN_MVAR"]
                if mask.any():
                    idx   = (valid["QMIN_MVAR"] - valid["qg_min"]).idxmax()
                    wlbl  = _name(valid.loc[idx])
                    wval  = valid.loc[idx, "qg_min"]
                else:
                    wlbl, wval = "—", 0.0
                vrow("Generator", "Q < Qmin (capacity)", "Qmin", "< Qmin", "MVar",
                     len(valid), int(mask.sum()), wlbl, wval)

    # ── Lines ────────────────────────────────────────────────────────────
    if not metrics_line.empty:
        ml = metrics_line
        n  = len(ml)

        def line_lbl(row):
            return f"{int(row.from_bus)} → {int(row.to_bus)} (ckt {int(row.ckt)})"

        # P swing amplitude
        thresh = T["line_pbr_swing_mw"]
        mask   = ml["pbr_swing"] > thresh
        idx    = ml["pbr_swing"].idxmax()
        vrow("Line", "P swing amplitude", thresh, f"> {thresh}", "MW",
             n, int(mask.sum()), line_lbl(ml.loc[idx]), ml.loc[idx, "pbr_swing"])

        # P swing as % of thermal rating
        if "RATE_A_MVA" in ml.columns:
            valid = ml.dropna(subset=["RATE_A_MVA"])
            valid = valid[valid["RATE_A_MVA"] > 0].copy()
            if not valid.empty:
                valid["swing_pct"] = valid["pbr_swing"] / valid["RATE_A_MVA"] * 100.0
                thresh_pct = T["line_pbr_swing_mw"]   # reuse MW threshold as pct reference
                # Use a separate pct threshold key if present, else default 10%
                thresh_pct = RISK_THRESHOLDS.get("line_pbr_swing_pct", 10.0)
                mask  = valid["swing_pct"] > thresh_pct
                idx   = valid["swing_pct"].idxmax()
                vrow("Line", "P swing % of thermal rating", thresh_pct, f"> {thresh_pct}%", "%",
                     len(valid), int(mask.sum()),
                     line_lbl(valid.loc[idx]), valid.loc[idx, "swing_pct"])

    # ── HV Buses ─────────────────────────────────────────────────────────
    if not metrics_bus.empty:
        mb = metrics_bus
        n  = len(mb)

        def bus_lbl(row):
            bus  = int(row["bus_num"])
            name = row.get("NAME", "")
            kv   = row.get("BASKV", "")
            lbl  = f"Bus {bus}" + (f" ({name})" if name and str(name) != "nan" else "")
            lbl += f" {kv:.0f} kV" if kv and str(kv) != "nan" else ""
            return lbl

        # V swing
        thresh = T["bus_v_swing_pu"]
        mask   = mb["v_swing"] > thresh
        idx    = mb["v_swing"].idxmax()
        vrow("HV Bus", "V swing amplitude", thresh, f"> {thresh}", "pu",
             n, int(mask.sum()), bus_lbl(mb.loc[idx]), mb.loc[idx, "v_swing"])

        # V > Vhi
        thresh = T["bus_v_hi_pu"]
        mask   = mb["v_max"] > thresh
        idx    = mb["v_max"].idxmax()
        vrow("HV Bus", "V > Vhi (envelope)", thresh, f"> {thresh}", "pu",
             n, int(mask.sum()), bus_lbl(mb.loc[idx]), mb.loc[idx, "v_max"])

        # V < Vlo
        thresh = T["bus_v_lo_pu"]
        mask   = mb["v_min"] < thresh
        idx    = mb["v_min"].idxmin()
        vrow("HV Bus", "V < Vlo (envelope)", thresh, f"< {thresh}", "pu",
             n, int(mask.sum()), bus_lbl(mb.loc[idx]), mb.loc[idx, "v_min"])

    # ── Loads ────────────────────────────────────────────────────────────
    if not metrics_load.empty and "pld_swing" in metrics_load.columns:
        mld   = metrics_load
        thresh = T["load_pld_swing_mw"]
        mask   = mld["pld_swing"] > thresh
        idx    = mld["pld_swing"].idxmax()
        vrow("Load", "P swing amplitude", thresh, f"> {thresh}", "MW",
             len(mld), int(mask.sum()), _name(mld.loc[idx]), mld.loc[idx, "pld_swing"])

    # ── LDDL ─────────────────────────────────────────────────────────────
    if not metrics_lddl.empty:
        lddl_map = {
            "P":           ("P swing",     "MW",  T["lddl_p_swing_mw"]),
            "Q":           ("Q swing",     "MVar",T["lddl_q_swing_mvar"]),
            "OS_P":        ("OS P swing",  "MW",  T["lddl_p_swing_mw"]),
            "OS_Q":        ("OS Q swing",  "MVar",T["lddl_q_swing_mvar"]),
            "BUS_VOLTAGE": ("Bus V swing", "pu",  T["lddl_v_swing_pu"]),
        }
        for _, lrow in metrics_lddl.iterrows():
            key = lrow.get("signal", "")
            if key not in lddl_map:
                continue
            metric, unit, thresh = lddl_map[key]
            val     = lrow["swing"]
            flagged = int(val > thresh)
            vrow("LDDL", metric, thresh, f"> {thresh}", unit,
                 1, flagged, lrow.get("column", key), val)

    # ── Write ─────────────────────────────────────────────────────────────
    cols = ["section", "metric", "threshold", "unit",
            "n_monitored", "n_violations", "violation_pct",
            "worst_element", "worst_value"]
    df_viol = pd.DataFrame(rows, columns=cols)
    out_path = os.path.join(output_dir, f"violation_counts_{run_tag}.csv")
    df_viol.to_csv(out_path, index=False)
    total_viol = df_viol["n_violations"].sum()
    print(f"-> Violation counts CSV: {out_path}  ({len(df_viol)} checks, {total_viol} total violations)")
    return df_viol


# ═══════════════════════════════════════════════════════════════════════════
# WORST-OFFENDER TIME SERIES
# ═══════════════════════════════════════════════════════════════════════════

def build_timeseries(t_full, df_full, metrics_gen, metrics_line, metrics_bus, metrics_load, metrics_lddl):
    """Build worst-offender time series from the FULL (untruncated) simulation data."""
    ts     = {}
    stride = max(1, len(t_full) // TIMESERIES_MAX_POINTS)
    sl     = slice(None, None, stride)

    t      = t_full   # already shifted to start at 0 by load_sim_full()
    df     = df_full

    def safe_arr(col):
        return df[col].to_numpy()[sl] if col else np.zeros(len(t))[sl]

    # ── Worst generator (highest pg_swing) ──────────────────────────────
    worst_gen_bus = int(metrics_gen.loc[metrics_gen["pg_swing"].idxmax(), "bus_num"])

    def gcol(pfx):
        cands = [c for c in cols_by_prefix(df, pfx)
                 if extract_bus_nums(c) and extract_bus_nums(c)[0] == worst_gen_bus]
        return cands[0] if cands else None

    angl_col = gcol("angl")
    abus_arr = df[angl_col].to_numpy() if angl_col else np.zeros(len(t))
    freq_arr = derive_freq(abus_arr, t)

    ts["gen"] = {
        "label": f"Generator at Bus {worst_gen_bus}",
        "t":    round6(t[sl]),
        "pg":   round6(safe_arr(gcol("powr")) * POWER_SCALE),
        "qg":   round6(safe_arr(gcol("vars")) * POWER_SCALE),
        "vt":   round6(safe_arr(gcol("etrm"))),
        "abus": round6(abus_arr[sl]),
        "freq": round6(freq_arr[sl]),
    }
    print(f"-> Worst generator: Bus {worst_gen_bus}")

    # ── Worst line (highest pbr_swing) ───────────────────────────────────
    worst_line = metrics_line.loc[metrics_line["pbr_swing"].idxmax()]
    fb  = int(worst_line["from_bus"])
    tb  = int(worst_line["to_bus"])
    ckt = int(worst_line["ckt"])

    parsed = line_cols(df)
    p_col  = next((c for c, f, t_, k, pq in parsed if f == fb and t_ == tb and k == ckt and pq == "P"), None)
    q_col  = next((c for c, f, t_, k, pq in parsed if f == fb and t_ == tb and k == ckt and pq == "Q"), None)

    ts["line"] = {
        "label": f"Line {fb} \u2192 {tb} (ckt {ckt})",
        "t":   round6(t[sl]),
        "pbr": round6(safe_arr(p_col)),
        "qbr": round6(safe_arr(q_col)),
    }
    print(f"-> Worst line: {fb} → {tb} (ckt {ckt})")

    # ── Worst HV bus (highest v_swing) ───────────────────────────────────
    worst_bus_row = metrics_bus.loc[metrics_bus["v_swing"].idxmax()]
    worst_bus_num = int(worst_bus_row["bus_num"])
    worst_bus_kv  = worst_bus_row["BASKV"]

    def bcol(pfx):
        return next((c for c in cols_by_prefix(df, pfx)
                     if extract_bus_nums(c) and extract_bus_nums(c)[0] == worst_bus_num), None)

    ts["bus"] = {
        "label": f"HV Bus {worst_bus_num} ({worst_bus_kv:.0f} kV)",
        "t":    round6(t[sl]),
        "vbus": round6(safe_arr(bcol("volt"))),
        "abus": round6(safe_arr(bcol("angl"))),
    }
    print(f"-> Worst HV bus: {worst_bus_num} ({worst_bus_kv:.0f} kV)")

    # ── Worst load bus (highest pld_swing) ───────────────────────────────
    worst_load_bus = int(metrics_load.loc[metrics_load["pld_swing"].idxmax(), "bus_num"])

    def lcol(pfx):
        return next((c for c in cols_by_prefix(df, pfx)
                     if extract_bus_nums(c) and extract_bus_nums(c)[0] == worst_load_bus), None)

    ts["load"] = {
        "label": f"Load Bus {worst_load_bus}",
        "t":    round6(t[sl]),
        "pld":  round6(safe_arr(lcol("plod")) * POWER_SCALE),
        "vbul": round6(safe_arr(lcol("volt"))),
    }
    print(f"-> Worst load bus: {worst_load_bus}")

    # ── LDDL time series ─────────────────────────────────────────────────
    LDDL_POWER_KEYS = {"P", "Q", "OS_P", "OS_Q"}
    lddl_signals = {}
    for key, col in LDDL_COLS.items():
        if col not in df.columns:
            continue
        arr = df[col].to_numpy()
        if key in LDDL_POWER_KEYS:
            arr = arr * POWER_SCALE
        lddl_signals[key] = round6(arr[sl])

    if lddl_signals:
        ts["lddl"] = {
            "label": "LDDL Signals",
            "t": round6(t[sl]),
            **lddl_signals,
        }
        print(f"-> LDDL time series included: {list(lddl_signals.keys())}")
    else:
        print("-> No LDDL columns found for time series")

    return ts


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    global OSCILLATION_FREQ_HZ, START_TIME_SEC
    global SIM_FILE, META_DIR, OUTPUT_DIR, META_FILES

    # ── Read simulation_config.csv ────────────────────────────────────────
    root   = Path.cwd()
    config = pd.read_csv(root / "simulation_config.csv")

    def _cfg(var, cast=str, default=None):
        row = config[config.Variable == var]
        if row.empty:
            return default
        v = row['Value'].iloc[0]
        return default if (str(v).strip().lower() == 'nan' or str(v).strip() == '') else cast(v)

    case_name           = _cfg('case_name',            str)
    bus_number          = _cfg('bus_number',            int)
    OSCILLATION_FREQ_HZ = _cfg('oscillation_frequency', float)
    osc_amp_mw          = _cfg('oscillation_amplitude', float)
    START_TIME_SEC      = _cfg('start_time_sec',        float, default=1.0)

    META_DIR   = str(root / "Processing")
    OUTPUT_DIR = str(root / "results")
    SIM_FILE   = str(root / "results" / f"{bus_number}_{OSCILLATION_FREQ_HZ}_Hz_{osc_amp_mw}MW_sim.csv")

    # Tag appended to every output filename: e.g. bus5003_0.4Hz_100MW
    freq_str = str(OSCILLATION_FREQ_HZ).rstrip('0').rstrip('.')
    amp_str  = str(int(osc_amp_mw)) if osc_amp_mw == int(osc_amp_mw) else str(osc_amp_mw)
    run_tag  = f"bus{bus_number}_{freq_str}Hz_{amp_str}MW"

    META_FILES.update({
        "buses":      f"{case_name}_buses.csv",
        "branches":   f"{case_name}_branches.csv",
        "generators": f"{case_name}_generators.csv",
        "loads":      f"{case_name}_loads.csv",
    })

    print(f"Case         : {case_name}")
    print(f"Bus          : {bus_number}")
    print(f"Osc. freq    : {OSCILLATION_FREQ_HZ} Hz")
    print(f"Sim file     : {SIM_FILE}")
    print(f"Meta dir     : {META_DIR}")
    print(f"Output dir   : {OUTPUT_DIR}")

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # ── Load metadata ─────────────────────────────────────────────────────
    print("\nLoading metadata...")
    meta_bus    = load_meta("buses")
    meta_branch = load_meta("branches")
    meta_gen    = load_meta("generators")
    meta_load   = load_meta("loads")
    print("-> Metadata loaded")

    # ── Load unified simulation file (trimmed) for metric computation ─────
    print("Loading simulation file (trimming startup transient)...")
    t, df = load_sim()
    print(f"-> {len(t)} time points, {len(df.columns)} columns")

    # ── Load full simulation file for time-series plots ───────────────────
    print("Loading full simulation file for time-series plots...")
    t_full, df_full = load_sim_full()
    print(f"-> {len(t_full)} time points (full, starts at t=0)")

    # ── Shared bus voltage lookup (built once, used by gens + loads) ──────
    print("Building bus voltage lookup...")
    vbus_lookup = build_vbus_lookup(t, df)

    # ── Compute per-element metrics ───────────────────────────────────────
    print("\nProcessing generators...")
    metrics_gen = process_generators(t, df, meta_gen, meta_bus, vbus_lookup)
    metrics_gen.to_csv(os.path.join(OUTPUT_DIR, f"metrics_generators_{run_tag}.csv"), index=False)

    print("Processing lines...")
    metrics_line = process_lines(t, df, meta_branch, meta_bus)
    metrics_line.to_csv(os.path.join(OUTPUT_DIR, f"metrics_lines_{run_tag}.csv"), index=False)

    print("Processing HV buses...")
    metrics_bus = process_buses(t, df, meta_bus)
    metrics_bus.to_csv(os.path.join(OUTPUT_DIR, f"metrics_buses_{run_tag}.csv"), index=False)

    print("Processing loads...")
    metrics_load = process_loads(t, df, meta_load, meta_bus, vbus_lookup)
    metrics_load.to_csv(os.path.join(OUTPUT_DIR, f"metrics_loads_{run_tag}.csv"), index=False)

    print("Processing LDDL signals...")
    metrics_lddl = process_lddl(t, df)
    if not metrics_lddl.empty:
        metrics_lddl.to_csv(os.path.join(OUTPUT_DIR, f"metrics_lddl_{run_tag}.csv"), index=False)

    print("\nWriting violation summary CSVs...")
    write_summary_risk_csv(metrics_gen, metrics_line, metrics_bus,
                           metrics_load, metrics_lddl, OUTPUT_DIR, run_tag)

    # ── Worst-offender time series ────────────────────────────────────────
    print("\nExtracting worst-offender time series...")
    ts = build_timeseries(t_full, df_full, metrics_gen, metrics_line, metrics_bus, metrics_load, metrics_lddl)

    ts_path = os.path.join(OUTPUT_DIR, f"timeseries_worst_{run_tag}.json")
    with open(ts_path, "w") as fh:
        json.dump(ts, fh)
    print(f"-> Time series written to {ts_path}")

    print(f"\nAll outputs written to: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()