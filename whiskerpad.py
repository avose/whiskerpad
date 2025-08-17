#!/usr/bin/env python3
import sys, pathlib
# Put the parent of this folder on sys.path so `import whiskerpad` works when run from repo root.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
from whiskerpad.app import main
if __name__ == "__main__":
    main()
