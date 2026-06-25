import os, sys
import matplotlib.pyplot as plt

from psse_config import configure_psse
psse_version = 36
psspy_version = 314
psspy = configure_psse(psse_version, psspy_version)

psspy.psseinit(200000)
_i = psspy.getdefaultint()
_f = psspy.getdefaultreal()
_s = psspy.getdefaultchar()

# =============================================================================
# INPUT
# =============================================================================
case_raw_name    = '240busWECC_2018_PSS.raw'
case_dyr_name    = '240busWECC_2018_PSS.dyr'
case_dyr_1_name    = 'Load_FO_Model.dyr'
case_sav1_name = '240busWECC_2018_PSS_Mod_LL.sav'

script_dir = os.path.dirname(os.path.abspath(__file__)) ## pwd
parent_dir = os.path.dirname(os.path.dirname(script_dir)) ## parent directory

case_raw_path = os.path.join(parent_dir, "PSSE_Cases", case_raw_name) 
case_sav_path = os.path.join(parent_dir, "PSSE_Cases", case_sav1_name) 
case_dyr_path = os.path.join(parent_dir, "PSSE_Cases", case_dyr_name)

outFile  = 'LO_with_UDM.out'    # Output file for dynamic simulation
csvFile  = 'LO_with_UDM.csv'    # CSV file for output


# =============================================================================
# MAIN
# =============================================================================

psspy.read(0, case_raw_path) # read raw file
LDDL_bus_number = 1401

P = 0
Q = 0
ierr = psspy.load_data_7(
    LDDL_bus_number,
    'OS',
    [_i,_i,_i,_i,_i,_i,_i],
    [P,Q,_f,_f,_f,_f,_f,_f]  
    )

psspy.fnsl([0,0,0,0,0,0,0,0])
psspy.save(case_sav_path)


psspy.cong(0)
psspy.conl(0,1,1,[0,0],[ 100.0,0.0,0.0, 100.0])
psspy.conl(0,1,2,[0,0],[ 100.0,0.0,0.0, 100.0])
psspy.conl(0,1,3,[0,0],[ 100.0,0.0,0.0, 100.0])

psspy.cong(0)  
psspy.ordr(0)  
psspy.fact()  
psspy.tysl(0)  

# Add dyr file
psspy.dyre_new_2([1, 1, 1, 1], case_dyr_path) ## read from PSSE_Cases folder
psspy.dyre_add_2([_i,_i,_i,_i], case_dyr_1_name) ## available in pwd
psspy.dynamics_solution_param_2([60,_i,_i,_i,_i,_i,_i,_i],[ 0.4,_f, 0.0033333,_f,_f,_f,_f,_f])  ## Dynamic solution network parameters (adjusting time step and step size)

psspy.addmodellibrary("LO_UDM_v36_dll.dll")   # reading dll file

psspy.delete_all_plot_channels()
# channels
ierr = psspy.load_array_channel([-1,1, LDDL_bus_number], 'OS', 'LDDL P')
ierr = psspy.load_array_channel([-1,2, LDDL_bus_number], 'OS', 'LDDL Q')
ierr = psspy.voltage_channel([-1,-1,-1,LDDL_bus_number], 'LDDL Bus Voltage')
ierr = psspy.bus_frequency_channel([-1,LDDL_bus_number], 'LDDL Bus Frequency')

# =============================================================================
# Run Dynamics - Load Change
# =============================================================================
ierr = psspy.strt_2([0, 0], outFile)

psspy.run(0, 15, 999, 10, 999)

# =============================================================================
# Export to CSV
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
	csv_dict[ch_id[chn_idx]] = ch_data[chn_idx]

df = pd.DataFrame(csv_dict)
df.to_csv(csvFile, index=False)

print(f"Simulation completed. Results saved to {csvFile}")




