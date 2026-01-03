# User Acceptance Testing (UAT): Cycle 2

This document outlines the User Acceptance Testing scenarios for the second release of the MLIP-AutoPipe framework. This release introduces advanced scientific features and a new Web User Interface. The goal of these tests is to ensure that the new features are not only functional but also provide a tangible improvement to the quality of the generated datasets and the overall user experience. These scenarios are designed to be more sophisticated than those in Cycle 1, encouraging the user to explore the powerful new capabilities and understand their scientific impact.

As with Cycle 1, a new Jupyter Notebook, `CYCLE02_UAT.ipynb`, will be provided to facilitate interactive testing. This notebook will include instructions and code snippets for enabling the advanced features, launching runs from both the CLI and the Web UI, and performing more sophisticated analysis on the output to verify the impact of the new algorithms. The focus is on demonstrating value: showing the user *why* FPS is better than random sampling, and illustrating how the Web UI can simplify their workflow.

## 1. Test Scenarios

| Scenario ID | Priority | Description                                                                   |
| :---------- | :------- | :---------------------------------------------------------------------------- |
| UAT-C2-001  | High     | Verify the Farthest Point Sampling (FPS) method produces a diverse dataset.   |
| UAT-C2-002  | High     | Verify the Web UI can successfully configure and launch a pipeline run.       |
| UAT-C2-003  | Medium   | Verify the hybrid MD/MC engine runs and improves exploration for alloys.      |
| UAT-C2-004  | Medium   | Verify the Web UI provides feedback during and after a pipeline run.          |

---

### **Scenario UAT-C2-001: Farthest Point Sampling (FPS) Diversity Verification**

*   **Priority:** High
*   **Description:** This test is arguably the most important one for this cycle, as it aims to provide the user with tangible, scientific proof that the new Farthest Point Sampling (FPS) method is superior to the basic random sampling from Cycle 1 for creating diverse datasets. The user experience must be compelling and educational, clearly demonstrating the value of this advanced feature. The UAT notebook will guide the user to first generate a large trajectory file. Then, they will run the sampling stage twice on this *same* trajectory data: once using the `random` sampler and once using the newly implemented `fps` sampler. This controlled experiment ensures the comparison is fair. After generating two databases (`results_random.db` and `results_fps.db`), the notebook will provide a sophisticated analysis workflow. It will load both datasets, compute a structural descriptor (like SOAP) for every structure, and then plot the distribution of pairwise distances between all structures in each dataset. The hypothesis is that the FPS dataset, by design, will have a distribution of distances that is shifted towards higher values, indicating greater dissimilarity or diversity. The notebook will generate and display these plots side-by-side, providing a clear, visual confirmation that FPS is actively selecting structures that cover a wider portion of the configuration space. This is a powerful demonstration that the tool is not just producing data, but producing *smarter* data.
*   **Success Criteria:**
    *   The pipeline must run successfully with the `sampling: {method: fps}` setting in the configuration.
    *   The generated plots of pairwise structural distances must show a clear, qualitative difference. The distribution for the FPS dataset should have a higher mean or be visibly shifted to the right (towards higher distance/dissimilarity) compared to the distribution for the random dataset.
    *   The final `results_fps.db` should contain the correct number of samples as specified in the configuration.

---

### **Scenario UAT-C2-002: Web UI Pipeline Launch**

*   **Priority:** High
*   **Description:** This test serves as the primary "happy path" verification for the new Web User Interface. Its goal is to confirm that a user can successfully configure and launch a complete pipeline run from start to finish using only the graphical interface, without needing to interact with the command line at all. This is crucial for making the tool accessible to a wider audience. The user will be instructed to launch the web application (e.g., by running `streamlit run app.py`). They will then be presented with an intuitive form. They will use the various widgets—dropdown menus to select elements, sliders to set temperature and pressure, number input boxes for the number of steps—to define a simple binary alloy system and configure the pipeline parameters. After filling out the form, they will click a prominent "Run Pipeline" button. This action should trigger the execution of the core MLIP-AutoPipe pipeline in the background. The user is not expected to see any code or terminal output. The test is successful if, after a reasonable amount of time, the expected output files, particularly the final `results.db`, are created in the designated output directory. This confirms that the UI is correctly communicating with the backend pipeline orchestrator and can manage a full workflow.
*   **Success Criteria:**
    *   The user is able to successfully start the Web UI application and view it in their browser.
    *   The user can fill out all the necessary parameters for a pipeline run using the provided form widgets.
    *   Clicking the "Run Pipeline" button successfully initiates the backend pipeline process without any visible errors in the UI.
    *   The pipeline runs to completion in the background, and the final output database (`results.db`) is correctly created on the filesystem in the expected location.

---

### **Scenario UAT-C2-003: Hybrid MD/MC Engine Verification for Alloys**

