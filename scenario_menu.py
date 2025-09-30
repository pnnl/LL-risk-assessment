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
    load_bus_ids: List[str] = field(default_factory=lambda: ["1"])  # always "1"

@dataclass
class LoadVariationConfig:
    shape: str = "Mono-periodic"  # 3a: shape (after reorg)
    freq_primary_hz: float = 1.00  # 3b: frequency
    freq_secondary_hz: Optional[float] = None
    start_time_s: float = 2.0      # 3c
    sim_run_time_s: float = 30.0   # 3d (now Stop time, logic changed)

@dataclass
class VisualizationConfig:
    case_file_location: str = str(Path.cwd())  # 1a
    network_latlong_file: str = "MiniWECC_240bus_Buses_Areas_Zones.csv"  # 4a
    mw_threshold: float = 20  # 4b (peak-peak threshold for visualization)
    cmax: float = 200         # kept in dataclass for compatibility (not menu-exposed)
    source_bus_name: str = "Source_Bus"  # kept in dataclass for compatibility (not menu-exposed)

@dataclass
class SystemPathsConfig:
    cwd: str = str(Path.cwd())  # kept for compatibility (not menu-exposed)
    PSSE_LOCATION: str = r"C:\Program Files\PTI\PSSE35\35.6\PSSBIN"  # kept (not menu-exposed)

@dataclass
class FileNamesConfig:
    raw_file: str = "240busWECC_2018_PSS.raw"     # 1b
    dyr_file: str = "240busWECC_2018_PSS.dyr"     # 1c
    output_file_location: str = str(Path.cwd())   # 1d

@dataclass
class ScenarioConfig:
    load_model: LoadModelConfig = field(default_factory=LoadModelConfig)
    load_variation: LoadVariationConfig = field(default_factory=LoadVariationConfig)
    viz: VisualizationConfig = field(default_factory=VisualizationConfig)
    system: SystemPathsConfig = field(default_factory=SystemPathsConfig)
    files: FileNamesConfig = field(default_factory=FileNamesConfig)

def _sync_bus_ids(cfg: ScenarioConfig):
    """Ensure load_bus_ids length matches load_bus_numbers length (pad with '1' or truncate)."""
    lm = cfg.load_model
    n = len(lm.load_bus_numbers)
    ids = list(lm.load_bus_ids)
    if len(ids) < n:
        ids += ["1"] * (n - len(ids))
    else:
        ids = ids[:n]
    lm.load_bus_ids = ids
# -------------------------
# NEW Section 1: File & Case Setup (old 3a + 4a/4b/4c)
# -------------------------
def configure_option_1a(cfg: ScenarioConfig):
    print("\n[1a] Case file location")
    default_loc = cfg.viz.case_file_location or str(Path.cwd())
    cfg.viz.case_file_location = _ask_path("Case file location (dir or file)", default_loc)

def configure_option_1b(cfg: ScenarioConfig):
    print("\n[1b] Raw file name")
    cfg.files.raw_file = _ask_path("Raw file name", cfg.files.raw_file)

def configure_option_1c(cfg: ScenarioConfig):
    print("\n[1c] DYR file name")
    cfg.files.dyr_file = _ask_path("DYR file name", cfg.files.dyr_file)

def configure_option_1d(cfg: ScenarioConfig):
    print("\n[1d] Output file location")
    cfg.files.output_file_location = _ask_path("Output file location", cfg.files.output_file_location)

# -------------------------
# NEW Section 2: LDDL model, size, and bus locations (old Section 1)
# -------------------------
def configure_option_2a(cfg: ScenarioConfig):
    print("\n[2a] LDDL model")
    cfg.load_model.model_type = _ask_choice(
        "Choose LDDL model", cfg.load_model.model_type, ["ZIP", "CMLD"]
    )

def configure_option_2b(cfg: ScenarioConfig):
    print("\n[2b] LDDL size (MW)")
    cfg.load_model.total_load_MW = _ask(
        "Total load MW", cfg.load_model.total_load_MW, float,
        lambda x: x >= 0 or (_ for _ in ()).throw(ValueError(">= 0 required"))
    )
    # Set MVAR = MW by default (hidden, no user input)
    cfg.load_model.total_load_MVAR = cfg.load_model.total_load_MW

def configure_option_2c(cfg: ScenarioConfig):
    print("\n[2c] LDDL bus numbers")
    lm = cfg.load_model

    current_numbers = list(lm.load_bus_numbers)
    current_n = len(current_numbers)

    n = _ask(
        "How many load buses?", current_n, int,
        lambda x: x > 0 or (_ for _ in ()).throw(ValueError("> 0 required"))
    )

    nums = []
    for i in range(n):
        # Per-index default:
        if i < current_n:
            default_num = current_numbers[i]          # use existing i-th value
        elif nums:                                     # if adding new rows, reuse last typed
            default_num = nums[-1]
        else:
            default_num = 1302                         # initial fallback

        nums.append(_ask(
            f"Bus #{i+1} number", default_num, int,
            lambda x: x > 0 or (_ for _ in ()).throw(ValueError("> 0 required"))
        ))

    lm.load_bus_numbers = nums
    lm.load_bus_ids = ["1"] * n   # restored behavior: all IDs = "1"


