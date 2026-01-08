# User Acceptance Testing (UAT): MLIP Structure Generator - CYCLE02

This document outlines the User Acceptance Testing (UAT) plan for the second development cycle of the MLIP Structure Generator. In this cycle, we introduce a suite of advanced features that greatly enhance the tool's power, scientific accuracy, and overall accessibility. This UAT plan is designed as a hands-on, tutorial-style guide for users to verify these powerful new capabilities. We will explore the new Web User Interface (UI), the "smart" Farthest Point Sampling (FPS) algorithm for creating maximally diverse datasets, and the generation of more complex and scientifically relevant materials. As with the previous cycle, using a Jupyter Notebook is highly recommended for the analytical parts of this UAT, as it allows for deeper, programmatic inspection and visualisation of the results, providing a richer and more educational testing experience. These scenarios are designed not just to validate the software, but to teach the user how to leverage its most powerful new features for their own research.

## 1. Test Scenarios

These scenarios are designed to validate the major new features introduced in CYCLE02. They build upon the core functionality that was verified in the first cycle and test the new functionalities in realistic, scientifically-motivated workflows.

### **Scenario ID: UAT-C02-01**
**Priority: High**
**Title: Generate an Ionic Crystal (NaCl) Dataset using the Web UI**

**Description (Min 300 words):**
This is the flagship scenario for CYCLE02, as it is designed to test two of the most significant new features simultaneously: the new Web User Interface and the `IonicGenerator`. The primary purpose of this test is to verify that a user can successfully define, execute, and monitor a data generation job for a complex material system entirely through an intuitive, graphical, browser-based interface. This marks the transition of the tool from a specialist command-line utility to a platform that is accessible to a much broader audience. We will use Sodium Chloride (NaCl), a classic ionic crystal, as our test case. The user's journey will begin by launching the Web UI via the `main_gui.py` script. They will then use the interactive widgets—such as dropdown menus and text input fields—to select the `ionic` generator, specify the elements 'Na' and 'Cl' along with their correct integer oxidation states (+1 and -1), and configure a short hybrid MD/MC simulation, enabling the new atomic swap move feature.

This scenario provides a comprehensive, end-to-end validation of the entire GUI workflow. It confirms that the frontend UI correctly translates user inputs from various widgets into a valid, structured configuration object that can be processed by the backend pipeline. On the backend, it rigorously tests the new `IonicGenerator` and its most critical feature: the charge-balancing logic that ensures a physically valid, neutral starting structure. Furthermore, it validates the new hybrid MD/MC exploration mode and, crucially, the `Charge Safety` feature, which should prevent the simulation from attempting physically impossible swaps between Na+ and Cl- ions. During the run, the user will be able to monitor the job's progress in real-time within the UI's status panel. Success for this test is defined by the job completing without any errors and the user being able to visualise a resulting NaCl structure directly in the UI's integrated 3D molecule viewer. This provides a seamless and intuitive "idea-to-insight" experience, confirming that the tool is now accessible to users who are not comfortable with, or do not need the complexity of, the command line.

### **Scenario ID: UAT-C02-02**
**Priority: High**
**Title: Verify the "Smart" Selection of Structures with Farthest Point Sampling (FPS)**

**Description (Min 300 words):**
This scenario is designed to validate the effectiveness and scientific value of the new Farthest Point Sampling (FPS) algorithm. The goal is to provide the user with tangible, quantitative proof that FPS produces a more structurally diverse—and therefore more valuable—dataset compared to the simple random sampling method available in CYCLE01. This is a critical test, as "smart sampling" is one of the key promises of the platform. The user will perform a carefully controlled two-stage experiment. First, they will run a standard MD simulation for a simple system (like the Silicon crystal from UAT-C01-02), configuring it to use the basic `random` sampler. Second, they will run the *exact same* simulation (from the same seed structure, with the same MD parameters), but this time they will switch the sampling method in the configuration to `fps`. This controlled experiment ensures that the only variable is the sampling algorithm itself.

This test does not have a simple pass/fail outcome based on a file being created; instead, it's an analytical verification that the user will perform, ideally within a Jupyter Notebook where they can combine code execution with analysis and plotting. After generating both datasets (`si_random.db` and `si_fps.db`), the user will be guided through a simple analysis script. Using a few lines of Python code, they will load the structures from both database files. Then, leveraging the new `descriptors.py` utility, they will calculate the SOAP (Smooth Overlap of Atomic Positions) descriptors for all structures in each dataset. The final step is to compute a measure of diversity, such as the average pairwise Euclidean distance between these descriptor vectors. The expected and verifiable outcome is that the average distance for the FPS-generated dataset is significantly higher than for the randomly generated one. This provides strong, quantitative evidence that the FPS algorithm is working as intended and is successfully selecting a more geometrically diverse set of structures, which is the core promise of this advanced feature. This scenario empowers the user to understand *why* FPS is a superior method and gives them the tools to verify its efficacy on their own systems.

### **Scenario ID: UAT-C02-03**
**Priority: Medium**
**Title: Verify Automatic Thermodynamic Ensemble Switching for a Surface System**

