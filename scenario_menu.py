from dataclasses import dataclass, field, asdict
from typing import Callable, Optional, Dict, Any, List
from pathlib import Path
import json
import sys

# -------------------------
# Utilities
# -------------------------
def _input_with_default(prompt: str, default: str) -> str:
    raw = input(f"{prompt} [{default}]: ").strip()
    return default if raw == "" else raw

def _ask(prompt: str, default: Any, cast: Callable[[str], Any] = str,
         validate: Optional[Callable[[Any], None]] = None) -> Any:
    while True:
        raw = _input_with_default(prompt, str(default))
        try:
            val = cast(raw)
            if validate:
                validate(val)
            return val
        except Exception as e:
            print(f"Invalid value: {e}. Please try again.")

def _ask_choice(prompt: str, default: str, choices: List[str]) -> str:
    choices_lower = [c.lower() for c in choices]
    while True:
        raw = _input_with_default(f"{prompt} ({'/'.join(choices)})", default).strip()
        if raw.lower() in choices_lower:
            return choices[choices_lower.index(raw.lower())]
        print(f"Please choose one of: {choices}")

def _ask_path(prompt: str, default: str) -> str:
    return _ask(prompt, default, str)

# -------------------------
# Config dataclasses
# -------------------------
@dataclass
class LoadModelConfig:
    model_type: str = "ZIP"  # ZIP or CMLD
    total_load_MW: float = 100.0
    total_load_MVAR: float = 100.0  # will be set from MW by default in 1b
    load_bus_numbers: List[int] = field(default_factory=lambda: [1302])
    load_bus_ids: List[str] = field(default_factory=lambda: ["1"])

@dataclass
class LoadVariationConfig:
    shape: str = "Mono-periodic"  # 2a: shape
    freq_primary_hz: float = 0.10  # 2b: frequency
    freq_secondary_hz: Optional[float] = None
    start_time_s: float = 2.0      # 2c
    sim_run_time_s: float = 30.0   # 2d

@dataclass
class VisualizationConfig:
    case_file_location: str = str(Path.cwd())  # 3a (unchanged)
    network_latlong_file: str = "MiniWECC_240bus_Buses_Areas_Zones.csv"  # 3b (unchanged)
    mw_threshold: float = 20  # 3c (renamed meaning: peak-peak threshold for visualization)
    cmax: float = 200         # kept in dataclass for compatibility (not menu-exposed)
    source_bus_name: str = "Source_Bus"  # kept in dataclass for compatibility (not menu-exposed)

@dataclass
class SystemPathsConfig:
    cwd: str = str(Path.cwd())  # kept for compatibility (not menu-exposed)
    PSSE_LOCATION: str = r"C:\Program Files\PTI\PSSE35\35.6\PSSBIN"  # kept (not menu-exposed)

@dataclass
class FileNamesConfig:
    raw_file: str = "240busWECC_2018_PSS.raw"     # 4a
    dyr_file: str = "240busWECC_2018_PSS.dyr"     # 4b
    output_file_location: str = str(Path.cwd())      # 4c (renamed label only)

@dataclass
class ScenarioConfig:
    load_model: LoadModelConfig = field(default_factory=LoadModelConfig)
    load_variation: LoadVariationConfig = field(default_factory=LoadVariationConfig)
    viz: VisualizationConfig = field(default_factory=VisualizationConfig)
    system: SystemPathsConfig = field(default_factory=SystemPathsConfig)
    files: FileNamesConfig = field(default_factory=FileNamesConfig)

# -------------------------
# Section 1: LDDL model, size, and bus locations
# -------------------------
def configure_option_1a(cfg: ScenarioConfig):
    print("\n[1a] LDDL model (ZIP/CMLD)")
    cfg.load_model.model_type = _ask_choice(
        "Choose LDDL model", cfg.load_model.model_type, ["ZIP", "CMLD"]
    )

