# -*- coding: utf-8 -*-
"""
Step8_ras_check.py
===================
Checks whether a user-defined Remedial Action Scheme (RAS) trigger condition
was met during a simulation, and produces a diagnostic plot. Rudimentary logic only.

Supported trigger signals
--------------------------
Bus selected:
  • Voltage magnitude (VOLT channel, pu)

Line selected:
  • Active power flow P (LINE_fb_tb_ckt_P channel, pu × 100 = MW)
  • Reactive power flow Q (LINE_fb_tb_ckt_Q channel, pu × 100 = MVar)
  • Angle difference  Δθ = θ_from − θ_to  (ANGL channels, degrees)

Trigger logic
-------------
  ABOVE threshold: signal > threshold  for a contiguous window ≥ duration_sec
  BELOW threshold: signal < threshold  for a contiguous window ≥ duration_sec

Usage
-----
  python Step8_ras_check.py                   # fully interactive
  python Step8_ras_check.py --bus 5003 --signal volt --threshold 1.05 --duration 0.5 --direction above
  python Step8_ras_check.py --line 5001-5003-1 --signal P --threshold 300 --duration 0.3 --direction above

Outputs (saved to results/)
---------------------------
  ras_check_<element_tag>_<run_tag>.png   — annotated time-series plot
  ras_check_<element_tag>_<run_tag>.csv   — per-time-step table with violation flag
"""

import os
import re
import sys
import argparse
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from pathlib import Path


POWER_SCALE = 100.0   # pu → MW / MVar (matches Step5)


# ═══════════════════════════════════════════════════════════════════════════
# CONFIG HELPER
# ═══════════════════════════════════════════════════════════════════════════

def _cfg(config: pd.DataFrame, var: str, cast=str, default=None):
    row = config[config.Variable == var]
    if row.empty:
        return default
    v = row['Value'].iloc[0]
    return default if (str(v).strip().lower() == 'nan' or str(v).strip() == '') else cast(v)


# ═══════════════════════════════════════════════════════════════════════════
# SIMULATION DATA LOADER
# ═══════════════════════════════════════════════════════════════════════════

def load_sim(sim_file: Path) -> tuple[np.ndarray, pd.DataFrame]:
    """Load full simulation CSV, shift time to start at 0."""
    df       = pd.read_csv(str(sim_file))
    time_col = df.columns[0]
    t        = df[time_col].to_numpy()
    t        = t - t[0]
    return t, df


# ═══════════════════════════════════════════════════════════════════════════
# ELEMENT & SIGNAL SELECTION
# ═══════════════════════════════════════════════════════════════════════════

def _extract_bus_nums(col: str) -> list[int]:
    return [int(x) for x in re.findall(r'\b(\d{4,6})\b', col)]


def _prefix(col: str) -> str:
    return col.split()[0].lower()


def list_buses(df: pd.DataFrame) -> list[int]:
    """All bus numbers with a VOLT channel in the sim CSV."""
    buses = []
    for col in df.columns:
        if _prefix(col) == 'volt':
            nums = _extract_bus_nums(col)
            if nums:
                buses.append(nums[0])
    return sorted(set(buses))


def list_lines(df: pd.DataFrame) -> list[tuple[int, int, int]]:
    """All (from_bus, to_bus, ckt) tuples with a LINE P channel."""
    pattern = re.compile(r'^LINE_(\d+)_(\d+)_(\d+)_P$', re.IGNORECASE)
    lines = []
    for col in df.columns:
        m = pattern.match(col)
        if m:
            lines.append((int(m.group(1)), int(m.group(2)), int(m.group(3))))
    return sorted(set(lines))


