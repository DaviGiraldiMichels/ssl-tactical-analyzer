"""
Tactical Metric: Expected Goals (xG) for RoboCup SSL.
Calculates the geometric and kinematic goal expectation for shots on target,
accounting for distance, visible angle, and goalkeeper/defender obstructions.
"""

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from src.parser.cleaner import MatchSnapshot


@dataclass
class ShotEvent:
    timestamp: float
    team: str  # 'yellow' or 'blue'
    shooter_id: Optional[int]
    start_x: float
    start_y: float
    shot_speed: float
    distance_to_goal: float
    visible_angle_deg: float
    xg: float
    outcome: str = "shot"  # 'goal', 'saved', 'blocked', 'missed'


@dataclass
class ShotStats:
    total_shots: int = 0
    total_xg: float = 0.0
    shots_on_target: int = 0
    goals: int = 0
    shots: List[ShotEvent] = field(default_factory=list)


class ExpectedGoalsAnalyzer:
    """Detects shots and evaluates Expected Goals (xG) for RoboCup SSL matches."""

    def __init__(
        self,
        field_length_meters: float = 9.0,   # Div B default
        goal_width_meters: float = 1.0,
        shot_speed_threshold: float = 1.8,  # m/s
        robot_radius: float = 0.09,
    ):
        self.field_length = field_length_meters
        self.goal_width = goal_width_meters
        self.shot_speed_threshold = shot_speed_threshold
        self.robot_radius = robot_radius

        self.yellow_stats = ShotStats()
        self.blue_stats = ShotStats()

        self._cooldown_timer: float = 0.0
        self._last_shooter: Optional[Tuple[str, int]] = None

    def _calculate_subtended_angle(self, px: float, py: float, target_x: float) -> float:
        """Calculates angular width (in radians) of the goal opening from point (px, py)."""
        top_post = (target_x, self.goal_width / 2.0)
        bot_post = (target_x, -self.goal_width / 2.0)

        v1 = (top_post[0] - px, top_post[1] - py)
        v2 = (bot_post[0] - px, bot_post[1] - py)

        d1 = math.hypot(v1[0], v1[1])
        d2 = math.hypot(v2[0], v2[1])

        if d1 < 1e-4 or d2 < 1e-4:
            return math.pi

        dot = (v1[0] * v2[0] + v1[1] * v2[1]) / (d1 * d2)
        dot = max(-1.0, min(1.0, dot))
        return math.acos(dot)

    def _calculate_block_factor(
        self, sx: float, sy: float, target_x: float, defenders: Dict[int, any]
    ) -> float:
        """
        Estimates obstruction fraction [0, 1] by defenders standing between shooter and goal.
        """
        block_factor = 0.0
        for d in defenders.values():
            # Check if defender is in front of shooter towards target_x
            if (target_x > sx and sx < d.x < target_x) or (target_x < sx and target_x < d.x < sx):
                # Distance of defender to the central shot line
                # Central line from (sx, sy) to (target_x, 0)
                dx = target_x - sx
                dy = 0.0 - sy
                line_len = math.hypot(dx, dy)
                if line_len > 1e-4:
                    perp_dist = abs(dy * d.x - dx * d.y + target_x * sy - 0.0 * sx) / line_len
                    if perp_dist < (self.robot_radius + 0.05):
                        # Defender is directly blocking
                        block_factor += 0.45

        return min(0.9, block_factor)

    def evaluate_xg(
        self,
        shooter_x: float,
        shooter_y: float,
        target_goal_x: float,
        shot_speed: float,
        defenders: Dict[int, any],
    ) -> Tuple[float, float, float]:
        """Returns (xg, distance, visible_angle_deg)."""
        dist = math.hypot(target_goal_x - shooter_x, 0.0 - shooter_y)
        angle_rad = self._calculate_subtended_angle(shooter_x, shooter_y, target_goal_x)
        angle_deg = math.degrees(angle_rad)

        block_fraction = self._calculate_block_factor(shooter_x, shooter_y, target_goal_x, defenders)

        # Baseline empirical xG model for SSL:
        # Logistic based on angle, penalized by distance and defender block
        angle_term = (angle_deg / 45.0)  # normalized to 45 deg opening
        dist_decay = math.exp(-0.35 * max(0.0, dist - 1.0))
        speed_bonus = min(1.3, max(0.8, shot_speed / 3.0))

        raw_xg = 0.85 * angle_term * dist_decay * (1.0 - block_fraction) * speed_bonus
        xg = max(0.01, min(0.99, raw_xg))

        return xg, dist, angle_deg

    def process_snapshot(self, snapshot: MatchSnapshot):
        if snapshot.ball is None:
            return

        bx, by = snapshot.ball.x, snapshot.ball.y
        b_speed = math.hypot(snapshot.ball.vx, snapshot.ball.vy)
        t = snapshot.timestamp_sec

        if t < self._cooldown_timer:
            return

        # Check if ball is moving fast towards a goal
        goal_x_blue = self.field_length / 2.0   # Yellow attacks +X
        goal_x_yellow = -self.field_length / 2.0  # Blue attacks -X

        # Case 1: Yellow shot on Blue's goal (moving towards +X)
        if snapshot.ball.vx > self.shot_speed_threshold and bx > 0:
            # Find closest yellow robot
            shooter_id = None
            min_d = float("inf")
            for r_id, r in snapshot.robots_yellow.items():
                d = math.hypot(bx - r.x, by - r.y)
                if d < min_d:
                    min_d = d
                    shooter_id = r_id

            if min_d < 0.35:
                xg, dist, angle_deg = self.evaluate_xg(
                    bx, by, goal_x_blue, b_speed, snapshot.robots_blue
                )
                shot = ShotEvent(
                    timestamp=t,
                    team="yellow",
                    shooter_id=shooter_id,
                    start_x=bx,
                    start_y=by,
                    shot_speed=b_speed,
                    distance_to_goal=dist,
                    visible_angle_deg=angle_deg,
                    xg=xg,
                )
                self.yellow_stats.total_shots += 1
                self.yellow_stats.total_xg += xg
                self.yellow_stats.shots.append(shot)
                self._cooldown_timer = t + 1.0  # 1 sec cooldown

        # Case 2: Blue shot on Yellow's goal (moving towards -X)
        elif snapshot.ball.vx < -self.shot_speed_threshold and bx < 0:
            shooter_id = None
            min_d = float("inf")
            for r_id, r in snapshot.robots_blue.items():
                d = math.hypot(bx - r.x, by - r.y)
                if d < min_d:
                    min_d = d
                    shooter_id = r_id

            if min_d < 0.35:
                xg, dist, angle_deg = self.evaluate_xg(
                    bx, by, goal_x_yellow, b_speed, snapshot.robots_yellow
                )
                shot = ShotEvent(
                    timestamp=t,
                    team="blue",
                    shooter_id=shooter_id,
                    start_x=bx,
                    start_y=by,
                    shot_speed=b_speed,
                    distance_to_goal=dist,
                    visible_angle_deg=angle_deg,
                    xg=xg,
                )
                self.blue_stats.total_shots += 1
                self.blue_stats.total_xg += xg
                self.blue_stats.shots.append(shot)
                self._cooldown_timer = t + 1.0
