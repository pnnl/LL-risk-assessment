# LL-risk-assessment
A suite of scripts that helps evaluate and visualize the grid reliability risk due to oscillations introduced by large dynamic digital loads (LDDLs) at the planning stage.

With this suite, users can run PSS/E simulations to identify high-risk large load interconnection points, where forced oscillations are likely to be amplified. Risk is expressed as a function of oscillation shape (monoperiodic square wave, biperiodic square wave, triangular), frequency, and source location. The script also helps users identify locations in a network where LL-induced oscillations may manifest as power swings above a specified threshold. The WECC 240-bus model is used as an illustrative example, but users may specify any PSS/E cases. 

To cite this work, please use "Biswas, Shuchismita, Antos C. Varghese, Kaustav Chatterjee, Sameer Nekkalapu, Brett Ross, and Jim Follum. "Evaluating the Risk to Bulk Power System Reliability from Large Load Induced Oscillations." Authorea Preprints (2025)."https://www.techrxiv.org/doi/full/10.36227/techrxiv.175623878.87007943

## Introduction
The structure of suite of scripts are detailed below.
```text
├─ main_LL_risk_assessment.py              # Main code 
├─ scenario_menu.py            # Setting command line interface options
├─ LDDL_Different_Load_Variations.py               # Different periodic load variation patterns
├─ LDDL_Viz_Functions.py       # Risk assessment and visualizations
├─ requirements.txt            # PSS/E, Python and Folder locations requirements
└─ README.md
```

Upon running the main file "main_LL_risk_assessment.py", the user is presented with a menu with options to change the parameters of simulation as shown in figure below.
<p align="center">
  <img src="images/SS_CLI_menu_LDDL_tool.png" alt="Options to User" />
</p>.


<p align="justify"> The menu has four sections. 
<p align="justify">  (1) The first section allows users to choose the location of case files, and specify case file names.
<p align="justify">  (2) The second section allows users to specify network locations where oscillations are to be injected from and other LDDL parameters. 
<p align="justify"> (3) The third section allows users to specify oscillation parameters.
<p align="justify">  (4) The fourth section allows users to specify latitude-longitude information of network parameters for effective visualizations. Users can also select a power swing MW threshold. The script will help identify network elements where the oscillation amplitude crosses the specified threshold.

  Three outputs are provided - (a) a csv with PSS/E dynamic simulation results, (b) a plot visualizing where oscillation amplitudes are above the specified threshold, and (c) a csv summarizing observed instances of high-amplitude oscillations across the network.
