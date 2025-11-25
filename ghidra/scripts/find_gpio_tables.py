# -*- coding: utf-8 -*-
#@category AlderLake
# Headless script: finds GPIO table references and hardcoded GPIO configurations
#
# This script searches for:
# 1. References to detected GPIO table offsets
# 2. Hardcoded GPIO configurations (especially VGPIO_USB_0)
# 3. Table application order and logic
#
# Usage (Headless):
# analyzeHeadless <project_dir> <project_name> \
#   -import PchInitDxe.efi \
#   -scriptPath . \
#   -postScript find_gpio_tables.py <table_offsets_file>

from ghidra.program.model.symbol import SymbolType
from ghidra.program.model.mem import MemoryAccessException
from ghidra.program.model.listing import CodeUnit
from ghidra.app.decompiler import DecompInterface, DecompileOptions
from ghidra.util.task import ConsoleTaskMonitor
import sys
import json

# Expected VGPIO_USB_0 configuration
# PAD_FUNC(NF1) | PAD_RESET(DEEP) | PAD_CFG0_NAFVWE_ENABLE
# Mode: NF1 (1), Reset: DEEP (1), NAFVWE: bit 7
VGPIO_USB_0_EXPECTED_DW0 = 0x40000480  # Approximate

def search_for_constant(value, tolerance=0x100):
    """
    Search for a constant value in the program.
    Returns list of addresses where the constant appears.
    """
    results = []
    memory = currentProgram.getMemory()
    
    # Search in all memory blocks
    for block in memory.getBlocks():
        if not block.isInitialized():
            continue
            
        addr = block.getStart()
        end = block.getEnd()
        
        while addr.compareTo(end) < 0:
            try:
                # Read 4 bytes as little-endian int
                val = memory.getInt(addr) & 0xFFFFFFFF
                
                # Check if it matches (with tolerance for bitfield variations)
                if abs(val - value) <= tolerance:
                    results.append((addr, val))
                    
            except MemoryAccessException:
                pass
            
            addr = addr.add(4)
    
    return results

def find_data_references(address):
    """Find all code references to a data address."""
    refs = []
    ref_mgr = currentProgram.getReferenceManager()
    
    references = ref_mgr.getReferencesTo(address)
    for ref in references:
        from_addr = ref.getFromAddress()
        func = getFunctionContaining(from_addr)
        if func:
            refs.append({
                'function': func.getName(),
                'address': str(from_addr),
                'type': str(ref.getReferenceType())
            })
    
    return refs

def analyze_function_for_loops(func):
    """
    Analyze a function to detect loops and table application patterns.
    """
    from ghidra.program.model.block import BasicBlockModel
    
    block_model = BasicBlockModel(currentProgram)
    blocks = block_model.getCodeBlocksContaining(func.getBody(), ConsoleTaskMonitor())
    
    has_loop = False
    block_list = []
    
    while blocks.hasNext():
        block = blocks.next()
        block_list.append(block)
    
    # Check for back-edges (loops)
    for b in block_list:
        dest_iter = b.getDestinations(ConsoleTaskMonitor())
        while dest_iter.hasNext():
            dest_ref = dest_iter.next()
            dest_block = dest_ref.getDestinationBlock()
            if dest_block is None:
                continue
            if dest_block.getMinAddress().getOffset() < b.getMinAddress().getOffset():
                has_loop = True
                break
        if has_loop:
            break
    
    return has_loop

def main():
    print("[*] Searching for GPIO table references and VGPIO_USB_0...")
    
    results = {
        'vgpio_usb_0_candidates': [],
        'table_references': [],
        'gpio_functions': []
    }
    
    # Search for VGPIO_USB_0 configuration
    print("[*] Searching for VGPIO_USB_0 constant (0x{0:08x})...".format(VGPIO_USB_0_EXPECTED_DW0))
    vgpio_matches = search_for_constant(VGPIO_USB_0_EXPECTED_DW0, tolerance=0x1000)
    
    print("[*] Found {0} potential VGPIO_USB_0 configurations:".format(len(vgpio_matches)))
    for addr, val in vgpio_matches:
        print("    - {0}: 0x{1:08x}".format(addr, val))
        
        # Find references to this address
        refs = find_data_references(addr)
        
        results['vgpio_usb_0_candidates'].append({
            'address': str(addr),
            'value': '0x{0:08x}'.format(val),
            'references': refs
        })
        
        if refs:
            print("      Referenced by:")
            for ref in refs:
                print("        - {0} @ {1}".format(ref['function'], ref['address']))
    
    # Search for common GPIO-related function patterns
    print("\n[*] Searching for GPIO initialization functions...")
    fm = currentProgram.getFunctionManager()
    
    gpio_keywords = ['gpio', 'pad', 'config', 'init', 'mmio']
    
    for func in fm.getFunctions(True):
        func_name = func.getName().lower()
        
        # Check if function name contains GPIO-related keywords
        if any(kw in func_name for kw in gpio_keywords):
            has_loop = analyze_function_for_loops(func)
            
            func_info = {
                'name': func.getName(),
                'address': str(func.getEntryPoint()),
                'has_loop': has_loop,
                'size': func.getBody().getNumAddresses()
            }
            
            results['gpio_functions'].append(func_info)
            
            if has_loop:
                print("    - {0} @ {1} (has loop, size: {2})".format(func.getName(), func.getEntryPoint(), func_info['size']))
    
    # Output results as JSON
    print("\n[*] Analysis complete. Results:")
    print(json.dumps(results, indent=2))
    
    # Also save to file if possible
    try:
        output_file = "/tmp/ghidra_gpio_analysis.json"
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2)
        print("\n[*] Results saved to {0}".format(output_file))
    except:
        print("\n[!] Could not save results to file")

if __name__ == "__main__":
    main()