def configure_option_1b(cfg: ScenarioConfig):
    print("\n[1b] LDDL size (MW)")
    cfg.load_model.total_load_MW = _ask(
        "Total load (MW)", cfg.load_model.total_load_MW, float,
        lambda x: x >= 0 or (_ for _ in ()).throw(ValueError(">= 0 required"))
    )
    # Set MVAR = MW by default (hidden, no user input)
    cfg.load_model.total_load_MVAR = cfg.load_model.total_load_MW

def configure_option_1c(cfg: ScenarioConfig):
    print("\n[1c] LDDL bus numbers")
    n = _ask(
        "How many load buses?", len(cfg.load_model.load_bus_numbers), int,
        lambda x: x > 0 or (_ for _ in ()).throw(ValueError("> 0 required"))
    )
    nums = []
    for i in range(n):
        nums.append(_ask(
            f"Bus #{i+1} number", cfg.load_model.load_bus_numbers[0], int,
            lambda x: x > 0 or (_ for _ in ()).throw(ValueError("> 0 required"))
        ))
    cfg.load_model.load_bus_numbers = nums
    cfg.load_model.load_bus_ids = ["1"] * n   # keep IDs dummy so config stays valid

# -------------------------
# Section 2: Load variation characteristics
# -------------------------
def configure_option_2a(cfg: ScenarioConfig):
    print("\n[2a] Load variation shape")
    print("Choose shape:")
    print("  1 = Mono-periodic")
    print("  2 = Bi-periodic")
    print("  3 = Triangular")

    shape_map = {"Mono-periodic": 1, "Bi-periodic": 2, "Triangular": 3}
    current_default = shape_map.get(cfg.load_variation.shape, 1)

    choice = _ask(
        "Enter choice number", current_default, int,
        lambda x: x in (1, 2, 3) or (_ for _ in ()).throw(ValueError("must be 1, 2, or 3"))
    )
    if choice == 1:
        cfg.load_variation.shape = "Mono-periodic"
        cfg.load_variation.freq_secondary_hz = None
    elif choice == 2:
        cfg.load_variation.shape = "Bi-periodic"
    elif choice == 3:
        cfg.load_variation.shape = "Triangular"
        cfg.load_variation.freq_secondary_hz = None

def configure_option_2b(cfg: ScenarioConfig):
    print("\n[2b] Frequency")
    lv = cfg.load_variation

    # Primary frequency always asked
    lv.freq_primary_hz = _ask(
        "Primary frequency (Hz)", lv.freq_primary_hz, float,
        lambda x: x > 0 or (_ for _ in ()).throw(ValueError("> 0 required"))
    )

    if lv.shape == "Bi-periodic":
        while True:
            default_secondary = lv.freq_secondary_hz if lv.freq_secondary_hz is not None else 0.5
            secondary = _ask(
                "Secondary frequency (Hz)", default_secondary, float,
                lambda x: x > 0 or (_ for _ in ()).throw(ValueError("> 0 required"))
            )
            if lv.freq_primary_hz < secondary:
                lv.freq_secondary_hz = secondary
                break
            else:
                print("Primary frequency must be slower (smaller) than Secondary frequency. Please try again.")
    else:
        lv.freq_secondary_hz = None

def configure_option_2c(cfg: ScenarioConfig):
    print("\n[2c] Start time")
    cfg.load_variation.start_time_s = _ask(
        "Start time (s)", cfg.load_variation.start_time_s, float,
        lambda x: x >= 0 or (_ for _ in ()).throw(ValueError(">= 0 required"))
    )

def configure_option_2d(cfg: ScenarioConfig):
    print("\n[2d] Run time")
    # Keep asking until run time > start time
    while True:
        val = _ask(
            "Simulation run time (s)", cfg.load_variation.sim_run_time_s, float,
            lambda x: x > 0 or (_ for _ in ()).throw(ValueError("> 0 required"))
        )
        if val <= cfg.load_variation.start_time_s:
            print("Run time cannot be smaller than start time. Please enter a larger value.")
        else:
            cfg.load_variation.sim_run_time_s = val
            break

