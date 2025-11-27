#!/usr/bin/env python3
import struct
import logging
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def hunt_vgpio_usb_0(bios_path):
    logger.info(f"Hunting for VGPIO_USB_0 in {bios_path}...")
    
    with open(bios_path, 'rb') as f:
        data = f.read()
    
    # Expected Patterns for VGPIO_USB_0 (NF1 | DEEP)
    # Mode NF1 = 1 << 10 = 0x400
    # Reset DEEP = 1 << 30 = 0x40000000
    # NAFVWE = 1 << 27 (usually) = 0x08000000
    
    patterns = [
        (0x48000400, "NF1 | DEEP | NAFVWE (Bit 27)"),
        (0x40000480, "NF1 | DEEP | NAFVWE (Bit 7)"),
        (0x40000400, "NF1 | DEEP (No NAFVWE)"),
        (0x40000402, "NF1 | DEEP | RX State (Bit 1)")
    ]
    
    found = False
    for val, desc in patterns:
        packed = struct.pack('<I', val)
        offset = 0
        while True:
            offset = data.find(packed, offset)
            if offset == -1:
                break
            
            # Found a match, check context
            # VGPIO table usually has 12 entries (12 * 16 bytes = 192 bytes)
            # Check if this looks like the start of a table
            
            # Check next entry (VGPIO_USB_1)
            # Should be similar (NF1 or GPIO)
            try:
                next_dw0 = struct.unpack('<I', data[offset+16:offset+20])[0]
                next_desc = "Unknown"
                if next_dw0 & 0x400: next_desc = "NF1"
                elif (next_dw0 >> 10) & 0xF == 0: next_desc = "GPIO"
                
                logger.info(f"Found {desc} (0x{val:08x}) at 0x{offset:x}")
                logger.info(f"  Next entry (+16): 0x{next_dw0:08x} ({next_desc})")
                
                if next_desc in ["NF1", "GPIO"]:
                    logger.info("  -> CANDIDATE! Context looks valid.")
                    found = True
            except:
                pass
            
            offset += 1

    if not found:
        logger.info("No exact hardcoded VGPIO_USB_0 configuration found.")
        logger.info("Proceeding with Default Synthesis strategy.")

if __name__ == "__main__":
    hunt_vgpio_usb_0('E7D25IMS.1M0')
