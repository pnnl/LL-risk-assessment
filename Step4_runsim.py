# -*- coding: utf-8 -*-
"""
Step4_runsim.py
================
Runs the forced-oscillation dynamic simulation.
Reads all settings from simulation_config.csv.

Outputs (written to results/):
  <bus>_sim.out   — PSS/E binary channel output
  <bus>_sim.csv   — exported time-series channel data

Supported oscillation shapes
-----------------------------
  square      : monoperiodic square wave at oscillation_frequency
  biperiodic  : fast inner square wave (oscillation_frequency_inner) modulated
                by a slow outer burst envelope (oscillation_frequency)
"""

import os, sys, time
import pandas as pd 
from pathlib import Path


from psse_config import configure_psse
psse_version = 35
psspy_version = 311
psspy = configure_psse(psse_version, psspy_version)


def initialize_dynamic_simulation(PF_file, dynamic_file):
    ### Initializing the dynamic simulation
    
    psspy.addmodellibrary(r"""gewt.dll""")
    psspy.time(0)
    psspy.case(PF_file)
    psspy.rstr(dynamic_file)
    psspy.powerflowmode()
    psspy.fact()
    psspy.tysl(0)
    psspy.dynamicsmode(0)
    psspy.delete_all_plot_channels()
    # psspy.text(r""" IDEV 'addChan3.idv'""")
    return()

def identify_channels(bus):
    # which channels to record
    data_dir = Path.cwd()/"Processing"
    csv_file_bus = data_dir/"monitored_buses.csv"
    csv_file_gen = data_dir/"monitored_generators.csv"
    csv_file_load = data_dir/"monitored_loads.csv"
    csv_file_line = data_dir/"monitored_lines.csv"
    
    ## Bus Channel Identification
    bus_data = pd.read_csv(csv_file_bus)
    Only_bus_list = bus_data['BUS_NUM'].tolist()
    bus_name_list  = bus_data['NAME'].tolist()

    ## Gen Channel Identification - (Plant Level) 
    gen_data = pd.read_csv(csv_file_gen)
    gen_bus_list = gen_data['BUS_NUM'].tolist()

    ## Load Channel Identification
    load_data = pd.read_csv(csv_file_load)
    load_bus_list = load_data['BUS_NUM'].tolist()

    ## Start of Line Flows Identification
    line_data = pd.read_csv(csv_file_line)
    line_frombus_list = line_data['FROM_BUS'].tolist()
    line_tobus_list = line_data['TO_BUS'].tolist()
    line_id_list  = line_data['CKT'].tolist()
    
    return (Only_bus_list, bus_name_list, gen_bus_list, load_bus_list, line_frombus_list, line_tobus_list,line_id_list)

def gen_channels (gen_buses):
    # Subsystem(4) defined to extract generation related channels
    psspy.bsys(4,0,[0.0,0.0],0,[],len(gen_buses),gen_buses,0,[],0,[])
    psspy.chsb(4,0,[-1,-1,-1,1,2,0]) #Pgen
    psspy.chsb(4,0,[-1,-1,-1,1,4,0]) #Terminal Voltages
    psspy.chsb(4,0,[-1,-1,-1,1,3,0]) #Qgen
    psspy.chsb(4,0,[-1,-1,-1,1,1,0]) #Angle
    return()

def load_channels(load_buses):
    # Subsystem(5) defined to extract load related channels
    psspy.bsys(5,0,[0.0,0.0],0,[],len(load_buses),load_buses,0,[],0,[])
    psspy.chsb(5,0,[-1,-1,-1,1,25,0])  #Pload
    psspy.chsb(5,0,[-1,-1,-1,1,13,0])  #Voltage magnitude    
    return()

def bus_channels(Only_buses):
    # Subsystem(6) defined to extract buses of interest related channels
    psspy.bsys(6,0,[0.0,0.0],0,[],len(Only_buses),Only_buses,0,[],0,[])
    psspy.chsb(6,0,[-1,-1,-1,1,14,0]) #Voltage magnitude and angle
    return()

def line_channels(Only_Frombuses,Only_Tobuses,line_id_list):
    # Subsystem(7) defined to extract lines related channels 

    psspy.bsys(7,0,[0.0,0.0],0,[],len(Only_Frombuses),Only_Frombuses,0,[],0,[])
    psspy.chsb(7,0,[-1,-1,-1,1,13,0]) #Voltage magnitude at From end buses
    psspy.bsys(8,0,[0.0,0.0],0,[],len(Only_Tobuses),Only_Tobuses,0,[],0,[])
    psspy.chsb(8,0,[-1,-1,-1,1,13,0])  #Voltage magnitude at To end buses

    for i in range(len(Only_Frombuses)):
        n1  = Only_Frombuses[i]
        n2  = Only_Tobuses[i]
        ID = str(line_id_list[i])

        ch_name = "Line_{0}_{1}_{2}_P".format(n1,n2,ID)
        ch_name1 = "Line_{0}_{1}_{2}_Q".format(n1,n2,ID)

        ierr = psspy.branch_p_and_q_channel( [-1, -1,-1, n1,n2], ID, [ch_name,ch_name1])
        print(ierr)
        if ierr != 0:
            print ("Warning: Channel creation failed for Line", n1, " and ",  n2, "ID", ID)
    
    return()

