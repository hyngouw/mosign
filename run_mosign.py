"""Entry point used by PyInstaller to build the double-clickable app."""

import sys

from mosign.app import main

if __name__ == "__main__":
    sys.exit(main())
