### Code for emulating double frequency square wave (DfSW) load variation behavior by LDDLs, mainly data centers
### This code is tested using PSS/E version 35.6

### Importing neccessary libraries
import os, sys
import timeit
import numpy as np

def prompt_with_default(prompt, default, cast=str):
    raw = input(f"{prompt} [{default}]: ").strip()
    return default if raw == "" else cast(raw)


### Initializing PSSE (change sys_path_PSSE and PSSE_LOCATION accordingly)
sys_path_PSSE = r'C:\Program Files\PTI\PSSE35\35.6\PSSPY311'  #or where else you find the psspy.pyc
sys.path.append(sys_path_PSSE)
PSSE_LOCATION = r"C:\Program Files\PTI\PSSE35\35.6\PSSBIN"
sys.path.append(PSSE_LOCATION)
os.environ['PATH'] = os.environ['PATH'] + ';' +  PSSE_LOCATION
local_dir = os.getcwd() ## finding current working directory
sys.path.append(local_dir)
os.environ['PATH'] += ';' + local_dir

import psse35
import psspy

psspy.psseinit(10000)
_i = psspy.getdefaultint()
_f = psspy.getdefaultreal()
_s = psspy.getdefaultchar()





### Simulation parameters are set here
## The load variation will be implemented for load at "load_bus_number" with ID "load_bus_ID"
eventStartTime = 2
load_bus_number = 1302
load_bus_name_ = 'HAllen_NV'
load_bus_ID = str(1)
Change_in_power_SW_step_MW = 100 

## Slower Freq (Bigger time step) Variables
Slower_Freq_in_DfSW_in_Hz = 0.5
Time_Step_of_Slower_Freq_in_DfSW_s = 1/Slower_Freq_in_DfSW_in_Hz
Change_in_power_SW_bigger_step = 0
Up_time_slower_load_var_in_s = Time_Step_of_Slower_Freq_in_DfSW_s/2
Down_time_slower_load_var_in_s = Time_Step_of_Slower_Freq_in_DfSW_s/2 

## Faster Freq (Smaller time step) Variables
Faster_Freq_in_DfSW_in_Hz = 5
Time_Step_of_Faster_Freq_in_DfSW_s = 1/Faster_Freq_in_DfSW_in_Hz
Change_in_power_SW_smaller_step = Change_in_power_SW_step_MW
Up_time_faster_load_var_in_s = Time_Step_of_Faster_Freq_in_DfSW_s/2
Down_time_faster_load_var_in_s = Time_Step_of_Faster_Freq_in_DfSW_s/2 


## 
num_period_of_load_var = 10 ## number of times the the load variation needs to be repeated
num_period_within_1_DfSW_period = 5 ## number of cycles within 1 DfSW period


print("Enter values (press Enter to keep default):")
eventStartTime = prompt_with_default("eventStartTime (sec)", eventStartTime, int)
load_bus_number = prompt_with_default("load_bus_number", load_bus_number, int)
load_bus_name_ = prompt_with_default("load_bus_name_", load_bus_name_, str)
load_bus_ID = prompt_with_default("load_bus_ID", load_bus_ID, str)
Change_in_power_SW_step_MW = prompt_with_default(
    "Change_in_power_SW_step_MW", Change_in_power_SW_step_MW, float
)
Slower_Freq_in_DfSW_in_Hz = prompt_with_default(
    "Slower_Freq_in_DfSW_in_Hz", Slower_Freq_in_DfSW_in_Hz, float
)
Faster_Freq_in_DfSW_in_Hz = prompt_with_default(
    "Faster_Freq_in_DfSW_in_Hz", Faster_Freq_in_DfSW_in_Hz, float
)

print("\nFinal values:")
print(f"{eventStartTime=}")
print(f"{load_bus_number=}")
print(f"{load_bus_name_=}")
print(f"{load_bus_ID=}")
print(f"{Change_in_power_SW_step_MW=}")
print(f"{Slower_Freq_in_DfSW_in_Hz=}")
print(f"{Faster_Freq_in_DfSW_in_Hz=}")

 
### Input (raw and dyr) and output (out and csv) file names are set here
### Note that raw and dyr files needs to be kept in local directory, and outputs will be saved to local directory
PSSE_files_dir = local_dir
OUTPUT_Folder = local_dir

rawFile = PSSE_files_dir + '\\' + '240busWECC_2018_PSS.raw'
dyrFile = PSSE_files_dir + '\\' + '240busWECC_2018_PSS.dyr' 
outFile = OUTPUT_Folder + '\\' + 'MiniWECC240_DfSW_load_Var_'+str(load_bus_number)+'_'+str(load_bus_name_)+'.out' 
csvFile = OUTPUT_Folder + '\\' +  'MiniWECC240_DfSW_load_Var_'+str(load_bus_number)+'_'+str(load_bus_name_)+'.csv' 


### Reading raw file
psspy.readrawversion(1, '35', rawFile) 
### Reading sav file
psspy.dyre_new([1,1,1,1], dyrFile, "","","")


### Initializing the dynamic simulation
psspy.fnsl([0,0,0,1,0,0,0,0])
psspy.cong(0)

psspy.conl(0,1,1,[0,0],[0.0,0.0,0.0,0.0])
psspy.conl(0,1,2,[0,0],[0.0,0.0,0.0,0.0])
psspy.conl(0,1,3,[0,0],[0.0,0.0,0.0,0.0])

ierr = psspy.ordr()
ierr = psspy.fact()
ierr = psspy.tysl(0) 

