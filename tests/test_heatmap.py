import unittest
import numpy as np

from src.metrics.heatmap import SpatialHeatmapAnalyzer, gaussian_filter_2d
from src.parser.cleaner import MatchSnapshot
from src.parser.proto_decoder import BallState, RobotState


class TestSpatialHeatmap(unittest.TestCase):
    def setUp(self):
        self.analyzer = SpatialHeatmapAnalyzer(field_length=12.0, field_width=9.0, grid_nx=48, grid_ny=36)

    def test_pos_to_grid_mapping(self):
        # Center (0, 0)
        r, c = self.analyzer._pos_to_grid(0.0, 0.0)
        self.assertEqual(c, 24)
        self.assertEqual(r, 18)

        # Top-left corner (-6.0, +4.5)
        r_tl, c_tl = self.analyzer._pos_to_grid(-6.0, 4.5)
        self.assertEqual(c_tl, 0)
        self.assertEqual(r_tl, 0)

        # Bottom-right corner (+6.0, -4.5)
        r_br, c_br = self.analyzer._pos_to_grid(6.0, -4.5)
        self.assertEqual(c_br, 47)
        self.assertEqual(r_br, 35)

    def test_gaussian_filter_2d(self):
        grid = np.zeros((20, 20), dtype=np.float32)
        grid[10, 10] = 50.0

        filtered = gaussian_filter_2d(grid, sigma=1.5)
        self.assertAlmostEqual(float(filtered.sum()), 50.0, places=1)
        self.assertLess(filtered[10, 10], 50.0)
        self.assertGreater(filtered[10, 11], 0.0)  # Diffused to neighbor

    def test_process_snapshots_and_export(self):
        # Accumulate 10 synthetic snapshots
        for i in range(10):
            snap = MatchSnapshot(
                timestamp_sec=float(i) * 0.1,
                referee_command="NORMAL",
                ball=BallState(x=1.0, y=0.5, z=0.0, vx=0.0, vy=0.0),
                robots_yellow={
                    0: RobotState(robot_id=0, team="yellow", x=-4.0, y=0.0, orientation=0.0),
                    1: RobotState(robot_id=1, team="yellow", x=2.0, y=1.0, orientation=0.0),
                },
                robots_blue={
                    0: RobotState(robot_id=0, team="blue", x=4.0, y=0.0, orientation=0.0),
                },
            )
            self.analyzer.process_snapshot(snap)

        exported = self.analyzer.export_all_heatmaps()

        self.assertIn("ball", exported)
        self.assertIn("yellow", exported)
        self.assertIn("blue", exported)
        self.assertIn("yellow_robots", exported)
        self.assertIn("0", exported["yellow_robots"])
        self.assertIn("1", exported["yellow_robots"])
        self.assertIn("0", exported["blue_robots"])

        ball_map = exported["ball"]
        self.assertEqual(len(ball_map), 36)  # ny
        self.assertEqual(len(ball_map[0]), 48)  # nx

        # Check values are in [0.0, 1.0]
        max_val = max(max(row) for row in ball_map)
        self.assertAlmostEqual(max_val, 1.0, places=2)


if __name__ == "__main__":
    unittest.main()