def pick_element(df: pd.DataFrame,
                 bus_arg: int | None,
                 line_arg: str | None) -> tuple[str, dict]:
    """
    Returns (element_type, element_info).
    element_type : 'bus' or 'line'
    element_info : dict with relevant keys
    """
    buses = list_buses(df)
    lines = list_lines(df)

    # ── Both supplied on CLI ──────────────────────────────────────────────
    if bus_arg is not None and line_arg is not None:
        print("ERROR: Specify either --bus or --line, not both.")
        sys.exit(1)

    # ── Bus from CLI ──────────────────────────────────────────────────────
    if bus_arg is not None:
        if bus_arg not in buses:
            print(f"ERROR: Bus {bus_arg} has no VOLT channel in the simulation CSV.")
            print(f"  Available buses: {buses}")
            sys.exit(1)
        return 'bus', {'bus': bus_arg}

    # ── Line from CLI ─────────────────────────────────────────────────────
    if line_arg is not None:
        parts = line_arg.strip().split('-')
        if len(parts) != 3:
            print("ERROR: --line must be FROM_BUS-TO_BUS-CKT  e.g.  5001-5003-1")
            sys.exit(1)
        try:
            fb, tb, ckt = int(parts[0]), int(parts[1]), int(parts[2])
        except ValueError:
            print("ERROR: Bus numbers and circuit ID must be integers.")
            sys.exit(1)
        if (fb, tb, ckt) not in lines:
            print(f"ERROR: Line {fb}→{tb} ckt {ckt} has no P channel in the simulation CSV.")
            print(f"  Available lines: {lines}")
            sys.exit(1)
        return 'line', {'from_bus': fb, 'to_bus': tb, 'ckt': ckt}

    # ── Interactive ───────────────────────────────────────────────────────
    all_items = (
        [(f"Bus  {b:>6}  (voltage magnitude)", 'bus',  {'bus': b}) for b in buses] +
        [(f"Line {fb:>6} → {tb:<6} ckt {ckt}  (P / Q / angle diff)",
          'line', {'from_bus': fb, 'to_bus': tb, 'ckt': ckt})
         for fb, tb, ckt in lines]
    )

    print("\nAvailable monitored elements:")
    print(f"  {'#':>4}   Description")
    print("  " + "-" * 56)
    for i, (desc, _, _) in enumerate(all_items):
        print(f"  {i+1:>4}   {desc}")
    print(f"\n  Enter a row number [1–{len(all_items)}]:")

    while True:
        try:
            raw = input("  Selection: ").strip()
            idx = int(raw)
            if 1 <= idx <= len(all_items):
                _, etype, einfo = all_items[idx - 1]
                return etype, einfo
            print(f"  Out of range — enter 1 to {len(all_items)}.")
        except (ValueError, EOFError, KeyboardInterrupt):
            print("  Invalid input — please enter a number.")


def pick_signal(element_type: str, signal_arg: str | None) -> str:
    """
    For 'bus'  : only 'volt' is available.
    For 'line' : choose from 'P', 'Q', 'angle_diff'.
    Returns the canonical signal name.
    """
    if element_type == 'bus':
        if signal_arg and signal_arg.lower() not in ('volt', 'voltage', 'v'):
            print(f"WARNING: For a bus the only available signal is voltage magnitude.")
            print(f"  Ignoring --signal '{signal_arg}' and using 'volt'.")
        return 'volt'

    # Line signals
    valid = {'p': 'P', 'pflow': 'P', 'active': 'P',
             'q': 'Q', 'qflow': 'Q', 'reactive': 'Q',
             'angle': 'angle_diff', 'angle_diff': 'angle_diff',
             'delta': 'angle_diff', 'da': 'angle_diff'}

    if signal_arg:
        canon = valid.get(signal_arg.lower())
        if canon:
            return canon
        print(f"WARNING: --signal '{signal_arg}' not recognised for a line.")

    # Interactive
    options = [
        ('P',          'Active power flow P  (MW)'),
        ('Q',          'Reactive power flow Q  (MVar)'),
        ('angle_diff', 'Angle difference  Δθ = θ_from − θ_to  (degrees)'),
    ]
    print("\n  Select signal to monitor:")
    for i, (key, desc) in enumerate(options):
        print(f"    {i+1}. {desc}")
    while True:
        try:
            raw = input("  Selection [1-3]: ").strip()
            idx = int(raw)
            if 1 <= idx <= len(options):
                return options[idx - 1][0]
            print("  Enter 1, 2, or 3.")
        except (ValueError, EOFError, KeyboardInterrupt):
            print("  Invalid input.")


def prompt_float(prompt: str, allow_negative: bool = True) -> float:
    while True:
        try:
            val = float(input(f"  {prompt}: ").strip())
            if not allow_negative and val < 0:
                print("  Must be ≥ 0.")
                continue
            return val
        except (ValueError, EOFError, KeyboardInterrupt):
            print("  Invalid — enter a number.")


