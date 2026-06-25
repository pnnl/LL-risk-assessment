import os
import sys
import glob


def _version_sort_key(path):
    """
    Sort version-suffixed folder names numerically instead of lexicographically.
    """
    name = os.path.basename(path)
    parts = []
    for chunk in name.split("."):
        if chunk.isdigit():
            parts.append(int(chunk))
        else:
            parts.append(chunk)
    return tuple(parts)


def _find_default_psse_root(psse_version):
    """
    Search standard PTI install locations and return the first match.
    """
    local_app = os.environ.get("LOCALAPPDATA", "")
    candidates = [
        os.path.join(r"C:\Program Files", "PTI", "PSSE" + psse_version),
        os.path.join(r"C:\Program Files (x86)", "PTI", "PSSE" + psse_version),
        os.path.join(local_app, "Programs", "PTI", "PSSE" + psse_version),
    ]

    for path in candidates:
        if os.path.isdir(path):
            return path

    msg = (
        "Could not find PSSE%s in any standard location.\n"
        "Searched:\n  %s\n"
        "Please pass install_dir explicitly."
        % (psse_version, "\n  ".join(candidates))
    )
    raise IOError(msg)  # IOError works in both Py2 and Py3


def _resolve_psse_base(psse_root, psse_version):
    """
    Return the directory that actually contains PSSBIN/.

    Handles two layouts:
      Flat   :  PSSE34/PSSBIN/          -> returns PSSE34/
      Nested :  PSSE35/35.6/PSSBIN/     -> returns PSSE35/35.6/
      Nested :  PSSE36/36.5/PSSBIN/     -> returns PSSE36/36.5/
    """
    # Case 1: flat layout (v34-style)
    if os.path.isdir(os.path.join(psse_root, "PSSBIN")):
        return psse_root

    # Case 2: nested layout (v35/v36-style)
    pattern = os.path.join(psse_root, psse_version + ".*")
    candidates = sorted(glob.glob(pattern), key=_version_sort_key, reverse=True)
    for candidate in candidates:
        if os.path.isdir(os.path.join(candidate, "PSSBIN")):
            return candidate

    # Case 3: nothing matched - fall back to root
    return psse_root


def _validate(directory, label):
    """Raise error if directory does not exist."""
    if not os.path.isdir(directory):
        raise IOError("%s directory not found: %s" % (label, directory))


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


def _import_module(name):
    """
    Import a module by name string.
    Works in both Python 2 and Python 3.
    """
    try:
        # Python 3.1+
        from importlib import import_module
        return import_module(name)
    except ImportError:
        # Python 2 fallback
        return __import__(name)


# ===================================================================
# Public API
# ===================================================================

def configure_psse(psse_version, psspy_version, install_dir=None):
    """
    Initialize PSS/E environment and return the psspy module ready to use.

    Parameters
    ----------
    psse_version : int or str
        PSS/E major version number (e.g. 34, 35, 36).
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
    >>> psspy = configure_psse(34, 27)
    >>> psspy = configure_psse(34, 37)
    >>> psspy = configure_psse(35, 311)
    >>> psspy = configure_psse(36, 311)
    >>> psspy = configure_psse(35, 311, install_dir=r"D:\\CustomPath\\PSSE35")
    """
    psse_version = str(psse_version)
    psspy_version = str(psspy_version)

    # 1. Resolve PSS/E root directory
    if install_dir:
        psse_root = install_dir
    else:
        psse_root = _find_default_psse_root(psse_version)

    # 2. Handle flat vs nested layout
    psse_base = _resolve_psse_base(psse_root, psse_version)

    # 3. Build PSSPY and PSSBIN paths from resolved base
    psspy_dir = os.path.join(psse_base, "PSSPY" + psspy_version)
    pssbin_dir = os.path.join(psse_base, "PSSBIN")

    # 4. Validate directories exist
    _validate(psse_root, "PSSE root")
    _validate(psspy_dir, "PSSPY")
    _validate(pssbin_dir, "PSSBIN")

    # 5. Patch sys.path & os.environ["PATH"]
    _add_to_sys_path(psspy_dir)
    _add_to_sys_path(pssbin_dir)
    _add_to_env_path(pssbin_dir)

    local_dir = _get_local_dir()
    _add_to_sys_path(local_dir)
    _add_to_env_path(local_dir)

    # 6. Version-specific init import (e.g. psse34, psse35)
    try:
        _import_module("psse" + psse_version)
    except ImportError:
        pass

    # 7. Import psspy and initialize
    import psspy
    psspy.psseinit()

    print(
        "[OK] PSS/E v%s | PSSPY%s | base=%s | initialized"
        % (psse_version, psspy_version, psse_base)
    )
    return psspy