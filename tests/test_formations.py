import unittest
import math

from src.metrics.formations import (
    TacticalFormationsAnalyzer,
    convex_hull_2d,
    polygon_area,
)
from src.parser.cleaner import MatchSnapshot
from src.parser.proto_decoder import BallState, RobotState


class TestTacticalFormations(unittest.TestCase):
    def test_convex_hull_and_area(self):
        # 1. Square 4x4 with an internal point (2, 2)
        pts = [(0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0), (2.0, 2.0)]
        hull = convex_hull_2d(pts)
        self.assertEqual(len(hull), 4)
        area = polygon_area(hull)
        self.assertAlmostEqual(area, 16.0, places=2)

        # 2. Triangle base 4, height 3
        tri = [(0.0, 0.0), (4.0, 0.0), (0.0, 3.0)]
        tri_hull = convex_hull_2d(tri)
        self.assertEqual(len(tri_hull), 3)
        self.assertAlmostEqual(polygon_area(tri_hull), 6.0, places=2)

        # 3. Degenerate collinear points
        line = [(0.0, 0.0), (1.0, 1.0), (2.0, 2.0)]
        line_hull = convex_hull_2d(line)
        self.assertAlmostEqual(polygon_area(line_hull), 0.0, places=2)

    def test_calculate_shape_and_metrics(self):
        analyzer = TacticalFormationsAnalyzer(field_length=12.0, field_width=9.0)

        # 4 robots forming a 2x3 rectangle
        robots = {
            0: RobotState(robot_id=0, team="yellow", x=-3.0, y=-1.0, orientation=0.0),
            1: RobotState(robot_id=1, team="yellow", x=-1.0, y=-1.0, orientation=0.0),
            2: RobotState(robot_id=2, team="yellow", x=-1.0, y=2.0, orientation=0.0),
            3: RobotState(robot_id=3, team="yellow", x=-3.0, y=2.0, orientation=0.0),
        }

        shape = analyzer.calculate_shape(robots, timestamp=1.0, team="yellow")
        self.assertIsNotNone(shape)
        self.assertAlmostEqual(shape.centroid_x, -2.0, places=2)
        self.assertAlmostEqual(shape.centroid_y, 0.5, places=2)
        self.assertAlmostEqual(shape.length_m, 2.0, places=2)
        self.assertAlmostEqual(shape.width_m, 3.0, places=2)
        self.assertAlmostEqual(shape.area_m2, 6.0, places=2)
        self.assertGreater(shape.stretch_index_m, 0.0)

    def test_support_triangles_detection(self):
        analyzer = TacticalFormationsAnalyzer(field_length=12.0, field_width=9.0)

        robots = {
            1: RobotState(robot_id=1, team="yellow", x=0.0, y=0.0, orientation=0.0),
            2: RobotState(robot_id=2, team="yellow", x=2.0, y=0.0, orientation=0.0),
            3: RobotState(robot_id=3, team="yellow", x=1.0, y=1.732, orientation=0.0),  # Equilateral triangle
            4: RobotState(robot_id=4, team="yellow", x=8.0, y=8.0, orientation=0.0),  # Far away robot
        }

        triangles = analyzer.detect_support_triangles(robots, min_area=0.3, max_dist=3.0)
        self.assertEqual(len(triangles), 1)
        tri = triangles[0]
        self.assertIn(1, tri.robot_ids)
        self.assertIn(2, tri.robot_ids)
        self.assertIn(3, tri.robot_ids)
        self.assertNotIn(4, tri.robot_ids)

    def test_analyzer_in_play_accumulation_and_export(self):
        analyzer = TacticalFormationsAnalyzer(field_length=12.0, field_width=9.0)

        # 1. Stopped snapshot should NOT accumulate
        snap_stop = MatchSnapshot(
            timestamp_sec=0.5,
            referee_command="STOP",
            robots_yellow={
                0: RobotState(robot_id=0, team="yellow", x=0.0, y=0.0, orientation=0.0),
                1: RobotState(robot_id=1, team="yellow", x=2.0, y=0.0, orientation=0.0),
                2: RobotState(robot_id=2, team="yellow", x=1.0, y=2.0, orientation=0.0),
            },
        )
        analyzer.process_snapshot(snap_stop)
        self.assertEqual(analyzer.yellow_stats.total_samples, 0)

        # 2. In-play snapshot SHOULD accumulate
        snap_play = MatchSnapshot(
            timestamp_sec=1.0,
            referee_command="NORMAL_START",
            robots_yellow={
                0: RobotState(robot_id=0, team="yellow", x=0.0, y=0.0, orientation=0.0),
                1: RobotState(robot_id=1, team="yellow", x=2.0, y=0.0, orientation=0.0),
                2: RobotState(robot_id=2, team="yellow", x=0.0, y=2.0, orientation=0.0),
            },
            robots_blue={
                0: RobotState(robot_id=0, team="blue", x=3.0, y=0.0, orientation=0.0),
                1: RobotState(robot_id=1, team="blue", x=5.0, y=0.0, orientation=0.0),
                2: RobotState(robot_id=2, team="blue", x=3.0, y=2.0, orientation=0.0),
            },
        )
        analyzer.process_snapshot(snap_play)
        self.assertEqual(analyzer.yellow_stats.total_samples, 1)
        self.assertEqual(analyzer.blue_stats.total_samples, 1)

        summary = analyzer.export_summary()
        self.assertIn("yellow", summary)
        self.assertIn("blue", summary)
        self.assertAlmostEqual(summary["yellow"]["avg_area_m2"], 2.0, places=1)
        self.assertAlmostEqual(summary["blue"]["avg_area_m2"], 2.0, places=1)


if __name__ == "__main__":
    unittest.main()
