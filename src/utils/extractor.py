#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-only

"""
UEFI firmware extraction module.

Handles extraction of UEFI modules from vendor BIOS images using
external tools (ifdtool, UEFIExtract).
"""

import os
import sys
import subprocess
import tempfile
import shutil
from pathlib import Path
from typing import List, Dict, Optional
import logging

logger = logging.getLogger(__name__)


class UEFIExtractor:
    """Extracts and organizes UEFI modules from vendor BIOS images"""

    def __init__(self, bios_image: str, work_dir: Optional[str] = None):
        """
        Initialize UEFI extractor.

        Args:
            bios_image: Path to vendor BIOS image file
            work_dir: Working directory for extraction (temp dir if None)
        """
        # Resolve absolute path immediately to avoid CWD issues
        self.bios_image = Path(bios_image).resolve()
        if not self.bios_image.exists():
            raise FileNotFoundError(f"BIOS image not found: {bios_image}")

        if work_dir:
            self.work_dir = Path(work_dir)
            self.work_dir.mkdir(parents=True, exist_ok=True)
            self.temp_dir = None
        else:
            self.temp_dir = tempfile.mkdtemp(prefix='bios2gpio_')
            self.work_dir = Path(self.temp_dir)

        self.bios_region_path: Optional[Path] = None
        self.extracted_modules_dir: Optional[Path] = None
        self.modules: List[Dict] = []

    def __del__(self):
        """Cleanup temporary directory if created"""
        if self.temp_dir and os.path.exists(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir)
            except Exception:
                pass

    def _find_tool(self, tool_name: str) -> Optional[str]:
        """Helper to find binary in PATH or adjacent dirs"""
        # 1. Check system PATH
        path = shutil.which(tool_name)
        if path:
            return path

        # 2. Check directory of this script
        script_dir = Path(__file__).parent
        if (script_dir / tool_name).exists():
            return str(script_dir / tool_name)

        # 3. Check directory of python interpreter (venv/bin)
        python_dir = Path(sys.executable).parent
        if (python_dir / tool_name).exists():
            return str(python_dir / tool_name)

        return None

    def check_dependencies(self) -> bool:
        """
        Check if required external tools are available.

        Returns:
            True if all dependencies are available
        """
        # Check for ifdtool
        ifdtool_path = self._find_tool('ifdtool')
        if not ifdtool_path:
            # Try coreboot util path
            # From bios2gpio/src/utils/extractor.py, go up to coreboot/util/
            coreboot_util = Path(__file__).parent.parent.parent.parent.parent / 'util'
            ifdtool_path = coreboot_util / 'ifdtool' / 'ifdtool'
            if not ifdtool_path.exists():
                logger.error(f"ifdtool not found at {ifdtool_path}. Please build it in util/ifdtool/")
                return False

        # Check for UEFIExtract
        uefi_extract = self._find_tool('UEFIExtract')
        if not uefi_extract:
            logger.warning("UEFIExtract not found in PATH. Will attempt to use alternative methods.")
            # UEFIExtract is optional but recommended

        return True

    def extract_bios_region(self, platform: str = 'adl') -> Path:
        """
        Extract BIOS region from IFD-formatted image using ifdtool.

        Args:
            platform: Platform-specific IFD format (e.g., 'adl' for Alder Lake)
                     Defaults to 'adl' (Alder Lake) as that is the only supported
                     platform in bios2gpio currently.

        Returns:
            Path to extracted BIOS region
        """
        logger.info(f"Extracting BIOS region from {self.bios_image}")

        ifdtool_path = self._find_tool('ifdtool')
        if not ifdtool_path:
            # From bios2gpio/src/utils/extractor.py, go up to coreboot/util/
            coreboot_util = Path(__file__).parent.parent.parent.parent.parent / 'util'
            ifdtool_path = str(coreboot_util / 'ifdtool' / 'ifdtool')

        # Run ifdtool to extract regions
        # Note: ifdtool -x creates files in current directory
        # Issue #5 Fix: Add platform-specific flag for correct IFD parsing
        # Without -p adl, Alder Lake BIOS regions are incorrectly extracted (wrong boundaries)
        cmd = [ifdtool_path, '-x', '-p', platform, str(self.bios_image)]

        try:
            result = subprocess.run(
                cmd,
                cwd=str(self.work_dir),
                capture_output=True,
                text=True,
                check=True
            )

            # ifdtool creates files like flashregion_1_bios.bin or flashregion_3_bios.bin
            # The index depends on the descriptor layout
            bios_files = list(self.work_dir.glob('flashregion_*_bios.bin'))

            if not bios_files:
                # Maybe it's already a BIOS region without IFD
                logger.warning("No BIOS region extracted (layout might be missing IFD). Using full image.")
                self.bios_region_path = self.bios_image
            else:
                self.bios_region_path = bios_files[0]
                logger.info(f"BIOS region extracted to {self.bios_region_path}")

            return self.bios_region_path

        except subprocess.CalledProcessError as e:
            logger.warning(f"ifdtool failed: {e.stderr}")
            logger.info("Assuming input is raw BIOS region without IFD")
            self.bios_region_path = self.bios_image
            return self.bios_region_path

    def extract_uefi_modules(self) -> Path:
        """
        Extract UEFI modules from BIOS image using UEFIExtract.
        
        Returns:
            Path to directory containing extracted modules
        """
        uefi_extract = self._find_tool('UEFIExtract')
        if not uefi_extract:
            logger.warning("UEFIExtract not available, will work with raw BIOS region")
            if not self.bios_region_path:
                self.extract_bios_region()
            
            self.extracted_modules_dir = self.work_dir / 'raw'
            self.extracted_modules_dir.mkdir(exist_ok=True)
            # Copy BIOS region to work dir for analysis
            target_file = self.extracted_modules_dir / 'bios_region.bin'
            if self.bios_region_path.resolve() != target_file.resolve():
                shutil.copy(self.bios_region_path, target_file)
            return self.extracted_modules_dir

        self.extracted_modules_dir = self.work_dir / 'uefi_extracted'
        self.extracted_modules_dir.mkdir(exist_ok=True)

        # Try extracting from the full BIOS image first (more reliable for UEFIExtract)
        # Copy to work dir to keep things clean
        local_image = self.extracted_modules_dir / self.bios_image.name
        shutil.copy(self.bios_image, local_image)
        
        cmd = [uefi_extract, str(local_image), 'all']
        
        try:
            # UEFIExtract might return non-zero on partial errors (e.g. code 8)
            # We allow this if it produces output
            subprocess.run(
                cmd,
                cwd=str(self.extracted_modules_dir),
                capture_output=True,
                text=True,
                check=False 
            )
            
            dump_dir = self.extracted_modules_dir / f"{local_image.name}.dump"
            
            if dump_dir.exists() and any(dump_dir.iterdir()):
                self.extracted_modules_dir = dump_dir
                logger.info(f"UEFI modules extracted to {self.extracted_modules_dir}")
                return self.extracted_modules_dir
                
        except Exception as e:
            logger.warning(f"Extraction from full image failed: {e}")

        # Fallback: Extract from BIOS region (if full image extraction failed or produced nothing)
        logger.info("Falling back to extraction from BIOS region...")
        if not self.bios_region_path:
            self.extract_bios_region()
            
        local_bios_copy = self.extracted_modules_dir / 'bios_for_extraction.bin'
        shutil.copy(self.bios_region_path, local_bios_copy)

        cmd = [uefi_extract, str(local_bios_copy), 'all']

        try:
            subprocess.run(
                cmd,
                cwd=str(self.extracted_modules_dir),
                capture_output=True,
                text=True,
                check=False
            )

            dump_dir = self.extracted_modules_dir / 'bios_for_extraction.bin.dump'
            if dump_dir.exists():
                self.extracted_modules_dir = dump_dir
                logger.info(f"UEFI modules extracted to {self.extracted_modules_dir}")
            else:
                logger.warning(f"Expected dump directory {dump_dir} not found after extraction")

        except subprocess.CalledProcessError as e:
            logger.error(f"UEFIExtract failed: {e.stderr}")
            raise

        return self.extracted_modules_dir

    def find_modules(self, patterns: List[str]) -> List[Dict]:
        """
        Find UEFI modules matching given name patterns.

        Args:
            patterns: List of name patterns to search for

        Returns:
            List of dicts with module info (path, name, size)
        """
        if not self.extracted_modules_dir:
            self.extract_uefi_modules()

        matching_modules = []
        seen_paths = set()

        # Ignore these non-BIOS regions to avoid false positives (e.g. ME GPIO tables)
        IGNORE_DIRS = ['me region', 'descriptor region', 'gbe region', 'padding']

        # Search for files matching patterns
        for pattern in patterns:
            pattern_lower = pattern.lower()

            # Walk through extracted directory
            for root, dirs, files in os.walk(self.extracted_modules_dir):
                for file in files:
                    file_path = Path(root) / file

                    # Get path relative to extraction root to check directory names
                    try:
                        rel_path = file_path.relative_to(self.extracted_modules_dir)
                    except ValueError:
                        continue

                    path_str = str(rel_path).lower()

                    # SKIP if in ignored region
                    if any(ignore in path_str for ignore in IGNORE_DIRS):
                        continue

                    # Check pattern against the relative path (includes parent dir names)
                    if pattern_lower in path_str:
                        if str(file_path) not in seen_paths:
                            module_info = {
                                'path': file_path,
                                'name': file,
                                'size': file_path.stat().st_size,
                                'pattern': pattern,
                            }
                            matching_modules.append(module_info)
                            seen_paths.add(str(file_path))

        self.modules = matching_modules
        logger.info(f"Found {len(matching_modules)} modules matching patterns (excluding ME/Descriptor)")

        return matching_modules

    def get_bios_region(self) -> Path:
        """
        Get path to BIOS region (extracting if necessary).

        Returns:
            Path to BIOS region file
        """
        if not self.bios_region_path:
            self.extract_bios_region()
        return self.bios_region_path

    def get_all_binary_files(self) -> List[Path]:
        """
        Get all binary files from extracted modules, excluding ignored regions.

        Returns:
            List of paths to binary files
        """
        if not self.extracted_modules_dir:
            self.extract_uefi_modules()

        binary_files = []
        IGNORE_DIRS = ['me region', 'descriptor region', 'gbe region']

        for root, dirs, files in os.walk(self.extracted_modules_dir):
            # Skip ignored directories early
            if any(ignore in str(Path(root)).lower() for ignore in IGNORE_DIRS):
                continue

            for file in files:
                file_path = Path(root) / file
                # Look for .bin, .efi, .pe32, .raw files and 'body' files from UEFIExtract
                if file_path.suffix.lower() in ['.bin', '.efi', '.pe32', '.raw', '.ui', ''] or 'body' in file_path.name.lower():
                    binary_files.append(file_path)

        return binary_files
