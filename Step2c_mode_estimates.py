# -*- coding: utf-8 -*-
"""
Modal Parameter Estimation — Ringdown Analysis
Pipeline: FFT peak picking → Hankel SVD order → VARPRO fit → mode assembly
We want to identify risky frequencies excitable from the location being studied
"""

import numpy as np
from scipy.signal import find_peaks, decimate
from scipy.optimize import least_squares
from scipy.linalg import svd
import matplotlib.pyplot as plt


FREQ_MIN          = 0.1    # Hz  — inter-area lower bound
FREQ_MAX          = 3.0    # Hz  — local modes upper bound
PROMINENCE_RATIO  = 0.05   # FFT peak prominence relative to band max
N_ZEROPAD         = 4      # zero-padding factor
ENERGY_THRESHOLD  = 0.8  # Hankel SVD cumulative energy fallback
NOISE_FLOOR_RATIO = 1e-4   # singular values below this x S[0] = noise
ZETA_INIT         = 0.05   # initial damping ratio guess
OMEGA_TOL         = 0.05   # +/-5% frequency bounds in VARPRO
ZETA_BOUNDS       = (1e-4, 0.30)  # upper bound matches ZETA_MAX — keeps optimizer out of overdamped region
MATCH_TOL         = 0.05   # max relative deviation to accept a pole-FFT match
ZETA_MAX          = 0.30   # modes with damping above this are discarded as unreliable estimates
TOP_N_MODES       = 5      # number of highest-amplitude modes shown in plots and console table
TARGET_SPS        = 15     # target sample rate after decimation (sps)
                           # NOTE: 15 sps → Nyquist 7.5 Hz, but only 3 samples/cycle at 5 Hz.
                           # VARPRO basis functions become ill-conditioned near the Nyquist.
                           # Modes above ~3 Hz should be interpreted with caution at this rate.
FFT_SPS           = 5      # sample rate used exclusively for FFT peak picking
                           # Nyquist = 2.5 Hz — sufficient for inter-area / local mode detection
                           # VARPRO always uses the full-rate signal

# 1. Select peaks from the frequency spectrum

def fft_peak_picking(h, dt, freq_min=FREQ_MIN, freq_max=FREQ_MAX,
                     prominence_ratio=PROMINENCE_RATIO, n_zeropad=N_ZEROPAD):
    """Detect dominant modal frequencies from zero-padded FFT.
    Returns (omega_peaks [rad/s], freqs [Hz], H_mag)."""

    N_fft = n_zeropad * len(h)
    H     = np.fft.rfft(h, n=N_fft)
    freqs = np.fft.rfftfreq(N_fft, dt)
    H_mag = np.abs(H)

    band   = (freqs >= freq_min) & (freqs <= freq_max)
    H_band = H_mag.copy()
    H_band[~band] = 0.0

    peaks, _ = find_peaks(
        H_band,
        prominence=prominence_ratio * H_band.max(),
        distance=int(0.1 / (freqs[1] - freqs[0])),   # min 0.05 Hz separation
    )

    if len(peaks) == 0:
        raise ValueError(
            f"No FFT peaks found in [{freq_min}, {freq_max}] Hz. "
            "Try reducing prominence_ratio or widening the frequency band."
        )

    order       = np.argsort(H_mag[peaks])[::-1]   # dominant first
    omega_peaks = 2 * np.pi * freqs[peaks[order]]
    return omega_peaks, freqs, H_mag


# 2. Estimate Model order via Hankel SVD

def hankel_model_order(h, energy_threshold=ENERGY_THRESHOLD,
                       max_order=None, noise_floor_ratio=NOISE_FLOOR_RATIO):
    """Estimate model order from SVD of Hankel matrix.
    Returns (N_order [even int], S [singular values])."""

    L     = len(h) // 3
    K     = len(h) - L + 1
    H_mat = np.array([h[i:i + K] for i in range(L)])
    _, S, _ = svd(H_mat, full_matrices=False)

    cap = max_order or len(h) // 4

    # Method 1: count singular values above relative noise floor
    N_count = int(np.sum(S > noise_floor_ratio * S[0]))

    # Method 2: largest gap scan from the tail
    n_search = min(N_count + 10, len(S) - 1)
    if n_search > 1:
        gaps   = S[:n_search] / (S[1:n_search + 1] + 1e-12)
        weight = np.arange(1, len(gaps) + 1, dtype=float)
        N_gap  = int(np.argmax(gaps * weight)) + 1
    else:
        N_gap = 2

    # Method 3: cumulative energy
    energy   = np.cumsum(S ** 2) / np.sum(S ** 2)
    N_energy = int(np.searchsorted(energy, energy_threshold)) + 1

    N_order = max(N_count, N_energy)
    N_order = min(N_order, N_gap + 4, cap)
    N_order = max(N_order, 2)
    if N_order % 2 != 0:
        N_order += 1   # round to even — conjugate pairs
    if N_order>10:
        N_order=10
    return N_order, S


