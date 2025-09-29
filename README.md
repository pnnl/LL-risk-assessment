# LL-risk-assessment
A suite of scripts that helps evaluate and visualize the grid reliability risk due to oscillations introduced by large dynamic digital loads (LDDLs) at the planning stage.

To cite this work, please use "Biswas, Shuchismita, Antos C. Varghese, Kaustav Chatterjee, Sameer Nekkalapu, Brett Ross, and Jim Follum. "Evaluating the Risk to Bulk Power System Reliability from Large Load Induced Oscillations." Authorea Preprints (2025)."https://www.techrxiv.org/doi/full/10.36227/techrxiv.175623878.87007943

## Introduction
The structure of suite of scripts are detailed below.
```text
├─ main_smaart.py              # Main code 
├─ scenario_menu.py            # Setting CLI options
├─ LDDL_Different_Load_Variations.py               # Different periodic load variation patterns
├─ LDDL_Viz_Functions.py       # Oscillation amplification analysis and visualizations
├─ requirements.txt            # PSS/E, Python and Folder locations requirements
└─ README.md
```

When the main file "main_smaart.py" is run, the user is presented with options as shown in figure below.
![Options to User](images/SS_CLI_menu_LDDL_tool.png)


The options are divided into four sections. In the first section the user has the flexibility to select the size and location of the LDDL. Second section provides options to choose the type of load variation - monoperiodic, biperiodic, or triangular - along with their corresponding parameters. Note that a default option is always avilable in case the user choose not to change anything. 
