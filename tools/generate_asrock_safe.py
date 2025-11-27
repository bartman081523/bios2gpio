#!/usr/bin/env python3
import sys
import logging
from pathlib import Path
from compose_gpio import compose_state
from gpio_generator import GPIOGenerator

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
logger = logging.getLogger(__name__)

def generate_safe_config(bios_path, reference_path, output_path):
    # 1. Get composed state (best effort reconstruction)
    # This ensures physical GPIOs are correct (matching MSI reference)
    logger.info(f"Composing state from {bios_path} using {reference_path}...")
    composed_state = compose_state(bios_path, reference_path)
    
    # 2. Convert dictionary to list for generator
    pads = []
    
    # We need to ensure we have ALL pads from the reference, even if missing in composition
    # (though compose_state should handle this if we used reference)
    # But wait, compose_state returns 'current_state' which might be missing pads.
    # We should iterate over the REFERENCE keys to ensure full coverage.
    
    from compose_gpio import parse_reference_header
    reference = parse_reference_header(reference_path)
    
    # Sort keys to maintain order (groups)
    # Ideally we'd parse groups from reference too, but for now let's rely on name sorting or existing order
    # Actually, let's just use the order from reference file if possible, or sort by group/name
    
    # Helper to get group from name
    def get_group(name):
        if name.startswith('GPP_'): return 'GPP_' + name.split('_')[1][0]
        if name.startswith('GPD'): return 'GPD'
        if name.startswith('VGPIO'): return 'vGPIO'
        return 'OTHER'

    sorted_names = sorted(reference.keys(), key=lambda x: (get_group(x), x))
    
    for name in sorted_names:
        # Determine configuration
        if name.startswith('VGPIO'):
            # SAFE DEFAULT for ALL VGPIOs
            pad_config = {
                'name': name,
                'group': get_group(name),
                'mode': 'GPIO',
                'direction': 'INPUT',
                'reset': 'DEEP',
                'termination': 'NONE',
                'is_vgpio': True,
                'dw0': '0x00000000', # Will be constructed by generator
                'dw1': '0x00000000'
            }
            logger.info(f"Setting safe default for {name}")
        else:
            # Physical GPIO - use composed state (or reference if missing)
            if name in composed_state:
                pad_config = composed_state[name]
                # Ensure group is set
                pad_config['group'] = get_group(name)
            else:
                logger.warning(f"Physical pad {name} missing in composition! Using reference default (risky but necessary).")
                # Fallback to reference mode (we only know mode from reference parsing)
                # This shouldn't happen if composition worked well for physical pads
                mode_val = reference[name]
                mode_str = f"NF{mode_val}" if mode_val > 0 else "GPIO"
                pad_config = {
                    'name': name,
                    'group': get_group(name),
                    'mode': mode_str,
                    'reset': 'PLTRST', # Guess
                    'direction': 'INPUT' # Guess
                }
        
        pads.append(pad_config)
        
    # 3. Generate Header
    generator = GPIOGenerator(platform='alderlake')
    generator.generate_coreboot_header(pads, Path(output_path))
    logger.info(f"Successfully generated {output_path}")

if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: generate_asrock_safe.py <bios_rom> <reference_h> <output_h>")
        sys.exit(1)
        
    generate_safe_config(sys.argv[1], sys.argv[2], sys.argv[3])
