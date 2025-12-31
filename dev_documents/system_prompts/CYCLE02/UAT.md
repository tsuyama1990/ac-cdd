# Cycle 02 User Acceptance Testing (UAT)

This document outlines the User Acceptance Testing scenarios for Cycle 02 of the MLIP-AutoPipe project. The focus of this cycle is on automating the initial stages of the workflow: expanding a minimal user configuration into a full set of parameters and automatically generating an initial set of diverse, physically relevant atomic structures. The success of this cycle is measured by the user's ability to achieve a complete, successful pipeline run starting from a vastly simplified input, thereby validating the core philosophy of "removing the expert from the loop."

## 1. Test Scenarios

| Scenario ID | Scenario Name                                      | Priority |
| :---------- | :------------------------------------------------- | :------- |
| UAT-C02-01  | Full Workflow from Minimal Alloy Configuration     | High     |
| UAT-C02-02  | Full Workflow from Minimal Covalent Configuration  | High     |
| UAT-C02-03  | Correctness of Heuristic DFT Parameter Expansion   | High     |
| UAT-C02-04  | User Override of Expanded Configuration            | Medium   |

---

### **Scenario UAT-C02-01: Full Workflow from Minimal Alloy Configuration**

**Description (Min 300 words):**
This is the primary "happy path" scenario for Cycle 02, testing the integration of all new components for a typical alloy system. The user's interaction should be drastically simplified compared to Cycle 01, which required a fully detailed configuration and a manually prepared database of structures. The user will create a minimal `input.yaml` file containing only the essential information for an alloy, for example, `system: {elements: ["Fe", "Pt"], composition: "FePt"}`. The goal is to verify that the system can take this high-level input and autonomously execute the entire pipeline developed to date, from configuration expansion and structure generation through to the final training of a potential. This test case is a comprehensive validation of the system's new intelligent front-end.

Upon invoking the pipeline with this minimal config, the `ConfigExpander` should first correctly identify the system as an 'alloy' by analyzing its constituent elements. It must then generate a complete `exec_config_dump.yaml` file, populating it with sensible, physically-based defaults for all necessary parameters, including DFT settings appropriate for the Fe-Pt system based on the SSSP protocol. Subsequently, the `StructureGenerator` must be triggered, automatically selecting and executing its SQS (Special Quasirandom Structures) algorithm to generate a set of initial alloy configurations that model random substitutional disorder. These generated structures must be saved to the database with the 'needs_labelling' status. From there, the workflow should proceed as established in Cycle 01: the new structures are labelled by the `LabellingEngine` and then used by the `TrainingEngine` to produce a final MLIP model file. A successful test run will demonstrate that the system can correctly chain together the configuration expansion, structure generation, labelling, and training modules into a single, seamless, and automated workflow, fulfilling the core objective of this cycle.

---

### **Scenario UAT-C02-02: Full Workflow from Minimal Covalent Configuration**

**Description (Min 300 words):**
This scenario serves as a crucial validation of the system's ability to handle different material types correctly and demonstrates the intelligence of the heuristic engine. It mirrors the previous scenario but targets a canonical covalent material, such as Silicon. The user will provide an even more minimal `input.yaml` containing only `system: {elements: ["Si"]}`. The purpose is to ensure that the system's internal logic correctly dispatches to the appropriate heuristic algorithms for both configuration and structure generation based on this simple change in chemistry. This test is vital for proving that the system is not a one-trick pony hardcoded for a single class of materials but possesses a degree of generalized "chemical intuition."

When the pipeline is executed with the Silicon input, the `ConfigExpander` must first identify Silicon as a 'covalent' material. This classification is the critical first step that should then influence the rest of the workflow. The `StructureGenerator`, instead of using the SQS method as in the alloy case, must now use the correct algorithm for covalent systems. For instance, it should apply a "Deep Rattling" (large random displacements) or a surrogate-model-based melt-quench protocol to a primitive Si crystal cell. This is designed to generate a diverse set of amorphised, defected, and strained structures that are important for capturing the strong, directional bonding in covalent materials. The rest of the pipeline should then proceed as normal, labelling these specific structures and training a potential. A successful test is defined by the system generating the correct type of initial structures for a covalent system, proceeding through the entire workflow without error, and producing a final MLIP. This validates the modularity and intelligence of the `StructureGenerator` and `ConfigExpander`.

