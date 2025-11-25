# -*- coding: utf-8 -*-
#@category AlderLake
# Headless script: finds functions with suspicious MmioWrite32 loops (GPIO candidates)
#
# Usage (Headless):
# analyzeHeadless <project_dir> <project_name> \
#   -import PchInitDxe.efi \
#   -scriptPath . \
#   -postScript find_gpio_mmio_loops.py

from ghidra.program.model.symbol import SymbolType
from ghidra.program.model.block import BasicBlockModel
from ghidra.util.task import ConsoleTaskMonitor

def get_function_by_name(name_substring):
    fm = currentProgram.getFunctionManager()
    matches = []
    for f in fm.getFunctions(True):
        if name_substring.lower() in f.getName().lower():
            matches.append(f)
    return matches

def find_import_by_name(name):
    sym_table = currentProgram.getSymbolTable()
    symbols = sym_table.getSymbolIterator(True)
    for sym in symbols:
        if sym.getSymbolType() == SymbolType.FUNCTION:
            if name.lower() in sym.getName().lower():
                if sym.getProgram() == currentProgram:
                    return sym
    return None

def is_call_to(target_func, instr):
    """Check if instruction is a call to target_func."""
    if not instr.getFlowType().isCall():
        return False
    refs = instr.getReferencesFrom()
    for ref in refs:
        if ref.getReferenceType().isCall():
            if ref.getToAddress() == target_func.getEntryPoint():
                return True
    return False

def function_contains_mmio_loop(func, mmio_func):
    """
    Simplified heuristic:
    - Are there at least 2 call sites to mmio_func in the same function?
    - Is there a loop (BasicBlock with back-edge)?
    """
    listing = currentProgram.getListing()
    body = func.getBody()
    instr_iter = listing.getInstructions(body, True)

    call_sites = []

    while instr_iter.hasNext():
        instr = instr_iter.next()
        if is_call_to(mmio_func, instr):
            call_sites.append(instr.getAddress())

    if len(call_sites) < 2:
        return False, call_sites

    # Simple loop detection via BasicBlocks (back-edge)
    block_model = BasicBlockModel(currentProgram)
    blocks = block_model.getCodeBlocksContaining(func.getBody(), ConsoleTaskMonitor())

    has_loop = False
    block_list = []
    while blocks.hasNext():
        block = blocks.next()
        block_list.append(block)

    for b in block_list:
        dest_iter = b.getDestinations(ConsoleTaskMonitor())
        while dest_iter.hasNext():
            dest_ref = dest_iter.next()
            dest_block = dest_ref.getDestinationBlock()
            if dest_block is None:
                continue
            # Back-edge: destination address < source address
            if dest_block.getMinAddress().getOffset() < b.getMinAddress().getOffset():
                has_loop = True
                break
        if has_loop:
            break

    return has_loop, call_sites

def main():
    print("[*] Searching for MmioWrite32-like functions...")

    # Try to find suitable MMIO helper functions
    candidate_names = ["MmioWrite32", "MmioAndThenOr32"]
    mmio_funcs = []

    for name in candidate_names:
        sym = find_import_by_name(name)
        if sym:
            func = getFunctionAt(sym.getAddress())
            if func:
                mmio_funcs.append(func)

    if not mmio_funcs:
        print("[!] No MmioWrite32-like function found - possibly different names or inline MMIO.")
        return

    fm = currentProgram.getFunctionManager()
    all_funcs = list(fm.getFunctions(True))

    for mmio_func in mmio_funcs:
        print("[*] Analyzing callers of {}".format(mmio_func.getName()))

        for func in all_funcs:
            has_loop, calls = function_contains_mmio_loop(func, mmio_func)
            if has_loop and calls:
                print("------------------------------------------------------")
                print("Candidate function: {} @ {}".format(func.getName(), func.getEntryPoint()))
                print("  Calls to {}:".format(mmio_func.getName()))
                for addr in calls:
                    print("    - {}".format(addr))

                # Optional: you could add more heuristics here,
                # e.g. number of calls, function size, etc.

if __name__ == "__main__":
    main()
