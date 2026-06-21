"""e2e_app — deterministic offline fixture web app for the browser-E2E executor.

See ``app.py`` for the full route/mode contract. Re-exported here so the package is
importable (``from e2e_app import make_server, main, MODES``) as well as runnable
(``python -m e2e_app --port P --store S --mode M``).
"""
from .app import MODES, E2EAppHandler, main, make_server  # noqa: F401
