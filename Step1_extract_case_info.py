"""
RATLLE- Risk Assessment Tool for Large Load Induced Events 
To provide feedback or report bugs, please email shuchismita.biswas@pnnl.gov

This script extracts case information from PSSE raw files for convenient data 
processing in the subsequent analysis. This script needs to be run only once
when starting to analyze a new case. Tested with PSSE 35.

Outputs (one CSV per element type):
  <case>_buses.csv        - Bus topology + voltage limits + solved V/theta + injections
  <case>_branches.csv     - Branch impedance/ratings + solved MW/Mvar flows + losses
  <case>_generators.csv   - Generator limits + solved dispatch + loading %
  <case>_loads.csv        - ZIP load components + solved actual consumption
  <case>_zones.csv        - Zone names
  <case>_areas.csv        - Area interchange schedule vs. actual
  <case>_interarea.csv    - Inter-area tie-line transfers
"""


import os, sys, csv
import pandas as pd
from pathlib import Path
from psse_config import configure_psse




# Initialize PSSE
def init_psse():
    """Initialise PSS/E and suppress its output."""
    psspy.psseinit(buses=200000)
    import redirect
    redirect.psse2py()

# Power flow solver
def solve_power_flow(method='FNSL'):
    """
    Parameters
    ----------
    method : str
        'FNSL' - Full Newton-Raphson (default)
        'FDNS' - Fast Decoupled Newton-Raphson
    """
    if method == 'FDNS':
        ierr = psspy.fdns([0, 0, 0, 1, 1, 0, 0, 0])
    else:
        ierr = psspy.fnsl([0, 0, 0, 1, 1, 0, 0, 0])

    if ierr == 0:
        print("  Power flow converged successfully.")
    else:
        print(f"  Power flow did not fully converge (error code {ierr}). "
              "Results extracted from last iteration.")
    return ierr

# Helper: Bus information lookup

def build_bus_lookups():
    """
    Query bus attributes and return lookup dicts keyed by bus number.

    Returns
    -------
    dict of {bus_num -> value} for: kv, vm_pu, va_deg, area, zone
    Also returns the raw arrays for use in extract_buses().
    """
    ierr, bus_num = psspy.abusint(-1, 1, 'NUMBER')
    ierr, bus_type = psspy.abusint(-1, 1, 'TYPE')
    ierr, bus_area = psspy.abusint(-1, 1, 'AREA')
    ierr, bus_zone = psspy.abusint(-1, 1, 'ZONE')
    ierr, bus_owner = psspy.abusint(-1, 1, 'OWNER')

    ierr, bus_kv = psspy.abusreal(-1, 1, 'BASE')
    ierr, bus_vm = psspy.abusreal(-1, 1, 'PU')
    ierr, bus_va = psspy.abusreal(-1, 1, 'ANGLED')
    ierr, bus_nvhi = psspy.abusreal(-1, 1, 'NVLMHI')
    ierr, bus_nvlo = psspy.abusreal(-1, 1, 'NVLMLO')
    ierr, bus_evhi = psspy.abusreal(-1, 1, 'EVLMHI')
    ierr, bus_evlo = psspy.abusreal(-1, 1, 'EVLMLO')

    ierr, bus_name = psspy.abuschar(-1, 1, 'NAME')

    n = len(bus_num[0])
    nums = bus_num[0]

    # Pre-build lookup dicts for downstream use
    kv_lu = {nums[i]: bus_kv[0][i] for i in range(n)}
    vm_lu = {nums[i]: bus_vm[0][i] for i in range(n)}
    va_lu = {nums[i]: bus_va[0][i] for i in range(n)}
    area_lu = {nums[i]: bus_area[0][i] for i in range(n)}
    zone_lu = {nums[i]: bus_zone[0][i] for i in range(n)}

    # Bundle raw arrays
    raw = dict(
        num=bus_num, type=bus_type, area=bus_area, zone=bus_zone, owner=bus_owner,
        kv=bus_kv, vm=bus_vm, va=bus_va,
        nvhi=bus_nvhi, nvlo=bus_nvlo, evhi=bus_evhi, evlo=bus_evlo,
        name=bus_name
    )

    return kv_lu, vm_lu, va_lu, area_lu, zone_lu, raw

# CSV Extractors