---

## 2. Behavior Definitions

**Scenario: UAT-C02-01 - Full Workflow from Minimal Alloy Configuration**

```gherkin
GIVEN a user has created a minimal 'input.yaml' file in their working directory with the content:
  """
  system:
    elements: ["Fe", "Pt"]
    composition: "FePt"
  """
AND the user has an empty ASE database file named 'structures.db' in the same directory.
WHEN the user executes the command: `mlip-pipe run --config input.yaml`.
THEN the system should first create a detailed 'exec_config_dump.yaml' file in the working directory.
AND this 'exec_config_dump.yaml' file should contain a field `structure_type: 'alloy'`.
AND the Structure Generator module should log a message indicating that it is executing the SQS algorithm.
AND after the generation step, the 'structures.db' file should contain at least 10 new atomic structures, all with the status 'needs_labelling'.
AND the Labelling Engine should subsequently be invoked and process these new structures.
AND the Training Engine should be invoked with the resulting labelled data.
AND a new file named 'model.ace' should be created in the output directory.
AND the process should terminate with a success message.
```

---

**Scenario: UAT-C02-02 - Full Workflow from Minimal Covalent Configuration**

```gherkin
GIVEN a user has created a minimal 'input.yaml' file with the content:
  """
  system:
    elements: ["Si"]
  """
AND the user has an empty ASE database file 'structures.db'.
WHEN the user executes the command: `mlip-pipe run --config input.yaml`.
THEN the system should create a detailed 'exec_config_dump.yaml' file.
AND this 'exec_config_dump.yaml' should contain a field `structure_type: 'covalent'`.
AND the Structure Generator module should log a message indicating that it is executing the "rattling" algorithm.
AND after the generation step, the 'structures.db' file should contain at least 10 new atomic structures.
AND the Labelling Engine should be invoked to process these structures.
AND a final MLIP file named 'model.ace' should be created in the output directory.
AND the process should terminate successfully.
```

---

**Scenario: UAT-C02-03 - Correctness of Heuristic DFT Parameter Expansion**

```gherkin
GIVEN a user has a minimal 'input.yaml' for "GaN" (Gallium Nitride).
AND the embedded SSSP Precision protocol data specifies a recommended wavefunction cutoff of 80 Ry for Ga and 55 Ry for N.
WHEN the user runs the pipeline, triggering the `ConfigExpander`.
THEN an 'exec_config_dump.yaml' file should be generated.
AND within this file, under the 'dft_compute' section, the value for the key 'ecutwfc' must be 80.0 (or a float very close to it), as it should be determined by the maximum of the requirements for the constituent elements.
AND the 'pseudopotentials' field in the same section must be a dictionary containing the correct SSSP filenames as values for the keys "Ga" and "N".
```

---

**Scenario: UAT-C02-04 - User Override of Expanded Configuration**

```gherkin
GIVEN the heuristic engine's default smearing degauss value is 0.02 Ry.
AND a user, who is an expert, wants to use a different value for a specific calculation.
AND the user creates an 'input.yaml' file with an explicit override:
  """
  system:
    elements: ["Si"]
  dft_compute:
    degauss: 0.05
  """
WHEN the system runs the `ConfigExpander` on this input.
THEN the generated 'exec_config_dump.yaml' file should be created successfully.
AND the value for the 'degauss' key in the final configuration file must be exactly 0.05, reflecting the user's explicit choice.
AND all other heuristic parameters that were not specified by the user, like 'ecutwfc', should still be generated automatically according to the standard heuristics.
```
