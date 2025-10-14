## File containing functions for three types of variations for LDDLs - monoperiodic, biperiodic and triangular
import os, sys
import timeit
import numpy as np


def LDDL_MonoPeriodic_Load_Var(cfg, LDDL_bus):
    
    sys.path.append(r"C:\Program Files\PTI\PSSE35\35.6\PSSPY311")
    sys.path.append(r"C:\Program Files\PTI\PSSE35\35.6\PSSBIN")
    os.environ['PATH'] += ';' + r"C:\Program Files\PTI\PSSE35\35.6\PSSBIN"

    import psse35
    import psspy
    
    Output_File_Name_Str = str(LDDL_bus)
   
    local_dir = os.getcwd() ## finding current working directory
    sys.path.append(local_dir)
    os.environ['PATH'] += ';' + local_dir
    
    
    psspy.psseinit(10000)
    _i = psspy.getdefaultint()
    _f = psspy.getdefaultreal()
    _s = psspy.getdefaultchar()
    
    ## Unpacking simulation parameters from cfg
    Load_model_type = cfg.load_model.model_type
    LDDL_var_ampli = cfg.load_model.total_load_MW
    LDDL_bus_numbers = cfg.load_model.load_bus_numbers
    LDDL_bus_number = LDDL_bus_numbers[0]
    LDDL_bus_IDs =cfg.load_model.load_bus_ids
    LDDL_bus_ID = LDDL_bus_IDs[0]
    CWD = cfg.system.cwd
    Freq_LDDL_var = cfg.load_variation.freq_primary_hz ## Frequency of square wave variation of LDDL
    LDDL_var_ST = cfg.load_variation.start_time_s ## start time of LDDL load variation in simulation
    Tot_sim_time = cfg.load_variation.sim_run_time_s
    ## Calculating other simulation variables
    TP_LDDL_var = 1/Freq_LDDL_var ## time period of individual cycles of square wave variation
    Up_time_in_1_TP = TP_LDDL_var/2 ## symmetric sw variation
    Down_time_in_1_TP = TP_LDDL_var/2 ## symmetric sw variation
    
    Num_total_LDDL_cycles = int((Tot_sim_time - LDDL_var_ST)/TP_LDDL_var) ## total LDDL time periods that can be completed
    Rem_time = (Tot_sim_time - LDDL_var_ST - (Num_total_LDDL_cycles*TP_LDDL_var) ) ## time left in simulation
    

    ## Setting the PSSS/E input raw, dyr files
    PSSE_files_dir = cfg.viz.case_file_location
    OUTPUT_Folder = cfg.files.output_file_location
    rawFile = PSSE_files_dir + '\\' + str(cfg.files.raw_file)
    dyrFile = PSSE_files_dir + '\\' + str(cfg.files.dyr_file)
    ## Setting the PSS/E output out and csv files based on cfg input
    outFile = OUTPUT_Folder + '\\' + 'LDDL_'+ str(Output_File_Name_Str)+'.out' 
    csvFile = OUTPUT_Folder + '\\' + 'LDDL_'+ str(Output_File_Name_Str)+'.csv' 
    
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
    
    
    ## Setting PSS/E simulation parameters for the dynamic simulation
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
    psspy.run(0, LDDL_var_ST, n_prt, n_out_channel, n_CRT_PLT) ## flat run till LDDL_var_ST s
    T_stop = LDDL_var_ST ## saving stop time 
    
    ## Identifies the nominal load in "load_bus_number" and saves as "Base_PIload_value"
    [ierr, TS_Load_bus_Nums] = psspy.aloadint(sid = -1, flag = 1, string = 'NUMBER')
    [ierr, TS_Load_bus_IDs] = psspy.aloadchar(sid = -1, flag = 1, string = 'ID')
    [ierr, S_nominal_p] = psspy.aloadcplx(sid = -1, flag = 1, string = 'ILACT') ## ILNOM
    
    # Find index where both match
    idx = next(
        (i for i, (num, bid) in enumerate(zip(TS_Load_bus_Nums[0], TS_Load_bus_IDs[0]))
         if num == LDDL_bus_number and bid == LDDL_bus_ID),
        None  # default if not found
    )

    Load_bus_index_in_load_arrays = TS_Load_bus_Nums[0].index(LDDL_bus_number) ## Identifying the index of LDDL_bus_number  among PSSE load bus num list
    Base_PIload_value = S_nominal_p[0][Load_bus_index_in_load_arrays].real ## Calculating the basecase active power load value for LDDL_bus_number
    
    
    ### Starting the square wave load variation and repeating for Num_total_LDDL_cycles
    for load_var_cycles in range(0, Num_total_LDDL_cycles): # the load variation is repeated "num_period_of_load_var" times
        
        psspy.load_chng_6(LDDL_bus_number, LDDL_bus_ID ,[_i,_i,_i,_i,_i,_i,_i],[  _f ,_f ,Base_PIload_value + LDDL_var_ampli  , 0, _f,_f,_f,_f],"") ## for the first half of this time period load value is increased to "Base_PIload_value + LDDL_var_ampli " 
        T_stop = T_stop + Up_time_in_1_TP ### Increased load value will be present for "Up_time_load_var_in_s"
        psspy.run(0, T_stop, n_prt, n_out_channel, n_CRT_PLT) ## 

        psspy.load_chng_6(LDDL_bus_number, LDDL_bus_ID ,[_i,_i,_i,_i,_i,_i,_i],[ _f ,_f, Base_PIload_value , 0 ,  _f,_f,_f,_f],"") ## for the second half of this load variation period, the value of the load is decreased to "Base_PIload_value"
        T_stop = T_stop + Down_time_in_1_TP  ### Reduced load value will be present for "Down_time_load_var_in_s"
        psspy.run(0, T_stop, n_prt, n_out_channel, n_CRT_PLT)
        
        
    ## Running without load variation for remaining time
    psspy.run(0, Tot_sim_time, n_prt, n_out_channel, n_CRT_PLT)
    
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
    return(df)



