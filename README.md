# LL-risk-assessment
A suite of scripts that helps evaluate and visualize the grid reliability risk due to oscillations introduced by large dynamic digital loads (LDDLs) at the planning stage.

With this suite, users can run PSS/E simulations to identify high-risk large load interconnection points, where forced oscillations are likely to be amplified. Risk is expressed as a function of oscillation shape (monoperiodic square wave, biperiodic square wave, triangular), frequency, and source location. The script also helps users identify locations in a network where LL-induced oscillations may manifest as power swings above a specified threshold. The WECC 240-bus model is used as an illustrative example, but users may specify any PSS/E cases. 

To cite this work, please use "Biswas, Shuchismita, Antos C. Varghese, Kaustav Chatterjee, Sameer Nekkalapu, Brett Ross, and Jim Follum. "Evaluating the Risk to Bulk Power System Reliability from Large Load Induced Oscillations." Authorea Preprints (2025)."https://www.techrxiv.org/doi/full/10.36227/techrxiv.175623878.87007943

## Introduction
The structure of suite of scripts are detailed below.
```text
├─ main_LL_risk_assessment.py              # Main code for asking configuration input and running the framework
├─ scenario_menu.py            # Setting command line interface options
├─ LDDL_Different_Load_Variations.py               # scripts for running PSSE simulations for different periodic load variation patterns
├─ LDDL_Viz_Functions.py       # scripts for analyzing PSSE output to generate risk assessment and visualizations
├─ system_summary.py           # scripts for shortlisting buses and tie-lines to be examined and recorded during PSSE simulations
├─ requirements.txt            # PSS/E, Python and Folder locations requirements
└─ README.md
```

Upon running the main file "main_LL_risk_assessment.py", the user is presented with a menu with options to change the parameters of simulation as shown in figure below.
<p align="center">
  <img src="images/SS_CLI_menu_LDDL_tool.png" alt="Options to User" />
</p>

<p align="justify"> The menu has four sections. 
<p align="justify">  (1) The first section allows users to choose the location of case files, and specify case file names.
<p align="justify">  (2) The second section allows users to specify network locations where oscillations are to be injected from and other LDDL parameters. 
<p align="justify"> (3) The third section allows users to specify oscillation parameters.
<p align="justify">  (4) The fourth section allows users to specify latitude-longitude information of network parameters for effective visualizations. Users can also select a power swing MW threshold. The script will help identify network elements where the oscillation amplitude crosses the specified threshold.

Alternatively, the user can also input the selections through a csv. 'input_config_wecc240.csv' is an example. 'PATH' should be replaced by folder where these scripts are contained. 

<img width="327" height="341" alt="image" src="https://github.com/user-attachments/assets/3d17f6d7-6de8-4bb3-bc5f-156ad88c3262" />

  Several outputs are provided - (a) a csv with PSS/E dynamic simulation results, (b) plots visualizing voltage deviations and elements where active power oscillation amplitudes are above the specified threshold, (c) a csv summarizing observed instances of high-amplitude oscillations across the network, and (d) csvs listing generators, loads, and tie-lines where oscillation amplitudes cross the specified threshold. Outputs are stored in a folder called 'Results_XXX' where XXX is the load bus specified. If the latitude and longitude of buses are provided, then a geographic plot visualizing the impact of oscillations will also be produced. An example is included for the WECC 240 bus case. 

  **NOTES for test cases**:
The scripts have been tested with three PSSE cases and dyr files, as uploaded here. 
1) The WECC 240 bus case https://www.nrel.gov/grid/test-case-repository (The scripts are configured to run 1 Hz oscillations from bus 1302 in this model by default).
2) The ACTIVSg500 case https://electricgrids.engr.tamu.edu/electric-grid-test-cases/activsg500/
3) The New England 68-Bus test system https://electricgrids.engr.tamu.edu/electric-grid-test-cases/new-england-68-bus-test-system/

We have not tested with larger systems incorporating user defined models yet. We welcome feedback if you test the scripts out with larger planning models. Please report bugs/other issues/suggestions to shuchismita.biswas@pnnl.gov. 

If PSSE version or other initialization parameters need to be specified, it can be done in the initialize_dynamic_simulation() function within LDDL_Different_Load_Variations.py.
