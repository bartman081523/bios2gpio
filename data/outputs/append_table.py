#!/usr/bin/env python3
import sys

def append_clkreq_table(target_file, source_file):
    # Read source file to extract the table
    with open(source_file, 'r') as f:
        content = f.read()
    
    start_marker = "/* PCIe CLK REQs as per devicetree.cb */"
    end_marker = "};"
    
    start_idx = content.find(start_marker)
    if start_idx == -1:
        print(f"Error: Could not find start marker in {source_file}")
        return
    
    # Find the end of the table (next }; after start)
    end_idx = content.find(end_marker, start_idx)
    if end_idx == -1:
        print(f"Error: Could not find end marker in {source_file}")
        return
    
    table_content = content[start_idx:end_idx+2]
    
    # Read target file
    with open(target_file, 'r') as f:
        target_content = f.read()
        
    # Append table
    with open(target_file, 'w') as f:
        f.write(target_content)
        f.write("\n\n")
        f.write(table_content)
        f.write("\n")
        
    print(f"Appended clkreq_disabled_table to {target_file}")

if __name__ == "__main__":
    append_clkreq_table("asrock_safe_gpio.h", "msi_gpio.h")
