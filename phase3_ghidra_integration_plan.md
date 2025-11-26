# Phase 3: Ghidra Integration for 100% Accuracy

## Objective

Achieve **367/367 (100%)** accuracy in GPIO state prediction by:
1. Reverse-engineering BIOS GPIO initialization code using Ghidra
2. Understanding table application logic (layering, masking, ordering)
3. Finding the missing `VGPIO_USB_0` configuration
4. Implementing "blind composition" heuristics that work without a reference file

## User Review Required

> [!IMPORTANT]
> **Ghidra Automation Strategy**
> This plan uses Ghidra's headless analyzer and Python scripting API to automate the reverse engineering process. The workflow will:
> - Extract UEFI modules from BIOS
> - Load them into Ghidra programmatically
> - Run analysis scripts to find GPIO initialization functions
> - Extract table references and application logic
> 
> **Alternative**: If you prefer manual Ghidra analysis with GUI, please let me know and I'll provide a guided walkthrough instead.

> [!WARNING]
> **VGPIO_USB_0 May Not Exist**
> If `VGPIO_USB_0` is truly unused on this platform (MSI Z690), we may need to accept 366/367 as the practical limit. The Ghidra analysis will help determine this definitively.

## Proposed Changes

### Component 1: Ghidra Analysis Infrastructure

#### [NEW] `ghidra_analyzer.py`
Python script to automate Ghidra headless analysis:
- Extract UEFI modules using `UEFIExtractor`
- Launch Ghidra headless analyzer on target modules
- Run custom Ghidra scripts to find GPIO-related functions
- Parse Ghidra output to extract table references and logic

#### [NEW] `ghidra_scripts/find_gpio_init.py`
Ghidra Python script to identify GPIO initialization code:
- Search for GPIO signature patterns (0x40000480, etc.)
- Find cross-references to detected GPIO tables
- Identify function call chains for GPIO configuration
- Extract table application order and masking logic

#### [NEW] `ghidra_scripts/extract_vgpio_usb_0.py`
Ghidra Python script specifically targeting VGPIO_USB_0:
- Search for hardcoded GPIO configurations
- Look for dynamic computation of GPIO values
- Find USB-related initialization code
- Extract any VGPIO_USB_0 references

---

### Component 2: Blind Composition Implementation

#### [MODIFY] [compose_gpio.py](file:///run/media/julian/ML2/Python/coreboot/coreboot/util/bios2gpio/compose_gpio.py)
Add blind composition mode based on Ghidra findings:
- Implement community-based isolation (don't mix communities)
- Add table priority/ordering based on discovered application sequence
- Implement pad group masking rules
- Add `--mode` flag: `oracle` (current) vs `blind` (new)

**Key additions**:
```python
def compose_blind(parsed_tables, ghidra_metadata):
    """
    Compose GPIO state without reference using Ghidra-derived rules.
    
    Args:
        parsed_tables: All detected GPIO tables
        ghidra_metadata: Table application rules from Ghidra analysis
    
    Returns:
        Composed GPIO state
    """
    # Apply tables in discovered order with community masking
    # Use priority hints from Ghidra
    # Handle VGPIO_USB_0 from hardcoded value if found
```

---

### Component 3: Integration with bios2gpio

#### [MODIFY] [bios2gpio.py](file:///run/media/julian/ML2/Python/coreboot/coreboot/util/bios2gpio/bios2gpio.py)
Integrate composition logic into main tool:
- Add `--compose` flag to enable composition mode
- Add `--ghidra-metadata` flag to provide Ghidra analysis results
- Generate composed [gpio.h](file:///run/media/julian/ML2/Python/coreboot/coreboot/util/bios2gpio/msi_gpio.h) output
- Compare against calibration file if provided

---

## Verification Plan

### Automated Tests

1. **Ghidra Analysis Validation**:
```bash
# Run Ghidra analysis on BIOS
python3 ghidra_analyzer.py --bios E7D25IMS.1M0 --output ghidra_results.json

# Verify GPIO functions were found
python3 -c "import json; data=json.load(open('ghidra_results.json')); print(f'Found {len(data[\"gpio_functions\"])} GPIO functions')"
```

2. **Blind Composition Test**:
```bash
# Run blind composition
python3 compose_gpio.py --bios E7D25IMS.1M0 --mode blind --ghidra-metadata ghidra_results.json

# Compare against reference
python3 compose_gpio.py --bios E7D25IMS.1M0 --mode blind --ghidra-metadata ghidra_results.json --reference msi_gpio.h
```

3. **End-to-End Integration**:
```bash
# Generate gpio.h using composition
python3 bios2gpio.py --bios E7D25IMS.1M0 --compose --ghidra-metadata ghidra_results.json --output generated_gpio.h

# Compare with reference
diff -u msi_gpio.h generated_gpio.h
```

### Manual Verification

1. **Ghidra GUI Review**: Open Ghidra project and manually verify identified GPIO functions
2. **Code Logic Validation**: Review extracted table application logic for correctness
3. **VGPIO_USB_0 Investigation**: Confirm whether it's hardcoded, dynamic, or unused

---

## Implementation Steps

### Step 1: Set Up Ghidra Environment
- Verify Ghidra installation and headless analyzer
- Create Ghidra project directory structure
- Test basic headless analysis workflow

### Step 2: Develop Ghidra Analysis Scripts
- Create `find_gpio_init.py` to locate GPIO functions
- Create `extract_vgpio_usb_0.py` for targeted search
- Test scripts on extracted UEFI modules

### Step 3: Build Ghidra Automation
- Implement `ghidra_analyzer.py` wrapper
- Integrate with `UEFIExtractor`
- Parse and structure Ghidra output

### Step 4: Implement Blind Composition
- Add community isolation logic to [compose_gpio.py](file:///run/media/julian/ML2/Python/coreboot/coreboot/util/bios2gpio/compose_gpio.py)
- Implement table ordering based on Ghidra metadata
- Add VGPIO_USB_0 handling (hardcoded value or skip)

### Step 5: Integration and Testing
- Add `--compose` flag to [bios2gpio.py](file:///run/media/julian/ML2/Python/coreboot/coreboot/util/bios2gpio/bios2gpio.py)
- Run end-to-end tests
- Validate against reference file

### Step 6: Documentation
- Document Ghidra workflow
- Create user guide for blind composition
- Update README with new features

---

## Expected Outcomes

1. **Ghidra Analysis Results**:
   - JSON file containing GPIO function addresses
   - Table application order and logic
   - VGPIO_USB_0 configuration (if found)

2. **Blind Composition**:
   - 366-367/367 accuracy without reference file
   - Automated composition integrated into `bios2gpio`

3. **VGPIO_USB_0 Resolution**:
   - Either found via Ghidra (100% accuracy)
   - Or confirmed as unused (366/367 accepted as limit)

---

## Timeline Estimate

- **Ghidra Setup & Scripting**: 2-3 hours
- **Analysis & Debugging**: 3-4 hours
- **Blind Composition Implementation**: 2-3 hours
- **Integration & Testing**: 1-2 hours
- **Total**: 8-12 hours of development time

---

## Risks and Mitigations

**Risk**: Ghidra analysis may not find clear table application logic
**Mitigation**: Fall back to heuristic rules based on community structure

**Risk**: VGPIO_USB_0 may be in obfuscated or encrypted code
**Mitigation**: Accept 366/367 as practical limit, document limitation

**Risk**: Ghidra headless mode may have issues with UEFI PE32 files
**Mitigation**: Use manual Ghidra GUI analysis as fallback
