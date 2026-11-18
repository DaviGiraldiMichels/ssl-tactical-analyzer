import unittest
from src.metrics.defense import DefenseAnalyzer
from src.metrics.kinematics import KinematicsAnalyzer
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

    def test_defense_tackle_and_save(self):
        analyzer = DefenseAnalyzer(field_length_meters=9.0, goal_width_meters=1.0)

        # 1. Test Tackle: Yellow 0 has ball, Blue 1 takes it away
        snap1 = MatchSnapshot(
            timestamp_sec=1.0,
            ball=BallState(x=0.0, y=0.0, vx=0.1, vy=0.0),
            robots_yellow={0: RobotState(0, "yellow", -0.09, 0.0, 0.0)},
            robots_blue={1: RobotState(1, "blue", 0.5, 0.0, 3.14)},
        )
        analyzer.process_snapshot(snap1, "yellow", 0)

        # Blue 1 strips ball
        snap2 = MatchSnapshot(
            timestamp_sec=1.05,
            ball=BallState(x=0.0, y=0.0, vx=0.0, vy=0.0),
            robots_yellow={0: RobotState(0, "yellow", -0.3, 0.0, 0.0)},
            robots_blue={1: RobotState(1, "blue", 0.09, 0.0, 3.14)},
        )
        analyzer.process_snapshot(snap2, "blue", 1)

        self.assertEqual(analyzer.blue_stats.tackles_won, 1)
        self.assertEqual(analyzer.blue_stats.tackles_by_robot[1], 1)

        # 2. Test Goalkeeper Save: Shot incoming on Blue's goal (in +X)
        analyzer.register_incoming_shot(shooter_team="yellow", xg=0.65, timestamp=2.0)

        # Blue goalie #0 in box (x=4.3, y=0.0) stops ball
        snap_save = MatchSnapshot(
            timestamp_sec=2.2,
            ball=BallState(x=4.25, y=0.0, vx=0.1, vy=0.0),
            robots_blue={0: RobotState(0, "blue", 4.3, 0.0, 3.14)},
        )
        analyzer.process_snapshot(snap_save, "blue", 0)

        self.assertEqual(analyzer.blue_stats.goalkeeper_saves, 1)
        self.assertAlmostEqual(analyzer.blue_stats.goals_prevented_xg, 0.65)

    def test_kinematics(self):
        analyzer = KinematicsAnalyzer(sprint_speed_threshold=2.0)

        # Frame 1: Robot 0 at (0, 0)
        snap1 = MatchSnapshot(
            timestamp_sec=0.0,
            robots_yellow={0: RobotState(0, "yellow", 0.0, 0.0, 0.0, vx=0.0, vy=0.0)},
        )
        analyzer.process_snapshot(snap1)

        # Frame 2: Robot 0 moves to (0.1, 0) with speed 2.5 m/s
        snap2 = MatchSnapshot(
            timestamp_sec=0.04,
            robots_yellow={0: RobotState(0, "yellow", 0.1, 0.0, 0.0, vx=2.5, vy=0.0)},
        )
        analyzer.process_snapshot(snap2)

        prof = analyzer.yellow_stats.profiles[0]
        self.assertAlmostEqual(prof.total_distance_m, 0.1, delta=0.01)
        self.assertEqual(prof.max_speed_ms, 2.5)
        self.assertEqual(prof.sprints_count, 1)


if __name__ == "__main__":
    unittest.main()
