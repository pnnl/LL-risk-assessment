
import os
import sys
import glob



def _find_default_psse_root(psse_version):
    """
    Search standard PTI install locations and return the first match.

    Parameters
    ----------
    psse_version : str
        Major version string, e.g. "34", "35".

    Returns
    -------
    str
        Path to the PSSExx folder.

    Raises
    ------
    FileNotFoundError
        If no installation directory is found.
    """
    candidates = [
        os.path.join(r"C:\Program Files", "PTI", f"PSSE{psse_version}"),
        os.path.join(r"C:\Program Files (x86)", "PTI", f"PSSE{psse_version}"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "PTI", f"PSSE{psse_version}"),
    ]

    for path in candidates:
        if os.path.isdir(path):
            return path

    raise FileNotFoundError(
        f"Could not find PSSE{psse_version} in any standard location.\n"
        f"Searched:\n  " + "\n  ".join(candidates) + "\n"
        f"Please pass install_dir explicitly."
    )


def _resolve_psse_base(psse_root, psse_version):
    """
    Return the directory that actually contains PSSBIN/.

    Handles two layouts:
      Flat   :  PSSE34/PSSBIN/          → returns PSSE34/
      Nested :  PSSE35/35.6/PSSBIN/     → returns PSSE35/35.6/

    Parameters
    ----------
    psse_root : str
        Top-level PSSExx directory.
    psse_version : str
        Major version string, e.g. "34", "35".

    Returns
    -------
    str
        The resolved base directory containing PSSBIN and PSSSPYxxx.
    """
    # ── Case 1: flat layout (v34-style) ──
    if os.path.isdir(os.path.join(psse_root, "PSSBIN")):
        return psse_root

    # ── Case 2: nested layout (v35-style) ──
    # Look for sub-folders like "35.6", "35.7", etc.
    pattern = os.path.join(psse_root, f"{psse_version}.*")
    candidates = sorted(glob.glob(pattern), reverse=True)  # newest first

    for candidate in candidates:
        if os.path.isdir(os.path.join(candidate, "PSSBIN")):
            return candidate

    # ── Case 3: nothing matched — fall back to root ──
    return psse_root


def _validate(directory, label):
    """
    Raise FileNotFoundError if directory does not exist.

    Parameters
    ----------
    directory : str
        Path to check.
    label : str
        Human-readable label for the error message.
    """
    if not os.path.isdir(directory):
        raise FileNotFoundError(
            f"{label} directory not found: {directory}"
        )


def _add_to_sys_path(directory):
    """Prepend directory to sys.path if not already present."""
    if directory not in sys.path:
        sys.path.insert(0, directory)


def _add_to_env_path(directory):
    """Prepend directory to os.environ['PATH'] if not already present."""
    current = os.environ.get("PATH", "")
    if directory.lower() not in current.lower():
        os.environ["PATH"] = directory + os.pathsep + current


def _get_local_dir():
    """Return the directory of the calling script (or cwd as fallback)."""
    try:
        return os.path.dirname(os.path.abspath(__file__))
    except NameError:
        return os.getcwd()


# ═══════════════════════════════════════════════════════════════════════
# Public API
# ═══════════════════════════════════════════════════════════════════════

def configure_psse(psse_version, psspy_version, install_dir=None):
    """
    Initialize PSS/E environment and return the psspy module ready to use.

    Parameters
    ----------
    psse_version : int or str
        PSS/E major version number (e.g. 34, 35).
    psspy_version : int or str
        PSSPY Python version tag (e.g. 27, 37, 311).
    install_dir : str, optional
        Full path to the PSSExx folder.
        If not provided, standard PTI locations are searched automatically.

    Returns
    -------
    psspy : module
        The imported psspy module, ready for use.

    Examples
    --------
    >>> psspy = configure_psse(34, 37)
    [OK] PSS/E v34 | PSSPY37 | base=C:\\...\\PSSE34 | initialized

    >>> psspy = configure_psse(35, 311)
    [OK] PSS/E v35 | PSSPY311 | base=C:\\...\\PSSE35\\35.6 | initialized

    >>> psspy = configure_psse(35, 311, install_dir=r"D:\\CustomPath\\PSSE35")
    """
    psse_version  = str(psse_version)
    psspy_version = str(psspy_version)

    # ── 1. Resolve PSS/E root directory ─────────────────────────────
    if install_dir:
        psse_root = install_dir
    else:
        psse_root = _find_default_psse_root(psse_version)

    # ── 2. Handle flat vs nested layout ─────────────────────────────
    psse_base = _resolve_psse_base(psse_root, psse_version)

    # ── 3. Build PSSPY and PSSBIN paths from resolved base ──────────
    psspy_dir  = os.path.join(psse_base, f"PSSPY{psspy_version}")
    pssbin_dir = os.path.join(psse_base, "PSSBIN")

    # ── 4. Validate directories exist ───────────────────────────────
    _validate(psse_root,  "PSSE root")
    _validate(psspy_dir,  "PSSPY")
    _validate(pssbin_dir, "PSSBIN")

    # ── 5. Patch sys.path & os.environ["PATH"] ─────────────────────
    _add_to_sys_path(psspy_dir)
    _add_to_sys_path(pssbin_dir)
    _add_to_env_path(pssbin_dir)

    local_dir = _get_local_dir()
    _add_to_sys_path(local_dir)
    _add_to_env_path(local_dir)

    # ── 6. Version-specific init import ─────────────────────────────
    try:
        __import__(f"psse{psse_version}")
    except ImportError:
        pass

    # ── 7. Import psspy and initialize ──────────────────────────────
    import psspy
    psspy.psseinit()

    print(
        f"[OK] PSS/E v{psse_version} | PSSPY{psspy_version} | "
        f"base={psse_base} | initialized"
    )
    return psspy


