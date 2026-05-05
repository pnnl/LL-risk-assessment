"""
Step7_zone3_impedance.py
=========================
Interactive Zone 3 relay reach calculator and impedance trajectory plotter.

Workflow:
  1. Reads simulation_config.csv to locate Processing/ and results/ folders.
  2. Lists monitored lines (from Processing/monitored_lines.csv).
     Falls back to the full branches CSV if the monitored file is absent.
  3. User selects a line interactively (numbered list) or via --line argument.
  4. Calculates Zone 3 reach using the mho-based formula:
       S_lim    = 1.5 * RATE_B_MVA
       Z_lim    = 0.85^2 * S_base / S_lim          [pu, system base]
       phi      = arctan(X / R)
       Z3_reach = Z_lim / cos(phi - 30°)
  5. Loads the simulation CSV, extracts V, P, Q for the selected line/bus,
     and computes the impedance trajectory:
       Z(t) = V(t)^2 / (P(t) - j*Q(t))             [pu]
  6. Plots the R-X diagram:
       - Zone 3 mho circle
       - Line impedance point
       - Pre-fault operating point
       - Full impedance trajectory (time-coloured)
  7. Saves results/zone3_<line_tag>_<run_tag>.csv  and  .png.

Notes:
  - All impedances are in per unit on the system MVA base (default 100 MVA).
  - P and Q channel data from PSSE are already in pu (before ×POWER_SCALE).
  - The relay is assumed to be at the FROM_BUS end.
  - RATE_B_MVA is used as the thermal limit (matches the Zone3Calculator class).
"""

import os
import re
import sys
import math
import argparse
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')          # headless-safe; switch to 'TkAgg' for interactive
import matplotlib.pyplot as plt
import matplotlib.cm as cm
from pathlib import Path


# ═══════════════════════════════════════════════════════════════════════════
# ZONE 3 CALCULATOR
# ═══════════════════════════════════════════════════════════════════════════

