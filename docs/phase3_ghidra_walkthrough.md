# Phase 3: Ghidra Integration - Progress Walkthrough

## Objective

Enhance Ghidra integration to find VGPIO_USB_0 and understand GPIO table application logic, achieving 367/367 (100%) accuracy.

## Work Completed

### 1. Analyzed Existing Infrastructure

**Found**:
- ✅ [ghidra_runner.py](file:///run/media/julian/ML2/Python/coreboot/coreboot/util/bios2gpio/ghidra_runner.py) - Wrapper to run Ghidra headless analysis
- ✅ [ghidra/scripts/find_gpio_mmio_loops.py](file:///run/media/julian/ML2/Python/coreboot/coreboot/util/bios2gpio/ghidra/scripts/find_gpio_mmio_loops.py) - Existing script to find MMIO write loops
- ✅ Integration in [bios2gpio.py](file:///run/media/julian/ML2/Python/coreboot/coreboot/util/bios2gpio/bios2gpio.py) with `--analyze-ghidra` flag
- ✅ Auto-detection of Ghidra installation at `util/bios2gpio/ghidra`

**Limitations of Current Implementation**:
- Only searches for MMIO write loops (generic pattern)
- No specific search for GPIO table references
- No search for hardcoded VGPIO_USB_0 configuration
- No JSON output parsing

### 2. Created Enhanced Ghidra Script

**File**: `ghidra/scripts/find_gpio_tables.py`

**Features**:
1. **VGPIO_USB_0 Search**:
   - Searches for constant `0x40000480` (expected DW0 value)
   - Tolerance of ±0x1000 to account for bitfield variations
   - Finds all code references to matching constants
   
2. **GPIO Function Detection**:
   - Identifies functions with GPIO-related keywords (gpio, pad, config, init, mmio)
   - Detects loops within functions (potential table iteration)
   - Reports function size and entry point

3. **JSON Output**:
   ```json
   {
     "vgpio_usb_0_candidates": [
       {
         "address": "0x12345678",
         "value": "0x40000480",
         "references": [
           {
             "function": "GpioInit",
             "address": "0x12340000",
             "type": "DATA_READ"
           }
         ]
       }
     ],
     "gpio_functions": [
       {
         "name": "ConfigureGpioPads",
         "address": "0x12350000",
         "has_loop": true,
         "size": 1024
       }
     ]
   }
   ```

### 3. Enhanced ghidra_runner.py

**Changes**:
1. Updated default script from `find_gpio_mmio_loops.py` to `find_gpio_tables.py`
2. Added JSON output parsing from `/tmp/ghidra_gpio_analysis.json`
3. Returns parsed results to caller (instead of just boolean)
4. Added `import json`

**New Return Value**:
- `None` - Analysis failed
- `True` - Analysis succeeded but no JSON output
- `dict` - Analysis succeeded with parsed JSON results

### 4. Integration Points

The enhanced Ghidra analysis can now be used in multiple ways:

**A. Standalone Analysis**:
```bash
python3 ghidra_runner.py path/to/module.efi
```

**B. Via bios2gpio**:
```bash
python3 bios2gpio.py --input E7D25IMS.1M0 --analyze-ghidra --output gpio.h
```

**C. Programmatic Use**:
```python
from ghidra_runner import run_ghidra_analysis

results = run_ghidra_analysis("PchInitDxe.efi")
if results and isinstance(results, dict):
    vgpio_candidates = results.get('vgpio_usb_0_candidates', [])
    for candidate in vgpio_candidates:
        print(f"Found VGPIO_USB_0 at {candidate['address']}: {candidate['value']}")
```

## Next Steps to Achieve 100% Accuracy

### Step 1: Run Enhanced Ghidra Analysis
```bash
# Extract UEFI modules and run Ghidra on GPIO-related modules
python3 bios2gpio.py --input E7D25IMS.1M0 --analyze-ghidra
```

### Step 2: Analyze Results
- Check `/tmp/ghidra_gpio_analysis.json` for VGPIO_USB_0 candidates
- Identify GPIO initialization functions
- Map table application order

### Step 3: Integrate with compose_gpio.py

**Option A: If VGPIO_USB_0 is found**:
```python
# Add hardcoded value to compose_gpio.py
if 'VGPIO_USB_0' in reference and 'VGPIO_USB_0' not in current_state:
    # Use value from Ghidra analysis
    current_state['VGPIO_USB_0'] = {
        'name': 'VGPIO_USB_0',
        'dw0': ghidra_results['vgpio_usb_0_value'],
        'dw1': 0x00000000,
        'mode': 'NF1',
        'reset': 'DEEP'
    }
```

**Option B: If VGPIO_USB_0 is not found**:
- Accept 366/367 as the practical limit
- Document that VGPIO_USB_0 is unused/disabled on this platform
- Or continue investigation with manual Ghidra GUI analysis

### Step 4: Implement Blind Composition Heuristics

Based on Ghidra findings, implement rules for table application:
- Community-based isolation
- Table ordering based on function call sequence
- Selective pad masking

## Testing Plan

1. **Test Ghidra Script**:
   ```bash
   # Run on a single module
   python3 ghidra_runner.py /path/to/extracted/module/body.bin
   cat /tmp/ghidra_gpio_analysis.json
   ```

2. **Test Full Integration**:
   ```bash
   # Run full analysis
   python3 bios2gpio.py --input E7D25IMS.1M0 --analyze-ghidra --calibrate-with msi_gpio.h
   ```

3. **Test Composition with Ghidra Results**:
   ```bash
   # Run composition with Ghidra metadata
   python3 compose_gpio.py --bios E7D25IMS.1M0 --reference msi_gpio.h --ghidra-results /tmp/ghidra_gpio_analysis.json
   ```

## Expected Outcomes

### Best Case (VGPIO_USB_0 Found):
- 367/367 (100%) accuracy
- Complete GPIO state reconstruction
- Blind composition capability

### Likely Case (VGPIO_USB_0 Not Found):
- 366/367 (99.7%) accuracy
- Confirmation that VGPIO_USB_0 is unused/disabled
- Documented limitation

### Minimum Case (Ghidra Analysis Issues):
- Fall back to Oracle Composition (366/367)
- Manual Ghidra GUI analysis as alternative
- Document findings for future improvement

## Files Modified

1. **Created**: `ghidra/scripts/find_gpio_tables.py` - Enhanced Ghidra analysis script
2. **Modified**: `ghidra_runner.py` - Added JSON parsing and updated default script
3. **Ready**: `compose_gpio.py` - Can integrate Ghidra results once available

## Current Status

✅ Enhanced Ghidra script created
✅ ghidra_runner.py updated
✅ Integration points identified
⏳ **Next**: Run enhanced Ghidra analysis on BIOS modules
⏳ **Next**: Parse results and integrate with composition logic
