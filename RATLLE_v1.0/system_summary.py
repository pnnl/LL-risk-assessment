def system_summary(rawFile,target_bus):
    '''
    Setting up which elements in the grid to inspect, 
    and generating a csv of bus numbers for visualization/analysis. 
    Code should be run for set-up before running the main_LL_risk_assessment
    Initial logic - all buses>200kV within specified area, all generator buses with aggregated generation>50 MW, all buses with load connected>100MW
    all lines>100kV within speified area, and lines connecting different zones or areas outside that area higher than 100 kV
    '''
    import psse35
    import psspy
    import pandas as pd
    
    # ===============================
    # User selectable inputs
    # ===============================
    
    GEN_THRESHOLD = 50.0  # MW
    LOAD_THRESHOLD = 100.0  # MW
    KV_HIGH_BUS = 200    # kV
    KV_HIGH_LINE = 100   # kV
    KV_HIGH_LINE_OUTSIDE = 100 #kV
    
    # ===============================
    # Initialize and suppress output
    # ===============================
    psspy.psseinit(100000)
    psspy.report_output(2, 'log.txt', [])
    psspy.progress_output(2, 'log_p.txt', [])
    psspy.alert_output(1, '', [])
    psspy.prompt_output(1, '', [])
    print(rawFile)
    psspy.readrawversion(1, '35', rawFile) 
    
    # ===============================
    # 1️⃣ Get all buses and metadata
    # ===============================
    ierr, all_buses = psspy.abusint(-1, 1, 'NUMBER')
    ierr, all_bus_names = psspy.abuschar(-1, 1, 'NAME')
    ierr, base_kv = psspy.abusreal(-1, 1, 'BASE')
    ierr, zone = psspy.abusint(-1, 1, 'ZONE')
    ierr, area = psspy.abusint(-1, 1, 'AREA')
    
    bus_info = pd.DataFrame({
        'BUS_NUMBER': all_buses[0],
        'BUS_NAME': all_bus_names[0],
        'BASE_KV': base_kv[0],
        'ZONE': zone[0],
        'AREA': area[0],
    })
    
    TARGET_AREA = bus_info[bus_info.BUS_NUMBER==target_bus].AREA.iloc[0]
    
    # ===============================
    # 2️⃣ Generator aggregation per bus
    # ===============================
    ierr, gen_buses = psspy.agenbusint(-1, 1, 'NUMBER')
    ierr, gen_bus_names = psspy.agenbuschar(-1, 1, 'NAME')
    ierr, pgen = psspy.agenbusreal(-1, 1, 'PGEN')
    
    gen_df = pd.DataFrame({'BUS_NUMBER': gen_buses[0], 'BUS_NAME': gen_bus_names[0], 'PGEN': pgen[0]})
    bus_gen = gen_df.groupby('BUS_NUMBER', as_index=False)['PGEN'].sum()
    
    # ===============================
    # 3️⃣ Load aggregation per bus
    # ===============================
    ierr, load_buses = psspy.aloadint(-1, 1, 'NUMBER')
    ierr, load_bus_names = psspy.aloadchar(-1, 1, 'NAME')
    ierr, pload = psspy.aloadreal(-1, 1, 'TOTALACT')
    
    load_df = pd.DataFrame({'BUS_NUMBER': load_buses[0], 'BUS_NAME': load_bus_names[0], 'PLOAD': pload[0]})
    bus_load = load_df.groupby('BUS_NUMBER', as_index=False)['PLOAD'].sum()
    
    # ===============================
    # 4️⃣ Merge all info together
    # ===============================
    bus_combined = (
        bus_info
        .merge(bus_gen, on='BUS_NUMBER', how='left')
        .merge(bus_load, on='BUS_NUMBER', how='left')
    )
    
    bus_combined.fillna(0, inplace=True)
    
    # ===============================
    # 5️⃣ Apply bus filter conditions
    # ===============================
    gen_filtered = bus_combined[bus_combined['PGEN'] > GEN_THRESHOLD].reset_index(drop=True)
    load_filtered = bus_combined[bus_combined['PLOAD'] > LOAD_THRESHOLD].reset_index(drop=True)
    bus_filtered = bus_combined[(bus_combined['AREA']==TARGET_AREA) & (bus_combined['BASE_KV'] > KV_HIGH_BUS)].reset_index(drop=True)
    
    # ===============================
    # 6️⃣ Transmission lines
    # ===============================
    ierr, from_bus = psspy.abrnint(-1, 1, 1, 1, 1, ['FROMNUMBER'])
    ierr, to_bus = psspy.abrnint(-1, 1, 1, 1, 1, ['TONUMBER'])
    ierr, ckt_id = psspy.abrnchar(-1, 1, 1, 1, 1, ['ID'])
    ierr, flow = psspy.abrnreal(sid=-1, string='P')
    
    import numpy as np
    kv_filtered = bus_combined.set_index('BUS_NUMBER').loc[from_bus[0]]
    line_df = pd.DataFrame({
        'FROMBUS': from_bus[0],
        'TOBUS': to_bus[0],
        'CKT': ckt_id[0],
        'Flow (MW)': flow[0],
        'FROM_KV': np.array(kv_filtered.BASE_KV)
    })
    
    # Add area/zone info
    zone_map = dict(zip(bus_info['BUS_NUMBER'], bus_info['ZONE']))
    area_map = dict(zip(bus_info['BUS_NUMBER'], bus_info['AREA']))
    
    line_df['FROM_ZONE'] = line_df['FROMBUS'].map(zone_map)
    line_df['TO_ZONE'] = line_df['TOBUS'].map(zone_map)
    line_df['FROM_AREA'] = line_df['FROMBUS'].map(area_map)
    line_df['TO_AREA'] = line_df['TOBUS'].map(area_map)
    
    # ===============================
    # 7️⃣ Filter lines
    # ===============================
    lines_filtered = line_df[
        (
            # Lines within target area above 100 kV
            ((line_df['FROM_AREA'] == TARGET_AREA) & (line_df['TO_AREA'] == TARGET_AREA) &
             (line_df['FROM_KV'] > KV_HIGH_LINE))
        ) |
        (
            # Lines connecting different zones or areas outside the area above 200 kV
            (((line_df['FROM_ZONE'] != line_df['TO_ZONE'])|(line_df['FROM_AREA'] != line_df['TO_AREA'])) &
             ((line_df['FROM_AREA'] != TARGET_AREA) | (line_df['TO_AREA'] != TARGET_AREA))&((line_df['FROM_KV'] > KV_HIGH_LINE_OUTSIDE)))
        )
    ].reset_index(drop=True)
    
    # ===============================
    # 8️⃣ Save outputs
    # ===============================
    from pathlib import Path
    folder_name = f"Results_{target_bus}"
    Path(folder_name).mkdir(parents=True, exist_ok=True)

    gen_filtered.to_csv(folder_name + "\\filtered_gen.csv",index=False)
    load_filtered.to_csv(folder_name + "\\filtered_load.csv",index=False)
    bus_filtered.to_csv(folder_name + "\\filtered_buses.csv", index=False)
    lines_filtered.to_csv(folder_name + "\\filtered_lines.csv", index=False)
    
    line_filtered_A = lines_filtered[['FROMBUS','FROM_KV','FROM_ZONE','FROM_AREA']]
    line_filtered_A.columns = ['BUS_NUMBER', 'BASE_KV', 'ZONE', 'AREA']
    line_filtered_A['BUS_NAME']=None
    line_filtered_B = lines_filtered[['TOBUS','FROM_KV','TO_ZONE','TO_AREA']]
    line_filtered_B.columns = ['BUS_NUMBER', 'BASE_KV', 'ZONE', 'AREA']
    line_filtered_B['BUS_NAME']=None
    
    combined = pd.concat([gen_filtered,load_filtered,bus_filtered, line_filtered_A, line_filtered_B], ignore_index=True).drop_duplicates()
    combined.to_csv(folder_name + '\\sys_bus_summary.csv')
    
    print("\n✅ Saved filtered_buses.csv and filtered_lines.csv")
    print(f"Gen retained: {len(gen_filtered)}")
    print(f"Loads retained: {len(load_filtered)}")
    print(f"Buses retained: {len(bus_filtered)}")
    print(f"Lines retained: {len(lines_filtered)}")
    return