class Zone3Calculator:
    """
    Calculate Zone 3 mho relay reach for transmission lines.

    Formulas
    --------
    S_lim    = 1.5 × RATE_B_MVA
    Z_lim    = 0.85² × S_base / S_lim          (pu on system base)
    phi      = arctan(X / R)                    (line angle, degrees)
    Z3_reach = Z_lim / cos(phi − 30°)
    """

    def __init__(self, s_base: float = 100.0):
        self.s_base = s_base

    def calculate(self, branch: dict) -> dict:
        R       = branch['R_PU']
        X       = branch['X_PU']
        rate2   = branch['RATE_B_MVA']
        from_kv = branch['FROM_KV']

        # ── Validate and interactively fill missing fields ───────────────
        def _is_bad(v):
            return v is None or (isinstance(v, float) and math.isnan(v)) or v <= 0

        def _prompt_float(field_name: str, current_val, description: str,
                          unit: str, must_positive: bool = True) -> float:
            """Print a diagnostic and ask the user to supply the value."""
            if current_val is None or (isinstance(current_val, float) and math.isnan(current_val)):
                reason = f"missing (NaN) in branch data"
            else:
                reason = f"= {current_val} (must be > 0)"
            print(f"\n  WARNING: {field_name} is {reason}.")
            print(f"  {description}")
            while True:
                try:
                    raw = input(f"  Enter {field_name} ({unit}): ").strip()
                    val = float(raw)
                    if must_positive and val <= 0:
                        print(f"  Value must be > 0. Try again.")
                        continue
                    return val
                except (ValueError, EOFError):
                    print("  Invalid input — please enter a number.")

        if _is_bad(rate2):
            rate2 = _prompt_float(
                "RATE_B_MVA",
                rate2,
                "This is the continuous thermal rating (MVA) used to set S_lim = 1.5 × RATE_B.\n"
                "  Check your case data or relay coordination study for this line's rating.",
                "MVA"
            )

        if _is_bad(from_kv):
            from_kv = _prompt_float(
                "FROM_KV",
                from_kv,
                "This is the nominal base kV at the relay (FROM_BUS) end of the line.\n"
                "  Used to convert the pu reach to primary ohms.",
                "kV"
            )

        if R is None or (isinstance(R, float) and math.isnan(R)):
            R = _prompt_float(
                "R_PU",
                R,
                "Branch resistance in per unit on the system MVA base.",
                "pu",
                must_positive=False
            )

        if X is None or (isinstance(X, float) and math.isnan(X)):
            X = _prompt_float(
                "X_PU",
                X,
                "Branch reactance in per unit on the system MVA base.",
                "pu",
                must_positive=False
            )

        if R == 0 and X == 0:
            raise ValueError(
                "R_PU = 0 and X_PU = 0 — zero-impedance branch, cannot compute line angle.")

        s_lim = 1.5 * rate2
        z_lim = (0.85 ** 2) * self.s_base / s_lim

        if R == 0:
            phi_deg = 90.0 if X > 0 else -90.0
        else:
            phi_deg = math.degrees(math.atan(X / R))
            if R < 0:
                phi_deg += 180.0 if X >= 0 else -180.0

        angle_diff_rad = math.radians(phi_deg - 30.0)
        cos_val        = math.cos(angle_diff_rad)
        if abs(cos_val) < 1e-10:
            raise ValueError(
                f"cos(φ − 30°) ≈ 0  (φ = {phi_deg:.2f}°) — reach undefined at this angle")
        z3_reach = z_lim / cos_val

        z3_r = z3_reach * math.cos(math.radians(phi_deg))
        z3_x = z3_reach * math.sin(math.radians(phi_deg))

        z_base_ohm   = (from_kv ** 2) / self.s_base
        z3_reach_ohm = z3_reach * z_base_ohm

        return {
            'from_bus':     branch['FROM_BUS'],
            'to_bus':       branch['TO_BUS'],
            'ckt':          branch['CKT'],
            'from_kv':      from_kv,
            'rate_b_mva':   rate2,
            'R_pu':         R,
            'X_pu':         X,
            'phi_deg':      round(phi_deg, 3),
            's_lim_mva':    round(s_lim, 3),
            'z_lim_pu':     round(z_lim, 6),
            'z3_reach_pu':  round(z3_reach, 6),
            'z3_r_pu':      round(z3_r, 6),
            'z3_x_pu':      round(z3_x, 6),
            'z_base_ohm':   round(z_base_ohm, 4),
            'z3_reach_ohm': round(z3_reach_ohm, 4),
        }


# ═══════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════

def _cfg(config: pd.DataFrame, var: str, cast=str, default=None):
    row = config[config.Variable == var]
    if row.empty:
        return default
    v = row['Value'].iloc[0]
    return default if (str(v).strip().lower() == 'nan' or str(v).strip() == '') else cast(v)


def load_branches(processing_dir: Path, case_name: str) -> pd.DataFrame:
    """Try monitored_lines.csv first, fall back to full branches CSV."""
    monitored = processing_dir / 'monitored_lines.csv'
    full      = processing_dir / f'{case_name}_branches.csv'

    if monitored.exists():
        df = pd.read_csv(monitored)
        # monitored_lines has FROM_BUS / TO_BUS / CKT — ensure type consistency
        print(f"  Using monitored lines: {monitored.name} ({len(df)} lines)")
    elif full.exists():
        df = pd.read_csv(full)
        df = df[df['STAT'] == 1].reset_index(drop=True)   # in-service only
        print(f"  Using full branch list: {full.name} ({len(df)} lines in-service)")
    else:
        raise FileNotFoundError(
            f"Neither {monitored} nor {full} found. Run Step1 and/or Step3b first.")

    # Normalise column names to uppercase
    df.columns = [c.upper() for c in df.columns]
    return df


def _parse_line_str(s: str, df: pd.DataFrame) -> pd.Series | None:
    """
    Try to parse 's' as FROM_BUS-TO_BUS-CKT and look it up in df.
    Returns the matching row or None if not found / bad format.
    """
    parts = s.strip().split('-')
    if len(parts) != 3:
        return None
    try:
        fb  = int(parts[0])
        tb  = int(parts[1])
        ckt = str(parts[2]).strip()
    except ValueError:
        return None

    mask = (
        (df['FROM_BUS'].astype(int) == fb) &
        (df['TO_BUS'].astype(int)   == tb) &
        (df['CKT'].astype(str).str.strip() == ckt)
    )
    hits = df[mask]
    return hits.iloc[0] if not hits.empty else None


