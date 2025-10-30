## File containing functions for three types of variations for LDDLs - monoperiodic, biperiodic and triangular
import os, sys
import psse35
import psspy

# setting up some common functions required for all load variation types

def get_loads_at_bus(busnum):
    """
    Returns a list of tuples (bus_number, load_id) for all loads in the currently loaded PSSE case.
    """
    loads = []
    # Get all load bus numbers
    ierr_bus, bus_numbers = psspy.aloadint(-1, string='NUMBER')  # -1 = all buses
    # Get all load IDs
    ierr_id, load_ids = psspy.aloadchar(-1, string='ID')
    if ierr_bus != 0 or ierr_id != 0:
        raise RuntimeError(f"psspy.aload* returned ierrs: bus={ierr_bus}, id={ierr_id}")

    # Flatten and clean up
    bus_list = bus_numbers[0] if bus_numbers else []
    id_list = [str(lid).strip().strip("'\"") for lid in (load_ids[0] if load_ids else [])]

    # Zip up to the shortest length to avoid mismatches
    for b, lid in zip(bus_list, id_list):
        loads.append((int(b), lid))

    return [t for t in loads if t[0] == busnum]

def edit_dyr(dyr_file, lddl_bus, base_load_id):
    # Modify existing load connected to LDDL bus to represent data center dynamics
    # LDDL represented as a composite load with composition matching the NERC LL survey
    from pathlib import Path
    lddl_bus = str(lddl_bus)

    # Path to your DYR file
    dyr_file = Path(dyr_file)

    # Read all lines
    lines = dyr_file.read_text().splitlines()
    line = lines[0]
    parts = line.strip().split()
    parts[0] = lddl_bus
    parts[2] = base_load_id
    line = " ".join(parts)
    lines[0] = line

    # Overwrite the same file
    dyr_file.write_text("\n".join(lines) + "\n")

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

def set_up_channels(cfg):
    # function for setting up PSSE channel outputs
    import pandas as pd
    import numpy as np
    network_info = pd.read_csv('Results_'+str(cfg.load_model.load_bus_number)+'\\sys_bus_summary.csv')
    gens = network_info[network_info.PGEN>0]
    branches = pd.read_csv('Results_'+str(cfg.load_model.load_bus_number)+'\\filtered_lines.csv')
    loads = pd.read_csv('Results_'+str(cfg.load_model.load_bus_number)+'\\filtered_load.csv')
    
    ### Setup plot chanels ###
    psspy.text(r"""<<< ------ Channel setup ------ >>>""")
    psspy.delete_all_plot_channels()
    psspy.bus_frequency_channel([-1, cfg.load_model.load_bus_number])
    
    for bus_number in network_info.BUS_NUMBER:
        psspy.voltage_channel([-1,-1,-1,bus_number])
    ierr, gen_bus = psspy.amachint(-1,1,'NUMBER')
    ierr, gen_id = psspy.amachchar(-1,1,'ID')
    for gen in gens.BUS_NUMBER:
        idx = [i for i, x in enumerate(gen_bus[0]) if x == gen]
        for iter_ in idx:
            psspy.machine_array_channel([-1, 2, gen],gen_id[0][iter_])  #ideally this line should be used. If issues obsreved uncomment chsb command
    # psspy.chsb(0,1,[-1,-1,-1,1,2,0])
    for i in range(len(branches)):
        frombus = branches.iloc[i]['FROMBUS']
        tobus = branches.iloc[i]['TOBUS']
        psspy.branch_p_channel([-1,-1,-1,int(frombus),int(tobus)])
    ierr, load_bus = psspy.aloadint(-1,1,'NUMBER')
    ierr, load_id = psspy.aloadchar(-1,1,'ID')
    tt = loads.BUS_NUMBER.values
    tt = np.append(tt,cfg.load_model.load_bus_number)
    for load in tt:
        idx = [i for i, x in enumerate(load_bus[0]) if x == load]
        for iter_ in idx:
            psspy.load_array_channel([-1, 1, load],load_id[0][iter_])  #ideally this line should be used. If issues obsreved uncomment chsb command
    #psspy.chsb(0,1,[-1,-1,-1,1,25,0])
    
    #if plotting all channels is desired, then uncomment the following lines instead of the set_up_channels() function

    # psspy.chsb(0,1,[-1,-1,-1,1,12,0])  # BSFREQ, bus pu frequency deviations.
    # psspy.chsb(0,1,[-1,-1,-1,1,13,0]) # VOLT, bus pu voltages (complex)
    # psspy.chsb(0,1,[-1,-1,-1,1,14,0]) # Voltage and Angle
    # psspy.chsb(0,1,[-1,-1,-1,1,15,0]) # Power flow
    # psspy.chsb(0,1,[-1,-1,-1,1,16,0]) # flow (P and Q)
    # psspy.chsb(0,1,[-1,-1,-1,1,2,0]) # Pelec
    # psspy.chsb(0,1,[-1,-1,-1,1,3,0]) # Qelec
    # psspy.chsb(0,1,[-1,-1,-1,1,25,0]) # Pload
        
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

