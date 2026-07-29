from __future__ import annotations

from pathlib import Path
import unittest

from pc_agent.kage_pilot import DojoTrainingPhase, DojoTrainingService


class KagePilotV03KServiceTelemetryTests(unittest.TestCase):
    def test_ring_progress_does_not_increment_completed_rounds(self):
        service = DojoTrainingService(project_dir=Path("C:/KageLink/pc_agent"))
        service._consume_output_line(
            "TRAINER_SEARCH state=SEARCH_LEADER move=right "
            "reason=concentric cell-ring search ring=3/29 completed=2 cells=19"
        )
        snapshot = service.snapshot()
        self.assertEqual(snapshot.completed_rounds, 0)

    def test_round_complete_updates_completed_rounds(self):
        service = DojoTrainingService(project_dir=Path("C:/KageLink/pc_agent"))
        service._consume_output_line("ROUND 10: COMPLETE / CONCLUIDA")
        snapshot = service.snapshot()
        self.assertEqual(snapshot.completed_rounds, 10)
        self.assertEqual(snapshot.phase, DojoTrainingPhase.READY)

    def test_loop_summary_updates_completed_rounds_and_stops(self):
        service = DojoTrainingService(project_dir=Path("C:/KageLink/pc_agent"))
        service._consume_output_line(
            "DOJO_LOOP_FINISHED requested=10 processed=10 completed=10 "
            "finished_without_combat=0 failed=0 emergency_stopped=0"
        )
        snapshot = service.snapshot()
        self.assertEqual(snapshot.completed_rounds, 10)
        self.assertEqual(snapshot.phase, DojoTrainingPhase.STOPPED)

    def test_dojo_final_is_authoritative_summary(self):
        service = DojoTrainingService(project_dir=Path("C:/KageLink/pc_agent"))
        service._consume_output_line("DOJO_FINAL phase=stopped completed=10 return_code=0")
        snapshot = service.snapshot()
        self.assertEqual(snapshot.completed_rounds, 10)
        self.assertEqual(snapshot.phase, DojoTrainingPhase.STOPPED)


if __name__ == "__main__":
    unittest.main()