def prompt_direction() -> str:
    print("\n  Trigger direction:")
    print("    1. ABOVE threshold  (signal > threshold)")
    print("    2. BELOW threshold  (signal < threshold)")
    while True:
        try:
            raw = input("  Selection [1/2]: ").strip()
            if raw == '1':
                return 'above'
            if raw == '2':
                return 'below'
            print("  Enter 1 or 2.")
        except (ValueError, EOFError, KeyboardInterrupt):
            print("  Invalid input.")


# ═══════════════════════════════════════════════════════════════════════════
# SIGNAL EXTRACTION
# ═══════════════════════════════════════════════════════════════════════════

def extract_signal(df: pd.DataFrame, t: np.ndarray,
                   element_type: str, element_info: dict,
                   signal: str) -> tuple[np.ndarray, str, str]:
    """
    Returns (values_array, signal_label, unit_string).
    """
    if element_type == 'bus':
        bus = element_info['bus']
        col = next((c for c in df.columns
                    if _prefix(c) == 'volt'
                    and _extract_bus_nums(c)
                    and _extract_bus_nums(c)[0] == bus), None)
        if col is None:
            print(f"ERROR: VOLT channel for bus {bus} not found.")
            sys.exit(1)
        return df[col].to_numpy(), f"Bus {bus} voltage magnitude", "pu"

    # Line
    fb  = element_info['from_bus']
    tb  = element_info['to_bus']
    ckt = element_info['ckt']

    if signal == 'P':
        pattern = re.compile(rf'^LINE_{fb}_{tb}_{ckt}_P$', re.IGNORECASE)
        col = next((c for c in df.columns if pattern.match(c)), None)
        if col is None:
            print(f"ERROR: LINE_{fb}_{tb}_{ckt}_P channel not found in simulation CSV.")
            sys.exit(1)
        return df[col].to_numpy(), \
               f"Line {fb}→{tb} ckt {ckt}  P flow", "MW"

    if signal == 'Q':
        pattern = re.compile(rf'^LINE_{fb}_{tb}_{ckt}_Q$', re.IGNORECASE)
        col = next((c for c in df.columns if pattern.match(c)), None)
        if col is None:
            print(f"ERROR: LINE_{fb}_{tb}_{ckt}_Q channel not found in simulation CSV.")
            print("  Q channels are only logged if they were included in Step3b monitoring.")
            sys.exit(1)
        return df[col].to_numpy(), \
               f"Line {fb}→{tb} ckt {ckt}  Q flow", "MVar"

    if signal == 'angle_diff':
        # Find ANGL channels for from_bus and to_bus
        def angl_col(bus: int):
            return next((c for c in df.columns
                         if _prefix(c) == 'angl'
                         and _extract_bus_nums(c)
                         and _extract_bus_nums(c)[0] == bus), None)

        col_from = angl_col(fb)
        col_to   = angl_col(tb)

        missing = []
        if col_from is None:
            missing.append(f"ANGL channel for bus {fb} (from-bus)")
        if col_to is None:
            missing.append(f"ANGL channel for bus {tb} (to-bus)")
        if missing:
            print(f"ERROR: Cannot compute angle difference — missing:")
            for m in missing:
                print(f"  • {m}")
            print("  Angle channels are logged when generator buses are monitored in Step3b.")
            sys.exit(1)

        delta = df[col_from].to_numpy() - df[col_to].to_numpy()
        return delta, f"Line {fb}→{tb} ckt {ckt}  Δθ (from−to)", "degrees"

    print(f"ERROR: Unknown signal '{signal}'.")
    sys.exit(1)


# ═══════════════════════════════════════════════════════════════════════════
# RAS TRIGGER LOGIC
# ═══════════════════════════════════════════════════════════════════════════

