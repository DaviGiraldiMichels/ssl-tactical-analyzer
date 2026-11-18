"""
Kinematics and Physical Workload Analyzer for RoboCup SSL.
Tracks total distance traveled, maximum peak speeds, and sprint counts per robot.
Essential for motor diagnostics, battery performance, and spatial work-rate evaluation.
"""

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from src.parser.cleaner import MatchSnapshot


@dataclass
class RobotKinematicProfile:
    robot_id: int
    team: str
    total_distance_m: float = 0.0
    max_speed_ms: float = 0.0
    avg_speed_ms: float = 0.0
    sprints_count: int = 0  # bursts above 2.0 m/s
    speed_samples_count: int = 0
    accumulated_speed: float = 0.0
    accumulated_x: float = 0.0
    accumulated_y: float = 0.0

    @property
    def avg_x(self) -> float:
        return self.accumulated_x / max(1, self.speed_samples_count)

    @property
    def avg_y(self) -> float:
        return self.accumulated_y / max(1, self.speed_samples_count)


@dataclass
class TeamKinematicsStats:
    total_team_distance_m: float = 0.0
    max_team_speed_ms: float = 0.0
    profiles: Dict[int, RobotKinematicProfile] = field(default_factory=dict)


class KinematicsAnalyzer:
    """Computes physical workload and velocity metrics for all robots."""

    def __init__(self, sprint_speed_threshold: float = 2.0):
        self.sprint_speed_threshold = sprint_speed_threshold
        self.yellow_stats = TeamKinematicsStats()
        self.blue_stats = TeamKinematicsStats()

        self._prev_snapshot: Optional[MatchSnapshot] = None
        self._in_sprint_state: Dict[str, Dict[int, bool]] = {"yellow": {}, "blue": {}}

    def process_snapshot(self, snapshot: MatchSnapshot):
        if self._prev_snapshot is None:
            self._prev_snapshot = snapshot
            return

        # 1. Process Yellow Team
        for r_id, r in snapshot.robots_yellow.items():
            if r_id not in self.yellow_stats.profiles:
                self.yellow_stats.profiles[r_id] = RobotKinematicProfile(robot_id=r_id, team="yellow")

            prof = self.yellow_stats.profiles[r_id]

            # Distance step
            if r_id in self._prev_snapshot.robots_yellow:
                prev_r = self._prev_snapshot.robots_yellow[r_id]
                step = math.hypot(r.x - prev_r.x, r.y - prev_r.y)
                # Ignore noise jumps > 1.0m in a single frame (16ms)
                if step < 0.5:
                    prof.total_distance_m += step
                    self.yellow_stats.total_team_distance_m += step

            # Speed with physical sanity limit (SSL robot speed limit is ~4.5 - 5.0 m/s)
            speed = min(6.5, math.hypot(r.vx, r.vy))
            if speed > prof.max_speed_ms:
                prof.max_speed_ms = speed
            if speed > self.yellow_stats.max_team_speed_ms:
                self.yellow_stats.max_team_speed_ms = speed

            prof.accumulated_speed += speed
            prof.accumulated_x += r.x
            prof.accumulated_y += r.y
            prof.speed_samples_count += 1
            prof.avg_speed_ms = prof.accumulated_speed / prof.speed_samples_count

            # Sprint detection
            was_sprinting = self._in_sprint_state["yellow"].get(r_id, False)
            if speed >= self.sprint_speed_threshold and not was_sprinting:
                prof.sprints_count += 1
                self._in_sprint_state["yellow"][r_id] = True
            elif speed < (self.sprint_speed_threshold - 0.4):
                self._in_sprint_state["yellow"][r_id] = False

        # 2. Process Blue Team
        for r_id, r in snapshot.robots_blue.items():
            if r_id not in self.blue_stats.profiles:
                self.blue_stats.profiles[r_id] = RobotKinematicProfile(robot_id=r_id, team="blue")

            prof = self.blue_stats.profiles[r_id]

            if r_id in self._prev_snapshot.robots_blue:
                prev_r = self._prev_snapshot.robots_blue[r_id]
                step = math.hypot(r.x - prev_r.x, r.y - prev_r.y)
                if step < 0.5:
                    prof.total_distance_m += step
                    self.blue_stats.total_team_distance_m += step

            # Speed with physical sanity limit
            speed = min(6.5, math.hypot(r.vx, r.vy))
            if speed > prof.max_speed_ms:
                prof.max_speed_ms = speed
            if speed > self.blue_stats.max_team_speed_ms:
                self.blue_stats.max_team_speed_ms = speed

            prof.accumulated_speed += speed
            prof.accumulated_x += r.x
            prof.accumulated_y += r.y
            prof.speed_samples_count += 1
            prof.avg_speed_ms = prof.accumulated_speed / prof.speed_samples_count

            was_sprinting = self._in_sprint_state["blue"].get(r_id, False)
            if speed >= self.sprint_speed_threshold and not was_sprinting:
                prof.sprints_count += 1
                self._in_sprint_state["blue"][r_id] = True
            elif speed < (self.sprint_speed_threshold - 0.4):
                self._in_sprint_state["blue"][r_id] = False

        self._prev_snapshot = snapshot