def LDDL_MonoPeriodic_Load_Var(cfg):
    psspy.psseinit(200000)
    
    ## Unpacking simulation parameters from cfg
    Load_model_type = cfg.load_model.model_type
    LDDL_var_ampli = cfg.load_model.total_load_MW
    LDDL_bus_number = cfg.load_model.load_bus_number
    Freq_LDDL_var = cfg.load_variation.freq_primary_hz ## Frequency of square wave variation of LDDL
    LDDL_var_ST = cfg.load_variation.start_time_s ## start time of LDDL load variation in simulation
    Tot_sim_time = cfg.load_variation.sim_run_time_s
    Output_File_Name_Str = str(LDDL_bus_number)
    
    ## Calculating other simulation variables (basically, oscillation time periods)
    D = 0.5 # 50% duty cycle, to change duty cycle, this parameter must be changed
    TP_LDDL_var = 1/Freq_LDDL_var ## time period of individual cycles of square wave variation
    Up_time_in_1_TP = TP_LDDL_var*D 
    Down_time_in_1_TP = TP_LDDL_var*(1-D) 
    Num_total_LDDL_cycles = int((Tot_sim_time - LDDL_var_ST)/TP_LDDL_var) ## total LDDL time periods that can be completed
     
    ## Setting the PSSS/E input raw, dyr files
    PSSE_files_dir = cfg.files.case_file_location
    OUTPUT_Folder = cfg.files.output_file_location+'\\'+'Results_'+str(LDDL_bus_number)
    rawFile = PSSE_files_dir + '\\' + str(cfg.files.raw_file)
    dyrFile = PSSE_files_dir + '\\' + str(cfg.files.dyr_file)
    dyrFile_ZIP = str('ZIP_Load_.dyr')
    dyrFile_CMLD = str('CMLD_Load_.dyr')

    ## Setting the PSS/E output out and csv files based on cfg input
    outFile = OUTPUT_Folder + '\\' + 'LDDL_'+ str(Output_File_Name_Str)+'.out' 
    csvFile = OUTPUT_Folder + '\\' + 'LDDL_'+ str(Output_File_Name_Str)+'.csv' 
    print(outFile)
    val_i = psspy.getdefaultint()
    _f = psspy.getdefaultreal()
    
    ### Reading raw file
    psspy.readrawversion(1, '35', rawFile) 
    
    # we place a load at the specified bus that introduces constant power load pulsations with the specified amplitude
    # Also modify the dynamic model of the first load id connected to the specified bus to represent data center dynamics
    # If the user wants to modify a particular load ID instead, they could specify the value in the base_load_id variable and comment out the following code snippet
    
    load_ids = get_loads_at_bus(LDDL_bus_number)
    if len(load_ids) <1:
        print('No load available at specified bus')
        sys.exit()
    else:
        base_load_id = load_ids[0][1]
        
    # place load at user specified bus, this is the constant power pulsating load component
    ierr = psspy.load_data_6(
        LDDL_bus_number,
        'LL',
        [val_i,val_i,val_i,val_i,val_i,val_i,val_i],
        [1,_f,_f,_f,_f,_f,_f,_f],          
        ""
        )
    if ierr != 0:
        print("Cannot add load at specified bus")
        sys.exit()
    
    ### Reading sav file
    psspy.dyre_new([1,1,1,1], dyrFile, "","","")
    # Edit dynamic load model
    if Load_model_type == 'ZIP':
        edit_dyr('ZIP_load_.dyr',LDDL_bus_number,base_load_id)
        psspy.dyre_add([val_i,val_i,val_i,val_i], dyrFile_ZIP, "","")
    else:
        edit_dyr('CMLD_load_.dyr',LDDL_bus_number,base_load_id)
        psspy.dyre_add([val_i,val_i,val_i,val_i], dyrFile_CMLD, "","")
    
    initialize_dynamic_simulation()
    set_up_channels(cfg)

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
    psspy.save("zzzxxx.cnv")
    psspy.snap([-1,-1,-1,-1,-1],r"""CMLD_Test.snp""")
    psspy.strt_2([1, 0],outFile)
    
    ### Initial flat run till eventStartTime
    psspy.run(0, LDDL_var_ST, n_prt, n_out_channel, n_CRT_PLT) ## flat run till LDDL_var_ST s
    T_stop = LDDL_var_ST ## saving stop time 
     
    ### Starting the square wave load variation and repeating for Num_total_LDDL_cycles
    for load_var_cycles in range(0, Num_total_LDDL_cycles): # the load variation is repeated "num_period_of_load_var" times
        
        psspy.load_chng_6(LDDL_bus_number, 'LL' ,[val_i,val_i,val_i,val_i,val_i,val_i,val_i],[LDDL_var_ampli ,0 , _f  , _f, _f,_f,_f,_f],"") ## for the first half of this time period load value is increased to "LDDL_var_ampli " 
        T_stop = T_stop + Up_time_in_1_TP ### Increased load value will be present for "Up_time_load_var_in_s"
        psspy.run(0, T_stop, n_prt, n_out_channel, n_CRT_PLT) ## 
    
        psspy.load_chng_6(LDDL_bus_number, 'LL' ,[val_i,val_i,val_i,val_i,val_i,val_i,val_i],[ 0 ,0, _f , _f ,  _f,_f,_f,_f],"") ## for the second half of this load variation period, the value of the load is decreased to 0
        T_stop = T_stop + Down_time_in_1_TP  ### Reduced load value will be present for "Down_time_load_var_in_s"
        psspy.run(0, T_stop, n_prt, n_out_channel, n_CRT_PLT)
        
    ## Running without load variation for remaining time
    psspy.run(0, Tot_sim_time, n_prt, n_out_channel, n_CRT_PLT)
        
    df = export_sim_to_csv(outFile,csvFile)
    
    return(df)