# 3. VARPRO separable nonlinear least squares

def _build_basis(t, params):
    """Build (N_samples x 2N_modes) basis matrix.
    params layout: [omega_n_0, zeta_0, omega_n_1, zeta_1, ...]"""

    N_modes = len(params) // 2
    Phi     = np.zeros((len(t), 2 * N_modes))
    for r in range(N_modes):
        omega_n = params[2 * r]
        zeta    = params[2 * r + 1]
        omega_d = omega_n * np.sqrt(max(1 - zeta ** 2, 1e-8))
        decay   = np.exp(-zeta * omega_n * t)
        Phi[:, 2 * r]     = decay * np.cos(omega_d * t)
        Phi[:, 2 * r + 1] = decay * np.sin(omega_d * t)
    return Phi


def _varpro_residual(params, t, h):
    """VARPRO residual: solve linear subproblem optimally, return residual vector."""
    Phi        = _build_basis(t, params)
    c, _, _, _ = np.linalg.lstsq(Phi, h, rcond=None)
    return h - Phi @ c


def varpro_fit(t, h, omega_init, zeta_init=ZETA_INIT,
               omega_tol=OMEGA_TOL, zeta_bounds=ZETA_BOUNDS):
    """VARPRO fit: nonlinear params (omega_n, zeta), linear params solved analytically.
    Returns (omega_n_fit, zeta_fit, c_fit)."""

    N_modes = len(omega_init)

    p0 = np.zeros(2 * N_modes)
    for r, w in enumerate(omega_init):
        p0[2 * r]     = w
        p0[2 * r + 1] = zeta_init

    lo, hi = [], []
    for w in omega_init:
        lo += [w * (1 - omega_tol), zeta_bounds[0]]
        hi += [w * (1 + omega_tol), zeta_bounds[1]]

    result = least_squares(
        _varpro_residual, p0, args=(t, h), bounds=(lo, hi),
        method='trf', ftol=1e-10, xtol=1e-10, gtol=1e-10, max_nfev=5000,
    )

    omega_n_fit = result.x[0::2]
    zeta_fit    = result.x[1::2]
    c_fit, _, _, _ = np.linalg.lstsq(_build_basis(t, result.x), h, rcond=None)
    return omega_n_fit, zeta_fit, c_fit


# 4.Pole-frequency matching and mode assembly

def match_and_assemble(omega_n_fit, zeta_fit, c_fit, omega_fft,
                       match_tol=MATCH_TOL, zeta_max=ZETA_MAX):
    """Match fitted poles to FFT peaks; discard spurious and overdamped poles.
    Returns list of mode dicts sorted by amplitude descending."""

    modes = []
    n_overdamped = 0
    for r in range(len(omega_n_fit)):
        w  = omega_n_fit[r]
        z  = zeta_fit[r]
        wd = w * np.sqrt(max(1 - z ** 2, 1e-8))

        diffs = np.abs(omega_fft - w) / omega_fft
        idx   = np.argmin(diffs)
        if diffs[idx] > match_tol:
            continue   # spurious pole — discard

        # Discard heavily overdamped poles — not physically meaningful oscillations
        if z > zeta_max:
            n_overdamped += 1
            continue

        c_cos, c_sin = c_fit[2 * r], c_fit[2 * r + 1]
        amplitude    = np.sqrt(c_cos ** 2 + c_sin ** 2)
        phase        = np.arctan2(-c_sin, c_cos)

        modes.append({
            'omega_n'  : w,
            'omega_d'  : wd,
            'freq_hz'  : w / (2 * np.pi),
            'zeta'     : z,
            'amplitude': amplitude,
            'phase'    : phase,
            'omega_fft': omega_fft[idx],
        })

    if n_overdamped:
        print(f"      [damping filter] {n_overdamped} pole(s) discarded (zeta > {zeta_max:.0%})")

    modes.sort(key=lambda m: m['amplitude'], reverse=True)
    return modes


# ---------------------------------------------------------------------------
# Top-level pipeline
# ---------------------------------------------------------------------------

