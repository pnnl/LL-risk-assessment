## Simulate a load impulse at chosen bus. Impulse response ringdown will be analyzed to obtain mode estimates
import os, sys, time
from pathlib import Path
import pandas as pd 

from psse_config import configure_psse
psse_version = 35
psspy_version = 311
psspy = configure_psse(psse_version, psspy_version)


def initialize_dynamic_simulation():
    ### Initializing the dynamic simulation
    psspy.fnsl([0,0,0,1,0,0,0,0])
    psspy.cong(0)
    
    psspy.conl(0,1,1,[0,0],[0.0,0.0,0.0,0.0])
    psspy.conl(0,1,2,[0,0],[0.0,0.0,0.0,0.0])
    psspy.conl(0,1,3,[0,0],[0.0,0.0,0.0,0.0])
    
    ierr = psspy.ordr()
    ierr = psspy.fact()
    ierr = psspy.tysl(0) 
    return()

def set_up_channels(bus_number):
    # function for setting up PSSE channel outputs - recording voltage angle at bus under study
    psspy.text(r"""<<< ------ Channel setup ------ >>>""")
    psspy.delete_all_plot_channels()
    psspy.voltage_and_angle_channel([-1,-1,-1,bus_number])
   
def export_sim_to_csv(outFile,csvFile):
    # =============================================================================
    # Export simulation outputs to csv
    # =============================================================================
    import dyntools
    import pandas as pd
    chnfobj = dyntools.CHNF(str(outFile))
    sh_ttl, ch_id, ch_data = chnfobj.get_data()
    plot_chns = list(range(1, len(ch_id)))
    csv_dict = {}
    time = ch_data['time']
    csv_dict['time'] = time
    for chn_idx in plot_chns:
        csv_dict[ch_id[chn_idx]] = ch_data[chn_idx] ### ch_id added as the keys (headings) and ch_data is added as the values (measurements)
    df = pd.DataFrame(csv_dict)
    df.to_csv(csvFile, index=False)
    return df
#------------------------------------------------

# Actual PSSE simulations run here. 

def load_impulse(sav_case, dyr_case, bus_number, load_step, csvpath):
    psspy.psseinit(200000)
    Tot_sim_time = 10
    Output_File_Name_Str = str(bus_number)
     
    ## Setting the PSS/E output out and csv files 
    outFile = csvpath + '\\' + 'impulse_'+ str(Output_File_Name_Str)+'.out' 
    csvFile = csvpath + '\\' + 'impulse_'+ str(Output_File_Name_Str)+'.csv' 
    
    cnvFile = csvpath + '\\' + 'Load_impulse_test_'+ str(Output_File_Name_Str)+'.cnv' 
    snpFile = csvpath + '\\' + 'Load_impulse_test_'+ str(Output_File_Name_Str)+'.snp' 
    print(outFile)
    val_i = psspy.getdefaultint()
    _f = psspy.getdefaultreal()
    
    ### Reading case
    psspy.case(sav_case) 
        
    # place fictional load at user specified bus to apply impulse
    ierr = psspy.load_data_6(
        bus_number,
        'bk',
        [val_i,val_i,val_i,val_i,val_i,val_i,val_i],
        [1,_f,_f,_f,_f,_f,_f,_f],          
        ""
        )
    if ierr != 0:
        print("Cannot add load at specified bus")
        sys.exit()
    
    ### Reading dyr file
    psspy.dyre_new([1,1,1,1], dyr_case, "","","")
    initialize_dynamic_simulation()
    set_up_channels(bus_number)

    ## Setting PSS/E simulation parameters for the dynamic simulation
    dyn_max_iter = 99 
    NW_soln_Acce_sfactor = 1.0 ## acceleration factor
    Delta_t_simulation = 0.0033333 ## time step for simulation
    T_const_filter_for_bus_freq_calc = 0.016
    n_prt = 999
    n_out_channel = 10
    n_CRT_PLT = 999
    
    ##### Dynamic simulation starts here...
    psspy.dynamics_solution_params([dyn_max_iter ,val_i,val_i,val_i,val_i,val_i,val_i,val_i],[ NW_soln_Acce_sfactor,_f, Delta_t_simulation, T_const_filter_for_bus_freq_calc,_f,_f,_f,_f],'')
    psspy.save(cnvFile)
    psspy.snap([-1,-1,-1,-1,-1], snpFile)
    psspy.strt_2([1, 0],outFile)
    
    ### Initial flat run till eventStartTime
    psspy.run(0, 1.5, n_prt, n_out_channel, n_CRT_PLT) ## flat run till LDDL_var_ST s
    psspy.load_chng_6(bus_number, 'bk' ,[val_i,val_i,val_i,val_i,val_i,val_i,val_i],[load_step ,0 , _f  , _f, _f,_f,_f,_f],"") ## for the first half of this time period load value is increased to "LDDL_var_ampli " 
    psspy.run(0, 2, n_prt, n_out_channel, n_CRT_PLT) ## 
    psspy.load_chng_6(bus_number, 'bk' ,[val_i,val_i,val_i,val_i,val_i,val_i,val_i],[ 0 ,0, _f , _f ,  _f,_f,_f,_f],"") ## for the second half of this load variation period, the value of the load is decreased to 0
    psspy.run(0, Tot_sim_time, n_prt, n_out_channel, n_CRT_PLT)
        
    df = export_sim_to_csv(outFile,csvFile)
    
    return(df)

def main():
    # 0.5 s Load impulse at user specified bus
    # Impulse response will be analyzed to obtain mode estimates
    
    start = time.time() 
    # pointing to case location and output directory
    root = Path.cwd()
    case_dir = root/"PSSE_Cases"
    meta_dir = root/"Processing"

    config_name = 'modal_analysis_config.csv' #specify config file here
    config = pd.read_csv(root/config_name)
    case_name = config[config.Variable == 'case_name']['Value'][0]
    dyr_name = case_name+'.dyr'
    sav_name = case_name+'.sav'
    sav_case = case_dir / sav_name
    dyr_case = case_dir / dyr_name
    
    step_mw = int(config[config.Variable == 'load_step_MW']['Value'].iloc[0])
    bus_number = int(config[config.Variable == 'bus_number']['Value'].iloc[0])
    
    load_impulse(str(sav_case), str(dyr_case), bus_number, step_mw, str(meta_dir))
    print(f"\nTotal runtime: {time.time() - start:.2f} seconds")


if __name__ == "__main__":
    main()