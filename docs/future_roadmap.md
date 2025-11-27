# Future Roadmap: Advanced GPIO State Reconstruction

## Objective
Achieve 100% accuracy in predicting the **Post-BIOS Initialization State** of GPIOs by correctly modeling how the BIOS applies configuration tables. This aims to bridge the gap between the **Static Binary Data** (what `bios2gpio` sees) and the **Runtime Hardware State** (what `inteltool` sees).

## 1. State Definitions & Taxonomy
To solve the "mismatch" problem, we must distinguish between three distinct states:

1.  **Reset State (Hardware Default)**
    -   The state of GPIO pads immediately after platform reset (e.g., `PLTRST#`).
    -   *Source*: Datasheet defaults (usually GPIO/Input).
    -   *Relevance*: The baseline before any software runs.

2.  **Static Configuration (The "Base" Tables)**
    -   The raw configuration data stored in the BIOS binary.
    -   *Current Status*: `bios2gpio` successfully extracts these. We found 35 candidates.
    -   *Problem*: We currently pick *one* "winner". However, the BIOS likely applies a "Base" table and then applies "Deltas" or selects different tables for different SKUs.

3.  **Post-Init State (The Goal)**
    -   The state of GPIOs after the BIOS (FSP + Board Code) has finished initialization but *before* the OS loads.
    -   *Composition*: `Base Table` + `Delta Tables` + `Dynamic Logic` (e.g., SKU detection).
    -   *Target*: This is what we want to generate.

4.  **Runtime State (The Reference)**
    -   The state read from hardware registers by `inteltool` on a running OS.
    -   *Contains*: Post-Init State + OS Driver changes (e.g., driver claiming a pad).
    -   *Usage*: Our "Ground Truth" for verification.

## 2. The "Layering" Hypothesis
The 62% match rate suggests that `bios2gpio` is finding the **Base Table**, but missing the **Deltas** that the BIOS applies later.

**Hypothesis**: The BIOS initializes GPIOs in layers:
1.  **Layer 1**: Apply massive "Base Table" (safe defaults).
2.  **Layer 2**: Apply "Community/Group Specific" tables (functionality).
3.  **Layer 3**: Apply "Board/SKU Specific" overrides (deltas).

**Evidence**:
-   We found 35 physical tables.
-   The "Winner" (Score 156) mismatches `GPP_I6`.
-   Another table (Score 132) *matches* `GPP_I6`.
-   This implies the correct state is a **composition** of these tables.

## 3. Implementation Plan (Next Conversation)

### Phase 1: Delta Analysis
**Goal**: Determine if the "rejected" tables contain the missing correct values.
-   **Action**: Create a tool to "diff" the 35 physical tables against the `inteltool` reference.
-   **Check**: Does the union of *all* tables cover 100% of the reference configuration?
    -   *If Yes*: The problem is **Table Selection/Composition**.
    -   *If No*: The configuration comes from **Code** (assembly), not tables.

### Phase 2: Heuristic Composition
**Goal**: Automate the reconstruction of the Post-Init state.
-   **Algorithm**:
    1.  Start with the "Base" table (largest/highest score).
    2.  Iteratively apply other tables as "patches" if they improve the match score against a *heuristic model* (or user-provided constraints).
    3.  Implement a `--compose` flag in `bios2gpio` to output the layered result.

### Phase 3: Ghidra-Assisted Logic (If Heuristics Fail)
**Goal**: Use static analysis to find the *actual* code flow.
-   **Action**: Update `bios2gpio`'s Ghidra script to:
    1.  Locate calls to `GpioConfigurePad` or `GpioSetPadConfig`.
    2.  Trace back the arguments to identify *which* tables are passed to these functions.
    3.  Map the execution flow: `Init(Table A) -> Init(Table B)`.

## 4. Deliverables
1.  **`analyze_deltas.py`**: A script to visualize differences between the 35 detected tables and the reference.
2.  **`bios2gpio --compose`**: Updated tool that merges tables to produce a "Post-Init" prediction.
3.  **Final Verification**: A report showing >95% match between the "Composed" output and `inteltool`.
