"""Pinned offline emulator; 2.1.4 fails our monitored Thumb IT regression.

Install locally with:
python -m pip install --no-deps --target firmware-lab/vendor-unicorn-213 unicorn==2.1.3
This module never installs anything or accesses a device.
"""
from pathlib import Path
import sys

vendor=Path(__file__).with_name('vendor-unicorn-213')
if vendor.is_dir():sys.path.insert(0,str(vendor))
import unicorn
if unicorn.__version__!='2.1.3':
    raise RuntimeError('Offline ARM validation requires pinned Unicorn 2.1.3; see emulator_runtime.py')
