"""Entry point for the animatic application."""

import sys
import os

# Add src to path so animatic package is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from animatic.main_window import main

if __name__ == "__main__":
    sys.exit(main())