def LDDL_BiPeriodic_Load_Var(cfg):
    import numpy as np
    psspy.psseinit(200000)
    val_i = psspy.getdefaultint()
    _f = psspy.getdefaultreal()
    
    ## Unpacking simulation parameters from cfg
    Load_model_type = cfg.load_model.model_type
    LDDL_var_ampli = cfg.load_model.total_load_MW
    
    LDDL_bus_number = cfg.load_model.load_bus_number
    Freq_LDDL_var_prime = cfg.load_variation.freq_primary_hz ## Frequency of square wave variation of LDDL
    Freq_LDDL_var_secondary = cfg.load_variation.freq_secondary_hz
    LDDL_var_ST = cfg.load_variation.start_time_s ## start time of LDDL load variation in simulation
    Tot_sim_time = cfg.load_variation.sim_run_time_s
    
    ## Calculating other simulation variables
    D = 0.5 # duty cycle
    TP_LDDL_var_prime = 1/Freq_LDDL_var_prime ## time period of individual cycles of bi periodic 
    # Up_time_in_1_TP_prime = TP_LDDL_var_prime*D ## symmetric 
    Down_time_in_1_TP_prime = TP_LDDL_var_prime*(1-D)
    TP_LDDL_var_secondary = 1/Freq_LDDL_var_secondary
    Up_time_in_1_TP_secondary = TP_LDDL_var_secondary/2 ## symmetric 
    Down_time_in_1_TP_secondary = TP_LDDL_var_secondary/2 ## symmetric 
    Num_total_LDDL_cycles = int((Tot_sim_time - LDDL_var_ST)/TP_LDDL_var_prime) ## total LDDL time periods that can be completed
    Num_fast_cycles = int(np.ceil((TP_LDDL_var_prime*D)/TP_LDDL_var_secondary))## within up part of the slow LDDL period
    #Rem_time = (Tot_sim_time - LDDL_var_ST - (Num_total_LDDL_cycles*TP_LDDL_var_prime) ) ## time left in simulation
    Output_File_Name_Str = str(LDDL_bus_number)
    
    ## Setting the PSSS/E input raw, dyr files
    PSSE_files_dir = cfg.files.case_file_location
    OUTPUT_Folder = cfg.files.output_file_location+'\\'+'Results_'+str(LDDL_bus_number)
    rawFile = PSSE_files_dir + '\\' + str(cfg.files.raw_file)
    dyrFile = PSSE_files_dir + '\\' + str(cfg.files.dyr_file)
    dyrFile_ZIP = str('ZIP_Load_.dyr')
    dyrFile_CMLD = str('CMLD_Load_.dyr')
    ## Setting the PSS/E output out and csv files based on cfg input
    outFile = OUTPUT_Folder + '\\' + 'LDDL_'+ str(Output_File_Name_Str)+'.out' 
    csvFile = OUTPUT_Folder + '\\' + 'LDDL_'+ str(Output_File_Name_Str)+'.csv' 
    
    ### Reading raw file
    psspy.readrawversion(1, '35', rawFile) 
    
    load_ids = get_loads_at_bus(LDDL_bus_number)
    if len(load_ids) <1:
        print('No load available at specified bus')
        sys.exit()
    else:
        base_load_id = load_ids[0][1]
        
    # place load at user specified bus, this is the constant power pulsating load component
    ierr = psspy.load_data_6(
        LDDL_bus_number,
        'LL',
        [val_i,val_i,val_i,val_i,val_i,val_i,val_i],
        [1,_f,_f,_f,_f,_f,_f,_f],          
        ""
        )
    if ierr != 0:
        print("Cannot add load at specified bus")
        sys.exit()
    
    ### Reading sav file
    psspy.dyre_new([1,1,1,1], dyrFile, "","","")
    if Load_model_type == 'ZIP':
        edit_dyr('ZIP_load_.dyr',LDDL_bus_number,base_load_id)
        psspy.dyre_add([val_i,val_i,val_i,val_i], dyrFile_ZIP, "","")
    else:
        edit_dyr('CMLD_load_.dyr',LDDL_bus_number,base_load_id)
        psspy.dyre_add([val_i,val_i,val_i,val_i], dyrFile_CMLD, "","")
    
    initialize_dynamic_simulation()
    set_up_channels(cfg)
    
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
    psspy.strt_2([1, 0],outFile)
    
    ### Initial flat run till eventStartTime
    psspy.run(0, LDDL_var_ST, n_prt, n_out_channel, n_CRT_PLT) ## flat run till LDDL_var_ST s
    T_stop = LDDL_var_ST ## saving stop time 
    
    ## TP_LDDL_var_prime
    
    for load_var_cycles in range(0, Num_total_LDDL_cycles): # pulsing load changes
        
        for fast_load_var_iter in range(0,Num_fast_cycles):
            psspy.load_chng_6(LDDL_bus_number, 'LL',[val_i,val_i,val_i,val_i,val_i,val_i,val_i],[ LDDL_var_ampli  , 0 ,  _f ,_f, _f,_f,_f,_f],"") ## real number array 
            T_stop = T_stop + Up_time_in_1_TP_secondary ### 
            psspy.run(0, T_stop, n_prt, n_out_channel, n_CRT_PLT)
            
            psspy.load_chng_6(LDDL_bus_number, 'LL' ,[val_i,val_i,val_i,val_i,val_i,val_i,val_i],[ 0 , 0 ,_f ,_f,  _f,_f,_f,_f],"") ## real number array 
            T_stop = T_stop + Down_time_in_1_TP_secondary ### 
            psspy.run(0, T_stop, n_prt, n_out_channel, n_CRT_PLT)
    
        psspy.load_chng_6(LDDL_bus_number, 'LL' ,[val_i,val_i,val_i,val_i,val_i,val_i,val_i],[ 0 , 0 , _f ,_f, _f,_f,_f,_f],"") ## real number array 
        T_stop = T_stop + Down_time_in_1_TP_prime ### 
        psspy.run(0, T_stop, n_prt, n_out_channel, n_CRT_PLT)
        
    ## Running without load variation for remaining time
    psspy.run(0, Tot_sim_time, n_prt, n_out_channel, n_CRT_PLT)
    
    df = export_sim_to_csv(outFile,csvFile)
    return(df)    


