import os
import subprocess
import tempfile
import shutil
import argparse
import sys
import json
from pathlib import Path

# Default Ghidra path based on user environment
DEFAULT_GHIDRA_HOME = "/run/media/julian/ML2/Python/coreboot/coreboot/util/bios2gpio/ghidra"

def run_ghidra_analysis(input_file, ghidra_home=None, script_name="find_gpio_tables.py"):
    """
    Runs Ghidra headless analysis on the given input file using the specified script.
    Returns parsed JSON results if available, None otherwise.
    """
    if ghidra_home is None:
        ghidra_home = os.environ.get("GHIDRA_HOME", DEFAULT_GHIDRA_HOME)

    ghidra_home_path = Path(ghidra_home)
    analyze_headless = ghidra_home_path / "support" / "analyzeHeadless"

    if not analyze_headless.exists():
        print(f"Error: Ghidra headless executable not found at {analyze_headless}")
        return None

    # Script location
    script_dir = Path(__file__).parent / "ghidra" / "scripts"
    if not (script_dir / script_name).exists():
        print(f"Error: Script {script_name} not found in {script_dir}")
        return None

    # Create a temporary directory for the Ghidra project
    with tempfile.TemporaryDirectory() as temp_dir:
        project_name = "temp_ghidra_project"
        
        cmd = [
            str(analyze_headless),
            temp_dir,
            project_name,
            "-import", str(input_file),
            "-scriptPath", str(script_dir),
            "-postScript", script_name,
            "-deleteProject" # Clean up after we are done
        ]

        print(f"Running Ghidra analysis on {input_file}...")
        print(f"Command: {' '.join(cmd)}")

        try:
            # Run Ghidra and capture output
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=False # Don't raise exception immediately, we want to handle return codes
            )
            
            # Print stdout/stderr
            print("--- Ghidra Output ---")
            print(result.stdout)
            if result.stderr:
                print("--- Ghidra Errors ---")
                print(result.stderr)
            
            if result.returncode != 0:
                print(f"Ghidra analysis failed with return code {result.returncode}")
                return None
            
            # Try to parse JSON output from /tmp/ghidra_gpio_analysis.json
            json_output_file = Path("/tmp/ghidra_gpio_analysis.json")
            if json_output_file.exists():
                try:
                    with open(json_output_file, 'r') as f:
                        results = json.load(f)
                    print(f"\n[*] Parsed Ghidra results: {len(results.get('vgpio_usb_0_candidates', []))} VGPIO_USB_0 candidates, {len(results.get('gpio_functions', []))} GPIO functions")
                    return results
                except Exception as e:
                    print(f"Warning: Could not parse Ghidra JSON output: {e}")
            
            return True  # Success but no JSON output

        except Exception as e:
            print(f"An error occurred while running Ghidra: {e}")
            return None

def main():
    parser = argparse.ArgumentParser(description="Run Ghidra analysis for bios2gpio")
    parser.add_argument("input_file", help="Path to the binary file (e.g., PchInitDxe.efi)")
    parser.add_argument("--ghidra-home", help="Path to Ghidra installation root", default=DEFAULT_GHIDRA_HOME)
    parser.add_argument("--script", help="Name of the Ghidra script to run", default="find_gpio_mmio_loops.py")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.input_file):
        print(f"Error: Input file {args.input_file} does not exist.")
        sys.exit(1)

    success = run_ghidra_analysis(args.input_file, args.ghidra_home, args.script)
    if not success:
        sys.exit(1)

if __name__ == "__main__":
    main()
