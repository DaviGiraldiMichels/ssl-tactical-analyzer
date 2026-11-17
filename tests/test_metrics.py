import unittest
from src.metrics.passing import PassAnalyzer
from src.metrics.pitch_control import PitchControlAnalyzer
from src.metrics.possession import PossessionAnalyzer
from src.metrics.xg import ExpectedGoalsAnalyzer
from src.parser.cleaner import MatchSnapshot
from src.parser.proto_decoder import BallState, RobotState


class TestSSLMetrics(unittest.TestCase):
    def test_possession_evaluation(self):
        analyzer = PossessionAnalyzer()

        # Frame 1: Yellow robot 0 holds ball at (-1.0, 0.0)
        snap1 = MatchSnapshot(
            timestamp_sec=1.0,
            ball=BallState(x=-0.91, y=0.0, vx=0.0, vy=0.0),
            robots_yellow={
                0: RobotState(robot_id=0, team="yellow", x=-1.0, y=0.0, orientation=0.0)
            },
            robots_blue={
                0: RobotState(robot_id=0, team="blue", x=2.0, y=0.0, orientation=3.14)
            },
        )
        team, r_id = analyzer.evaluate_frame(snap1)
        self.assertEqual(team, "yellow")
        self.assertEqual(r_id, 0)

        # Frame 2: Ball is far from everyone
        snap2 = MatchSnapshot(
            timestamp_sec=2.0,
            ball=BallState(x=0.0, y=0.0),
            robots_yellow={0: RobotState(0, "yellow", -2.0, 0.0, 0.0)},
            robots_blue={0: RobotState(0, "blue", 2.0, 0.0, 3.14)},
        )
        team, r_id = analyzer.evaluate_frame(snap2)
        self.assertEqual(team, "loose")
        self.assertIsNone(r_id)

    def test_pitch_control_surface(self):
        analyzer = PitchControlAnalyzer(field_length_meters=9.0, field_width_meters=6.0)

        # Symmetric scenario
        snap = MatchSnapshot(
            timestamp_sec=0.0,
            robots_yellow={
                0: RobotState(0, "yellow", -2.0, 0.0, 0.0),
            },
            robots_blue={
                0: RobotState(0, "blue", 2.0, 0.0, 3.14),
            },
        )

        _, y_pct, b_pct = analyzer.calculate_control_surface(snap)
        self.assertAlmostEqual(y_pct, 50.0, delta=2.0)
        self.assertAlmostEqual(b_pct, 50.0, delta=2.0)

    def test_expected_goals(self):
        analyzer = ExpectedGoalsAnalyzer(field_length_meters=9.0, goal_width_meters=1.0)

        # Shot from 1.5m in front of open goal
        xg_close, dist, angle = analyzer.evaluate_xg(
            shooter_x=3.0,
            shooter_y=0.0,
            target_goal_x=4.5,
            shot_speed=4.0,
            defenders={},
        )
        self.assertGreater(xg_close, 0.5)

        # Shot from halfway line (4.5m away) with defender blocking
        xg_far, dist_far, angle_far = analyzer.evaluate_xg(
            shooter_x=0.0,
            shooter_y=0.0,
            target_goal_x=4.5,
            shot_speed=3.0,
            defenders={0: RobotState(0, "blue", 4.0, 0.0, 3.14)},
        )
        self.assertLess(xg_far, xg_close)


if __name__ == "__main__":
    unittest.main()