def LDDL_BiPeriodic_Load_Var(cfg, LDDL_bus):
    
    sys.path.append(r"C:\Program Files\PTI\PSSE35\35.6\PSSPY311")
    sys.path.append(r"C:\Program Files\PTI\PSSE35\35.6\PSSBIN")
    os.environ['PATH'] += ';' + r"C:\Program Files\PTI\PSSE35\35.6\PSSBIN"

    import psse35
    import psspy
    
    Output_File_Name_Str = str(LDDL_bus)
    
    local_dir = os.getcwd() ## finding current working directory
    sys.path.append(local_dir)
    os.environ['PATH'] += ';' + local_dir
    
    
    psspy.psseinit(10000)
    _i = psspy.getdefaultint()
    _f = psspy.getdefaultreal()
    _s = psspy.getdefaultchar()
    
    ## Unpacking simulation parameters from cfg
    Load_model_type = cfg.load_model.model_type
    LDDL_var_ampli = cfg.load_model.total_load_MW
    
    LDDL_bus_numbers = cfg.load_model.load_bus_numbers
    LDDL_bus_number = LDDL_bus_numbers[0]
    LDDL_bus_IDs =cfg.load_model.load_bus_ids
    LDDL_bus_ID = LDDL_bus_IDs[0]
    CWD = cfg.system.cwd
    Freq_LDDL_var_prime = cfg.load_variation.freq_primary_hz ## Frequency of square wave variation of LDDL
    Freq_LDDL_var_secondary = cfg.load_variation.freq_secondary_hz
    LDDL_var_ST = cfg.load_variation.start_time_s ## start time of LDDL load variation in simulation
    Tot_sim_time = cfg.load_variation.sim_run_time_s
    
    ## Calculating other simulation variables
    TP_LDDL_var_prime = 1/Freq_LDDL_var_prime ## time period of individual cycles of bi periodic 
    Up_time_in_1_TP_prime = TP_LDDL_var_prime/2 ## symmetric 
    Down_time_in_1_TP_prime = TP_LDDL_var_prime/2 ## symmetric 
    TP_LDDL_var_secondary = 1/Freq_LDDL_var_secondary
    Up_time_in_1_TP_secondary = TP_LDDL_var_secondary/2 ## symmetric 
    Down_time_in_1_TP_secondary = TP_LDDL_var_secondary/2 ## symmetric 
    Num_total_LDDL_cycles = int((Tot_sim_time - LDDL_var_ST)/TP_LDDL_var_prime) ## total LDDL time periods that can be completed
    Num_fast_cycles = int((TP_LDDL_var_prime/TP_LDDL_var_secondary)/2) ## within up part of the slow LDDL period
    Rem_time = (Tot_sim_time - LDDL_var_ST - (Num_total_LDDL_cycles*TP_LDDL_var_prime) ) ## time left in simulation
    


    ## Setting the PSSS/E input raw, dyr files
    PSSE_files_dir = cfg.viz.case_file_location
    OUTPUT_Folder = cfg.files.output_file_location
    rawFile = PSSE_files_dir + '\\' + str(cfg.files.raw_file)
    dyrFile = PSSE_files_dir + '\\' + str(cfg.files.dyr_file)
    ## Setting the PSS/E output out and csv files based on cfg input
    outFile = OUTPUT_Folder + '\\' + 'LDDL_'+ str(Output_File_Name_Str)+'.out' 
    csvFile = OUTPUT_Folder + '\\' + 'LDDL_'+ str(Output_File_Name_Str)+'.csv' 
    
    
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
    

    ## Setting PSS/E simulation parameters for the dynamic simulation
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
    psspy.run(0, LDDL_var_ST, n_prt, n_out_channel, n_CRT_PLT) ## flat run till LDDL_var_ST s
    T_stop = LDDL_var_ST ## saving stop time 
    
    ## Identifies the nominal load in "load_bus_number" and saves as "Base_PIload_value"
    [ierr, TS_Load_bus_Nums] = psspy.aloadint(sid = -1, flag = 1, string = 'NUMBER')
    [ierr, TS_Load_bus_IDs] = psspy.aloadchar(sid = -1, flag = 1, string = 'ID')
    [ierr, S_nominal_p] = psspy.aloadcplx(sid = -1, flag = 1, string = 'ILACT') ## ILNOM
    
    # Find index where both match
    idx = next(
        (i for i, (num, bid) in enumerate(zip(TS_Load_bus_Nums[0], TS_Load_bus_IDs[0]))
         if num == LDDL_bus_number and bid == LDDL_bus_ID),
        None  # default if not found
    )


    Load_bus_index_in_load_arrays = TS_Load_bus_Nums[0].index(LDDL_bus_number) ## Identifying the index of LDDL_bus_number  among PSSE load bus num list
    Base_PIload_value = S_nominal_p[0][Load_bus_index_in_load_arrays].real ## Calculating the basecase active power load value for LDDL_bus_number
    
    
    ## TP_LDDL_var_prime
    
    for load_var_cycles in range(0, Num_total_LDDL_cycles): # pulsing load changes
        
        for fast_load_var_iter in range(0,Num_fast_cycles):
            psspy.load_chng_6(LDDL_bus_number, LDDL_bus_ID,[_i,_i,_i,_i,_i,_i,_i],[ Base_PIload_value + 0 + LDDL_var_ampli  , 0 ,  _f ,_f, _f,_f,_f,_f],"") ## real number array 
            T_stop = T_stop + Up_time_in_1_TP_secondary ### 
            psspy.run(0, T_stop, n_prt, n_out_channel, n_CRT_PLT)
            
            
            psspy.load_chng_6(LDDL_bus_number, LDDL_bus_ID ,[_i,_i,_i,_i,_i,_i,_i],[ Base_PIload_value , 0 ,_f ,_f,  _f,_f,_f,_f],"") ## real number array 
            T_stop = T_stop + Down_time_in_1_TP_secondary ### 
            psspy.run(0, T_stop, n_prt, n_out_channel, n_CRT_PLT)
    
        psspy.load_chng_6(LDDL_bus_number, LDDL_bus_ID ,[_i,_i,_i,_i,_i,_i,_i],[ Base_PIload_value , 0 , _f ,_f, _f,_f,_f,_f],"") ## real number array 
        T_stop = T_stop + Down_time_in_1_TP_prime ### 
        psspy.run(0, T_stop, n_prt, n_out_channel, n_CRT_PLT)
        
        
    ## Running without load variation for remaining time
    psspy.run(0, Tot_sim_time, n_prt, n_out_channel, n_CRT_PLT)
    
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
    return(df)    