**Description (Min 300 words):**
This scenario tests the "intelligence" and automation of the newly enhanced MD engine. Its purpose is to verify that the system can correctly identify a surface (or slab) configuration—a common and important type of simulation in catalysis and electronics—and automatically apply the correct thermodynamic ensemble (NVT) to prevent well-known simulation artifacts, such as the artificial collapse or expansion of the vacuum layer under pressure coupling. The user will be instructed to use one of the new advanced generators, such as the `InterfaceGenerator`, to create a structure that has a vacuum layer along one of the crystallographic axes (e.g., a slab of Aluminum). They will then configure the exploration to use the new `"auto"` ensemble mode, which delegates the choice of ensemble to the simulation engine itself.

The key to this test is not just that the simulation runs, but that it runs with the *correct physical model*. The user will need to inspect the application's log output after the run is complete. The test is considered successful if the log file contains a specific, clear message indicating that a vacuum was detected and that the simulation ensemble was automatically switched to NVT for the duration of the run. This confirms that the `detect_vacuum` utility in the physics module is working correctly and is properly integrated as a decision-making component within the `MDEngine`. For a more advanced and visual verification in a Jupyter Notebook, the user could load the full trajectory from the simulation and plot the length of the simulation box's z-axis (the axis with the vacuum) over the course of the simulation. For a correctly run NVT simulation, this value should remain constant (within very small thermal fluctuations). An incorrectly run NPT simulation would show it fluctuating wildly or collapsing to zero. This provides deep, visual validation that the automation is not only a convenience feature but is essential for scientific correctness.

## 2. Behavior Definitions

The following are Gherkin-style (GIVEN/WHEN/THEN) definitions that describe the expected behavior for each of the advanced test scenarios. This structured format provides an unambiguous contract for the functionality being delivered, ensuring that developers and users have a shared understanding of what constitutes a successful outcome.

---

**Scenario: UAT-C02-01 - Generate an Ionic Crystal (NaCl) Dataset using the Web UI**

*   **GIVEN** I have successfully launched the MLIP Structure Generator Web UI in my web browser using the `main_gui.py` script.
*   **AND** I have used the UI's navigation controls to select the `ionic` generator from the list of available generator types.
*   **AND** I have used the interactive widgets to enter the elements `Na` with a `charge` of `1` and `Cl` with a `charge` of `-1`.
*   **AND** I have used the UI to configure a short hybrid MD/MC simulation, enabling the "swap move" feature.
*   **AND** I have set the final output database name to `nacl_dataset.db` in the appropriate text field.
*   **WHEN** I click the "Run Generation" button in the Web UI.
*   **THEN** the job should start execution in a background process, and the UI should immediately update to show a "Running" or "In Progress" status, without freezing the browser.
*   **AND** the simulation should run to completion without any error messages being displayed in the UI's log panel.
*   **AND** upon completion, the UI status should update to "Completed" or "Success".
*   **AND** a new file named `nacl_dataset.db` should be created in the application's output directory on the server.
*   **AND** the UI's integrated 3D molecule viewer should automatically load and display one of the final, valid NaCl structures from the newly created database, confirming the entire workflow was successful.

---

**Scenario: UAT-C02-02 - Verify the "Smart" Selection of Structures with Farthest Point Sampling (FPS)**

*   **GIVEN** I have two YAML configuration files, `si_random_config.yaml` and `si_fps_config.yaml`, that are identical in every way (MD parameters, number of steps, etc.) except for the `sampling.method` key, which is `random` in one and `fps` in the other.
*   **AND** I have successfully run the generator pipeline from the command line using both of these configuration files, producing two distinct database files: `si_random.db` and `si_fps.db`.
*   **WHEN** I open a Jupyter Notebook and execute a prepared analysis script that performs the following actions:
    1.  Loads all of the ASE `Atoms` objects from both `si_random.db` and `si_fps.db`.
    2.  Calculates the SOAP structural descriptors for every structure in each of the two sets.
    3.  For each set, calculates the average pairwise Euclidean distance between all of the descriptor vectors within that set.
*   **THEN** the calculated average distance for the structures originating from `si_fps.db` should be measurably and significantly larger than the average distance calculated for the structures from `si_random.db`.
*   **AND** both of the database files should contain the same total number of structures, as specified in their shared configuration.

---

**Scenario: UAT-C02-03 - Verify Automatic Ensemble Switching for a Surface System**

*   **GIVEN** I have a valid YAML configuration file that uses the `interface` generator to create an Aluminum slab structure, which is known to have a vacuum layer along the z-axis.
*   **AND** the configuration file's exploration section has the `ensemble` parameter explicitly set to the string `auto`.
*   **AND** I have configured the application's logging settings to write all output to a file named `simulation.log`.
*   **WHEN** I execute the generator pipeline from the command line using this specific configuration file.
*   **THEN** the application should run the entire pipeline to completion without any errors.
*   **AND** a log file named `simulation.log` should be created in the output directory.
*   **AND** when I inspect the contents of the log file, it must contain a clear and specific line of text that explicitly states "Vacuum detected. Switching to NVT ensemble for this simulation."
