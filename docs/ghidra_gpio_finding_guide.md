# Ghidra Guide: Finding the "True" GPIO Table (Alder Lake / Z690)

This guide describes how to manually identify the **final** and **correct** GPIO initialization table in an Intel UEFI BIOS image using Ghidra. This is the "Ground Truth" step required to calibrate automated parsers.

## Prerequisites

1.  **UEFIExtract / UEFITool**: To extract the BIOS region and individual modules.
2.  **Ghidra**: With the standard x86/64 analysis enabled.
3.  **Target BIOS**: A vendor BIOS image (e.g., MSI Z690).

## Step 1: Extract and Import

1.  Open the BIOS image in UEFITool.
2.  Search for modules named `PchInitDxe`, `GpioInit`, `SiliconInit`, or `FspS`.
    *   *Tip*: `PchInitDxe` is often the best place to look for the final DXE configuration.
3.  Extract the PE32 body of these modules.
4.  Import the extracted `.efi` files into a new Ghidra project.
5.  Run **Auto Analysis** (default settings are usually fine).

## Step 2: Locate GPIO Initialization Code

We are looking for code that writes to the PCH GPIO MMIO registers.

### Method A: String Search
1.  Open **Search -> For Strings...**
2.  Filter for: `GPIO`, `GPP_`, `PadCfg`, `Community`, `PADCFG`.
3.  Look for debug strings like `"Initializing PCH GPIO"`, `"ConfigureGpio"`, or `"GpioPadConfig Applied"`.
4.  Follow the references (XREFs) from these strings to the code.

### Method B: MMIO Helper Search
1.  Look in the **Symbol Tree** (Imports or Exports) for functions like:
    *   `MmioWrite32`
    *   `MmioAndThenOr32`
    *   `PciSegmentRead32` / `PciSegmentWrite32`
    *   `GpioPadConfigTable`
2.  Right-click and **Show References to**.
3.  Look for functions that call these helpers repeatedly or in a loop.

## Step 3: Identify the Initialization Loop

You are looking for a function that iterates over an array and writes to MMIO. In the Decompiler view, it will look something like this:

```c
// Pseudo-code example
void ConfigureGpio(void *Table, int Count) {
    for (int i = 0; i < Count; i++) {
        // Calculate MMIO address: Base + Offset + (i * Stride)
        // Write DW0
        MmioWrite32(GpioBase + Table[i].Offset, Table[i].Dw0);
        // Write DW1
        MmioWrite32(GpioBase + Table[i].Offset + 4, Table[i].Dw1);
    }
}
```

**Key Indicators:**
*   **Loop**: A `for` or `while` loop.
*   **MMIO Calculation**: An address calculation involving a base (often `0xFDxxxxxx` or derived from P2SB) and an index.
*   **Double Write**: Two 32-bit writes to adjacent addresses (offset `+0` and `+4`) strongly suggest `PADCFG_DW0` and `PADCFG_DW1`.

## Step 4: Analyze the Data Structure

Once you find the loop, look at the data source (`Table[i]`).

1.  **Locate the Array**: Double-click the `Table` variable or the address it points to. It usually leads to a `.data` or `.rdata` section.
2.  **Determine Struct Size**:
    *   Look at the stride in the loop (e.g., `i * 16` implies a 16-byte struct).
    *   Or observe how fields are accessed (`entry + 0`, `entry + 4`, `entry + 8`).
3.  **Define the Struct**:
    *   Right-click the data at the start of the array.
    *   **Data -> Create Structure**.
    *   Edit the structure to match your findings (e.g., `PadOffset`, `Dw0`, `Dw1`, `Flags`).
4.  **Verify Content**:
    *   Does the number of entries match the loop count?
    *   Do the values look like valid GPIO configs (e.g., `0x44000xxx` for native functions)?

## Step 5: Select the "Final" Table

You might find multiple tables (Early PEI, S3 Resume, DXE). To pick the right one for coreboot:

1.  **Prefer DXE over PEI**: `PchInitDxe` usually applies the final configuration before OS boot.
2.  **Check for "S3" context**: If the function is only called when `BootMode == S3_RESUME`, ignore it (unless you specifically need S3 data).
3.  **Coverage**: The correct table should cover most/all GPIO communities (GPP_A, GPP_B, etc.).
4.  **Compare**: As a sanity check, compare a few entries with `inteltool` output or existing coreboot `gpio.h` files.

## Step 6: Export for Automation

Once identified:
1.  Note the **Offset** of the table in the file.
2.  Note the **Struct Layout** (field order and size).
3.  Note any **Magic Values** or terminators.

Use this information to configure your `bios2gpio` parsers.