def apply_decimation(h, dt, target_sps=TARGET_SPS):
    """Decimate h to target_sps using scipy.signal.decimate (Chebyshev anti-alias filter).
    Returns (h_dec, dt_dec). Passes through unchanged if target_sps is None or
    the signal is already at or below target_sps.

    Uses zero_phase=True (filtfilt internally) to avoid group-delay distortion —
    critical for VARPRO which fits both amplitude and phase of each mode.

    For large decimation factors (>13) scipy chains two decimate calls to avoid
    excessive filter order; this is handled automatically here by factoring the
    decimation ratio into two stages if needed."""

    if target_sps is None:
        return h, dt

    current_sps = round(1.0 / dt)
    factor = current_sps // target_sps

    if factor <= 1:
        print(f"[decimate] No decimation needed ({current_sps} sps ≤ {target_sps} sps target)")
        return h, dt

    # Chain into two stages if factor > 13 to keep filter order reasonable
    if factor > 13:
        f1 = int(np.round(np.sqrt(factor)))   # first stage factor
        f2 = factor // f1                      # second stage factor
        h = decimate(h, f1, zero_phase=True)
        h = decimate(h, f2, zero_phase=True)
    else:
        h = decimate(h, factor, zero_phase=True)

    dt_dec = dt * factor
    print(f"[decimate] {current_sps} sps → {round(1/dt_dec)} sps  (factor {factor})")
    return h, dt_dec



