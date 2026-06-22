"""``python -m e2e_app`` entrypoint → delegates to :func:`e2e_app.app.main`.

Runnable two ways, both used by the executor/tests:
  - as a package on ``sys.path``:  ``python -m e2e_app --port P --store S --mode M``
  - by file path:                  ``python <.../e2e_app/__main__.py> ...``
The package-relative import is tried first; the path-based fallback lets the executor
launch the fixture by absolute file path without putting its parent on PYTHONPATH.
"""
import sys

try:  # package context: python -m e2e_app
    from e2e_app.app import main
except ImportError:  # path context: python <dir>/__main__.py
    import os
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from app import main  # type: ignore

if __name__ == "__main__":
    sys.exit(main())
