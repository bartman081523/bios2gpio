# bios2gpio - GPIO Extraction Tool

Extract GPIO configurations from vendor BIOS images without requiring `inteltool` to run on the target hardware.

## Overview

This tool analyzes vendor UEFI BIOS images to extract GPIO pad configurations, which can then be used to create coreboot GPIO configuration files. This eliminates the need to boot vendor firmware on the target hardware and run `inteltool`.

## Supported Platforms

- Intel Alder Lake (12th gen Core, Z690/H670/B660 chipsets)

## Requirements

### System Dependencies

- **ifdtool**: Intel Flash Descriptor tool (included in coreboot `util/ifdtool/`)
- **UEFIExtract** (optional but recommended): UEFI firmware extraction tool
  - Download from: https://github.com/LongSoft/UEFITool

### Python Dependencies

```bash
pip install -r requirements.txt
```

## Installation

1. Build ifdtool:
```bash
cd /path/to/coreboot/util/ifdtool
make
```

2. Install UEFIExtract (optional):
```bash
# Download from https://github.com/LongSoft/UEFITool/releases
# Extract and place UEFIExtract in your PATH
```

3. Install Python dependencies:
```bash
cd /path/to/coreboot/util/bios2gpio
pip install -r requirements.txt
```

## Usage

### Basic Usage

Extract GPIO configuration from a vendor BIOS image:

```bash
./bios2gpio.py --platform alderlake --input vendor_bios.bin --output gpio.h
```

### Advanced Usage

Generate multiple output formats:

```bash
./bios2gpio.py --platform alderlake \
    --input vendor_bios.bin \
    --output gpio.h \
    --json gpio_data.json \
    --report gpio_summary.txt
```

### Options

- `--platform`: Target platform (currently only `alderlake` supported)
- `--input`, `-i`: Input vendor BIOS image file (required)
- `--output`, `-o`: Output coreboot gpio.h file
- `--json`, `-j`: Output JSON file with parsed GPIO data
- `--report`, `-r`: Output human-readable summary report
- `--work-dir`, `-w`: Working directory for extraction (uses temp dir if not specified)
- `--min-entries`: Minimum entries to consider a GPIO table (default: 10)
- `--verbose`, `-v`: Enable verbose logging for debugging

## How It Works

### 1. Firmware Extraction

The tool uses `ifdtool` to extract the BIOS region from Intel Flash Descriptor (IFD) formatted images. If `UEFIExtract` is available, it further extracts individual UEFI modules (PEI/DXE drivers).

### 2. GPIO Table Detection

The tool scans binary data for patterns that match GPIO pad configuration structures:

- **Name-based filtering**: Searches for modules with names containing `Gpio`, `PchInit`, `SiliconInit`, etc.
- **Binary pattern scanning**: Looks for arrays of fixed-size structures (8, 12, or 16 bytes) that match GPIO pad configuration layout
- **Validation**: Verifies that pad configurations have valid values for mode, reset domain, termination, etc.
- **Confidence scoring**: Ranks detected tables by likelihood of being actual GPIO configurations

### 3. Configuration Parsing

Detected tables are parsed into logical GPIO pad configurations:

- Extracts pad mode (GPIO vs native function)
- Determines direction (input/output) for GPIO mode
- Reads output value, pull resistor configuration, reset domain
- Identifies interrupt routing if configured

### 4. Output Generation

Generates coreboot-compatible GPIO configuration files using standard macros:

- `PAD_CFG_GPO()` - GPIO output
- `PAD_CFG_GPI_TRIG_OWN()` - GPIO input
- `PAD_CFG_NF()` - Native function
- `PAD_CFG_GPI_APIC_LOW()` - GPIO input with APIC interrupt
- etc.

## Validation

To validate the tool's accuracy, compare extracted GPIO configurations against a known reference:

```bash
# Extract from MSI Z690 vendor BIOS
./bios2gpio.py --platform alderlake \
    --input msi_z690_vendor.bin \
    --output msi_extracted_gpio.h \
    --json msi_extracted.json

# Compare against coreboot reference
# (Manual comparison or use gpio_comparator.py if implemented)
```

## Limitations

- **Vendor customization**: Heavily customized or obfuscated GPIO initialization code may not be detected
- **Runtime configuration**: Some GPIO pads may be reconfigured at runtime by DXE drivers or ACPI methods
- **Platform support**: Currently only supports Intel Alder Lake; other platforms require additional definitions
- **Accuracy**: Without hardware validation, extracted configurations should be verified before use

## Troubleshooting

### No GPIO tables detected

- Try increasing verbosity: `--verbose`
- Check if the BIOS image is encrypted or compressed
- Ensure the image is a full SPI dump or valid BIOS update file
- Try lowering `--min-entries` threshold

### Incorrect pad names

- The tool uses heuristics to guess pad identities
- Pad names may not match exactly; manual verification recommended
- Compare against Intel PCH datasheet for your platform

### ifdtool not found

- Build ifdtool: `cd util/ifdtool && make`
- Ensure it's in your PATH or the tool will find it in coreboot tree

## Contributing

To add support for additional platforms:

1. Create a new platform definition file in `platforms/`
2. Define GPIO groups, pad structures, and bitfield layouts
3. Update `bios2gpio.py` to recognize the new platform

## License

GPL-2.0-only (same as coreboot)

## References

- Intel Alder Lake PCH Datasheet
- coreboot GPIO documentation
- UEFITool: https://github.com/LongSoft/UEFITool