def pick_line(df: pd.DataFrame, line_arg: str | None) -> pd.Series:
    """
    Return a single branch row.

    Resolution order:
      1. --line command-line argument (FROM_BUS-TO_BUS-CKT)
      2. Interactive prompt — user may enter either:
           • a row number  from the printed list
           • a line string  e.g.  5001-5003-1
    """
    def label(r):
        fb  = int(r['FROM_BUS'])
        tb  = int(r['TO_BUS'])
        ckt = str(r['CKT']).strip()
        fkv = f"{float(r.get('FROM_KV', 0)):.0f}" if 'FROM_KV' in r.index else "?"
        return f"{fb:>6} → {tb:<6}  ckt {ckt:<3}  {fkv} kV"

    # ── CLI argument ──────────────────────────────────────────────────────
    if line_arg:
        row = _parse_line_str(line_arg, df)
        if row is None:
            raise ValueError(
                f"--line '{line_arg}' not found.\n"
                "  Format: FROM_BUS-TO_BUS-CKT  (e.g.  5001-5003-1)\n"
                "  Check that the line exists in the branch data and is in-service.")
        return row

    # ── Interactive ───────────────────────────────────────────────────────
    print("\nAvailable lines:")
    print(f"  {'#':>4}   {'FROM':>6} → {'TO':<6}  {'CKT':<4}  kV")
    print("  " + "-" * 48)
    for i, (_, row) in enumerate(df.iterrows()):
        print(f"  {i+1:>4}   {label(row)}")
    print(f"\n  Enter a row number [1–{len(df)}]  OR  type FROM_BUS-TO_BUS-CKT  (e.g. 5001-5003-1)")

    while True:
        try:
            raw = input("  Selection: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nAborted.")
            sys.exit(0)

        if not raw:
            print("  Please enter a number or FROM-TO-CKT string.")
            continue

        # Try as integer index first
        try:
            idx = int(raw)
            if 1 <= idx <= len(df):
                return df.iloc[idx - 1]
            print(f"  Number out of range — enter 1 to {len(df)}.")
            continue
        except ValueError:
            pass

        # Try as FROM-TO-CKT string
        row = _parse_line_str(raw, df)
        if row is not None:
            return row

        # Neither worked — give specific feedback
        parts = raw.split('-')
        if len(parts) == 3:
            print(f"  Line '{raw}' not found in the branch list. "
                  "Check bus numbers and circuit ID.")
        else:
            print(f"  '{raw}' is not a valid number or FROM-TO-CKT string. "
                  "Example: 5001-5003-1")


def find_sim_columns(df_sim: pd.DataFrame, from_bus: int, to_bus: int, ckt: str):
    """
    Return (volt_col, p_col, q_col) for the selected line from the sim CSV.
    VOLT column is for from_bus; LINE_fb_tb_ckt_P/Q for the power flow.
    """
    # Voltage at from_bus
    volt_col = None
    for col in df_sim.columns:
        if col.split()[0].lower() == 'volt':
            nums = [int(x) for x in re.findall(r'\b(\d{4,6})\b', col)]
            if nums and nums[0] == from_bus:
                volt_col = col
                break

    # Line P and Q
    p_col = q_col = None
    ckt_int = int(ckt) if ckt.isdigit() else None
    pattern = re.compile(
        rf'^LINE_{from_bus}_{to_bus}_(\d+)_(P|Q)$', re.IGNORECASE)
    for col in df_sim.columns:
        m = pattern.match(col)
        if m:
            col_ckt = int(m.group(1))
            col_pq  = m.group(2).upper()
            if ckt_int is None or col_ckt == ckt_int:
                if col_pq == 'P':
                    p_col = col
                else:
                    q_col = col

    return volt_col, p_col, q_col


# ═══════════════════════════════════════════════════════════════════════════
# IMPEDANCE TRAJECTORY
# ═══════════════════════════════════════════════════════════════════════════

