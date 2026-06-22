"""``python -m quickfix`` entry point — delegates to the CLI core."""
from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