def LDDL_Tria_Load_Var(cfg): ## Function to Emulate Triangular Load Variation
    psspy.psseinit(200000)
    val_i = psspy.getdefaultint()
    _f = psspy.getdefaultreal()
    
    ## Unpacking simulation parameters from cfg
    Load_model_type = cfg.load_model.model_type
    LDDL_var_ampli = cfg.load_model.total_load_MW
    LDDL_bus_number = cfg.load_model.load_bus_number    
    Output_File_Name_Str = str(LDDL_bus_number)
    Freq_LDDL_var = cfg.load_variation.freq_primary_hz ## Frequency of square wave variation of LDDL
    LDDL_var_ST = cfg.load_variation.start_time_s ## start time of LDDL load variation in simulation
    Tot_sim_time = cfg.load_variation.sim_run_time_s
    
    ## Calculating other simulation variables
    TP_LDDL_var = 1/Freq_LDDL_var ## time period of individual cycles of square wave variation
    Up_time_in_1_TP = TP_LDDL_var/2 ## symmetric sw variation
    # Down_time_in_1_TP = TP_LDDL_var/2 ## symmetric sw variation
    
    Num_total_LDDL_cycles = int((Tot_sim_time - LDDL_var_ST)/TP_LDDL_var) ## total LDDL time periods that can be completed
    #Rem_time = (Tot_sim_time - LDDL_var_ST - (Num_total_LDDL_cycles*TP_LDDL_var) ) ## time left in simulation
    
    ## Setting the PSSS/E input raw, dyr files
    PSSE_files_dir = cfg.files.case_file_location
    OUTPUT_Folder = cfg.files.output_file_location+'\\'+'Results_'+str(LDDL_bus_number)
    rawFile = PSSE_files_dir + '\\' + str(cfg.files.raw_file)
    dyrFile = PSSE_files_dir + '\\' + str(cfg.files.dyr_file)
    dyrFile_ZIP = str('ZIP_Load_.dyr')
    dyrFile_CMLD = str('CMLD_Load_.dyr')

    ## Setting the PSS/E output out and csv files based on cfg input
    outFile = OUTPUT_Folder + '\\' + 'LDDL_'+ str(Output_File_Name_Str)+'.out' 
    csvFile = OUTPUT_Folder + '\\' + 'LDDL_'+ str(Output_File_Name_Str)+'.csv'
    
    ### Reading raw file
    psspy.readrawversion(1, '35', rawFile) 
    load_ids = get_loads_at_bus(LDDL_bus_number)
    if len(load_ids) <1:
        print('No load available at specified bus')
        sys.exit()
    else:
        base_load_id = load_ids[0][1]
        
    # place load at user specified bus, this is the constant power pulsating load component
    ierr = psspy.load_data_6(
        LDDL_bus_number,
        'LL',
        [val_i,val_i,val_i,val_i,val_i,val_i,val_i],
        [1,_f,_f,_f,_f,_f,_f,_f],          
        ""
        )
    if ierr != 0:
        print("Cannot add load at specified bus")
        sys.exit()
    
    ### Reading sav file
    psspy.dyre_new([1,1,1,1], dyrFile, "","","")
    if Load_model_type == 'ZIP':
        edit_dyr('ZIP_load_.dyr',LDDL_bus_number,base_load_id)
        psspy.dyre_add([val_i,val_i,val_i,val_i], dyrFile_ZIP, "","")
    else:
        edit_dyr('CMLD_load_.dyr',LDDL_bus_number,base_load_id)
        psspy.dyre_add([val_i,val_i,val_i,val_i], dyrFile_CMLD, "","")
    
    initialize_dynamic_simulation()
    set_up_channels(cfg)
    
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
    psspy.strt_2([1, 0],outFile)
    
    ### Initial flat run till eventStartTime
    psspy.run(0, LDDL_var_ST, n_prt, n_out_channel, n_CRT_PLT) ## flat run till LDDL_var_ST s
    T_stop = LDDL_var_ST ## saving stop time 
    
    ### Starting the triangular wave load variation and repeating for Num_total_LDDL_cycles
    # delta_ramp_change_time = Delta_t_simulation*6
    ramp_change_ON_time = Up_time_in_1_TP
    num_steps_to_impl_ramp_change = 25
    single_delta_ramp_step_time = ramp_change_ON_time/num_steps_to_impl_ramp_change

    for load_var_cycles in range(0, Num_total_LDDL_cycles): # for each time period of triangular load var
        for delta_ramp_change_period_num in range(1,num_steps_to_impl_ramp_change+1):
            psspy.load_chng_6(LDDL_bus_number, 'LL',[val_i,val_i,val_i,val_i,val_i,val_i,val_i],[ LDDL_var_ampli*(delta_ramp_change_period_num/num_steps_to_impl_ramp_change) , 0 ,  _f ,_f, _f,_f,_f,_f],"") ## real number array 
            T_stop = T_stop + (single_delta_ramp_step_time ) ### 
            psspy.run(0, T_stop, n_prt, n_out_channel, n_CRT_PLT)
            
        for delta_ramp_change_period_num in range(1,num_steps_to_impl_ramp_change+1):
            psspy.load_chng_6(LDDL_bus_number, 'LL',[val_i,val_i,val_i,val_i,val_i,val_i,val_i],[ LDDL_var_ampli -  LDDL_var_ampli*(delta_ramp_change_period_num/num_steps_to_impl_ramp_change) , 0 ,_f ,_f,  _f,_f,_f,_f],"") ## real number array 
            T_stop = T_stop + (single_delta_ramp_step_time ) ### 
            psspy.run(0, T_stop, n_prt, n_out_channel, n_CRT_PLT)
                
    ## Running without load variation for remaining time
    psspy.run(0, Tot_sim_time, n_prt, n_out_channel, n_CRT_PLT)
    df = export_sim_to_csv(outFile,csvFile)
    return(df)