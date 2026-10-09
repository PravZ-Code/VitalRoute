"""Pytest configuration and environment fixtures for VitalRoute tests."""
import os
import sys
from pathlib import Path

# Ensure backend root is always in sys.path
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# Ensure software directory is always in sys.path for desktop app tests
SOFTWARE_DIR = BACKEND_DIR.parent / "software"
if str(SOFTWARE_DIR) not in sys.path:
    sys.path.insert(0, str(SOFTWARE_DIR))