# -------------------------
# NEW Section 3: Load variation characteristics (old Section 2)
# -------------------------
def configure_option_3a(cfg: ScenarioConfig):
    print("\n[3a] Load variation shape")
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

def configure_option_3b(cfg: ScenarioConfig):
    print("\n[3b] Frequency")
    lv = cfg.load_variation

    # Primary frequency (no parentheses/brackets in prompt text)
    lv.freq_primary_hz = _ask(
        "Primary frequency Hz", lv.freq_primary_hz, float,
        lambda x: x > 0 or (_ for _ in ()).throw(ValueError("> 0 required"))
    )

    if lv.shape == "Bi-periodic":
        while True:
            default_secondary = lv.freq_secondary_hz if lv.freq_secondary_hz is not None else 0.5
            secondary = _ask(
                "Secondary frequency Hz", default_secondary, float,
                lambda x: x > 0 or (_ for _ in ()).throw(ValueError("> 0 required"))
            )
            if lv.freq_primary_hz < secondary:
                lv.freq_secondary_hz = secondary
                break
            else:
                print("Primary frequency must be slower (smaller) than Secondary frequency. Please try again.")
    else:
        lv.freq_secondary_hz = None

def configure_option_3c(cfg: ScenarioConfig):
    print("\n[3c] Start time")
    cfg.load_variation.start_time_s = _ask(
        "Start time s", cfg.load_variation.start_time_s, float,
        lambda x: x >= 0 or (_ for _ in ()).throw(ValueError(">= 0 required"))
    )

def configure_option_3d(cfg: ScenarioConfig):
    print("\n[3d] Stop time")
    # New rule: Stop time > Start time + 5 cycles (cycles from PRIMARY frequency)
    lv = cfg.load_variation
    # Ensure primary freq is valid
    f = lv.freq_primary_hz if lv.freq_primary_hz and lv.freq_primary_hz > 0 else 0.10
    min_stop = lv.start_time_s + 5.0 / f
    while True:
        val = _ask(
            "Stop time s", lv.sim_run_time_s, float,
            lambda x: x > 0 or (_ for _ in ()).throw(ValueError("> 0 required"))
        )
        if val <= min_stop:
            print(f"Stop time must be greater than Start time + 5 cycles."
                  f" With primary frequency {f} Hz, minimum stop time is {min_stop:.3f} s.")
        else:
            lv.sim_run_time_s = val
            break

# -------------------------
# NEW Section 4: Analysis & Visualization (old Section 3 without 3a)
# -------------------------
def configure_option_4a(cfg: ScenarioConfig):
    print("\n[4a] Network lat/long file")
    cfg.viz.network_latlong_file = _ask_path(
        "Network lat/long file", cfg.viz.network_latlong_file
    )

def configure_option_4b(cfg: ScenarioConfig):
    print("\n[4b] Peak-peak threshold for risk assessment")
    cfg.viz.mw_threshold = _ask(
        "Peak-peak threshold", cfg.viz.mw_threshold, float,
        lambda x: x >= 0 or (_ for _ in ()).throw(ValueError(">= 0 required"))
    )

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
Section 1 (Model Input/ Output Setup):
  1a  : Case files location
  1b  : Raw file name
  1c  : DYR file name
  1d  : Output files location

Section 2 (LDDL model & locations):
  2a  : LDDL model
  2b  : LDDL size (MW)
  2c  : LDDL bus numbers
  
Section 3 (Load variation characteristics):
  3a  : Shape (Mono-periodic / Bi-periodic / Triangular)
  3b  : Frequency
  3c  : Start time (s)
  3d  : Stop time (s) 

Section 4 (Analysis & Visualization):
  4a  : Network lat/long file
  4b  : Peak-peak threshold (MW) for risk assessment

Other:
  R   : Review & Run
  Q   : Quit
==========================================
""") #   3d  : Stop time (s) — must be > Start time + 5 cycles (from primary frequency)
    return input("Choose an option: ").strip()

def build_actions() -> Dict[str, Callable[[ScenarioConfig], None]]:
    return {
        # Section 1 (new)
        "1a": configure_option_1a,
        "1b": configure_option_1b,
        "1c": configure_option_1c,
        "1d": configure_option_1d,
        # Section 2 (old section 1)
        "2a": configure_option_2a,
        "2b": configure_option_2b,
        "2c": configure_option_2c,
        # Section 3 (old section 2)
        "3a": configure_option_3a,
        "3b": configure_option_3b,
        "3c": configure_option_3c,
        "3d": configure_option_3d,
        # Section 4 (old section 3 minus 3a)
        "4a": configure_option_4a,
        "4b": configure_option_4b,
    }

# # Example main loop
# if __name__ == "__main__":
#     cfg = ScenarioConfig()
#     actions = build_actions()
#     while True:
#         choice = show_menu().upper()
#         if choice == "Q":
#             print("Thank you for using Large Load Risk Assessment Tool!")
#             break
#         if choice == "R":
#             run_review_and_execute(cfg)
#             continue
#         fn = actions.get(choice)
#         if fn:
#             fn(cfg)
#         else:
#             print("Invalid option. Try again.")
