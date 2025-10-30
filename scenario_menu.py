from dataclasses import dataclass, field, asdict
from typing import Callable, Optional, Dict, Any, List
from pathlib import Path
import json
import numpy as np
import csv
import ast

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
# Configuring dataclasses
# -------------------------
@dataclass
class SystemPathsConfig:
    cwd: str = str(Path.cwd())  # kept for compatibility (not menu-exposed)
    PSSE_LOCATION: str = r"C:\Program Files\PTI\PSSE35\35.6\PSSBIN"  # kept (not menu-exposed)
    
@dataclass
class FileNamesConfig:
    case_file_location: str = str(Path.cwd()) +'\\PSSE_Cases'    # 1a
    raw_file: str = "240busWECC_2018_PSS.raw"     # 1b
    dyr_file: str = "240busWECC_2018_PSS.dyr"     # 1c
    output_file_location: str = str(Path.cwd())   # 1d
    
@dataclass
class LoadModelConfig:
    model_type: str = "ZIP"      # 2a - ZIP or CMLD
    total_load_MW: float = 100.0 # 2b
    #total_load_MVAR: float = 0   # will be set as 0 by default 
    load_bus_number: List[int] = 1302 #2c
    
@dataclass
class LoadVariationConfig:
    shape: str = "Mono-periodic"   # 3a: shape (after reorg)
    freq_primary_hz: float = 1.00  # 3b: frequency
    freq_secondary_hz: Optional[float] = None
    start_time_s: float = 2.0      # 3c
    sim_run_time_s: float = 30.0   # 3d (now Stop time, logic changed)

@dataclass
class VisualizationConfig:
    network_latlong_file: str = "MiniWECC_240bus_Buses_Areas_Zones.csv"  # 4a
    mw_threshold: float = 20  # 4b (peak-peak threshold for visualization)
   
@dataclass
class ScenarioConfig:
    system: SystemPathsConfig = field(default_factory=SystemPathsConfig)
    files: FileNamesConfig = field(default_factory=FileNamesConfig)
    load_model: LoadModelConfig = field(default_factory=LoadModelConfig)
    load_variation: LoadVariationConfig = field(default_factory=LoadVariationConfig)
    viz: VisualizationConfig = field(default_factory=VisualizationConfig)

#-------- reading and saving configuration as csv------

def load_config_from_csv(csv_path: str) -> ScenarioConfig:
    """Load configuration values from a CSV file into a ScenarioConfig."""
    cfg = ScenarioConfig()
    print(f"Loading configuration from {csv_path} ...")

    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            section = row["section"].strip()
            key = row["key"].strip()
            value_raw = row["value"].strip()

            # Try to interpret value safely
            try:
                value = ast.literal_eval(value_raw)
            except Exception:
                value = value_raw

            # Set section/key if valid
            target = getattr(cfg, section, None)
            if target is None:
                print(f"⚠️  Unknown section '{section}', skipping row.")
                continue

            if hasattr(target, key):
                setattr(target, key, value)
            else:
                print(f"⚠️  Unknown key '{key}' in section '{section}', skipping row.")

    print("Configuration loaded successfully.\n")
    return cfg

def save_config_to_csv(cfg: ScenarioConfig, csv_path: str):
    """Save current configuration into a CSV file."""
    rows = []
    for section_name, section_obj in asdict(cfg).items():
        for key, value in section_obj.items():
            rows.append({
                "section": section_name,
                "key": key,
                "value": value
            })
    with open(csv_path, "w", newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=["section", "key", "value"])
        writer.writeheader()
        writer.writerows(rows)
    print(f"Configuration saved to {csv_path}")
    
# -------------- setting configuration options-----
    
def configure_option_1a(cfg: ScenarioConfig):
    print("\n[1a] Case file location")
    default_loc = cfg.viz.case_file_location or str(Path.cwd()+'\\PSSE_Cases')
    cfg.files.case_file_location = _ask_path("Case file location (dir or file)", default_loc)

def configure_option_1b(cfg: ScenarioConfig):
    print("\n[1b] Raw file name")
    cfg.files.raw_file = _ask_path("Raw file name", cfg.files.raw_file)

def configure_option_1c(cfg: ScenarioConfig):
    print("\n[1c] DYR file name")
    cfg.files.dyr_file = _ask_path("DYR file name", cfg.files.dyr_file)

def configure_option_1d(cfg: ScenarioConfig):
    print("\n[1d] Output file location")
    cfg.files.output_file_location = _ask_path("Output file location", cfg.files.output_file_location)

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

def configure_option_2c(cfg: ScenarioConfig):
    print("\n[2c] LDDL bus number")
    cfg.load_model.load_bus_number = _ask(
        "Which bus to place a LDDL?", cfg.load_model.load_bus_number, int,
        lambda x: x >= 0 or (_ for _ in ()).throw(ValueError(">= 0 required"))
    )
    
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
            # --- Default secondary frequency is 10 Hz if not set ---
            default_secondary = lv.freq_secondary_hz or 10.0

            lv.freq_secondary_hz = _ask(
                "Secondary frequency Hz", default_secondary, float,
                lambda x: x > 0 or (_ for _ in ()).throw(ValueError("> 0 required"))
            )

            if lv.freq_primary_hz < lv.freq_secondary_hz:
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
    # Rule: Stop time > Start time + 5 cycles (cycles from PRIMARY frequency)
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
# Showing Menu
# -------------------------
def show_menu() -> str:
    print("""
================== MENU ==================
Section 1 (Model Input/ Output Setup):
  1a  : Case files location
  1b  : Raw file name
  1c  : DYR file name
  1d  : Output files location

Section 2 (LDDL model & location):
  2a  : LDDL model
  2b  : LDDL size (MW)
  2c  : LDDL bus number
  
Section 3 (Load variation characteristics):
  3a  : Shape (Mono-periodic square / Bi-periodic square / Triangular)
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
""") 
    return input("Choose an option: ").strip()

def build_actions() -> Dict[str, Callable[[ScenarioConfig], None]]:
    return {
        # Section 1 
        "1a": configure_option_1a,
        "1b": configure_option_1b,
        "1c": configure_option_1c,
        "1d": configure_option_1d,
        # Section 2 
        "2a": configure_option_2a,
        "2b": configure_option_2b,
        "2c": configure_option_2c,
        # Section 3 
        "3a": configure_option_3a,
        "3b": configure_option_3b,
        "3c": configure_option_3c,
        "3d": configure_option_3d,
        # Section 4 
        "4a": configure_option_4a,
        "4b": configure_option_4b,
    }

