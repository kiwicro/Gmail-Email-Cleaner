#!/usr/bin/env python3
"""
Gmail Email Cleanmail - Desktop App
Entry point for the application.
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from src.main import main

if __name__ == '__main__':
    main()
