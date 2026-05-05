"""
Modify existing HV bus load to a LEL load 
connected to a MV bus 
This code adds step down transformer, moves the HV load to MV bus
and a oscillation injection block (const P load periodically varied with Python script)
"""

from pathlib import Path
import os
import sys

from psse_config import configure_psse
psse_version = 35
psspy_version = 311
psspy = configure_psse(psse_version, psspy_version)


# =============================================================================
# INPUT
# =============================================================================
def edit_dyr(dyr_filename, lddl_bus, base_load_id):
    # Modify existing load connected to LDDL bus to represent data center dynamics
    # LDDL represented as a composite load with composition matching the NERC LL survey
    from pathlib import Path
    lddl_bus = str(lddl_bus)

    # Path to your DYR file
    dyr_file = Path.cwd()/dyr_filename

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

def add_ll_at_bus(sav_case, dyr_case, bus_number, load_id, csvpath, dyr_file = 'CMLD_Load_.dyr'):
    
    
    psspy.psseinit(200000) 

    _i = psspy.getdefaultint()
    _f = psspy.getdefaultreal()
    _s = psspy.getdefaultchar()

    psspy.case(sav_case)  ## Load powerflow case 
    
    # if any idv files are needed
    # psspy.runrspnsfile('23HW3ap_gnet.idv')
    # psspy.runrspnsfile('23HW3ap_dera_changes.idv')
    # psspy.runrspnsfile('23HW3ap_composite_load_changes.idv')

    savFile = csvpath / 'LLmod.sav' 
    snpFile = csvpath / 'LLmod.snp' 
    
    # Original bus at which LDDL is present
    old_bus = bus_number
    # if no load id provided by user, choose largest load at bus to modify
    
    
    
    if load_id==0:
        ierr, (bus_nums,) = psspy.aloadint(-1, 1, ['NUMBER'])
        ierr, load_ids = psspy.aloadchar(-1,1, 'ID')
        ierr, (mva_values,) = psspy.aloadreal(-1,1, ['TOTALACT'])
        if ierr == 0:
            # Filter to only loads at the target bus
            df = pd.DataFrame({
            'bus': bus_nums,
            'id': load_ids[0],
            'mva': mva_values
            })
       
        bus_loads = df[df['bus'] == bus_number]
        if len(bus_loads)>0:
            largest = bus_loads.loc[bus_loads['mva'].idxmax()]
            old_id = str(largest.id)
            print(old_id)
            
        else:
            print("No loads found at bus or error occurred.")
            sys.exit()
    else:
        old_id = load_id

    # New load bus
    new_bus = old_bus*10+1
    new_id = "ll"
    

    ierr, load_rating = psspy.loddt2(bus_number, old_id ,'TOTAL', 'ACT')
    
    # Transformer parameters
    n_transformers = 1
    r_pu = [0] * n_transformers
    x_pu = [0.08] * n_transformers
    
    
    xfmr_base = [abs(load_rating)*1.25/n_transformers] * n_transformers ## Transformer MVA is taken to be 1.25 * load MVA
    

    
    # Shunt options
    hv_shunt_flag = 0   #flag to set shunt at high kV original bus then input 1 otherwise 0
    lv_shunt_flag = 0   #flag to set shunt at low kV original bus then input 1 otherwise 0
    shunt_hv_MW = 0  ## Shunt G value at high kV bus
    shunt_lv_MW = 0   ## Shunt G value at low kV bus
    shunt_hv_MVAR = 5.0   ## Shunt B value at high kV bus 
    shunt_lv_MVAR = 15.0  ## Shunt B value at low kV bus

    #Add new bus
    ierr = psspy.bus_data_4(new_bus,0,[1,_i,_i,_i],[34.5, 1.0,0.0, 1.1, 0.9, 1.1, 0.9],"LLmod")
    
    # Add transformer(s)
    for i in range(n_transformers):
        xfmr_id = str(i+1)
        psspy.two_winding_data_6(old_bus,new_bus,xfmr_id,[1,new_bus,_i,0,0,0,33,0,new_bus,0,0,1,0,1,1,1],[0,x_pu[i],xfmr_base[i],1.0,0.0,0.0, 1.0,0.0, 1.0, 1.0, 1.0, 1.0,0.0,0.0, 1.1, 0.9, 1.1, 0.9,0.0,0.0,0.0])
    
    # Add Loads
    ierr = psspy.moveload(old_bus, str(old_id), new_bus, new_id) #move load at HV bus to MV
    load_buses = [new_bus]
    psspy.bsys(1,0,[0.0,0.0],0,[],len(load_buses),load_buses,0,[],0,[])
    
    ierr, xarray = psspy.aloadcplx(1, 1, 'TOTALACT')
    
    Pload = xarray[0][0].real
    Qload = xarray[0][0].imag
    denom = Pload*Pload + Qload*Qload
    PF = Pload/(denom**0.5)
    
    if PF < 0.99:  #If powerfactor is less than 0.99 then powerfactor is adjusted by adjusting qload
        qnew = (((Pload/0.99)**2 - Pload**2)**0.5 ) 
        psspy.load_chng_5(new_bus, 'll' ,[_i,_i,_i,_i,_i,_i,_i],[ _f ,qnew, _f , _f ,  _f,_f,_f,_f])
    
    # Add oscillation injection block
    ierr = psspy.load_data_5(
        new_bus,
        'os',
        [_i,_i,_i,_i,_i,_i,_i],
        [0,_f,_f,_f,_f,_f,_f,_f]
        )

    ## Add shunts (if needed)
    
    if hv_shunt_flag == 1:
        psspy.shunt_data(old_bus,r"""1""",1,[shunt_hv_MW,shunt_hv_MVAR])
    
    if lv_shunt_flag == 1:
        psspy.shunt_data(new_bus,r"""1""",1,[shunt_lv_MW,shunt_lv_MVAR])    
    
     
    ### Solve and Saving the modified Power flow case
    psspy.rsol([1,0,0,0,0,0,0,0,0,1],[ 500.0, 5.0])
    psspy.fnsl([1,1,1,1,1,0,0,0])  ## solves the powerflow
    psspy.cong(0)
    psspy.ordr(0)
    psspy.fact()
    psspy.tysl(0)
    ierr = psspy.save(str(savFile))
    

    
    
    edit_dyr(dyr_file, bus_number, 'll') 
    psspy.dyre_new([1,1,1,1], dyr_case, "","","")
    val_i = psspy.getdefaultint()
    psspy.dyre_add([val_i,val_i,val_i,val_i], dyr_file, "","")
    psspy.snap([-1,-1,-1,-1,-1], str(snpFile))
    psspy.dynamicsmode(1)


if __name__ == '__main__':
    import pandas as pd
    root = Path.cwd()
    data_dir = root/"Processing"
    config_params = pd.read_csv(root/"simulation_config.csv")
    bus_number = int(config_params[config_params.Variable=='bus_number']['Value'].iloc[0])
    case = (config_params[config_params.Variable=='case_name']['Value'].iloc[0])
    sav_case1 = case+'.sav'
    dyr_name_val = config_params[config_params.Variable=='dyr_name']['Value'].iloc[0]
    # Append .dyr extension if not already present
    dyr_case1 = dyr_name_val if str(dyr_name_val).endswith('.dyr') else dyr_name_val + '.dyr'
    sav_case = root/"PSSE_Cases"/sav_case1
    dyr_case = root/"PSSE_Cases"/dyr_case1
    load_id = config_params[config_params.Variable=='load_id']['Value'].iloc[0]
    if str(load_id).lower() == "nan":
        load_id2 = 0
    else:
        load_id2 = load_id
    
    print(load_id2)
    print(bus_number)
    add_ll_at_bus(str(sav_case), str(dyr_case), bus_number, load_id2,  data_dir, 'CMLD_Load_.dyr')
