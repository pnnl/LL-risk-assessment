# LL-risk-assessment
A suite of scripts that helps evaluate and visualize the grid reliability risk due to events introduced by large dynamic digital loads (LDDLs) at the planning stage.

## Data Generation Scripts
This section provides scripts designed to emulate the behavior of data center loads using PSS/E. A demonstration using 240 bus MiniWECC system is provided. The codes are generic and can be applied to any test system modeled in PSS/E. The implementation currently focuses on three primary types of Load Dependent Dynamic Load (LDDL) behaviors that are commonly observed in real-world scenarios:

1. Square wave load variation
2. Double frequency square wave (DfSW) load variation
3. Triangular load variation

The parametrization of each of these load behavior characteristics are provided below.
1. Square wave load variation - Change in power in MW, Frequency of Load variation
2. Double frequency square wave (DfSW) load variation - Change in power in MW, Faster Frequency of Load variation, Slower Frequency of Load variation
3. Triangular load variation - Change in power in MW, Frequency of Load variation