def LDDL_channels(bus):
    ### Channels at the newly added LDDL bus
    LDDL_bus_number=bus*10+1
    ierr = psspy.load_array_channel([-1,1, LDDL_bus_number], 'LL', 'LDDL P')
    ierr = psspy.load_array_channel([-1,2, LDDL_bus_number], 'LL', 'LDDL Q')
    ierr = psspy.load_array_channel([-1,1, LDDL_bus_number], 'OS', 'LDDL OS P')
    ierr = psspy.load_array_channel([-1,2, LDDL_bus_number], 'OS', 'LDDL OS Q')
    ierr = psspy.voltage_channel([-1,-1,-1,LDDL_bus_number], 'LDDL Bus Voltage')
    ierr = psspy.bus_frequency_channel([-1,LDDL_bus_number], 'LDDL Bus Frequency') 
    return()
     

def export_sim_to_csv (outFile, csvFile):
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
    return()


# ═══════════════════════════════════════════════════════════════════════════
# LOAD STEP SEQUENCE GENERATORS
# Each function yields (load_MW, hold_seconds) tuples that describe the
# complete oscillation waveform.  run_simulation() iterates these tuples
# and issues all psspy.load_chng_6 / psspy.run calls — so PSS/E setup
# never needs to be duplicated across shapes.
# ═══════════════════════════════════════════════════════════════════════════

def _square_steps(freq, MW, num_cycles=8, duty=0.5):
    """
    Monoperiodic square wave.
    Yields (load_MW, hold_seconds) for each half-cycle.

    Parameters
    ----------
    freq       : float  oscillation frequency (Hz)
    MW         : float  peak load amplitude (MW)
    num_cycles : int    number of complete on/off cycles
    duty       : float  fraction of each period where load is ON (default 0.5)
    """
    period    = 1.0 / freq
    up_time   = period * duty
    down_time = period * (1.0 - duty)
    for _ in range(num_cycles):
        yield MW, up_time
        yield 0,  down_time


def _biperiodic_steps(freq_outer, freq_inner, MW, num_cycles=8, duty=0.5):
    """
    Biperiodic (burst) square wave.

    Each outer cycle consists of:
      - a burst-ON window  : rapid inner toggling between MW and 0
      - a burst-OFF window : load held at 0 (silence)

    Parameters
    ----------
    freq_outer : float  outer burst envelope frequency (Hz)
    freq_inner : float  inner toggling frequency inside each burst (Hz)
    MW         : float  peak load amplitude (MW)
    num_cycles : int    number of complete outer envelope cycles
    duty       : float  fraction of each outer period that is burst-ON (default 0.5)
    """
    outer_period = 1.0 / freq_outer
    burst_on     = outer_period * duty           # duration of fast-toggle window
    burst_off    = outer_period * (1.0 - duty)   # duration of silent window

    inner_period = 1.0 / freq_inner
    inner_up     = inner_period * 0.5
    inner_down   = inner_period * 0.5
    # number of complete inner cycles that fit inside the burst-ON window
    inner_cycles = max(1, int(burst_on / inner_period))

    for _ in range(num_cycles):
        # burst-ON: rapid inner square wave
        for _ in range(inner_cycles):
            yield MW, inner_up
            yield 0,  inner_down
        # burst-OFF: zero
        yield 0, burst_off


# ═══════════════════════════════════════════════════════════════════════════
# SINGLE SIMULATION FUNCTION
# All PSS/E initialisation, channel setup, and solver settings live here.
# The load-stepping loop at the bottom is shape-agnostic — it just iterates
# whatever step sequence the generator above produced.
# ═══════════════════════════════════════════════════════════════════════════

