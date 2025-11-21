# bios2gpio - Static GPIO Extraction Tool

**bios2gpio** is a reverse-engineering tool designed to extract Intel PCH GPIO configurations directly from vendor UEFI BIOS images.

It generates **coreboot-compatible `gpio.h`** files without requiring you to boot the vendor firmware or run `inteltool` on the physical hardware. This is essential for porting coreboot to new mainboards where you might not have the hardware yet, or want to analyze the vendor's configuration statically.

## Features

*   **Static Extraction:** works entirely on binary BIOS images (`.bin`, `.rom`).
*   **Signature-Based Detection:** Uses specific patterns (e.g., Alder Lake GPP_I sequence) to identify GPIO tables with near-100% accuracy, ignoring garbage data.
*   **Smart Parsing:** Automatically handles IFD splitting (via `ifdtool`) and UEFI module extraction (via `UEFIExtract`).
*   **Calibration Mode:** Can use a known-good `gpio.h` (e.g., from a similar supported board) to mathematically find the correct table offset in a raw binary.
*   **Image Comparison:** Compare two vendor BIOS images (e.g., MSI vs ASRock) to see if they share the exact same GPIO configuration.
*   **Coreboot Output:** Generates ready-to-use C macros (`PAD_CFG_GPO`, `PAD_CFG_NF`, etc.).

## Supported Platforms

*   **Intel Alder Lake (PCH-S)** (Z690, H670, B660)
    *   *Verified on:* MSI PRO Z690-A, ASRock Z690 Steel Legend.

*Support for Raptor Lake and Meteor Lake can be added by defining signatures in `platforms/`.*

## Prerequisites

1.  **Python 3.6+**
2.  **ifdtool**: Required to split the BIOS region from the SPI image.
    *   Usually found in `coreboot/util/ifdtool`.
3.  **UEFIExtract**: Required to unpack UEFI modules.
    *   Available from [LongSoft/UEFITool](https://github.com/LongSoft/UEFITool).

## Installation

1.  Clone the repository (or place in `util/bios2gpio`).
2.  Ensure `ifdtool` and `UEFIExtract` are either in your system `$PATH` **OR** placed in the same directory as the python scripts.

## Usage

### 1. Standard Extraction
Extract GPIOs from a vendor BIOS update or SPI dump.

```bash
./bios2gpio.py --platform alderlake \
    --input asrock_z690_bios.bin \
    --output gpio.h \
    --json gpio.json
```

*   **Output:** `gpio.h` (C header), `gpio.json` (Structured data).

### 2. Comparison Mode
Check if two different boards (or BIOS versions) use the same GPIO table. This is useful to see if a new board is a "clone" of an existing supported board.

```bash
./compare_images.py \
    --image-a msi_z690_v1.bin \
    --image-b asrock_z690_v2.bin
```

*   **Output:** A detailed line-by-line diff of pad modes, directions, and resets.

### 3. Calibration Mode (Dev/Research)
If you have a supported board (e.g., MSI Z690) and want to find where the GPIO table is located in a raw binary to debug the detector:

```bash
./bios2gpio.py --platform alderlake \
    --input msi_z690.bin \
    --calibrate-with ../../src/mainboard/msi/ms7d25/gpio.h
```

## How It Works

1.  **Decomposition:** The tool uses `ifdtool` to isolate the BIOS region and `UEFIExtract` to unpack PEI/DXE modules / FSP binaries.
2.  **Detection:**
    *   **Signature Scan:** Searches for specific bit-patterns known to be constant on the platform (e.g., `GPP_I0` is GPIO, `GPP_I1`..`I4` are Native Functions for DisplayPort).
    *   **Heuristic Scan:** If signatures fail, it scans for array-like structures that match the statistical properties of a GPIO table.
3.  **Filtering:** Rejects tables that are too large (>350 entries) or contain invalid register bits.
4.  **Parsing:** Maps the raw binary data (DW0/DW1 registers) to logical names (`GPP_B12`) using the physical group order defined in `platforms/alderlake.py`.

## Troubleshooting

*   **"UEFIExtract not found":** Copy the `UEFIExtract` binary into the script folder.
*   **"No GPIO tables detected":** Ensure the input file is a valid SPI dump (16MB/32MB). If it's a capsule update, try extracting the body first.
*   **Low match score:** The tool prioritizes the "Reference Code" table (initial defaults). Coreboot `gpio.h` often contains runtime overrides (e.g., enabling Native Functions that default to GPIO). A 50-60% match against a mature coreboot port is often considered a **perfect** extraction of the vendor defaults.