def extract_modes(h, dt, freq_min=FREQ_MIN, freq_max=FREQ_MAX,
                  prominence_ratio=PROMINENCE_RATIO, energy_threshold=ENERGY_THRESHOLD,
                  zeta_init=ZETA_INIT, omega_tol=OMEGA_TOL, match_tol=MATCH_TOL,
                  zeta_max=ZETA_MAX, n_zeropad=N_ZEROPAD, fft_sps=FFT_SPS, verbose=True):
    """Full automated pipeline.
    FFT peak picking uses a decimated copy of the signal (fft_sps).
    VARPRO fitting and model order estimation use the full-rate signal throughout.
    Returns (modes, residual, model_order, h_reconstructed, freqs, H_mag)."""

    t = np.arange(len(h)) * dt

    # Stage 1 — decimate to fft_sps for peak picking only; VARPRO always uses full signal
    h_fft, dt_fft = apply_decimation(h, dt, target_sps=fft_sps)
    if verbose:
        print(f"[1] FFT peak picking on signal decimated to {round(1/dt_fft)} sps "
              f"(full signal at {round(1/dt)} sps retained for VARPRO)")
    omega_fft, freqs, H_mag = fft_peak_picking(
        h_fft, dt_fft, freq_min, freq_max, prominence_ratio, n_zeropad)
    if verbose:
        print(f"[1] FFT peaks found: {len(omega_fft)}")
        for w in omega_fft:
            print(f"      {w / (2 * np.pi):.4f} Hz")

    # Stage 2 — model order from full signal
    N_order, S_vals = hankel_model_order(h, energy_threshold)
    N_modes = N_order // 2
    if verbose:
        print(f"[2] Model order (Hankel SVD): N = {N_order}  ->  {N_modes} modes")

    # Stage 3 — sequential seeding + joint global VARPRO
    if verbose:
        print(f"[3] Running sequential seed-finding + joint VARPRO...")

    # Pass A: fit FFT-dominant modes, subtract, find residual seeds
    omega_n1, zeta1, c1 = varpro_fit(t, h, omega_fft, zeta_init, omega_tol)

    Phi1    = _build_basis(t, np.array([v for pair in zip(omega_n1, zeta1) for v in pair]))
    h_resid = h - Phi1 @ c1

    n_remaining = (N_order // 2) - len(omega_fft)
    all_seeds   = list(omega_n1)   # refined seeds from pass 1

    if n_remaining > 0:
        N_fft_pad   = n_zeropad * len(h_resid)
        H_resid_f   = np.fft.rfft(h_resid, n=N_fft_pad)
        freqs_resid = np.fft.rfftfreq(N_fft_pad, dt)
        H_resid_mag = np.abs(H_resid_f)

        band   = (freqs_resid >= freq_min) & (freqs_resid <= freq_max)
        H_scan = H_resid_mag.copy(); H_scan[~band] = 0.0

        min_dist       = max(1, int(0.03 / (freqs_resid[1] - freqs_resid[0])))
        resid_peaks, _ = find_peaks(H_scan, prominence=1e-3 * H_scan.max(),
                                    distance=min_dist)
        resid_peaks    = resid_peaks[np.argsort(H_resid_mag[resid_peaks])[::-1]]

        if len(resid_peaks) >= n_remaining:
            omega_seeds2 = 2 * np.pi * freqs_resid[resid_peaks[:n_remaining]]
            all_seeds.extend(omega_seeds2)
            if verbose:
                for w in omega_seeds2:
                    print(f"      {w / (2 * np.pi):.4f} Hz  [residual seed]")
        else:
            if verbose:
                print(f"      [!] Only {len(resid_peaks)} residual peaks, "
                      f"need {n_remaining}. Proceeding with {len(omega_fft)} modes.")

    # Pass B: joint VARPRO on original signal with all seeds
    omega_seeds_all = np.array(all_seeds)
    if verbose:
        print(f"[3] Joint VARPRO with {len(omega_seeds_all)} modes on full signal...")

    omega_n_fit, zeta_fit, c_fit = varpro_fit(t, h, omega_seeds_all, zeta_init, omega_tol)

    if verbose:
        print(f"[3] Joint VARPRO converged.")

    # Stage 4
    modes = match_and_assemble(omega_n_fit, zeta_fit, c_fit, omega_seeds_all,
                               match_tol, zeta_max)
    if verbose:
        print(f"[4] Matched modes: {len(modes)}")

    # Reconstruct and compute residual
    h_rec = np.zeros_like(h)
    for m in modes:
        decay  = np.exp(-m['zeta'] * m['omega_n'] * t)
        h_rec += m['amplitude'] * decay * np.cos(m['omega_d'] * t + m['phase'])

    rms_residual = np.sqrt(np.mean((h - h_rec) ** 2)) / (np.max(np.abs(h)) + 1e-12)

    if verbose:
        # Sort by FFT spectral height at each mode's frequency for display
        def fft_height(m):
            idx = np.argmin(np.abs(freqs - m['freq_hz']))
            return H_mag[idx]

        print(f"\n{'─'*63}")
        print(f"{'Mode':<6} {'Freq [Hz]':<12} {'Zeta':<10} {'Amplitude':<12} {'FFT height':<12} {'Damp%'}")
        print(f"{'─'*63}")
        modes_by_fft = sorted(modes, key=fft_height, reverse=True)
        for i, m in enumerate(modes_by_fft[:TOP_N_MODES]):
            print(f"{i+1:<6} {m['freq_hz']:<12.4f} {m['zeta']:<10.4f} "
                  f"{m['amplitude']:<12.4f} {fft_height(m):<12.2f} {100 * m['zeta']:.2f}%")
        if len(modes) > TOP_N_MODES:
            print(f"  ... {len(modes) - TOP_N_MODES} additional mode(s) identified but not shown")
        print(f"{'─'*63}")
        print(f"RMS residual (normalized): {rms_residual:.2e}")

    return modes, rms_residual, N_order, h_rec, freqs, H_mag, omega_fft


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------

def plot_results(h, dt, modes, h_rec, freqs, H_mag, omega_fft=None,
                 top_n=TOP_N_MODES, save_path='modal_results.png'):
    """Three-panel plot: time-domain fit | FFT spectrum | damping bars.
    FFT seeds (omega_fft) are shown as orange triangle markers on the spectrum.
    Only the top_n highest-amplitude modes are annotated on the spectrum
    and shown in the damping bar chart."""

    t   = np.arange(len(h)) * dt
    # Sort by FFT spectral height at each mode's frequency, then take top_n.
    # This ranks modes by their prominence in the observed spectrum rather than
    # by fitted VARPRO amplitude, which is what "top modes by spectrum" means visually.
    def fft_height(m):
        idx = np.argmin(np.abs(freqs - m['freq_hz']))
        return H_mag[idx]
    modes_plot = sorted(modes, key=fft_height, reverse=True)[:top_n]

    fig, axes = plt.subplots(3, 1, figsize=(10, 10))

    # Time domain — reconstruction uses all fitted modes, not just top_n
    ax = axes[0]
    ax.plot(t, h, 'k', lw=1.2, label='Signal')
    ax.plot(t, h_rec, 'r--', lw=1.5, label='Reconstruction')
    ax.set_xlabel('Time [s]'); ax.set_ylabel('Amplitude')
    ax.set_title('Impulse Response: Signal vs. Reconstruction')
    ax.legend(); ax.grid(True, alpha=0.3)

    # Frequency domain — annotate only top_n modes
    ax = axes[1]
    ax.plot(freqs, H_mag / H_mag.max(), 'k', lw=1.0)
    # FFT seeds passed to VARPRO — orange triangles at top of plot
    if omega_fft is not None:
        for w in omega_fft:
            f_seed = w / (2 * np.pi)
            ax.axvline(f_seed, lw=1.0, linestyle=':', color='darkorange', alpha=0.6)
            ax.annotate(f'{f_seed:.3f}',
                        xy=(f_seed, 0.97), xycoords=('data', 'axes fraction'),
                        fontsize=7, color='darkorange', ha='center', va='top',
                        rotation=90)
    # Fitted modes — dashed coloured lines
    for m in modes_plot:
        ax.axvline(m['freq_hz'], lw=1.2, linestyle='--', alpha=0.7,
                   label=f"{m['freq_hz']:.3f} Hz")
    ax.set_xlim(0, 8.0)
    ax.set_xlabel('Frequency [Hz]'); ax.set_ylabel('Normalized Magnitude')
    ax.set_title('FFT Spectrum  (▲ orange = FFT seeds to VARPRO)')
    ax.legend(fontsize=8); ax.grid(True, alpha=0.3)

    # Damping bars — only top_n modes
    ax = axes[2]
    freqs_hz = [m['freq_hz'] for m in modes_plot]
    zetas    = [100 * m['zeta'] for m in modes_plot]
    bars = ax.bar(range(len(modes_plot)), zetas, color='steelblue', alpha=0.8)
    # Annotate each bar with the amplitude value for easy energy comparison
    # for bar, m in zip(bars, modes_plot):
    #     ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.3,
    #             f'A={m["amplitude"]:.3f}', ha='center', va='bottom', fontsize=8)
    ax.set_xticks(range(len(modes_plot)))
    ax.set_xticklabels([f'{f:.3f} Hz' for f in freqs_hz], rotation=30)
    ax.set_ylabel('Damping Ratio [%]')
    ax.set_title(f'Mode Estimates')
    ax.grid(True, alpha=0.3, axis='y')

    plt.tight_layout()
    plt.savefig(save_path, dpi=150, bbox_inches='tight')
    plt.show()
    print(f"Plot saved to {save_path}")

def zscore_normalize(x):
    x = np.asarray(x)
    mean = np.mean(x)
    std = np.std(x)
    return (x - mean) / std

if __name__ == '__main__':
    import pandas as pd
    from pathlib import Path

    root     = Path.cwd()
    data_dir = root / "Processing"

    config = pd.read_csv(root / 'modal_analysis_config.csv')

    def _cfg(var, cast=str, default=None):
        row = config[config.Variable == var]
        if row.empty:
            return default
        v = row['Value'].iloc[0]
        return default if (str(v).strip().lower() == 'nan' or str(v).strip() == '') else cast(v)

    bus_number = _cfg('bus_number', int)
    freq_min   = _cfg('freq_min',   float, default=FREQ_MIN)
    freq_max   = _cfg('freq_max',   float, default=FREQ_MAX)
    prom_ratio = _cfg('prominence_ratio', float, default=PROMINENCE_RATIO)

    impulse_csv = data_dir / f'impulse_{bus_number}.csv'
    print(f"Reading impulse response: {impulse_csv}")

    data   = pd.read_csv(impulse_csv)
    data   = data[data['time'] > 2]
    t      = np.array(data['time'][1:])
    h      = np.diff(data[data.columns[2]])
    h_norm = h

    dt = t[1] - t[0]

    print(f"Extracting modes  (freq range: {freq_min}–{freq_max} Hz, prominence: {prom_ratio})")
    modes, residual, model_order, h_rec, freqs, H_mag, omega_fft = extract_modes(
        h_norm, dt,
        freq_min=freq_min, freq_max=freq_max,
        prominence_ratio=prom_ratio,
        zeta_max=ZETA_MAX, verbose=True)

    # Save plot to Processing/ folder so it stays alongside the impulse CSV
    plot_out = data_dir / f'modal_results_{bus_number}.png'
    plot_results(h_norm, dt, modes, h_rec, freqs, H_mag, omega_fft,
                 save_path=str(plot_out))

    # Save mode table to CSV
    if modes:
        modes_df = pd.DataFrame(modes)
        modes_df.to_csv(data_dir / f'mode_estimates_{bus_number}.csv', index=False)
        print(f"Mode estimates saved: {data_dir / f'mode_estimates_{bus_number}.csv'}")