def run_simulation(bus, shape, freq, MW, freq_inner=None):
    """
    Run a PSS/E dynamic simulation with the requested oscillation shape.

    Parameters
    ----------
    bus        : int    source bus number
    shape      : str    'square' or 'biperiodic'
    freq       : float  oscillation frequency (Hz) — outer envelope for biperiodic
    MW         : float  peak oscillation amplitude (MW)
    freq_inner : float  inner toggling frequency (Hz), required for biperiodic only
    """
    PF_file      = "LLmod.sav"
    dynamic_file = str(Path.cwd() / "LLmod.snp")

    op_dir  = Path.cwd() / "results"
    op_dir.mkdir(exist_ok=True)
    outFile = str(op_dir / f"{bus}_{freq}_Hz_{MW}MW_sim.out")
    csvFile = str(op_dir / f"{bus}_{freq}_Hz_{MW}MW_sim.csv")

    LDDL_var_ST     = 1    # load variation start time (seconds)
    LDDL_bus_number = bus * 10 + 1

    # ── Build the step sequence for the chosen shape ──────────────────────
    shape = shape.lower()
    if shape == 'square':
        steps = list(_square_steps(freq, MW))

    elif shape == 'biperiodic':
        if freq_inner is None:
            raise ValueError(
                "oscillation_shape 'biperiodic' requires "
                "'oscillation_frequency_inner' to be set in simulation_config.csv.")
        if freq_inner <= freq:
            raise ValueError(
                f"oscillation_frequency_inner ({freq_inner} Hz) must be greater "
                f"than oscillation_frequency ({freq} Hz).")
        steps = list(_biperiodic_steps(freq, freq_inner, MW))

    else:
        raise ValueError(
            f"oscillation_shape '{shape}' not recognised. "
            "Supported values: 'square', 'biperiodic'.")

    # ── PSS/E initialisation (identical for all shapes) ───────────────────
    psspy.psseinit(200000)

    _i = psspy.getdefaultint()
    _f = psspy.getdefaultreal()
    _s = psspy.getdefaultchar()

    initialize_dynamic_simulation(PF_file, dynamic_file)
    Only_bus_list, bus_name_list, gen_bus_list, load_bus_list, \
        line_frombus_list, line_tobus_list, line_id_list = identify_channels(bus)

    ## Channels Extraction
    gen_channels(gen_bus_list)
    load_channels(load_bus_list)
    bus_channels(Only_bus_list)
    line_channels(line_frombus_list, line_tobus_list, line_id_list)
    LDDL_channels(bus)

    psspy.bsysdef(1,0)
    psspy.bsys(1,1,[ 300., 500.],0,[],0,[],0,[],0,[])
    psspy.bsysdef(1,0)
    psspy.bsys(1,1,[ 200., 500.],4,[14,26,30,24],0,[],0,[],0,[])
    psspy.bsysdef(1,0)
    psspy.bsys(1,1,[ 200., 299.],4,[14,26,30,24],0,[],0,[],0,[])
    psspy.bsysdef(0,0)
    psspy.set_genang_3(1, 600.0,0.0,1)
    psspy.set_vltscn(1, 1.4, 0.7)
    psspy.set_relang(1,0,"")
    psspy.set_zsorce_reconcile_flag(1)
    psspy.set_load_model_thresh( 5.0, 1.61, 0.97)
    psspy.set_netfrq(1)

    print(f'Start dynamic simulation  [{shape}  {freq} Hz  {MW} MW]')

    psspy.strt_2([0,0], outFile)
    n_prt         = 999
    n_out_channel = 10
    n_CRT_PLT     = 999

    # Initial flat run before oscillations begin
    psspy.run(0, LDDL_var_ST, n_prt, n_out_channel, n_CRT_PLT)
    T_stop = LDDL_var_ST

    # ── Shape-agnostic load-stepping loop ─────────────────────────────────
    for load_mw, hold_sec in steps:
        psspy.load_chng_6(
            LDDL_bus_number, 'os',
            [_i, _i, _i, _i, _i, _i, _i],
            [load_mw, 0, _f, _f, _f, _f, _f, _f])
        T_stop += hold_sec
        psspy.run(0, T_stop, n_prt, n_out_channel, n_CRT_PLT)

    export_sim_to_csv(outFile, csvFile)


def main():
    """Entry point: reads simulation_config.csv and runs the oscillation simulation."""
    start = time.time()
    root = Path.cwd()

    config = pd.read_csv(root / "simulation_config.csv")

    def _cfg(var, cast=str, default=None):
        row = config[config.Variable == var]
        if row.empty:
            return default
        v = row['Value'].iloc[0]
        return default if (str(v).strip().lower() == 'nan' or str(v).strip() == '') else cast(v)

    bus_number          = _cfg('bus_number',                  int)
    oscillation_shape   = _cfg('oscillation_shape',           str,   default='square')
    oscillation_freq    = _cfg('oscillation_frequency',       float)
    oscillation_amp     = _cfg('oscillation_amplitude',       float)
    oscillation_freq_in = _cfg('oscillation_frequency_fast', float)   # only needed for biperiodic
                                                                    # ignored otherwise
    print(f"Bus            : {bus_number}")
    print(f"Shape          : {oscillation_shape}")
    print(f"Frequency      : {oscillation_freq} Hz")
    print(f"Amplitude      : {oscillation_amp} MW")
    if oscillation_shape=='biperiodic' and oscillation_freq_in is not None:
        print(f"Faster frequency: {oscillation_freq_in} Hz")

    run_simulation(
        bus        = bus_number,
        shape      = oscillation_shape,
        freq       = oscillation_freq,
        MW         = oscillation_amp,
        freq_inner = oscillation_freq_in,
    )

    print(f"\nTotal runtime: {time.time() - start:.2f} seconds")


if __name__ == "__main__":
    main()