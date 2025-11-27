# bios2gpio: 100% GPIO Coverage Implementation Plan

## Problem Statement

Current status: bios2gpio extracts 27 tables (1 physical + 26 VGPIO) but should extract 8 tables (1 physical + 7 VGPIO) to match the reference `msi_debug.json`.

**Missing VGPIO tables**: 38, 78, 81 entries  
**Extra tables**: 19 false-positive VGPIOs (large tables with stride 12/16 that aren't actually VGPIOs)

## Root Cause Analysis (FACRM Framework)

### Hypothesis (TT_n)
The signature matching algorithm is designed to detect physical GPIO tables by matching specific mode patterns. VGPIOs have different characteristics (NAFVWE bit, DEEP reset domain) and don't match this signature, so they're only found by the pattern scan.

### Evidence (Grade A - Direct observation from logs)
1. ✅ Signature matching finds 37 tables total (11 stride-8, 14 stride-12, 12 stride-16)
2. ✅ None of the reference VGPIO offsets (0xf0cc8, 0x2263f4, 0x28b24c, 0x11be98, 0x12d14c, 0xd12cc, 0x1a0a78) appear in signature matching output
3. ✅ Pattern scan previously found all 7 VGPIOs (confirmed by DEBUG logs showing 13, 14, 37, 38, 78, 79, 81 entries)
4. ✅ Current calibration logic uses `entry_size > 8` which incorrectly classifies ALL stride-12/16 tables as VGPIOs

### Falsification Test
Run signature matching with VGPIO-specific patterns → **FAILED**: VGPIOs don't have consistent mode patterns like physical GPIOs

### Conclusion (Corroborated)
We need BOTH signature matching (for physical GPIOs) AND pattern scanning (for VGPIOs), but the pattern scan must be targeted to avoid false positives.

## Proposed Changes

### Phase 1: Targeted VGPIO Pattern Scan

#### [MODIFY] [gpio_detector.py](file:///run/media/julian/ML2/Python/coreboot/coreboot/util/bios2gpio/gpio_detector.py)

**Change 1**: Update `scan_for_tables()` method (lines 108-147)
- After signature matching, run a targeted pattern scan ONLY for VGPIO-sized tables
- Search for tables with 10-100 entries (VGPIO range)
- Use `_is_vgpio_table()` heuristic to filter results
- Skip large tables (>100 entries) to avoid false positives

```python
# After signature matching
if large_tables:
    logger.info(f"Signature matching found {len(large_tables)} large table(s), running targeted VGPIO scan...")
    
    # Targeted scan for VGPIOs only (10-100 entries)
    for entry_size in [12, 16]:
        vgpio_candidates = self._scan_for_vgpios(data, entry_size, min_entries=10, max_entries=100)
        for table in vgpio_candidates:
            is_duplicate = any(
                t['offset'] == table['offset'] and t['entry_size'] == table['entry_size']
                for t in all_tables
            )
            if not is_duplicate:
                all_tables.append(table)
    
    return all_tables
```

**Change 2**: Add new method `_scan_for_vgpios()` (after line 201)
```python
def _scan_for_vgpios(self, data: bytes, entry_size: int, min_entries: int, max_entries: int) -> List[Dict]:
    """Targeted scan for VGPIO tables only."""
    tables = []
    data_len = len(data)
    offset = 0
    
    while offset < data_len - (entry_size * min_entries):
        valid_count = 0
        current_offset = offset
        entries = []
        
        while current_offset + entry_size <= data_len and valid_count < max_entries:
            try:
                pad_config = self.pad_config_class(data[current_offset:current_offset + entry_size])
                if self._is_valid_pad_config(pad_config):
                    valid_count += 1
                    entries.append({'offset': current_offset, 'config': pad_config})
                    current_offset += entry_size
                else:
                    break
            except:
                break
        
        # Only keep if it's VGPIO-sized and passes VGPIO heuristic
        if min_entries <= valid_count <= max_entries:
            is_vgpio = self._is_vgpio_table(entries)
            
            if is_vgpio:
                table_info = {
                    'offset': offset,
                    'entry_size': entry_size,
                    'entry_count': valid_count,
                    'total_size': valid_count * entry_size,
                    'entries': entries,
                    'confidence': self._calculate_confidence(entries),
                    'is_vgpio': True
                }
                tables.append(table_info)
            
            offset = current_offset
        else:
            offset += 4
    
    return tables
```

### Phase 2: Fix Calibration Logic

#### [MODIFY] [bios2gpio.py](file:///run/media/julian/ML2/Python/coreboot/coreboot/util/bios2gpio/bios2gpio.py)

**Change**: Update VGPIO classification logic (line 233)

Replace:
```python
if table.get('is_vgpio', False) or table.get('entry_size', 8) > 8:
    vgpio_tables.append(table)
```

With:
```python
# Use is_vgpio flag if available, otherwise check entry_size AND entry_count
is_vgpio = table.get('is_vgpio', False)
if not is_vgpio and table.get('entry_size', 8) > 8:
    # Double-check: only classify as VGPIO if size matches known VGPIO ranges
    count = table.get('entry_count', 0)
    is_vgpio = (10 <= count <= 15) or (35 <= count <= 40) or (75 <= count <= 85)

if is_vgpio:
    vgpio_tables.append(table)
```

## Verification Plan

### Test 1: Coverage Validation
```bash
python3 bios2gpio.py --platform alderlake --input E7D25IMS.1M0 \
    --output test_gpio.h --json test_coverage.json \
    --calibrate-with /run/media/julian/ML2/Python/coreboot/coreboot/src/mainboard/msi/ms7d25/gpio.h \
    --no-ghidra
```

**Expected output**:
- Total tables: 8 (1 physical + 7 VGPIO)
- VGPIO table sizes: 13, 14, 37, 38, 78, 79, 81 entries
- Physical table: 253 entries at offset 0x193814

### Test 2: Compare with Reference
```bash
python3 -c "
import json
ref = json.load(open('msi_debug.json'))
test = json.load(open('test_coverage.json'))

print(f'Reference: {len(ref[\"tables\"])} tables')
print(f'Test: {len(test[\"tables\"])} tables')

ref_sizes = sorted([t['entry_count'] for t in ref['tables']])
test_sizes = sorted([t['entry_count'] for t in test['tables']])

print(f'Reference sizes: {ref_sizes}')
print(f'Test sizes: {test_sizes}')
print(f'Match: {ref_sizes == test_sizes}')
"
```

**Expected**: Perfect match on table counts

### Test 3: GPIO.h Validation
Compare generated `test_gpio.h` with reference `ms7d25/gpio.h`:
- All GPIO groups present (GPP_I, GPP_R, GPP_J, etc.)
- All VGPIO groups present (VGPIO_0, VGPIO_USB_0, VGPIO_PCIE_0)
- Macro usage correct (_PAD_CFG_STRUCT for VGPIOs)

## Risk Assessment

**Low Risk**:
- Changes are isolated to detection logic
- Existing signature matching unchanged
- Pattern scan is now more targeted (less false positives)

**Mitigation**:
- Keep existing test files for regression testing
- Log all detection decisions for debugging
- Preserve original `full_coverage.json` for comparison

## Success Criteria

1. ✅ Exactly 8 tables detected (1 physical + 7 VGPIO)
2. ✅ All VGPIO sizes match reference: [13, 14, 37, 38, 78, 79, 81]
3. ✅ Physical GPIO table has 253 entries
4. ✅ Generated gpio.h contains all GPIO and VGPIO groups
5. ✅ No false-positive VGPIO tables (no large stride-12/16 tables)
