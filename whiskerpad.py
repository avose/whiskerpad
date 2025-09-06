#!/usr/bin/env python3

import sys
import pathlib
import argparse

# Put the parent of this folder on sys.path so `import whiskerpad` works when run from repo root.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from whiskerpad.app import main

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="WhiskerPad notebook application")
    parser.add_argument("--verbosity", type=int, default=0, 
                        help="Set verbosity level (0=quiet, 1=normal, 2=verbose, 3+=debug)")
    args = parser.parse_args()
    
    sys.exit(main(verbosity=args.verbosity))