def find_violations(values: np.ndarray, t: np.ndarray,
                    threshold: float, direction: str,
                    duration_sec: float) -> list[dict]:
    """
    Scan for contiguous windows where the condition holds for ≥ duration_sec.

    Returns list of dicts:
        { 't_start', 't_end', 'duration', 'peak_value', 'peak_time',
          'indices' (slice) }
    """
    if direction == 'above':
        mask = values > threshold
    else:
        mask = values < threshold

    dt = float(np.median(np.diff(t)))
    min_samples = max(1, int(np.ceil(duration_sec / dt)))

    violations = []
    in_window  = False
    win_start  = 0

    for i in range(len(mask)):
        if mask[i] and not in_window:
            in_window = True
            win_start = i
        elif not mask[i] and in_window:
            in_window = False
            length = i - win_start
            if length >= min_samples:
                seg   = values[win_start:i]
                p_idx = win_start + (np.argmax(seg) if direction == 'above'
                                     else np.argmin(seg))
                violations.append({
                    't_start':   round(float(t[win_start]), 4),
                    't_end':     round(float(t[i - 1]),     4),
                    'duration':  round(float(t[i - 1] - t[win_start]), 4),
                    'peak_value': round(float(values[p_idx]), 4),
                    'peak_time':  round(float(t[p_idx]), 4),
                    'i_start':   win_start,
                    'i_end':     i,
                })

    # Handle window still open at end of series
    if in_window:
        i = len(mask)
        length = i - win_start
        if length >= min_samples:
            seg   = values[win_start:i]
            p_idx = win_start + (np.argmax(seg) if direction == 'above'
                                 else np.argmin(seg))
            violations.append({
                't_start':   round(float(t[win_start]), 4),
                't_end':     round(float(t[-1]),        4),
                'duration':  round(float(t[-1] - t[win_start]), 4),
                'peak_value': round(float(values[p_idx]), 4),
                'peak_time':  round(float(t[p_idx]), 4),
                'i_start':   win_start,
                'i_end':     i,
            })

    return violations


# ═══════════════════════════════════════════════════════════════════════════
# PLOT
# ═══════════════════════════════════════════════════════════════════════════