def compute_trajectory(df_sim: pd.DataFrame, t: np.ndarray,
                       volt_col: str, p_col: str, q_col: str) -> tuple:
    """
    Compute Z(t) = V(t)^2 / (P(t) - j*Q(t))  [all in pu on 100 MVA base].

    V in p.u. in the sim files. P, Q, needs to be divided by 100. 10 MVA Sbase.

    Returns (R_traj, X_traj) arrays, same length as t, with NaN where
    |S| is too small to be meaningful (near zero-load instants).
    """
    V = df_sim[volt_col].to_numpy()
    P = df_sim[p_col].to_numpy()/100
    Q = df_sim[q_col].to_numpy()/100 if q_col else np.zeros_like(P)

    # Z = V² / (P - jQ)  →  R + jX = V²(P + jQ) / (P² + Q²)
    V2    = V ** 2
    denom = P ** 2 + Q ** 2
    # Mask near-zero load to avoid nonsensical huge impedances
    with np.errstate(invalid='ignore', divide='ignore'):
        R_traj = np.where(denom > 1e-6, V2 * P / denom, np.nan)
        X_traj = np.where(denom > 1e-6, V2 * Q / denom, np.nan)  # Note: -(-Q) = Q

    return R_traj, X_traj


# ═══════════════════════════════════════════════════════════════════════════
# MHO CIRCLE
# ═══════════════════════════════════════════════════════════════════════════

def mho_circle(z3_reach: float, phi_deg: float, n: int = 360):
    """
    Return (R_circle, X_circle) for a mho characteristic.
    The mho circle passes through the origin and its diameter end-point
    is the reach vector Z3_reach∠phi.
    Centre = reach_vector / 2, radius = z3_reach / 2.
    """
    cx = 0.5 * z3_reach * math.cos(math.radians(phi_deg))
    cy = 0.5 * z3_reach * math.sin(math.radians(phi_deg))
    r  = z3_reach / 2.0
    angles = np.linspace(0, 2 * math.pi, n)
    return cx + r * np.cos(angles), cy + r * np.sin(angles)


# ═══════════════════════════════════════════════════════════════════════════
# PLOT
# ═══════════════════════════════════════════════════════════════════════════

