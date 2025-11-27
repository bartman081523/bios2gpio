# Asrock Z690 Coreboot Build - Complete Walkthrough

## Summary
Successfully completed the Coreboot full image build for Asrock Z690 Steel Legend with Tianocore (EDK2) payload, including VGPIO verification, EDK2 build fix, and full flash ROM creation with vendor regions.

## Part 1: VGPIO Verification

**Status**: ✅ Complete

Verified that the Asrock Z690 [gpio.h](file:///run/media/julian/ML2/Python/coreboot/coreboot/src/mainboard/msi/ms7d25/gpio.h) contains all VGPIOs with safe defaults:
- Created comparison script: [compare_vgpios.py](file:///run/media/julian/ML2/Python/coreboot/coreboot/util/bios2gpio/compare_vgpios.py)
- Compared against MSI Z690 reference: [ms7d25/gpio.h](file:///run/media/julian/ML2/Python/coreboot/coreboot/src/mainboard/msi/ms7d25/gpio.h)
- **Result**: Perfect match - 115 VGPIOs in both files
- **Important**: VGPIOs are **board-specific** and extracted from Asrock BIOS, not copied from MSI

### VGPIO Configuration Differences
Asrock and MSI have different VGPIO configurations (as expected):
- **Asrock VGPIO_0**: `PAD_BUF(TX_DISABLE)`
- **MSI VGPIO_0**: `PAD_BUF(RX_DISABLE) | 1`

## Part 2: EDK2 Build Fix

**Status**: ✅ Complete

Fixed the NASM assembly error in EDK2's [ExceptionHandlerAsm.nasm](file:///run/media/julian/ML2/Python/coreboot/coreboot/payloads/external/edk2/workspace/mrchromebox/UefiCpuPkg/Library/CpuExceptionHandlerLib/X64/ExceptionHandlerAsm.nasm):

#### Problem
32-bit push instruction in x64 code at line 73:
```nasm
push    strict dword 0      ; 0 will be fixed
```

#### Solution
Patched [ExceptionHandlerAsm.nasm:L73](file:///run/media/julian/ML2/Python/coreboot/coreboot/payloads/external/edk2/workspace/mrchromebox/UefiCpuPkg/Library/CpuExceptionHandlerLib/X64/ExceptionHandlerAsm.nasm#L73):
```diff
-    push    strict dword 0      ; 0 will be fixed
+    push    strict qword 0      ; 0 will be fixed
```

## Part 3: Coreboot Build

**Status**: ✅ Complete

Successfully built the complete Coreboot image:
- **Command**: `make -j$(nproc)`
- **Build time**: ~2 minutes
- **Exit code**: 0 (success)

### Build Artifacts
- **coreboot.rom**: 32 MB (BIOS region only)
- **UEFIPAYLOAD.fd**: 8.0 MB (Tianocore payload)

## Part 4: Full Flash ROM Creation

**Status**: ✅ Complete

Created full 32MB flash ROM with vendor regions from [Z690-Steel-Legend_21.01.ROM](file:///run/media/julian/ML2/Python/coreboot/coreboot/util/bios2gpio/Z690-Steel-Legend_21.01.ROM):

### Extracted Regions
- **Flash Descriptor (IFD)**: 4 KB (0x0 - 0xfff)
- **Intel ME**: 3.8 MB (0x1000 - 0x3d8fff)
- **BIOS**: 16 MB (0x1000000 - 0x1ffffff) - from coreboot build
- **GbE**: Unused

### Creation Process
```bash
# 1. Extract regions from vendor BIOS
util/ifdtool/ifdtool -x util/bios2gpio/Z690-Steel-Legend_21.01.ROM

# 2. Create 32MB blank image
dd if=/dev/zero of=build/asrock_z690_full_flash.rom bs=1M count=32

# 3. Place IFD at offset 0x0
dd if=flashregion_0_flashdescriptor.bin of=build/asrock_z690_full_flash.rom bs=1 conv=notrunc

# 4. Place ME at offset 0x1000
dd if=flashregion_2_intel_me.bin of=build/asrock_z690_full_flash.rom bs=1 seek=$((0x1000)) conv=notrunc

# 5. Place BIOS region at offset 16MB
dd if=build/coreboot.rom of=build/asrock_z690_full_flash.rom bs=1M skip=16 seek=16 conv=notrunc
```

### Final ROM
- **File**: [asrock_z690_full_flash.rom](file:///run/media/julian/ML2/Python/coreboot/coreboot/build/asrock_z690_full_flash.rom)
- **Size**: 32 MB (33554432 bytes)
- **Contains**: IFD + ME + Coreboot BIOS with Tianocore

## Verification

### Flash Layout Verification
```
Flash Descriptor: ✅ Present (ICH Revision detected)
Intel ME Region:  ✅ Present (VSCC table found)
BIOS Region:      ✅ Present (Coreboot + Tianocore)
GbE Region:       ⚠️  Unused (as in vendor BIOS)
```

### Files Modified
1. [ExceptionHandlerAsm.nasm:L73](file:///run/media/julian/ML2/Python/coreboot/coreboot/payloads/external/edk2/workspace/mrchromebox/UefiCpuPkg/Library/CpuExceptionHandlerLib/X64/ExceptionHandlerAsm.nasm#L73) - Fixed 32-bit push

## Flashing Instructions

### Full Flash (with hardware programmer)
```bash
flashrom -p <programmer> -w build/asrock_z690_full_flash.rom
```

### BIOS Region Only (internal)
```bash
flashrom -p internal --ifd -i bios -w build/coreboot.rom
```

> [!CAUTION]
> **Always backup your current BIOS before flashing!**
> Test with a hardware programmer first if possible.

> [!WARNING]
> The full flash ROM contains the vendor ME firmware. Ensure you have the right to use it.
