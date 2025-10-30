'''
for questions, or to report bugs in the script, please email shuchismita.biswas@pnnl.gov
For methodology, please refer https://www.techrxiv.org/doi/full/10.36227/techrxiv.175623878.87007943
'''
import pandas as pd
import sys, os

# import user-defined functions

from scenario_menu import (
    ScenarioConfig,
    build_actions,
    show_menu,
    load_config_from_csv,
    save_config_to_csv
)

from system_summary import system_summary
from LDDL_Different_Load_Variations import LDDL_MonoPeriodic_Load_Var
from LDDL_Different_Load_Variations import LDDL_BiPeriodic_Load_Var
from LDDL_Different_Load_Variations import LDDL_Tria_Load_Var
from LDDL_Viz_Functions import Read_System_Bus_Lat_Long
from LDDL_Viz_Functions import Process_LDDL_out_for_Viz
from LDDL_Viz_Functions import LDDL_OscAna_Viz

def main():
    print("Do you want to load configuration from CSV? (y/n)")
    use_csv = input().strip().lower()
    
    if use_csv == "y":
        csv_path = input("Enter CSV file name: ").strip()
        try:
            cfg = load_config_from_csv(csv_path)
        except FileNotFoundError:
            print(f"⚠️  CSV file not found at {csv_path}. Starting with defaults instead.")
            cfg = ScenarioConfig()
    else:
        cfg = ScenarioConfig()
    
    actions = build_actions()
    
    while True:
        choice = show_menu().strip()
        U = choice.upper()
        if U == "Q":
            print("Thank you for using Large Load Risk Assessment Tool!")
            break
        elif U == "R":
            print("\n===== CURRENT CONFIGURATION =====")
            print(cfg)
            print("\nModel Type:", cfg.load_model.model_type)
            print("Load Bus:", cfg.load_model.load_bus_number)
            print("=================================\n")
            
            # prompt to save config back to CSV
            save_config_to_csv(cfg, 'config_out.csv')
            LDDL_bus_number = cfg.load_model.load_bus_number
            # add PSSE paths to file
            sys.path.append(r"C:\Program Files\PTI\PSSE35\35.6\PSSPY311")
            sys.path.append(r"C:\Program Files\PTI\PSSE35\35.6\PSSBIN")
            os.environ['PATH'] += ';' + r"C:\Program Files\PTI\PSSE35\35.6\PSSBIN"
            local_dir = os.getcwd() ## finding current working directory
            sys.path.append(local_dir)
            os.environ['PATH'] += ';' + local_dir           
            
            system_summary(cfg.files.case_file_location+'\\'+cfg.files.raw_file,LDDL_bus_number) 
            #to obtain geographic visualization, latitude and longitude info can be added as additional columns to the output of this command - sys_bus_summary.csv
            # file with lat long information should be specified as the 'Network lat/long file' variable (option 4a in the user-selectable menu)
    
            if cfg.load_variation.shape == "Mono-periodic":
                    df = LDDL_MonoPeriodic_Load_Var(cfg)
            elif cfg.load_variation.shape == "Bi-periodic":
                    df = LDDL_BiPeriodic_Load_Var(cfg)
            elif cfg.load_variation.shape == "Triangular":
                    df = LDDL_Tria_Load_Var(cfg)
    
            CSV_Folder = "Results_"+str(LDDL_bus_number)
            PSSE_measurement_file = CSV_Folder + '\\' + 'LDDL_'+ str(LDDL_bus_number)+'.csv'
    
            df = pd.read_csv(PSSE_measurement_file) #output of PSSE simulations
    
            if not df.empty:
                    BUS_FILE = cfg.viz.network_latlong_file
                    bus_info = Read_System_Bus_Lat_Long(BUS_FILE, cfg)
                    osc_line, names_line, osc_gen, gen_buses, osc_load, load_buses = Process_LDDL_out_for_Viz(df, cfg)
    
                    MW_THRESHOLD = cfg.viz.mw_threshold
                    Output_Folder = cfg.files.output_file_location
                    location = str(LDDL_bus_number)
                    
                    LDDL_OscAna_Viz(location,MW_THRESHOLD,osc_line,names_line,osc_gen,gen_buses,osc_load,load_buses, bus_info,Output_Folder)
                      
            print("✅ LDDL Load variation simulation over.\n")
            break  # Exit the menu after run
    
        elif choice in actions:
            actions[choice](cfg)
        elif U in actions:
            actions[U](cfg)
        else:
            print("Unknown option. Try again.")
    return cfg, LDDL_bus_number

if __name__ == "__main__":
    [cfg, LDDL_bus] = main()