def plot_impedance(t: np.ndarray, R_traj: np.ndarray, X_traj: np.ndarray,
                   result: dict, line_tag: str, run_tag: str,
                   output_dir: str, start_time: float = 0.0):
    """
    R-X diagram with:
      - Zone 3 mho circle
      - Line impedance point (R_pu + jX_pu)
      - Pre-fault operating point (t < start_time)
      - Impedance trajectory (time-coloured)
    """
    z3   = result['z3_reach_pu']
    phi  = result['phi_deg']
    R_ln = result['R_pu']
    X_ln = result['X_pu']

    circ_R, circ_X = mho_circle(z3, phi)

    # Pre-fault point = median of first 10% of trajectory
    n_pre = max(1, len(t) // 10)
    R_pre = float(np.nanmedian(R_traj[:n_pre]))
    X_pre = float(np.nanmedian(X_traj[:n_pre]))

    # ── Figure ────────────────────────────────────────────────────────────
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))

    ax = axes[0]
    ax.set_aspect('equal')
    # Zone 3 mho circle
    ax.plot(circ_R, circ_X, color='#e8623a', lw=1.8, ls='--', label='Zone 3 mho boundary')

    # # Line impedance
    # ax.plot(R_ln, X_ln, 's', color='#e89030', ms=9, zorder=5,
    #         label=f'Line Z  ({R_ln:.4f} + j{X_ln:.4f} pu)')

    # Pre-fault operating point
    ax.plot(R_pre, X_pre, 'D', color='#40b878', ms=8, zorder=5,
            label=f'Pre-fault op point  ({R_pre:.4f} + j{X_pre:.4f} pu)')

    # Trajectory coloured by time
    valid = ~(np.isnan(R_traj) | np.isnan(X_traj))
    if valid.any():
        t_v   = t[valid]
        R_v   = R_traj[valid]
        X_v   = X_traj[valid]
        norm  = plt.Normalize(t_v.min(), t_v.max())
        cmap  = cm.plasma
        for i in range(len(R_v) - 1):
            c = cmap(norm(t_v[i]))
            ax.plot(R_v[i:i+2], X_v[i:i+2], color=c, lw=1.2, alpha=0.85)
        sm = plt.cm.ScalarMappable(cmap=cmap, norm=norm)
        sm.set_array([])
        cbar = fig.colorbar(sm, ax=ax, pad=0.02)
        cbar.set_label('Time (s)', fontsize=9)
        plt.setp(cbar.ax.yaxis.get_ticklabels(), fontsize=8)

    ax.axhline(0, color='#1a3a5c', lw=0.7)
    ax.axvline(0, color='#1a3a5c', lw=0.7)

    ax.set_xlabel('Resistance R (pu)',  fontsize=10)
    ax.set_ylabel('Reactance X (pu)',   fontsize=10)
    ax.set_title(f'Impedance Trajectory — {line_tag}',
                  fontsize=11, pad=8)
    for spine in ax.spines.values():
        spine.set_edgecolor('#1a3a5c')

    leg = ax.legend(fontsize=8, edgecolor='#1a3a5c',)

    # ── Time-series panel ─────────────────────────────────────────────────
    ax2 = axes[1]

    Z_mag = np.sqrt(R_traj**2 + X_traj**2)
    ax2.plot(t, Z_mag, lw=1.3, label='|Z| (pu)')
    ax2.axhline(z3, color='#e8623a', lw=1.5, ls='--',
                label=f'Z3 reach = {z3:.4f} pu')
    # Mark when trajectory enters the zone
    inside = Z_mag < z3
    if inside.any():
        first_in = t[inside][0]
        ax2.axvline(first_in, color='#e89030', lw=1.2, ls=':',
                    label=f'Enters Z3 at t={first_in:.3f} s')

    ax2.set_xlabel('Time (s)',     fontsize=10)
    ax2.set_ylabel('|Z| (pu)',     fontsize=10)
    ax2.set_title('Impedance Magnitude vs Time',  fontsize=11, pad=8)
    for spine in ax2.spines.values():
        spine.set_edgecolor('#1a3a5c')
    ax2.legend(fontsize=8, edgecolor='#1a3a5c')
    ax2.grid(True, color='#C0C0C0', lw=0.5)

    # ── Annotations ───────────────────────────────────────────────────────
    info = (
        f"From {result['from_bus']} → {result['to_bus']}  ckt {result['ckt']}\n"
        f"Z_line = {R_ln:.4f} + j{X_ln:.4f} pu\n"
        f"φ = {phi:.1f}°    RATE_B = {result['rate_b_mva']:.0f} MVA\n"
        f"S_lim = {result['s_lim_mva']:.0f} MVA    Z_lim = {result['z_lim_pu']:.4f} pu\n"
        f"Z3 reach = {z3:.4f} pu"
    )
    fig.text(0.5, 0.01, info, ha='center', va='bottom',
             fontsize=8,
             bbox=dict( edgecolor='#1a3a5c',
                       boxstyle='round,pad=0.4'))

    plt.tight_layout(rect=[0, 0.08, 1, 1])

    png_path = os.path.join(output_dir, f"zone3_{line_tag}_{run_tag}.png")
    plt.savefig(png_path, dpi=150, bbox_inches='tight',
                facecolor=fig.get_facecolor())
    plt.close()
    print(f"-> Plot saved: {png_path}")
    return png_path


