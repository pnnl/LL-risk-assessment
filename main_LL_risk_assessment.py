import pandas as pd

from scenario_menu import (
    ScenarioConfig,
    build_actions,
    show_menu,
    run_review_and_execute,
)


from LDDL_Different_Load_Variations import LDDL_MonoPeriodic_Load_Var
from LDDL_Different_Load_Variations import LDDL_BiPeriodic_Load_Var
from LDDL_Different_Load_Variations import LDDL_Tria_Load_Var
from LDDL_Viz_Functions import Read_System_Bus_Lat_Long
from LDDL_Viz_Functions import Process_LDDL_out_for_Viz
from LDDL_Viz_Functions import LDDL_OscAna_Viz
from LDDL_Viz_Functions import Print_Summary_Osc_Violation


def main():
    cfg = ScenarioConfig()
    actions = build_actions()

    while True:
        choice = show_menu().strip()
        U = choice.upper()
        if U == "Q":
            print("Thank you for using Large Load Risk Assessment Tool!")
            break
        elif U == "R":
            
            print(cfg)
            print('\n')
            print(cfg.load_model.model_type)
            print(cfg.load_model.load_bus_numbers)
            print(cfg.load_model.load_bus_ids)
            
            Locations = cfg.load_model.load_bus_numbers
            LDDL_bus = Locations[0]
            for LDDL_bus in Locations:
            
                if(cfg.load_variation.shape == "Mono-periodic"):
                    df = LDDL_MonoPeriodic_Load_Var(cfg, LDDL_bus)
                elif(cfg.load_variation.shape == "Bi-periodic"):
                    df = LDDL_BiPeriodic_Load_Var(cfg, LDDL_bus)
                elif(cfg.load_variation.shape == "Triangular"):
                    df = LDDL_Tria_Load_Var(cfg, LDDL_bus)
                
                CSV_Folder = cfg.viz.case_file_location
                PSSE_measurement_file = CSV_Folder + '\\' + 'LDDL_'+ str(LDDL_bus)+'.csv' 
                df = pd.read_csv( PSSE_measurement_file) 
                
                if not df.empty:
                    BUS_FILE = cfg.viz.network_latlong_file
                    bus_info = Read_System_Bus_Lat_Long(BUS_FILE, cfg)
                    [osc_line, names_line, osc_gen, gen_buses, osc_load, load_buses] = Process_LDDL_out_for_Viz(df, cfg)
                    
                    MW_THRESHOLD = cfg.viz.mw_threshold
                    CMAX         = cfg.viz.cmax

                    location = str(LDDL_bus)
                    
                    Output_Folder = cfg.files.output_file_location
                    LDDL_OscAna_Viz(location, MW_THRESHOLD, CMAX , osc_line, names_line, osc_gen, gen_buses, osc_load, load_buses, bus_info, Output_Folder)
                    Print_Summary_Osc_Violation(location, MW_THRESHOLD, CMAX , osc_line, names_line, osc_gen, gen_buses, osc_load, load_buses, bus_info, Output_Folder )
                    
        
            
            print("LDDL Load variation simulation over. \n")
            break   # Exit the menu
            
        elif choice in actions:
            actions[choice](cfg)
        elif U in actions:
            actions[U](cfg)
        else:
            print("Unknown option. Try again.")
            
    return(cfg, LDDL_bus)

if __name__ == "__main__":
    [cfg, LDDL_bus] = main()
