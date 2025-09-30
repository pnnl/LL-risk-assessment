# LL-risk-assessment
A suite of scripts that helps evaluate and visualize the grid reliability risk due to oscillations introduced by large dynamic digital loads (LDDLs) at the planning stage.

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
</p>


<p align="justify"> The menu has four sections. First section provides option to change the locations of input and output files, as well as options to provide different PSS/E raw and dyr files than the default 240 bus WECC system. In the second section the user has the flexibility to select the size and location of the LDDL. Third section provides options to choose the type of load variation - monoperiodic, biperiodic, or triangular - along with their corresponding parameters. Note that a default option is always avilable in case the user choose not to change anything. In the fourth section, user can provide the latitude-longitude information for visualization as well as vary the peak-peak threshold in MW for risk assessment. The tool provides three outputs - a summary of the critical transmission lines impacted due to LDDL variation as an output csv file, a visualization of the same, and another output csv that has the LDDL load variation data generated using PSS/E.</p>
