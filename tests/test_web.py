import unittest
from pathlib import Path

from src.web.server import MatchCache


class TestWebBackend(unittest.TestCase):
    def test_match_cache_and_frame_generation(self):
        sample_log = "data/sample_matches/synthetic_match.log.gz"
        self.assertTrue(Path(sample_log).exists())

        cache = MatchCache()
        data = cache.get_or_parse(sample_log, max_fps=20)

        # 1. Metadata checks
        self.assertIn("metadata", data)
        meta = data["metadata"]
        self.assertEqual(meta["yellow_name"], "UDESC Robotics")
        self.assertEqual(meta["blue_name"], "ER-Force")
        self.assertGreater(meta["duration_sec"], 0)
        self.assertGreater(len(data["frames"]), 0)

        # 2. KPI checks
        self.assertIn("kpis", data)
        kpis = data["kpis"]
        self.assertIn("possession_y", kpis)
        self.assertIn("passes_y_total", kpis)
        self.assertIn("xg_y", kpis)
        self.assertIn("saves_b", kpis)

        # 3. Frames structure check
        first_frame = data["frames"][0]
        self.assertIn("t", first_frame)
        self.assertIn("ball", first_frame)
        self.assertIn("y", first_frame)
        self.assertIn("b", first_frame)

        # 4. Events check
        self.assertIn("events", data)
        self.assertGreater(len(data["events"]), 0)


if __name__ == "__main__":
    unittest.main()