# ═══════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="Zone 3 relay reach calculator and impedance trajectory plotter.")
    parser.add_argument(
        '--line', default=None,
        help="Line to analyse as FROM_BUS-TO_BUS-CKT  (e.g. 5001-5003-1). "
             "If omitted, an interactive list is shown.")
    parser.add_argument(
        '--s-base', type=float, default=100.0,
        help="System MVA base (default: 100).")
    args = parser.parse_args()

    # ── Config ───────────────────────────────────────────────────────────
    root        = Path.cwd()
    config      = pd.read_csv(root / "simulation_config.csv")
    case_name   = _cfg(config, 'case_name')
    bus_number  = _cfg(config, 'bus_number',            int)
    osc_freq    = _cfg(config, 'oscillation_frequency', float)
    osc_amp     = _cfg(config, 'oscillation_amplitude', float)

    processing_dir = root / "Processing"
    results_dir    = root / "results"
    results_dir.mkdir(exist_ok=True)

    freq_str = str(osc_freq).rstrip('0').rstrip('.')
    amp_str  = str(int(osc_amp)) if osc_amp == int(osc_amp) else str(osc_amp)
    run_tag  = f"bus{bus_number}_{freq_str}Hz_{amp_str}MW"
    sim_file = results_dir / f"{bus_number}_{osc_freq}_Hz_{osc_amp}MW_sim.csv"

    print(f"Case    : {case_name}")
    print(f"Run tag : {run_tag}")
    print(f"Sim file: {sim_file}")

    # ── Branch data ───────────────────────────────────────────────────────
    branches = load_branches(processing_dir, case_name)

    # ── Line selection ────────────────────────────────────────────────────
    selected = pick_line(branches, args.line)
    from_bus = int(selected['FROM_BUS'])
    to_bus   = int(selected['TO_BUS'])
    ckt      = str(selected['CKT']).strip()
    line_tag = f"{from_bus}_{to_bus}_ckt{ckt}"
    print(f"\nSelected: {from_bus} → {to_bus}  ckt {ckt}  "
          f"({float(selected.get('FROM_KV', 0)):.0f} kV)")

    # ── Zone 3 calculation ────────────────────────────────────────────────
    calc = Zone3Calculator(s_base=args.s_base)
    try:
        result = calc.calculate(selected.to_dict())
    except ValueError as e:
        print(f"\nERROR: {e}")
        sys.exit(1)

    print("\n── Zone 3 Results ────────────────────────────────────────────")
    print(f"  Line impedance  : {result['R_pu']:.5f} + j{result['X_pu']:.5f} pu")
    print(f"  Line angle φ    : {result['phi_deg']:.2f}°")
    print(f"  RATE_B_MVA      : {result['rate_b_mva']:.1f} MVA")
    print(f"  S_lim           : {result['s_lim_mva']:.1f} MVA")
    print(f"  Z_lim           : {result['z_lim_pu']:.5f} pu")
    print(f"  Z3 reach (pu)   : {result['z3_reach_pu']:.5f} pu")
    print(f"  Z3 reach (Ω)    : {result['z3_reach_ohm']:.3f} Ω  (primary, "
          f"{result['from_kv']:.0f} kV base)")
    print("──────────────────────────────────────────────────────────────")

    # Save Zone 3 result CSV
    z3_csv = results_dir / f"zone3_{line_tag}_{run_tag}.csv"
    pd.DataFrame([result]).to_csv(z3_csv, index=False)
    print(f"\n-> Zone 3 results saved: {z3_csv}")

    # ── Load simulation data ──────────────────────────────────────────────
    if not sim_file.exists():
        print(f"\nWARNING: Simulation file not found ({sim_file}).")
        print("Zone 3 CSV saved. Skipping trajectory plot.")
        return

    print("\nLoading simulation CSV…")
    df_sim   = pd.read_csv(str(sim_file))
    time_col = df_sim.columns[0]
    t        = df_sim[time_col].to_numpy()
    t        = t - t[0]    # shift to start at 0

    volt_col, p_col, q_col = find_sim_columns(df_sim, from_bus, to_bus, ckt)

    if volt_col is None:
        print(f"WARNING: No VOLT channel found for bus {from_bus}. "
              "Cannot compute trajectory.")
        return
    if p_col is None:
        print(f"WARNING: No LINE_{from_bus}_{to_bus}_{ckt}_P channel found. "
              "Cannot compute trajectory.")
        return

    print(f"  Voltage channel : {volt_col}")
    print(f"  P flow channel  : {p_col}")
    print(f"  Q flow channel  : {q_col or '(not found — assuming Q=0)'}")

    # ── Impedance trajectory ──────────────────────────────────────────────
    R_traj, X_traj = compute_trajectory(df_sim, t, volt_col, p_col, q_col)

    # ── Plot ─────────────────────────────────────────────────────────────
    print("\nGenerating plot…")
    plot_impedance(t, R_traj, X_traj, result, line_tag, run_tag,
                   str(results_dir))

    print("\nDone.")


if __name__ == "__main__":
    main()