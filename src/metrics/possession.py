"""
Tactical Metric: Ball Possession and Control in SSL.
Calculates frame-by-frame possession, team percentages, zone distributions,
and turnover events.
"""

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from src.parser.cleaner import MatchSnapshot


@dataclass
class PossessionEvent:
    start_time: float
    end_time: float
    team: str  # 'yellow', 'blue', 'contested', 'loose'
    robot_id: Optional[int] = None
    zone: str = "middle"  # 'defensive', 'middle', 'offensive'


@dataclass
class PossessionStats:
    total_time_sec: float = 0.0
    yellow_time_sec: float = 0.0
    blue_time_sec: float = 0.0
    contested_time_sec: float = 0.0
    loose_time_sec: float = 0.0

    # Zone percentages (yellow perspective)
    yellow_defensive_sec: float = 0.0
    yellow_middle_sec: float = 0.0
    yellow_offensive_sec: float = 0.0

    # Zone percentages (blue perspective)
    blue_defensive_sec: float = 0.0
    blue_middle_sec: float = 0.0
    blue_offensive_sec: float = 0.0

    yellow_turnovers: int = 0
    blue_turnovers: int = 0

    robot_possession_sec: Dict[str, Dict[int, float]] = field(
        default_factory=lambda: {"yellow": {}, "blue": {}}
    )

    @property
    def yellow_possession_pct(self) -> float:
        controlled = self.yellow_time_sec + self.blue_time_sec
        return (self.yellow_time_sec / controlled * 100.0) if controlled > 0 else 50.0

    @property
    def blue_possession_pct(self) -> float:
        controlled = self.yellow_time_sec + self.blue_time_sec
        return (self.blue_time_sec / controlled * 100.0) if controlled > 0 else 50.0


class PossessionAnalyzer:
    """Analyzes ball possession over a sequence of MatchSnapshots."""

    def __init__(
        self,
        dribbler_dist_threshold: float = 0.16,  # meters (robot radius ~0.09m + ball radius ~0.021m + margin)
        contest_dist_threshold: float = 0.22,    # meters
        dribbler_angle_max: float = 0.85,       # ~48 degrees front angle
        field_length_meters: float = 9.0,        # Div B default
    ):
        self.dribbler_dist = dribbler_dist_threshold
        self.contest_dist = contest_dist_threshold
        self.dribbler_angle_max = dribbler_angle_max
        self.field_length = field_length_meters

        self.stats = PossessionStats()
        self._prev_snapshot: Optional[MatchSnapshot] = None
        self._last_possessing_team: Optional[str] = None

    def _determine_zone(self, x: float, team: str) -> str:
        """Categorizes X position into defensive, middle, or offensive third."""
        third = self.field_length / 6.0  # field is [-L/2, +L/2], so thirds are -L/6 and +L/6
        # Assume Yellow defends negative X, Blue defends positive X by default
        if team == "yellow":
            if x < -third:
                return "defensive"
            elif x > third:
                return "offensive"
            return "middle"
        else:
            if x > third:
                return "defensive"
            elif x < -third:
                return "offensive"
            return "middle"

    def _check_robot_control(self, rx: float, ry: float, r_orient: float, bx: float, by: float) -> Tuple[bool, float]:
        dx = bx - rx
        dy = by - ry
        dist = math.hypot(dx, dy)
        if dist > self.dribbler_dist:
            return False, dist

        # Check angle towards ball relative to robot front
        angle_to_ball = math.atan2(dy, dx)
        angle_diff = abs((angle_to_ball - r_orient + math.pi) % (2 * math.pi) - math.pi)

        return (angle_diff <= self.dribbler_angle_max), dist

    def evaluate_frame(self, snapshot: MatchSnapshot) -> Tuple[str, Optional[int]]:
        """
        Evaluates possession for a single snapshot.
        Returns (team, robot_id), where team in ['yellow', 'blue', 'contested', 'loose'].
        """
        if snapshot.ball is None:
            return "loose", None

        bx, by = snapshot.ball.x, snapshot.ball.y

        closest_yellow_id = None
        closest_yellow_dist = float("inf")
        yellow_in_control = False

        for r_id, r in snapshot.robots_yellow.items():
            in_ctrl, dist = self._check_robot_control(r.x, r.y, r.orientation, bx, by)
            if dist < closest_yellow_dist:
                closest_yellow_dist = dist
                closest_yellow_id = r_id
                yellow_in_control = in_ctrl

        closest_blue_id = None
        closest_blue_dist = float("inf")
        blue_in_control = False

        for r_id, r in snapshot.robots_blue.items():
            in_ctrl, dist = self._check_robot_control(r.x, r.y, r.orientation, bx, by)
            if dist < closest_blue_dist:
                closest_blue_dist = dist
                closest_blue_id = r_id
                blue_in_control = in_ctrl

        # Disputa (both teams close)
        if closest_yellow_dist <= self.contest_dist and closest_blue_dist <= self.contest_dist:
            return "contested", None

        if yellow_in_control or (closest_yellow_dist <= self.dribbler_dist and closest_yellow_dist < closest_blue_dist):
            return "yellow", closest_yellow_id

        if blue_in_control or (closest_blue_dist <= self.dribbler_dist and closest_blue_dist < closest_yellow_dist):
            return "blue", closest_blue_id

        return "loose", None

    def process_snapshot(self, snapshot: MatchSnapshot):
        dt = 0.0166  # default
        if self._prev_snapshot is not None:
            dt = snapshot.timestamp_sec - self._prev_snapshot.timestamp_sec
            if dt <= 0 or dt > 0.5:
                dt = 0.0166

        team, robot_id = self.evaluate_frame(snapshot)
        self.stats.total_time_sec += dt

        if team == "yellow":
            self.stats.yellow_time_sec += dt
            if robot_id is not None:
                curr = self.stats.robot_possession_sec["yellow"].get(robot_id, 0.0)
                self.stats.robot_possession_sec["yellow"][robot_id] = curr + dt
            if snapshot.ball:
                zone = self._determine_zone(snapshot.ball.x, "yellow")
                if zone == "defensive":
                    self.stats.yellow_defensive_sec += dt
                elif zone == "middle":
                    self.stats.yellow_middle_sec += dt
                else:
                    self.stats.yellow_offensive_sec += dt

            if self._last_possessing_team == "blue":
                self.stats.blue_turnovers += 1
            self._last_possessing_team = "yellow"

        elif team == "blue":
            self.stats.blue_time_sec += dt
            if robot_id is not None:
                curr = self.stats.robot_possession_sec["blue"].get(robot_id, 0.0)
                self.stats.robot_possession_sec["blue"][robot_id] = curr + dt
            if snapshot.ball:
                zone = self._determine_zone(snapshot.ball.x, "blue")
                if zone == "defensive":
                    self.stats.blue_defensive_sec += dt
                elif zone == "middle":
                    self.stats.blue_middle_sec += dt
                else:
                    self.stats.blue_offensive_sec += dt

            if self._last_possessing_team == "yellow":
                self.stats.yellow_turnovers += 1
            self._last_possessing_team = "blue"

        elif team == "contested":
            self.stats.contested_time_sec += dt
        else:
            self.stats.loose_time_sec += dt

        self._prev_snapshot = snapshot
