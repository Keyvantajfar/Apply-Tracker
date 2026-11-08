"""PyInstaller entry point (the package uses relative imports, so it cannot be the entry itself)."""
import sys

from gradapp.cli import main

if __name__ == "__main__":
    sys.exit(main())
