"""Canonical isolated Kage Pilot round entrypoint.

KageLink 3.5.1 adds visual position, conservative relocalization, closed-loop
return and a defensive R hold during the existing round startup delay without
changing the validated combat or Trainer matching contracts.
"""

from __future__ import annotations

from pc_agent.kage_pilot.dojo_user_templates_v351 import (
    install_user_owned_template_pipeline,
)
from pc_agent.kage_pilot.dojo_precombat_guard_v351 import (
    install_round_precombat_r_hold,
)

install_user_owned_template_pipeline()
install_round_precombat_r_hold()

from kage_pilot_visual_return import main


if __name__ == "__main__":
    raise SystemExit(main())
