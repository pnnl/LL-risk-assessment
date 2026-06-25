import os, sys
import matplotlib.pyplot as plt
from psse_config import configure_psse
psse_version = 34
psspy_version = 37
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
case_dyr_FO_UDM_name = 'Load_FO_Model.dyr'

case_dyr_1_name    = 'Load_FO_Model.dyr'
case_sav1_name = '240busWECC_2018_PSS_Mod_LL.sav'

script_dir = os.path.dirname(os.path.abspath(__file__)) ## pwd
parent_dir = os.path.dirname(os.path.dirname(script_dir)) ## parent directory

case_raw_path = os.path.join(parent_dir, "PSSE_Cases", case_raw_name)
case_sav1_path = os.path.join(parent_dir, "PSSE_Cases", case_sav1_name)
case_dyr_path = os.path.join(parent_dir, "PSSE_Cases", case_dyr_name)

outFile  = 'LO_with_UDM.out'    # Output file for dynamic simulation
csvFile  = 'LO_with_UDM.csv'    # CSV file for output


# =============================================================================
# MAIN
# =============================================================================
LDDL_bus_number = 1401  #Bus at which the LDDL osc is introduced
psspy.bus_size_level(200000)
psspy.new_dimension(200000)
psspy.read(0, case_raw_path)

P = 0
Q = 0
ierr = psspy.load_data_5(
       LDDL_bus_number,
       'OS',
       [_i,_i,_i,_i,_i,_i,_i],
       [P,Q,_f,_f,_f,_f,_f,_f]
       )


psspy.fnsl([0,0,0,0,0,0,0,0])  ## solves the powerflow
psspy.save(case_sav1_path)



psspy.cong(0)
psspy.conl(0)
psspy.ordr(0)
psspy.fact()
psspy.tysl(0)

psspy.dyre_new([1,1,1,1], case_dyr_path,r"""conec""",r"""conet""",r"""compile""")
psspy.dyre_add([_i,_i,_i,_i], case_dyr_FO_UDM_name, "","")
psspy.dynamics_solution_param_2([60,_i,_i,_i,_i,_i,_i,_i],[ 0.4,_f, 0.0033333,_f,_f,_f,_f,_f])

psspy.addmodellibrary(r"""LO_UDM_v34_dll.dll""")

psspy.delete_all_plot_channels()
### Channels at the newly added LDDL bus
ierr = psspy.load_array_channel([-1,1, LDDL_bus_number], 'OS', 'LDDL P')
ierr = psspy.load_array_channel([-1,2, LDDL_bus_number], 'OS', 'LDDL Q')
ierr = psspy.voltage_channel([-1,-1,-1,LDDL_bus_number], 'LDDL Bus Voltage')
ierr = psspy.bus_frequency_channel([-1,LDDL_bus_number], 'LDDL Bus Frequency')

psspy.strt_2([0,0], outFile)

n_prt = 999
n_out_channel = 10
n_CRT_PLT = 999
Tot_sim_time = 15

psspy.run(0, Tot_sim_time, n_prt, n_out_channel, n_CRT_PLT)

# =============================================================================
# The following piece of code exports channels to CSV
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