def extract_buses(output_file, raw):
    """
    Write bus CSV combining:
      - Static topology  : base kV, type, area, zone, owner, voltage limits
      - Solved power flow results   : solved V (pu), angle (deg)
    """
    headers = [
        'BUS_NUM', 'NAME', 'BASKV', 'TYPE', 'AREA', 'ZONE', 'OWNER',
        'VM_PU', 'VA_DEG',
        'NVHI', 'NVLO', 'EVHI', 'EVLO'
    ]

    with open(output_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(headers)

        n = len(raw['num'][0])
        for i in range(n):

            writer.writerow([
                raw['num'][0][i],
                raw['name'][0][i].strip() if raw['name'] and raw['name'][0] else '',
                raw['kv'][0][i],
                raw['type'][0][i],
                raw['area'][0][i],
                raw['zone'][0][i],
                raw['owner'][0][i],
                raw['vm'][0][i],
                raw['va'][0][i],
                raw['nvhi'][0][i], raw['nvlo'][0][i],
                raw['evhi'][0][i], raw['evlo'][0][i],
                           ])

    print(f"  {output_file}: {n} buses")

def extract_branches(output_file, kv_lu):
    """
    Write branch CSV combining:
      - Static parameters : R, X, B, RATE A/B/C, length, meter end
      - Solved results    : MW & Mvar flows, MVA loading %, MW & Mvar losses
    """
    # Static
    ierr, br_from = psspy.abrnint(-1, 1, 1, 1, 1, 'FROMNUMBER')
    ierr, br_to = psspy.abrnint(-1, 1, 1, 1, 1, 'TONUMBER')
    ierr, br_stat = psspy.abrnint(-1, 1, 1, 1, 1, 'STATUS')
    ierr, br_met = psspy.abrnint(-1, 1, 1, 1, 1, 'METERNUMBER')
    ierr, br_id = psspy.abrnchar(-1, 1, 1, 1, 1, 'ID')

    ierr, br_rx = psspy.abrncplx(-1, 1, 1, 1, 1, 'RX')   # R + jX in one call
    ierr, br_b = psspy.abrnreal(-1, 1, 1, 1, 1, 'CHARGING')
    ierr, br_rate1 = psspy.abrnreal(-1, 1, 1, 1, 1, 'RATEA')
    ierr, br_rate2 = psspy.abrnreal(-1, 1, 1, 1, 1, 'RATEB')
    ierr, br_rate3 = psspy.abrnreal(-1, 1, 1, 1, 1, 'RATEC')
    ierr, br_len = psspy.abrnreal(-1, 1, 1, 1, 1, 'LENGTH')

    # Solved flows & losses
    # from-bus injection
    ierr, br_pq_from = psspy.abrncplx(-1, 1, 1, 1, 1, 'PQ')
    ierr, br_mva = psspy.abrnreal(-1, 1, 1, 1, 1, 'MVA')
    ierr, br_pct = psspy.abrnreal(-1, 1, 1, 1, 1, 'PCTRATEA')
    ierr, br_ploss = psspy.abrnreal(-1, 1, 1, 1, 1, 'PLOSS')
    ierr, br_qloss = psspy.abrnreal(-1, 1, 1, 1, 1, 'QLOSS')

    headers = [
        'FROM_BUS', 'TO_BUS', 'CKT', 'STAT',
        'R_PU', 'X_PU', 'B_PU',
        'RATE_A_MVA', 'RATE_B_MVA', 'RATE_C_MVA', 'LENGTH', 'MET',
        'FROM_KV', 'TO_KV', 'P_FROM_MW', 'Q_FROM_MVAR',
        'MVA', 'LOADING_PCT', 'PLOSS_MW', 'QLOSS_MVAR'
    ]

    def _r(arr, i, default=0.0):
        return arr[0][i] if arr and arr[0] else default

    with open(output_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(headers)

        n = len(br_from[0])
        for i in range(n):
            fb, tb = br_from[0][i], br_to[0][i]
            writer.writerow([
                fb, tb,
                br_id[0][i].strip() if br_id and br_id[0] else '',
                br_stat[0][i],
                br_rx[0][i].real if br_rx and br_rx[0] else 0.0,
                br_rx[0][i].imag if br_rx and br_rx[0] else 0.0,
                _r(br_b, i),
                _r(br_rate1, i), _r(br_rate2, i), _r(br_rate3, i),
                _r(br_len, i),
                br_met[0][i],
                kv_lu.get(fb, 0.0), kv_lu.get(tb, 0.0),
                br_pq_from[0][i].real if br_pq_from and br_pq_from[0] else 0.0,
                br_pq_from[0][i].imag if br_pq_from and br_pq_from[0] else 0.0,
                _r(br_mva, i), _r(br_pct, i),
                _r(br_ploss, i), _r(br_qloss, i)
            ])

    print(f"  {output_file}: {n} branches")

def extract_generators(output_file, kv_lu, vm_lu, va_lu, area_lu, zone_lu):
    """
    Write generator CSV combining:
      - Static info : Pmax/Pmin, Qmax/Qmin, Mbase, area, zone
      - Solved dispatch   : Pgen, Qgen, loading % relative to Pmax
    """
    ierr, gen_bus = psspy.amachint(-1, 4, 'NUMBER')
    ierr, gen_stat = psspy.amachint(-1, 4, 'STATUS')
    ierr, gen_id = psspy.amachchar(-1, 4, 'ID')

    ierr, gen_pg = psspy.amachreal(-1, 4, 'PGEN')
    ierr, gen_qg = psspy.amachreal(-1, 4, 'QGEN')
    ierr, gen_pt = psspy.amachreal(-1, 4, 'PMAX')
    ierr, gen_pb = psspy.amachreal(-1, 4, 'PMIN')
    ierr, gen_qt = psspy.amachreal(-1, 4, 'QMAX')
    ierr, gen_qb = psspy.amachreal(-1, 4, 'QMIN')
    ierr, gen_mbase = psspy.amachreal(-1, 4, 'MBASE')
    ierr, gen_pct = psspy.amachreal(-1, 4, 'PERCENT')   # solved loading %

    headers = [
        'BUS_NUM', 'ID', 'STAT', 'AREA', 'ZONE',
        'PGEN_MW', 'QGEN_MVAR',
        'PMAX_MW', 'PMIN_MW', 'QMAX_MVAR', 'QMIN_MVAR',
        'MBASE_MVA', 'LOADING_PCT',
        'BUS_KV', 'VM_PU', 'VA_DEG'
    ]

    def _r(arr, i, default=0.0):
        return arr[0][i] if arr and arr[0] else default

    with open(output_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(headers)

        n = len(gen_bus[0])
        for i in range(n):
            bus = gen_bus[0][i]
            writer.writerow([
                bus,
                gen_id[0][i].strip() if gen_id and gen_id[0] else '',
                gen_stat[0][i],
                area_lu.get(bus, 0),
                zone_lu.get(bus, 0),
                _r(gen_pg, i), _r(gen_qg, i),
                _r(gen_pt, i), _r(gen_pb, i),
                _r(gen_qt, i), _r(gen_qb, i),
                _r(gen_mbase, i),
                _r(gen_pct, i),
                kv_lu.get(bus, 0.0),
                vm_lu.get(bus, 0.0),
                va_lu.get(bus, 0.0)
            ])

    print(f"  {output_file}: {n} generators")

def extract_loads(output_file, kv_lu, vm_lu, va_lu):
    """
    Write load CSV combining:
      - ZIP model components  : constant-power (PL/QL), constant-current (IP/IQ),
                                constant-admittance (YP/YQ)
      - Solved actual totals  : MVAACT (voltage-adjusted), TOTALACT
      - Bus voltage context   : kV, V (pu), angle
    """
    ierr, load_bus = psspy.aloadint(-1, 1, 'NUMBER')
    ierr, load_area = psspy.aloadint(-1, 1, 'AREA')
    ierr, load_zone = psspy.aloadint(-1, 1, 'ZONE')
    ierr, load_stat = psspy.aloadint(-1, 1, 'STATUS')
    ierr, load_owner = psspy.aloadint(-1, 1, 'OWNER')
    ierr, load_id = psspy.aloadchar(-1, 1, 'ID')

    # ZIP components (static, from RAW data)
    # constant-power component
    ierr, load_mva = psspy.aloadcplx(-1, 1, 'MVAACT')
    # constant-current component
    ierr, load_il = psspy.aloadcplx(-1, 1, 'ILACT')
    # constant-admittance component
    ierr, load_yl = psspy.aloadcplx(-1, 1, 'YLACT')

    # Solved total (voltage-corrected sum of all ZIP components)
    ierr, load_total = psspy.aloadcplx(-1, 1, 'TOTALACT')

    headers = [
        'BUS_NUM', 'ID', 'STAT', 'AREA', 'ZONE', 'OWNER',
        'PL_MW', 'QL_MVAR',         # constant-power (Z)
        'IP_MW', 'IQ_MVAR',         # constant-current (I)
        'YP_MW', 'YQ_MVAR',         # constant-admittance (P)
        'PTOTAL_MW', 'QTOTAL_MVAR',  # solved total (all components)
        'BUS_KV', 'VM_PU', 'VA_DEG'
    ]

    def _c(arr, i, part='real', default=0.0):
        if not (arr and arr[0]):
            return default
        return arr[0][i].real if part == 'real' else arr[0][i].imag

    with open(output_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(headers)

        n = len(load_bus[0])
        for i in range(n):
            bus = load_bus[0][i]
            writer.writerow([
                bus,
                load_id[0][i].strip() if load_id and load_id[0] else '',
                load_stat[0][i],
                load_area[0][i],
                load_zone[0][i],
                load_owner[0][i],
                _c(load_mva, i, 'real'), _c(load_mva, i, 'imag'),
                _c(load_il,  i, 'real'), _c(load_il,  i, 'imag'),
                _c(load_yl,  i, 'real'), _c(load_yl,  i, 'imag'),
                _c(load_total, i, 'real'), _c(load_total, i, 'imag'),
                kv_lu.get(bus, 0.0),
                vm_lu.get(bus, 0.0),
                va_lu.get(bus, 0.0)
            ])

    print(f"  {output_file}: {n} loads")
    

# optional - area information is just for information and decision making

def extract_areas(output_file):
    """Write area interchange schedule vs. actual generation/load."""
    ierr, area_num = psspy.aareaint(-1, 1, 'NUMBER')
    ierr, area_isw = psspy.aareaint(-1, 1, 'ISW')
    ierr, area_pdes = psspy.aareareal(-1, 1, 'PDES')
    ierr, area_ptol = psspy.aareareal(-1, 1, 'PTOL')
    ierr, area_pnet = psspy.aareareal(-1, 1, 'PNET')
    ierr, area_pgen = psspy.aareareal(-1, 1, 'PGEN')
    ierr, area_pload = psspy.aareareal(-1, 1, 'PLOAD')
    ierr, area_name = psspy.aareachar(-1, 1, 'ARNAME')

    def _r(arr, i, default=0.0):
        return arr[0][i] if arr and arr[0] else default

    with open(output_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['AREA_NUM', 'AREA_NAME', 'ISW',
                        'PDES', 'PTOL', 'PNET', 'PGEN', 'PLOAD'])
        for i in range(len(area_num[0])):
            writer.writerow([
                area_num[0][i],
                area_name[0][i].strip() if area_name and area_name[0] else '',
                _r(area_isw, i, 0),
                _r(area_pdes, i), _r(area_ptol, i), _r(area_pnet, i),
                _r(area_pgen, i), _r(area_pload, i)
            ])

    print(f"  {output_file}: {len(area_num[0])} areas")


def extract_interarea(output_file):
    """Write inter-area tie scheduled vs. actual transfers (gracefully handles missing data)."""
    headers = ['FROM_AREA', 'TO_AREA', 'CKT', 'PDES', 'PTOL', 'PACT']

    try:
        ierr, ixfr_from = psspy.aiession(-1, 1, 'ARFROM')
        ierr, ixfr_to = psspy.aiession(-1, 1, 'ARTO')
        ierr, ixfr_pdes = psspy.aiessionr(-1, 1, 'PDES')
        ierr, ixfr_ptol = psspy.aiessionr(-1, 1, 'PTOL')
        ierr, ixfr_pact = psspy.aiessionr(-1, 1, 'PACT')
        ierr, ixfr_id = psspy.aiessionc(-1, 1, 'TESSION')

        if ierr != 0 or not ixfr_from or not ixfr_from[0]:
            raise ValueError("No inter-area data found")

        with open(output_file, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for i in range(len(ixfr_from[0])):
                writer.writerow([
                    ixfr_from[0][i],
                    ixfr_to[0][i],
                    ixfr_id[0][i].strip() if ixfr_id else '1',
                    ixfr_pdes[0][i],
                    ixfr_ptol[0][i],
                    ixfr_pact[0][i]
                ])
        print(f"  {output_file}: {len(ixfr_from[0])} inter-area transfers")

    except Exception:
        with open(output_file, 'w', newline='') as f:
            csv.writer(f).writerow(headers)
        print(f"  {output_file}: 0 inter-area transfers (none defined in case)")

# ---------------------------------------------------------------------------
# System summary  (printed to console)
# ---------------------------------------------------------------------------

def print_system_summary(raw, kv_lu):
    """
    Print a system-wide MW/Mvar balance using data already held in memory.
    Uses the raw bus arrays from build_bus_lookups() for bus/branch counts,
    and makes two small additional queries for generation/loss totals.
    """
    ierr, gen_pg = psspy.amachreal(-1, 4, 'PGEN')
    ierr, gen_qg = psspy.amachreal(-1, 4, 'QGEN')
    ierr, load_tot = psspy.aloadcplx(-1, 1, 'TOTALACT')
    ierr, br_ploss = psspy.abrnreal(-1, 1, 1, 1, 1, 'PLOSS')
    ierr, br_qloss = psspy.abrnreal(-1, 1, 1, 1, 1, 'QLOSS')
    ierr, gen_bus = psspy.amachint(-1, 4, 'NUMBER')
    ierr, load_bus = psspy.aloadint(-1, 1, 'NUMBER')
    ierr, br_from = psspy.abrnint(-1, 1, 1, 1, 1, 'FROMNUMBER')

    total_pgen = sum(gen_pg[0]) if gen_pg and gen_pg[0] else 0.0
    total_qgen = sum(gen_qg[0]) if gen_qg and gen_qg[0] else 0.0
    total_pload = sum(
        l.real for l in load_tot[0]) if load_tot and load_tot[0] else 0.0
    total_qload = sum(
        l.imag for l in load_tot[0]) if load_tot and load_tot[0] else 0.0
    total_ploss = sum(br_ploss[0]) if br_ploss and br_ploss[0] else 0.0
    total_qloss = sum(br_qloss[0]) if br_qloss and br_qloss[0] else 0.0

    print("\n" + "=" * 55)
    print("SYSTEM SUMMARY")
    print("=" * 55)
    print(f"  Buses:        {len(raw['num'][0])}")
    print(f"  Generators:   {len(gen_bus[0])}")
    print(f"  Loads:        {len(load_bus[0])}")
    print(f"  Branches:     {len(br_from[0])}")
    print("-" * 55)
    print(
        f"  Total Generation:  {total_pgen:10.2f} MW  {total_qgen:10.2f} Mvar")
    print(
        f"  Total Load:        {total_pload:10.2f} MW  {total_qload:10.2f} Mvar")
    print(
        f"  Total Losses:      {total_ploss:10.2f} MW  {total_qloss:10.2f} Mvar")
    print("=" * 55)

# Main function
def run(raw_file, output_dir='.', pf_method='FNSL'):
    """
    Full pipeline:
      1. Initialise PSS/E
      2. Load RAW case
      3. Solve power flow
      4. Build bus lookups
      5. Extract all element types to CSV [Will be utilized in subsequent steps, but the
                                          information extraction needed only once per case
                                          you can simulate any number of large load simulations
                                          at different buses/frequencies/amplitudes]
      6. Print system summary
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(exist_ok=True)
    base = Path(raw_file).stem

    print("-" * 55)
    print(f"Case : {raw_file}")
    print("-" * 55)

    # 1. Init
    init_psse()

    # 2. Load
    print("\nLoading case...")
    ierr = psspy.read(0, raw_file)
    if ierr != 0:
        print(f"ERROR: could not load RAW file (code {ierr}). Aborting.")
        return

    # 3. Solve
    print(f"\nSolving power flow ({pf_method})...")
    solve_power_flow(pf_method)

    # 4. Build bus lookup functions
    print("\nBuilding bus lookups...")
    kv_lu, vm_lu, va_lu, area_lu, zone_lu, raw = build_bus_lookups()

    # 5. Extract
    print("\nExtracting results:")
    extract_buses(output_dir / f"{base}_buses.csv",      raw)
    extract_branches(output_dir / f"{base}_branches.csv",   kv_lu)
    extract_generators(
        output_dir / f"{base}_generators.csv", kv_lu, vm_lu, va_lu, area_lu, zone_lu)
    extract_loads(output_dir / f"{base}_loads.csv",      kv_lu, vm_lu, va_lu)
    extract_areas(output_dir / f"{base}_areas.csv")
    extract_interarea(output_dir / f"{base}_interarea.csv")

    # 6. Summary
    print_system_summary(raw, kv_lu)

    print("\nDone.")

# Run
if __name__ == '__main__':
    
    psse_version = 35
    psspy_version = 311
    psspy = configure_psse(psse_version, psspy_version)
    
    
    # pointing to case location and output directory
    root = Path.cwd()
    case_dir = root/"PSSE_Cases"
    output_dir = root/"Processing"

    config_name = 'Pre_Screening_config.csv'
    config = pd.read_csv(root/config_name)
    case_name = config[config.Variable == 'case_name']['Value'][0]
    raw_case_name = case_name+'.raw'
    sav_case_name = case_name+'.sav'
    
    
    raw_case = case_dir / raw_case_name
    sav_case = case_dir / sav_case_name

    run(str(raw_case), output_dir, pf_method='FNSL')
    
    psspy.save(str(sav_case))
