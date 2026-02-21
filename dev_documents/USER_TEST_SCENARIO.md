# User Test Scenarios & Success Criteria: Fe/Pt Deposition on MgO

## 1. Grand Challenge: Hetero-epitaxial Growth & Ordering
**Goal**: Simulate the deposition of Fe and Pt atoms onto an MgO(001) substrate, observe the nucleation of clusters, and visualize the L10 ordering process using a combination of MD and Adaptive Kinetic Monte Carlo (aKMC).

## 2. Scientific Workflow Steps (The "Aha!" Moments)
The tutorial must guide the user through the following phases:

### Phase 1: Divide & Conquer Training
* **Concept**: Do not train everything at once.
* **Step A**: Train MgO bulk & surface (ensure rigid substrate).
* **Step B**: Train Fe-Pt bulk alloy (reproduce L10 phase stability).
* **Step C**: Train the Interface. Place Fe/Pt clusters on MgO slab, perform DFT, and learn the adhesion energy.
* **Success Criteria**: The potential predicts correct adhesion energy and does not explode when Fe hits MgO.

### Phase 2: Dynamic Deposition (MD)
* **Action**: Use LAMMPS `fix deposit` to drop Fe and Pt atoms alternately onto the MgO substrate at high temperature (e.g., 600K).
* **Observation**: Atoms should migrate on the surface and form small islands (nucleation), not sink *into* the MgO (check core-repulsion).

### Phase 3: Long-Term Ordering (aKMC)
* **Action**: Take the disordered cluster formed in Phase 2 and pass it to EON (aKMC).
* **Observation**: Overcome time-scale limitations to observe the Fe and Pt atoms rearranging into a chemically ordered structure (L10-like local order) inside the cluster.

## 3. Visualization Requirements
* **Artifacts**: The notebook must generate:
    * Snapshot of the MgO substrate with deposited Fe/Pt islands.
    * Cross-section view showing the interface.
    * Color-coded view of Fe vs Pt to show mixing/ordering status (e.g., utilizing OVITO's modifier logic or ASE constraints).

## 4. Execution Constraints (Mock vs Real)
* **CI/CD Mode**: Use a tiny system (e.g., small unit cell, 10 deposited atoms, 5 aKMC steps) or pre-calculated data to finish within 5 minutes.
* **User Mode**: Full scale (large slab, 500 atoms deposition, 1000+ aKMC steps).