def plot_ras(t: np.ndarray, values: np.ndarray,
             signal_label: str, unit: str,
             threshold: float, direction: str, duration_sec: float,
             violations: list[dict],
             element_tag: str, run_tag: str,
             output_dir: str) -> str:
 
    triggered = len(violations) > 0
    thr_label = (">" if direction == 'above' else "<") + f" {threshold} {unit}"
 
    fig, axes = plt.subplots(2, 1, figsize=(13, 8),
                             gridspec_kw={'height_ratios': [3, 1]})
    fig.patch.set_facecolor('#f5f7fa')
 
    # ── Main time-series panel ────────────────────────────────────────────
    ax = axes[0]
    ax.set_facecolor('#ffffff')
 
    # Signal trace
    ax.plot(t, values, color='#1a6ea8', lw=1.4, label=signal_label, zorder=3)
 
    # Threshold line
    thr_color = '#c0392b' if direction == 'above' else '#27ae60'
    ax.axhline(threshold, color=thr_color, lw=1.6, ls='--',
               label=f'RAS threshold  {thr_label}', zorder=4)
 
    # Shade violation windows
    first_shade = True
    for v in violations:
        label_shade = (f'RAS condition met  (≥ {duration_sec} s)'
                       if first_shade else None)
        ax.axvspan(v['t_start'], v['t_end'],
                   color='#e74c3c', alpha=0.15, zorder=2,
                   label=label_shade)
        # Peak marker
        ax.plot(v['peak_time'], v['peak_value'],
                'v' if direction == 'above' else '^',
                color='#e67e22', ms=8, zorder=5)
        # Duration annotation
        mid_t = (v['t_start'] + v['t_end']) / 2
        ax.annotate(f"{v['duration']:.2f} s",
                    xy=(mid_t, v['peak_value']),
                    xytext=(mid_t, v['peak_value'] * 1.01
                            if direction == 'above'
                            else v['peak_value'] * 0.99),
                    ha='center', va='bottom' if direction == 'above' else 'top',
                    fontsize=8, color='#e67e22')
        first_shade = False
 
    ax.set_ylabel(f"{signal_label.split('  ')[-1]}  ({unit})",
                  color='#2c3e50', fontsize=10)
    ax.set_title(
        f"RAS Check — {signal_label}\n"
        f"Trigger: signal {thr_label}  for ≥ {duration_sec} s  |  "
        f"{'⚠ RAS CONDITION MET' if triggered else '✓ No RAS trigger'}",
        color='#c0392b' if triggered else '#27ae60',
        fontsize=11, pad=8
    )
    ax.tick_params(colors='#2c3e50')
    for spine in ax.spines.values():
        spine.set_edgecolor('#bdc3c7')
    ax.grid(True, color='#ecf0f1', lw=0.8, zorder=1)
    ax.legend(fontsize=8, facecolor='#ffffff', edgecolor='#bdc3c7',
              labelcolor='#2c3e50', loc='upper right')
 
    # ── Violation flag panel ──────────────────────────────────────────────
    ax2 = axes[1]
    ax2.set_facecolor('#ffffff')
 
    flag = np.zeros(len(t))
    for v in violations:
        flag[v['i_start']:v['i_end']] = 1.0
 
    ax2.fill_between(t, flag, color='#e74c3c', alpha=0.6,
                     step='pre', label='Condition active')
    ax2.set_ylim(-0.1, 1.5)
    ax2.set_yticks([0, 1])
    ax2.set_yticklabels(['OFF', 'ON'], color='#2c3e50', fontsize=8)
    ax2.set_xlabel('Time (s)', color='#2c3e50', fontsize=10)
    ax2.set_ylabel('RAS trigger', color='#2c3e50', fontsize=10)
    ax2.tick_params(colors='#2c3e50', axis='x')
    ax2.tick_params(colors='#2c3e50', axis='y')
    for spine in ax2.spines.values():
        spine.set_edgecolor('#bdc3c7')
    ax2.grid(True, color='#ecf0f1', lw=0.8, axis='x')
 
    # ── Summary box ───────────────────────────────────────────────────────
    total_viol_time = sum(v['duration'] for v in violations)
    summary_lines = [
        f"Signal : {signal_label}",
        f"Threshold : {thr_label}    Min duration : {duration_sec} s",
        f"Violation windows found : {len(violations)}",
    ]
    if violations:
        worst = max(violations, key=lambda v: abs(v['peak_value'] - threshold))
        summary_lines += [
            f"Total time in violation : {total_viol_time:.3f} s",
            f"Worst exceedance : {worst['peak_value']:.4f} {unit}"
            f"  at t = {worst['peak_time']:.3f} s",
        ]
    else:
        summary_lines.append("Condition was never sustained for the required duration.")
 
    fig.text(0.5, 0.01, "   |   ".join(summary_lines),
             ha='center', va='bottom', fontsize=8, color='#2c3e50',
             bbox=dict(facecolor='#eaf2fb', edgecolor='#aed6f1',
                       boxstyle='round,pad=0.4'))
 
    plt.tight_layout(rect=[0, 0.06, 1, 1])
 
    png_path = os.path.join(output_dir, f"ras_check_{element_tag}_{run_tag}.png")
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
        description="RAS trigger checker — determines if a remedial action scheme "
                    "condition was sustained during simulation.")
    parser.add_argument('--bus',       type=int,   default=None,
                        help="Bus number to monitor (VOLT signal).")
    parser.add_argument('--line',      type=str,   default=None,
                        help="Line to monitor as FROM-TO-CKT  e.g.  5001-5003-1.")
    parser.add_argument('--signal',    type=str,   default=None,
                        help="Signal: 'volt' (bus) | 'P', 'Q', 'angle_diff' (line).")
    parser.add_argument('--threshold', type=float, default=None,
                        help="Threshold value (pu / MW / MVar / degrees).")
    parser.add_argument('--duration',  type=float, default=None,
                        help="Minimum sustained duration (seconds).")
    parser.add_argument('--direction', type=str,   default=None,
                        choices=['above', 'below'],
                        help="'above' = signal > threshold; 'below' = signal < threshold.")
    args = parser.parse_args()

    # ── Config ───────────────────────────────────────────────────────────
    root   = Path.cwd()
    config = pd.read_csv(root / "simulation_config.csv")

    case_name  = _cfg(config, 'case_name')
    bus_number = _cfg(config, 'bus_number',            int)
    osc_freq   = _cfg(config, 'oscillation_frequency', float)
    osc_amp    = _cfg(config, 'oscillation_amplitude', float)

    results_dir = root / "results"
    results_dir.mkdir(exist_ok=True)

    freq_str = str(osc_freq).rstrip('0').rstrip('.')
    amp_str  = str(int(osc_amp)) if osc_amp == int(osc_amp) else str(osc_amp)
    run_tag  = f"bus{bus_number}_{freq_str}Hz_{amp_str}MW"
    sim_file = results_dir / f"{bus_number}_{osc_freq}_Hz_{osc_amp}MW_sim.csv"

    if not sim_file.exists():
        print(f"ERROR: Simulation file not found: {sim_file}")
        print("  Run Step4 first to generate the simulation output.")
        sys.exit(1)

    print(f"Case     : {case_name}")
    print(f"Run tag  : {run_tag}")
    print(f"Sim file : {sim_file}")

    # ── Load data ─────────────────────────────────────────────────────────
    t, df_sim = load_sim(sim_file)
    print(f"Loaded   : {len(t)} time points  (t = {t[0]:.2f} … {t[-1]:.2f} s)")

    # ── Element selection ─────────────────────────────────────────────────
    element_type, element_info = pick_element(df_sim, args.bus, args.line)

    if element_type == 'bus':
        element_tag = f"bus{element_info['bus']}"
    else:
        fb  = element_info['from_bus']
        tb  = element_info['to_bus']
        ckt = element_info['ckt']
        element_tag = f"line{fb}_{tb}_ckt{ckt}"

    print(f"\nMonitoring : {element_type.upper()}  {element_info}")

    # ── Signal selection ──────────────────────────────────────────────────
    signal = pick_signal(element_type, args.signal)
    print(f"Signal     : {signal}")

    # ── Extract signal ────────────────────────────────────────────────────
    values, signal_label, unit = extract_signal(
        df_sim, t, element_type, element_info, signal)

    print(f"\nSignal statistics:")
    print(f"  Min    : {np.nanmin(values):.4f} {unit}")
    print(f"  Max    : {np.nanmax(values):.4f} {unit}")
    print(f"  Mean   : {np.nanmean(values):.4f} {unit}")
    print(f"  Std    : {np.nanstd(values):.4f} {unit}")

    # ── Threshold ─────────────────────────────────────────────────────────
    if args.threshold is not None:
        threshold = args.threshold
    else:
        print(f"\n  Signal range: {np.nanmin(values):.4f} – {np.nanmax(values):.4f} {unit}")
        threshold = prompt_float(f"Enter RAS threshold ({unit})")

    # ── Direction ─────────────────────────────────────────────────────────
    if args.direction is not None:
        direction = args.direction
    else:
        direction = prompt_direction()

    # ── Duration ─────────────────────────────────────────────────────────
    if args.duration is not None:
        duration_sec = args.duration
    else:
        dt_sim = float(np.median(np.diff(t)))
        print(f"\n  Simulation time step ≈ {dt_sim*1000:.1f} ms")
        duration_sec = prompt_float(
            "Enter minimum sustained duration for RAS to act (seconds)",
            allow_negative=False)

    print(f"\nRAS logic  : signal {('>' if direction == 'above' else '<')} "
          f"{threshold} {unit}  for ≥ {duration_sec} s")

    # ── Find violations ───────────────────────────────────────────────────
    violations = find_violations(values, t, threshold, direction, duration_sec)

    if violations:
        print(f"\n⚠  RAS CONDITION MET — {len(violations)} violation window(s):")
        for i, v in enumerate(violations, 1):
            print(f"   Window {i}: t = {v['t_start']:.3f} s → {v['t_end']:.3f} s  "
                  f"({v['duration']:.3f} s)  |  "
                  f"peak = {v['peak_value']:.4f} {unit} at t = {v['peak_time']:.3f} s")
    else:
        print(f"\n✓  No RAS trigger — condition never sustained for {duration_sec} s.")

    # ── Save CSV ──────────────────────────────────────────────────────────
    flag = np.zeros(len(t), dtype=int)
    for v in violations:
        flag[v['i_start']:v['i_end']] = 1

    df_out = pd.DataFrame({
        'time_s':        t,
        signal.lower():  values,
        'threshold':     threshold,
        'condition_met': flag,
    })
    csv_path = results_dir / f"ras_check_{element_tag}_{run_tag}.csv"
    df_out.to_csv(csv_path, index=False)
    print(f"\n-> Results CSV: {csv_path}")

    # ── Plot ──────────────────────────────────────────────────────────────
    print("Generating plot…")
    plot_ras(t, values, signal_label, unit,
             threshold, direction, duration_sec,
             violations, element_tag, run_tag, str(results_dir))

    print("\nDone.")


if __name__ == "__main__":
    main()