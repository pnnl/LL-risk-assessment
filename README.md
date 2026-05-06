# RATLLE — Risk Assessment Tool for Large Load Induced Events

A Python-based script suite for evaluating bulk power system reliability risk from oscillations introduced by large dynamic digital loads (LDDLs), using PSS/E as the simulation engine. Tested with PSS/E v35 and WECC planning cases in v34. Revised - 5/6/2026.

The risk assessment script suite is divided into three modules, designed for pre-screening vulnerable locations, running time-series simulations, and analyzing simulation outputs (Figure 1). The scripts are written in a simplified modular function-style in Python, so that they can be easily understood and modified to suit a utility’s needs.

> \*\*To cite this work:\*\* Biswas, S., Varghese, A. C., Chatterjee, K., Nekkalapu, S., Ross, B., and Follum, J. "Evaluating the Risk to Bulk Power System Reliability from Large Load Induced Oscillations." \*Authorea Preprints\* (2025). \[https://www.techrxiv.org/doi/full/10.36227/techrxiv.175623878.87007943](https://www.techrxiv.org/doi/full/10.36227/techrxiv.175623878.87007943)

<img width="2084" height="940" alt="image" src="https://github.com/user-attachments/assets/a6c3db39-62a6-41d4-b4f7-53e695eac9c2" />
Figure 1. Script architecture

## Script architecture

**Module 1: Pre-screening**

Planners might consider the risk assessment question from two perspectives:

* How can one quickly identify the most vulnerable locations in their system?
* How would they go about conducting more detailed risk analysis for an individual location?

*Step 1: Identify locations with high voltage and angle sensitivity.*

* Add fictitious load to user-selected buses (specified voltages in a specified area) without switched shunts and note change in voltage due to change in MW/MVar injection.
* Add fictitious load to user-selected generator buses (>specified generation threshold in a specified area) and note change in bus angle due to change in MW injection.

*Step 2: Identify excitable frequencies from a selected location*

* Simulate a load impulse at user selected location.
* Analyze ringdown response using an automated FFT+VARPRO pipeline to identify risky mode frequencies excitable from the selected location.

**Module 2: Simulation**

* Modify existing HV load to represent a data-center load with an oscillation injection block.
* Run PSS/E simulations to inject oscillation from user-selected location and specifiable (shape, frequency, amplitude) combinations.
* Two shapes can be selected - square wave, biperiodic square wave.

**Module 3: Analysis**

* Analyze simulation outputs to compute risk metrics and identify most-impacted elements.
* Risk is visualized through interactive HTML dashboards as well as summary spreadsheets.
* Thresholds can be set by an utility according to their risk budget.
* Users can also visualize impedance trajectories and RAS activation likelihood for selected elements without having to explicitly configure them in simulation models.

\---

## Folder structure

```
Root/
│
├── psse\_config.py                  ← Edit once: set your PSS/E install path and version
│
├── Pre\_Screening\_config.csv        ← Configuration for Steps 1, 2a, 2b, 2c
├── modal\_analysis\_config.csv       ← Configuration for Steps 2b and 2c
├── simulation\_config.csv           ← Configuration for Steps 3a through 8
│
├── PSSE\_Cases/                     ← Place your .sav, .dyr, and .raw, .idv files here
│
├── Processing/                     ← Intermediate outputs 
│
├── results/                        ← Simulation outputs and plots 
│
├── Step1\_extract\_case\_info.py
├── Step2a\_locational\_sensitivity.py
├── Step2b\_load\_impulse.py
├── Step2c\_mode\_estimates.py
├── Step3a\_simsetup\_loadadd.py
├── Step3b\_simsetup\_monitoredqty.py
├── Step4\_runsim.py
├── Step5\_analyze\_sim.py
├── Step6\_metrics\_visualization.py
├── Step7a\_distance\_z3\_reach.py
└── Step7b\_RAS\_check.py
```

\---

## First-time setup

Open `psse\_config.py` and set your PSS/E installation details:

```python
PSSE\_INSTALL\_DIR = r"C:\\Program Files\\PTI\\PSSE35\\PSSBIN"
PSSE\_VERSION     = 35
```

This file is imported by every script that calls PSS/E — you only need to edit it once.

\---

## Configuration files

All user inputs are driven by three CSV configuration files. Edit these before running any step.

### `Pre\_Screening\_config.csv`

Used by Steps 1, 2a, 2b, and 2c. One row per case.

|Column|Description|Example|
|-|-|-|
|`case\_name`|PSS/E .sav file name (without extension)|`WECC\_2031\_HW`|
|`dyr\_name`|Dynamics .dyr file name (without extension)|`WECC\_2031\_HW\_dyn`|
|`voltage\_sensitivity\_minKV`|Minimum bus voltage (kV) for sensitivity screening|`69`|
|`voltage\_sensitivity\_maxKV`|Maximum bus voltage (kV) for sensitivity screening|`138`|
|`area`|PSS/E area number to screen (leave blank for all areas)|`3`|
|`angle\_sensitivity\_minMW`|Minimum MW injection for angle sensitivity calculation|`25`|

### `modal\_analysis\_config.csv`

Used by Steps 2b and 2c. One row per bus to analyse.

|Column|Description|Example|
|-|-|-|
|`case\_name`|PSS/E .sav file name (without extension)|`WECC\_2031\_HW`|
|`dyr\_name`|Dynamics .dyr file name (without extension)|`WECC\_2031\_HW\_dyn`|
|`bus\_number`|Bus where the load impulse is injected|`5003`|
|`load\_step\_MW`|Impulse magnitude in MW|`50`|

### `simulation\_config.csv`

Used by Steps 3a through 8. One row per simulation scenario.

|Column|Description|Example|
|-|-|-|
|`case\_name`|PSS/E .sav file name (without extension)|`WECC\_2031\_HW`|
|`dyr\_name`|Dynamics .dyr file name (without extension)|`WECC\_2031\_HW\_dyn`|
|`bus\_number`|Bus where the LDDL oscillation is injected|`5003`|
|`load\_id`|Load ID at that bus|`1`|
|`oscillation\_shape`|Waveform type: `square`, `biperiodic`|`square`|
|`oscillation\_frequency`|Oscillation frequency in Hz|`0.4`|
|`oscillation\_amplitude`|Peak oscillation amplitude in MW|`100`|
|'oscillation\_frequency\_fast'|Faster frequency (Hz) for biperiodic load variation|`4`|



\---

## Running the scripts

The steps are designed to run in sequence. You can stop after any step if only partial results are needed — for example, stopping after Step 2c gives you mode estimates without running full simulations.

### Step 1 — Extract case information

```bash
python Step1\_extract\_case\_info.py
```

Reads the PSS/E case and writes bus, branch, generator, load, and area summary CSVs to `Processing/`. Run this first for any new case.

\---

### Step 2a — Voltage and angle sensitivity screening

```bash
python Step2a\_locational\_sensitivity.py
```

Applies small fictitious injections at each bus in the specified voltage range and computes dV/dP, dV/dQ, and dθ/dP. Use this to identify vulnerable locations in the network.

\---

### Step 2b — Load impulse simulation

```bash
python Step2b\_load\_impulse.py
```

Applies a short load impulse at the bus specified in `modal\_analysis\_config.csv` and records the ringdown response.

\---

### Step 2c — Mode estimation

```bash
python Step2c\_mode\_estimates.py
```

Analyses the ringdown signal from Step 2b to identify excitable oscillatory modes. If a prominent mode is found near a particular frequency, that frequency is a priority candidate for detailed simulation in Steps 3–8.

\---

### Step 3a — Simulation setup: add LDDL model

```bash
python Step3a\_simsetup\_loadadd.py
```

Modifies the PSS/E case to represent the LDDL. Moves the existing load to an MV bus behind a step-down transformer, replaces its dynamic model with a CMLD model (NERC LMWG data center parameters), and adds a separate oscillation injection block. Outputs `LLmod.sav`, `LLmod.snp`, and a modified `.dyr` file.

\---

### Step 3b — Simulation setup: select monitored quantities

```bash
python Step3b\_simsetup\_monitoredqty.py
```

Uses the case summary from Step 1 to compile the list of buses, generators, loads, and lines to be logged during simulation. Outputs four CSVs to `Processing/`. Adjust selection criteria in the script if the default channel count is too large for your system.

\---

### Step 4 — Run simulation

```bash
python Step4\_runsim.py
```

Runs the PSS/E dynamic simulation with the oscillation waveform defined in `simulation\_config.csv`. Outputs `results/<bus>\_sim.out` and `results/<bus>\_sim.csv`. Simulation outputs are tagged with a run identifier of the form `bus<N>\_<freq>Hz\_<amp>MW` (e.g. `bus5003\_0.4Hz\_100MW`) so multiple scenarios can coexist in the `results/` folder.

\---

### Step 5 — Analyse simulation results

```bash
python Step5\_analyze\_sim.py
```

Reads the simulation CSV and computes swing amplitude, envelope, and thermal loading metrics for generators, lines, buses, and loads. Flags elements that exceed configurable risk thresholds and writes summary and detail violation reports.
To adjust the risk thresholds, edit the `RISK\_THRESHOLDS` dictionary near the top of the script.

\---

### Step 6 — Interactive risk dashboard

```bash
python Step6\_metrics\_visualization.py
```

Generates a self-contained HTML dashboard (`results/risk\_visualization\_<run\_tag>.html`) from the metrics produced by Step 5. The dashboard includes summary risk statistics and time-series plots for the worst elements in each category. Users can interactively change violation thresholds.

\---

### Step 7a — Zone 3 distance relay check

```bash
python Step7a\_distance\_z3\_reach                       # interactive
python Step7a\_distance\_z3\_reach --line 5001-5003-1     # direct
```

For a selected line, computes the Zone 3 mho relay reach (if not already present in PSSE model) and plots the apparent impedance trajectory from the simulation against the Zone 3 boundary. If RATE\_B (or any other branch parameter) is missing from the case data, the script prompts you to enter it manually.

Reach setting philosophy is simple - zone 3 reach is set in a way that the relay doesn't trip for 150% of rate B flow if voltage falls below 0.85 p.u.

### Step 7b — RAS trigger check

```bash
python Step7b\_RAS\_check.py                                                              # interactive
python Step8\_RAS\_check.py --bus 5003 --signal volt --threshold 1.05 --duration 0.5 --direction above
python Step8\_RAS\_check.py --line 5001-5003-1 --signal P --threshold 300 --duration 0.3 --direction above
```

Checks whether a user-defined Remedial Action Scheme trigger condition was sustained during the simulation. Only rudimentary rules can be implemented at present. You specify an element, a signal, a threshold, a direction (above/below), and a minimum duration. The script identifies all windows where the condition is met and produces an annotated time-series plot and a per-timestep CSV with a condition flag.

Supported signals:

|Element type|Available signals|
|-|-|
|Bus|Voltage magnitude (pu)|
|Line|Active power P (MW), Reactive power Q (MVar), Angle difference Δθ from–to (degrees)|

\---

## Test cases

The scripts have been tested with the following publicly available PSS/E cases:

|Case|Source|Default scenario|
|-|-|-|
|WECC 240-bus|[NREL Test Case Repository](https://www.nrel.gov/grid/test-case-repository)|1.2 Hz oscillation from bus 6508|

\---

## Reporting issues

Please report bugs, unexpected behaviour, or suggestions to **shuchismita.biswas@pnnl.gov**.

## Known limitations 
Simulation script fails if no load present at bus selected to be LDDL oscillation source in the base case. 
LDDL MV bus number must be specified if the HV bus number has seven digits. 
Visualization improvement opportunities in the HTML dashboard.
