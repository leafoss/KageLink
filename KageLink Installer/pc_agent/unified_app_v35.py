from __future__ import annotations

# Compatibility module for KageLink 3.5 packaging and older entry points.
# The canonical unified_app owns the Dojo service, authenticated routes,
# GAME interlock and shutdown lifecycle.
from unified_app import APP_VERSION, app, dojo_service, runtime_status

__all__ = ["APP_VERSION", "app", "dojo_service", "runtime_status"]