# -------------------------
# Section 3: Analysis & Visualization
# -------------------------
def configure_option_3a(cfg: ScenarioConfig):
    print("\n[3a] Case file location (default CWD)")
    default_loc = cfg.viz.case_file_location or str(Path.cwd())
    cfg.viz.case_file_location = _ask_path("Case file location (dir or file)", default_loc)

def configure_option_3b(cfg: ScenarioConfig):
    print("\n[3b] Network lat long file")
    cfg.viz.network_latlong_file = _ask_path(
        "Network lat long file", cfg.viz.network_latlong_file
    )

def configure_option_3c(cfg: ScenarioConfig):
    print("\n[3c] Peak-peak threshold for visualization")
    cfg.viz.mw_threshold = _ask(
        "Peak-peak threshold", cfg.viz.mw_threshold, float,
        lambda x: x >= 0 or (_ for _ in ()).throw(ValueError(">= 0 required"))
    )

# -------------------------
# Section 4: File Names
# -------------------------
def configure_option_4a(cfg: ScenarioConfig):
    print("\n[4a] Raw file name")
    cfg.files.raw_file = _ask_path("Raw file name", cfg.files.raw_file)

def configure_option_4b(cfg: ScenarioConfig):
    print("\n[4b] DYR file name")
    cfg.files.dyr_file = _ask_path("DYR file name", cfg.files.dyr_file)

def configure_option_4c(cfg: ScenarioConfig):
    print("\n[4c] Output file locations")
    cfg.files.output_file_location = _ask_path("Output file location", cfg.files.output_file_location)

# -------------------------
# Review / Run
# -------------------------
def run_review_and_execute(cfg: ScenarioConfig):
    print("\n========== REVIEW CONFIG ==========")
    print(json.dumps(asdict(cfg), indent=2))
    print("\n[Stub] Replace with actual PSSE/visualization calls")
    print("===================================\n")

# -------------------------
# Menu helpers
# -------------------------
def show_menu() -> str:
    print("""
================== MENU ==================
Section 1:
  1a  : LDDL model (ZIP/CMLD)
  1b  : LDDL size (MW)
  1c  : LDDL bus numbers

Section 2 (Load variation characteristics):
  2a  : Shape (Mono-periodic / Bi-periodic / Triangular)
  2b  : Frequency (one for Mono/Triangular; two for Bi-periodic)
  2c  : Start time (default 2 s)
  2d  : Run time (must be > Start time)

Section 3 (Analysis & Visualization):
  3a  : Case file location (default CWD)
  3b  : Network lat long file (default MiniWECC_240bus_Buses_Areas_Zones.csv)
  3c  : Peak-peak threshold for visualization (default 20)

Section 4 (File Names):
  4a  : Raw file name
  4b  : DYR file name
  4c  : Output file location

Other:
  R   : Review & Run
  Q   : Quit
==========================================
""")
    return input("Choose an option: ").strip()

def build_actions() -> Dict[str, Callable[[ScenarioConfig], None]]:
    return {
        # Section 1
        "1a": configure_option_1a,
        "1b": configure_option_1b,
        "1c": configure_option_1c,
        # Section 2
        "2a": configure_option_2a,
        "2b": configure_option_2b,
        "2c": configure_option_2c,
        "2d": configure_option_2d,
        # Section 3
        "3a": configure_option_3a,
        "3b": configure_option_3b,
        "3c": configure_option_3c,
        # Section 4
        "4a": configure_option_4a,
        "4b": configure_option_4b,
        "4c": configure_option_4c,
    }

# (Your main loop would go here, unchanged)
# Example:
# if __name__ == "__main__":
#     cfg = ScenarioConfig()
#     actions = build_actions()
#     while True:
#         choice = show_menu().upper()
#         if choice == "Q":
#             print("Goodbye.")
#             break
#         if choice == "R":
#             run_review_and_execute(cfg)
#             continue
#         fn = actions.get(choice)
#         if fn:
#             fn(cfg)
#         else:
#             print("Invalid option. Try again.")