*   **Priority:** Medium
*   **Description:** This test is designed to allow the user to see and verify the effect of the new hybrid MD/MC exploration engine. While the underlying algorithms are complex, the user-facing result should be intuitive: the engine should be better at exploring different chemical orderings in an alloy. The UAT notebook will guide the user to first create a highly-ordered initial structure. For example, a supercell of a CuAu alloy where all the Cu atoms are in one layer and all the Au atoms are in another. This is a physically unrealistic starting point but is excellent for testing. The user will then configure the pipeline to use this structure as its input and will enable the Monte Carlo features in the `exploration` config (`enable_mc: true`, with a reasonable `mc_swap_probability`). After running the pipeline, the notebook will provide tools to analyze the output. It will load several of the final structures from the `results.db` and create visualizations. The user should be able to clearly see that the final structures are now disordered, with Cu and Au atoms mixed throughout the crystal, in stark contrast to the perfectly ordered initial state. This provides strong evidence that the atomic swap moves were successfully performed and that the MD/MC engine is correctly exploring different chemical arrangements.
*   **Success Criteria:**
    *   The pipeline must complete successfully with the `enable_mc: true` flag in the configuration.
    *   Visual inspection of the final atomic structures from the output database must show a clear difference in elemental distribution compared to the ordered initial structure. The final structures should appear significantly more disordered or "mixed."
    *   The run should produce a trajectory file showing this transformation over time.

---

### **Scenario UAT-C2-004: Web UI Feedback and Visualization**

*   **Priority:** Medium
*   **Description:** A critical aspect of a good graphical user interface is providing feedback to the user. A UI that becomes unresponsive after an action is clicked is a poor user experience. This test verifies that the MLIP-AutoPipe Web UI keeps the user informed about the status of their pipeline run. Building on the previous UI test (UAT-C2-002), after the user clicks the "Run Pipeline" button, they will be instructed to observe the UI. The interface should immediately update to provide some form of progress indication. This could be a simple text message like "Pipeline is running...", a spinning icon, or perhaps a more advanced view that shows the output of the pipeline's log file in real-time. This feedback is essential to reassure the user that the system is working. Once the pipeline run is complete, the UI must update again to clearly signal that the process is finished. A "Run Completed Successfully!" message should appear. Critically, the UI should then automatically display a result, for example by rendering a 3D visualization of one of the newly generated atomic structures using a library like `py3Dmol`. This provides immediate gratification and a tangible output for the user's work.
*   **Success Criteria:**
    *   Immediately after the "Run Pipeline" button is clicked, the Web UI must display a clear progress indicator.
    *   When the background pipeline process has finished, the UI must update its status to show a completion message.
    *   After completion, a 3D molecular viewer embedded in the UI must successfully render one of the atomic structures from the final output dataset.

---

## 2. Behavior Definitions

This section provides formal Gherkin-style definitions for the expected behavior in each UAT scenario. These definitions serve as the precise contract for what constitutes a successful test outcome. They are written in a user-centric format to bridge the gap between technical implementation and the user's expectations. For Cycle 2, these definitions become more nuanced. For instance, the FPS test's `THEN` clause doesn't just check for file existence but for a qualitative improvement in the dataset, linking the feature to its intended scientific benefit. Similarly, the Web UI tests explicitly define requirements for user feedback (e.g., "display a progress indicator"), making user experience a testable criterion. The `CYCLE02_UAT.ipynb` notebook will be structured around these definitions. Each Gherkin step will correspond to a set of cells in the notebook: "Given" steps will be handled by configuration setup cells, "When" steps by cells that execute the pipeline (either via CLI or by instructing the user to click a button in the UI), and "Then" steps by automated analysis and assertion cells that programmatically check the outcomes against these definitions and render a clear "Pass" or "Fail" verdict.

### **UAT-C2-001: Farthest Point Sampling (FPS) Diversity Verification**

```gherkin
GIVEN a large trajectory file "trajectory.xyz" has been pre-generated
  AND a configuration file "config_fps.yaml" is set to use the "fps" sampling method
  AND another configuration file "config_random.yaml" is set to use the "random" sampling method
WHEN the user runs the sampling pipeline using "config_fps.yaml" to generate a database "results_fps.db"
  AND the user runs the sampling pipeline on the same trajectory using "config_random.yaml" to generate "results_random.db"
THEN both pipeline runs should complete successfully
  AND an analysis script that calculates and plots the distribution of structural similarity for both databases
  SHOULD show that the distribution for "results_fps.db" is shifted towards higher diversity compared to "results_random.db"
```

### **UAT-C2-002: Web UI Pipeline Launch**

```gherkin
GIVEN the MLIP-AutoPipe Web UI application is running and accessible in a web browser
WHEN the user interacts with the form elements to define a valid set of pipeline parameters (e.g., selecting elements, setting temperature)
  AND the user clicks the "Run Pipeline" button
THEN a background process for the pipeline should start without any errors showing in the UI
  AND the user should be able to see a progress indicator on the page
  AND after the process finishes, a file named "results.db" should exist in the configured output directory
```

### **UAT-C2-003: Hybrid MD/MC Engine Verification for Alloys**

```gherkin
GIVEN a configuration file "config_mc.yaml" with "exploration.enable_mc" set to true
  AND an initial structure file "ordered_alloy.xyz" containing a perfectly layered, ordered alloy
WHEN the user runs the pipeline, providing "ordered_alloy.xyz" as the starting point
THEN the pipeline should execute and complete successfully
  AND when the final structures in the output "results.db" are visualized
  THEY should show a clearly disordered, mixed-phase alloy, indicating that atomic swaps occurred
```

### **UAT-C2-004: Web UI Feedback and Visualization**

```gherkin
GIVEN the Web UI is running and the user has just clicked the "Run Pipeline" button to start a new job
WHEN the backend pipeline is processing the request
THEN the main area of the Web UI should display a status indicator, such as a "Running..." message or a loading spinner
  AND WHEN the pipeline job is complete
  THEN the status indicator should disappear and be replaced by a "Completed" message
  AND a component on the page, such as a py3Dmol frame, should render a 3D view of an atom from the results
```