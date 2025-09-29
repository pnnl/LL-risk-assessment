
import os, sys
import timeit
import numpy as np


sys.path.append(r"C:\Program Files\PTI\PSSE35\35.6\PSSPY311")
sys.path.append(r"C:\Program Files\PTI\PSSE35\35.6\PSSBIN")
os.environ['PATH'] += ';' + r"C:\Program Files\PTI\PSSE35\35.6\PSSBIN"

import psse35
import psspy

import matplotlib.pyplot as plt
from matplotlib import cm, colors            # cm & colors both needed
import cartopy.crs as ccrs
import cartopy.feature as cfeature
from cartopy.mpl.ticker import LongitudeFormatter, LatitudeFormatter
import matplotlib as mpl
import os


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
            print("Thank you for using Large Load Modeling Tool!")
            break
        elif U == "R":
            #run_review_and_execute(cfg)
            
            print(cfg)
            print('\n')
            print(cfg.load_model.model_type)
            # print(cfg.load_model.total_load_MW)
            # print(cfg.load_variation.shape)
            # print(cfg.viz.case_file_location)
            # print('\n')
            
            
            #print(cfg.system.PSSE_LOCATION)
            
            
            if(cfg.load_variation.shape == "Mono-periodic"):
                df = LDDL_MonoPeriodic_Load_Var(cfg)
            elif(cfg.load_variation.shape == "Bi-periodic"):
                df = LDDL_BiPeriodic_Load_Var(cfg)
            elif(cfg.load_variation.shape == "Triangular"):
                df = LDDL_Tria_Load_Var(cfg)
            
            if not df.empty:
                BUS_FILE = cfg.viz.network_latlong_file
                bus_info = Read_System_Bus_Lat_Long(BUS_FILE)
                [osc_line, names_line, osc_gen, gen_buses, osc_load, load_buses] = Process_LDDL_out_for_Viz(df)
                
                MW_THRESHOLD = cfg.viz.mw_threshold
                CMAX         = cfg.viz.cmax
                
                LOCATIONS = [
                    "1004_SanJuan_NM", "1101_Coronado_AZ", "1302_HAllen_NV",
                    "1401_PaloVerde_AZ", "2600_Adelanto_CA", "4008_Malin_OR",
                    "4010_Celilo_OR", "4101_Coulee_WA", "4102_Hanford_WA",
                    "5001_Canada_BC",
                ]
                location = LOCATIONS[2]                                  # 1302_HAllen_NV
    
                LDDL_OscAna_Viz(location, MW_THRESHOLD, CMAX , osc_line, names_line, osc_gen, gen_buses, osc_load, load_buses, bus_info)
                Print_Summary_Osc_Violation(location, MW_THRESHOLD, CMAX , osc_line, names_line, osc_gen, gen_buses, osc_load, load_buses, bus_info )
                
        
            
            print("LDDL Load variation simulation over. \n")
            break   # automatically exit after R
            
        elif choice in actions:
            actions[choice](cfg)
        elif U in actions:
            actions[U](cfg)
        else:
            print("Unknown option. Try again.")

if __name__ == "__main__":
    main()