### Setup plot chanels ###
psspy.text(r"""<<< ------ Chanel setup ------ >>>""")
psspy.delete_all_plot_channels()
psspy.chsb(0,1,[-1,-1,-1,1,12,0])  # BSFREQ, bus pu frequency deviations.
psspy.chsb(0,1,[-1,-1,-1,1,13,0]) # VOLT, bus pu voltages (complex)
psspy.chsb(0,1,[-1,-1,-1,1,14,0]) # Voltage and Angle
#psspy.chsb(0,1,[-1,-1,-1,1,15,0]) # Power flow
psspy.chsb(0,1,[-1,-1,-1,1,16,0]) # flow (P and Q)
psspy.chsb(0,1,[-1,-1,-1,1,2,0]) # Pelec
psspy.chsb(0,1,[-1,-1,-1,1,3,0]) # Qelec
psspy.chsb(0,1,[-1,-1,-1,1,25,0]) # Pload






## Setting simulation parameters for the dynamic simulation
start_time = timeit.default_timer()
dyn_max_iter = 99 
NW_soln_Acce_sfactor = 1.0 ## acceleration factor
Delta_t_simulation = 0.0033333 ## time step for simulation
T_const_filter_for_bus_freq_calc = 0.016

n_prt = 999
n_out_channel = 10
n_CRT_PLT = 999



##### Dynamic simulation starts here...
psspy.dynamics_solution_params([dyn_max_iter ,_i,_i,_i,_i,_i,_i,_i],[ NW_soln_Acce_sfactor,_f, Delta_t_simulation, T_const_filter_for_bus_freq_calc,_f,_f,_f,_f],'')
psspy.strt_2([1, 0],outFile)


### Initial flat run till eventStartTime
psspy.run(0, eventStartTime, n_prt, n_out_channel, n_CRT_PLT)
T_till_prev_LC = eventStartTime



## Identifies the nominal load in "load_bus_number" and saves as "Base_PIload_value"
[ierr, Load_bus_Nums_p] = psspy.aloadint(sid = -1, flag = 1, string = 'NUMBER')
[ierr, S_nominal_p] = psspy.aloadcplx(sid = -1, flag = 1, string = 'ILNOM') ## ILACT is the actual complex const I power

Load_bus_index_in_load_arrays = Load_bus_Nums_p[0].index(load_bus_number)
Base_PIload_value = S_nominal_p[0][Load_bus_index_in_load_arrays].real





## Starting DfSW load variation
n_dT_OChange = 1
for k_lc in range(0,num_period_of_load_var): # pulsing load changes
    psspy.load_chng_6(load_bus_number, load_bus_ID,[_i,_i,_i,_i,_i,_i,_i],[ _f ,_f, Base_PIload_value + Change_in_power_SW_bigger_step , 0 , _f,_f,_f,_f],"") ## real number array 
    
    
    ## Faster variations within a time period of slower time period starts here
    for fast_load_var_iter in range(0, num_period_within_1_DfSW_period):
        psspy.load_chng_6(load_bus_number, load_bus_ID,[_i,_i,_i,_i,_i,_i,_i],[ _f ,_f, Base_PIload_value + Change_in_power_SW_bigger_step + Change_in_power_SW_smaller_step , 0 , _f,_f,_f,_f],"") ## real number array 
        
        t_next_pause = T_till_prev_LC + (Up_time_faster_load_var_in_s * (n_dT_OChange)) ### Only 5 time steps are used for loading OC change!! - As smooth as it gets
        psspy.run(0, t_next_pause, n_prt, n_out_channel, n_CRT_PLT)
        T_till_prev_LC = t_next_pause
        
        
        psspy.load_chng_6(load_bus_number, load_bus_ID,[_i,_i,_i,_i,_i,_i,_i],[ _f ,_f, Base_PIload_value + Change_in_power_SW_bigger_step  , 0 , _f,_f,_f,_f],"") ## real number array 
        
        t_next_pause = T_till_prev_LC + (Down_time_faster_load_var_in_s * (n_dT_OChange)) ### Only 5 time steps are used for loading OC change!! - As smooth as it gets
        psspy.run(0, t_next_pause, n_prt, n_out_channel, n_CRT_PLT)
        T_till_prev_LC = t_next_pause
        
    ## Down time with load remaining on Nominal value
    psspy.load_chng_6(load_bus_number, load_bus_ID,[_i,_i,_i,_i,_i,_i,_i],[_f ,_f, Base_PIload_value , 0 , _f,_f,_f,_f],"") ## real number array 
    
    
    t_next_pause = T_till_prev_LC + (Down_time_slower_load_var_in_s * (n_dT_OChange)) ### Only 5 time steps are used for loading OC change!! - As smooth as it gets
    psspy.run(0, t_next_pause, n_prt, n_out_channel, n_CRT_PLT)
    T_till_prev_LC = t_next_pause



# =============================================================================
# Export simulation outputs to csv
# =============================================================================
import dyntools
import pandas as pd
chnfobj = dyntools.CHNF(outFile)
sh_ttl, ch_id, ch_data = chnfobj.get_data()
plot_chns = list(range(1, len(ch_id)))
csv_dict = {}
time = ch_data['time']
csv_dict['time'] = time
for chn_idx in plot_chns:
    csv_dict[ch_id[chn_idx]] = ch_data[chn_idx] ### ch_id added as the keys (headings) and ch_data is added as the values (measurements)
df = pd.DataFrame(csv_dict)
df.to_csv(csvFile, index=False)

