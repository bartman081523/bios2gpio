import re
import sys

def parse_vgpios(filepath):
    vgpios = set()
    with open(filepath, 'r') as f:
        for line in f:
            # Look for _PAD_CFG_STRUCT(VGPIO_...)
            match = re.search(r'_PAD_CFG_STRUCT\((VGPIO_\w+),', line)
            if match:
                vgpios.add(match.group(1))
    return vgpios

def main():
    if len(sys.argv) < 3:
        print("Usage: compare_vgpios.py <msi_gpio.h> <asrock_gpio.h>")
        sys.exit(1)

    msi_vgpios = parse_vgpios(sys.argv[1])
    asrock_vgpios = parse_vgpios(sys.argv[2])

    print(f"MSI VGPIOs: {len(msi_vgpios)}")
    print(f"Asrock VGPIOs: {len(asrock_vgpios)}")

    missing = msi_vgpios - asrock_vgpios
    extra = asrock_vgpios - msi_vgpios

    if missing:
        print("\nMissing VGPIOs in Asrock (need safe defaults):")
        for v in sorted(missing):
            print(v)
    
    if extra:
        print("\nExtra VGPIOs in Asrock (unexpected?):")
        for v in sorted(extra):
            print(v)

    if not missing and not extra:
        print("\nVGPIO sets match perfectly!")

if __name__ == "__main__":
    main()
