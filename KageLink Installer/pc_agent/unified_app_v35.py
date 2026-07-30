from __future__ import annotations

# Compatibility module retained for installed 3.5.x entry points. The canonical
# runtime owns the Dojo service and start/stop routes; this wrapper installs the
# user-template and 3.5.1 reliability routes without duplicating combat logic.
import unified_app as _canonical

from pc_agent.dojo_templates_api_v35 import install_dojo_template_routes


APP_VERSION = "3.5.1"
_canonical.APP_VERSION = APP_VERSION
_canonical.legacy.APP_VERSION = APP_VERSION
_canonical.legacy.app.version = APP_VERSION

app = _canonical.app
dojo_service = _canonical.dojo_service
runtime_status = _canonical.runtime_status

install_dojo_template_routes(app, _canonical.legacy.security, dojo_service)

__all__ = ["APP_VERSION", "app", "dojo_service", "runtime_status"]
