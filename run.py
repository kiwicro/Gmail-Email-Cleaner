#!/usr/bin/env python3
"""
Gmail Email Cleanmail - Entry point

Run this script to start the local web interface.
All data stays on your local machine - nothing is sent externally.
"""

import sys
import os

# Add src to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.app import run_app

if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
        description='Gmail Email Cleanmail - Local Gmail Aggregation Tool'
    )
    parser.add_argument(
        '--port', '-p',
        type=int,
        default=5000,
        help='Port to run the server on (default: 5000)'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Run in debug mode'
    )

    args = parser.parse_args()

    run_app(port=args.port, debug=args.debug)