def LDDL_Tria_Load_Var(cfg, LDDL_bus): ## Function to Emulate Triangular Load Variation
    
    sys.path.append(r"C:\Program Files\PTI\PSSE35\35.6\PSSPY311")
    sys.path.append(r"C:\Program Files\PTI\PSSE35\35.6\PSSBIN")
    os.environ['PATH'] += ';' + r"C:\Program Files\PTI\PSSE35\35.6\PSSBIN"

    import psse35
    import psspy
    
    
    Output_File_Name_Str = str(LDDL_bus)
    
    local_dir = os.getcwd() ## finding current working directory
    sys.path.append(local_dir)
    os.environ['PATH'] += ';' + local_dir
    
    
    psspy.psseinit(10000)
    _i = psspy.getdefaultint()
    _f = psspy.getdefaultreal()
    _s = psspy.getdefaultchar()
    
    ## Unpacking simulation parameters from cfg
    Load_model_type = cfg.load_model.model_type
    LDDL_var_ampli = cfg.load_model.total_load_MW
    
    LDDL_bus_numbers = cfg.load_model.load_bus_numbers
    LDDL_bus_number = LDDL_bus_numbers[0]
    LDDL_bus_IDs =cfg.load_model.load_bus_ids
    LDDL_bus_ID = LDDL_bus_IDs[0]
    
    CWD = cfg.system.cwd
    
    Freq_LDDL_var = cfg.load_variation.freq_primary_hz ## Frequency of square wave variation of LDDL
    LDDL_var_ST = cfg.load_variation.start_time_s ## start time of LDDL load variation in simulation
    Tot_sim_time = cfg.load_variation.sim_run_time_s
    
    ## Calculating other simulation variables
    TP_LDDL_var = 1/Freq_LDDL_var ## time period of individual cycles of square wave variation
    Up_time_in_1_TP = TP_LDDL_var/2 ## symmetric sw variation
    Down_time_in_1_TP = TP_LDDL_var/2 ## symmetric sw variation
    
    Num_total_LDDL_cycles = int((Tot_sim_time - LDDL_var_ST)/TP_LDDL_var) ## total LDDL time periods that can be completed
    Rem_time = (Tot_sim_time - LDDL_var_ST - (Num_total_LDDL_cycles*TP_LDDL_var) ) ## time left in simulation
    


    ## Setting the PSSS/E input raw, dyr files
    PSSE_files_dir = cfg.viz.case_file_location
    OUTPUT_Folder = cfg.files.output_file_location
    rawFile = PSSE_files_dir + '\\' + str(cfg.files.raw_file)
    dyrFile = PSSE_files_dir + '\\' + str(cfg.files.dyr_file)
    ## Setting the PSS/E output out and csv files based on cfg input
    outFile = OUTPUT_Folder + '\\' + 'LDDL_'+ str(Output_File_Name_Str)+'.out' 
    csvFile = OUTPUT_Folder + '\\' + 'LDDL_'+ str(Output_File_Name_Str)+'.csv' 
    
    
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
    

    ## Setting PSS/E simulation parameters for the dynamic simulation
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
    psspy.run(0, LDDL_var_ST, n_prt, n_out_channel, n_CRT_PLT) ## flat run till LDDL_var_ST s
    T_stop = LDDL_var_ST ## saving stop time 
    
    ## Identifies the nominal load in "load_bus_number" and saves as "Base_PIload_value"
    [ierr, TS_Load_bus_Nums] = psspy.aloadint(sid = -1, flag = 1, string = 'NUMBER')
    [ierr, TS_Load_bus_IDs] = psspy.aloadchar(sid = -1, flag = 1, string = 'ID')
    [ierr, S_nominal_p] = psspy.aloadcplx(sid = -1, flag = 1, string = 'ILACT') ## ILNOM
    
    # Find index where both match
    idx = next(
        (i for i, (num, bid) in enumerate(zip(TS_Load_bus_Nums[0], TS_Load_bus_IDs[0]))
         if num == LDDL_bus_number and bid == LDDL_bus_ID),
        None  # default if not found
    )


    Load_bus_index_in_load_arrays = TS_Load_bus_Nums[0].index(LDDL_bus_number) ## Identifying the index of LDDL_bus_number  among PSSE load bus num list
    Base_PIload_value = S_nominal_p[0][Load_bus_index_in_load_arrays].real ## Calculating the basecase active power load value for LDDL_bus_number
    
    
    
    ### Starting the triangular wave load variation and repeating for Num_total_LDDL_cycles
    delta_ramp_change_time = Delta_t_simulation*6

    ramp_change_ON_time = Up_time_in_1_TP
    num_steps_to_impl_ramp_change = 25
    single_delta_ramp_step_time = ramp_change_ON_time/num_steps_to_impl_ramp_change


    for load_var_cycles in range(0, Num_total_LDDL_cycles): # for each time period of triangular load var
        for delta_ramp_change_period_num in range(1,num_steps_to_impl_ramp_change+1):
            psspy.load_chng_6(LDDL_bus_number, LDDL_bus_ID,[_i,_i,_i,_i,_i,_i,_i],[ Base_PIload_value + LDDL_var_ampli*(delta_ramp_change_period_num/num_steps_to_impl_ramp_change) , 0 ,  _f ,_f, _f,_f,_f,_f],"") ## real number array 
            T_stop = T_stop + (single_delta_ramp_step_time ) ### 
            psspy.run(0, T_stop, n_prt, n_out_channel, n_CRT_PLT)
            
        for delta_ramp_change_period_num in range(1,num_steps_to_impl_ramp_change+1):
            psspy.load_chng_6(LDDL_bus_number, LDDL_bus_ID,[_i,_i,_i,_i,_i,_i,_i],[ Base_PIload_value + LDDL_var_ampli -  LDDL_var_ampli*(delta_ramp_change_period_num/num_steps_to_impl_ramp_change) , 0 ,_f ,_f,  _f,_f,_f,_f],"") ## real number array 
            T_stop = T_stop + (single_delta_ramp_step_time ) ### 
            psspy.run(0, T_stop, n_prt, n_out_channel, n_CRT_PLT)
                
    ## Running without load variation for remaining time
    psspy.run(0, Tot_sim_time, n_prt, n_out_channel, n_CRT_PLT)
    
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
    return(df)