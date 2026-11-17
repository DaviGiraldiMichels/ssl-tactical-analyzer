"""
Data Cleaner and Temporal Synchronizer for SSL Matches.
Handles multi-camera fusion, coordinate normalization (mm to meters),
orientation standardization, and velocity estimation.
"""

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from src.parser.proto_decoder import (
    BallState,
    FieldGeometry,
    RefereeState,
    RobotState,
    VisionFrame,
)


def angle_difference(a: float, b: float) -> float:
    """Calculates shortest angular difference between two angles in radians [-pi, pi]."""
    diff = (a - b + math.pi) % (2 * math.pi) - math.pi
    return diff


@dataclass
class MatchSnapshot:
    """Unified synchronized state of the field at a given timestamp."""

    timestamp_sec: float
    ball: Optional[BallState] = None
    robots_yellow: Dict[int, RobotState] = field(default_factory=dict)
    robots_blue: Dict[int, RobotState] = field(default_factory=dict)
    referee_command: str = "STOP"
    referee_stage: str = "NORMAL_FIRST_HALF"
    score_yellow: int = 0
    score_blue: int = 0


class SSLDataCleaner:
    """Processes, synchronizes, and cleans raw vision and referee frames."""

    def __init__(
        self,
        time_window_sec: float = 0.0166,  # ~60 Hz snapshot interval
        normalize_to_meters: bool = True,
        standardize_team_attack_right: Optional[str] = None,  # 'yellow' or 'blue'
    ):
        self.time_window_sec = time_window_sec
        self.normalize_to_meters = normalize_to_meters
        self.scale = 0.001 if normalize_to_meters else 1.0  # mm to meters
        self.standardize_team = standardize_team_attack_right

        self._current_snapshot: Optional[MatchSnapshot] = None
        self._last_emitted_time: float = -1.0
        self._prev_snapshot: Optional[MatchSnapshot] = None

        self._current_referee: Optional[RefereeState] = None

    def update_referee(self, ref: RefereeState):
        self._current_referee = ref
        if self._current_snapshot:
            self._current_snapshot.referee_command = ref.command
            self._current_snapshot.referee_stage = ref.stage
            self._current_snapshot.score_yellow = ref.yellow.score
            self._current_snapshot.score_blue = ref.blue.score

    def process_frame(self, frame: VisionFrame) -> Optional[MatchSnapshot]:
        """
        Ingests a vision frame from a camera.
        Returns a completed MatchSnapshot when the time window advances.
        """
        t_sec = frame.t_capture

        if self._current_snapshot is None:
            self._current_snapshot = self._create_empty_snapshot(t_sec)

        # Check if this frame belongs to a new time window
        if t_sec - self._current_snapshot.timestamp_sec >= self.time_window_sec:
            completed = self._finalize_snapshot(self._current_snapshot)
            self._current_snapshot = self._create_empty_snapshot(t_sec)
            self._merge_frame_into_snapshot(frame, self._current_snapshot)
            return completed
        else:
            self._merge_frame_into_snapshot(frame, self._current_snapshot)
            return None

    def flush(self) -> Optional[MatchSnapshot]:
        """Flushes the final pending snapshot."""
        if self._current_snapshot is not None:
            completed = self._finalize_snapshot(self._current_snapshot)
            self._current_snapshot = None
            return completed
        return None

    def _create_empty_snapshot(self, t_sec: float) -> MatchSnapshot:
        cmd = self._current_referee.command if self._current_referee else "STOP"
        stg = self._current_referee.stage if self._current_referee else "NORMAL_FIRST_HALF"
        sc_y = self._current_referee.yellow.score if self._current_referee else 0
        sc_b = self._current_referee.blue.score if self._current_referee else 0

        return MatchSnapshot(
            timestamp_sec=t_sec,
            referee_command=cmd,
            referee_stage=stg,
            score_yellow=sc_y,
            score_blue=sc_b,
        )

    def _merge_frame_into_snapshot(self, frame: VisionFrame, snapshot: MatchSnapshot):
        # 1. Merge Ball
        best_ball = frame.primary_ball
        if best_ball is not None:
            if snapshot.ball is None or best_ball.confidence > snapshot.ball.confidence:
                snapshot.ball = BallState(
                    x=best_ball.x * self.scale,
                    y=best_ball.y * self.scale,
                    z=best_ball.z * self.scale,
                    confidence=best_ball.confidence,
                )

        # 2. Merge Yellow Robots
        for r_id, r in frame.robots_yellow.items():
            if r_id not in snapshot.robots_yellow or r.confidence > snapshot.robots_yellow[r_id].confidence:
                snapshot.robots_yellow[r_id] = RobotState(
                    robot_id=r_id,
                    team="yellow",
                    x=r.x * self.scale,
                    y=r.y * self.scale,
                    orientation=r.orientation,
                    confidence=r.confidence,
                )

        # 3. Merge Blue Robots
        for r_id, r in frame.robots_blue.items():
            if r_id not in snapshot.robots_blue or r.confidence > snapshot.robots_blue[r_id].confidence:
                snapshot.robots_blue[r_id] = RobotState(
                    robot_id=r_id,
                    team="blue",
                    x=r.x * self.scale,
                    y=r.y * self.scale,
                    orientation=r.orientation,
                    confidence=r.confidence,
                )

    def _finalize_snapshot(self, snapshot: MatchSnapshot) -> MatchSnapshot:
        # Calculate velocities by comparing with previous snapshot
        dt = 0.0
        if self._prev_snapshot is not None:
            dt = snapshot.timestamp_sec - self._prev_snapshot.timestamp_sec

        if dt > 0.001 and self._prev_snapshot is not None:
            # Ball velocity
            if snapshot.ball and self._prev_snapshot.ball:
                snapshot.ball.vx = (snapshot.ball.x - self._prev_snapshot.ball.x) / dt
                snapshot.ball.vy = (snapshot.ball.y - self._prev_snapshot.ball.y) / dt

            # Yellow robots velocity
            for r_id, r in snapshot.robots_yellow.items():
                if r_id in self._prev_snapshot.robots_yellow:
                    prev_r = self._prev_snapshot.robots_yellow[r_id]
                    r.vx = (r.x - prev_r.x) / dt
                    r.vy = (r.y - prev_r.y) / dt
                    r.omega = angle_difference(r.orientation, prev_r.orientation) / dt

            # Blue robots velocity
            for r_id, r in snapshot.robots_blue.items():
                if r_id in self._prev_snapshot.robots_blue:
                    prev_r = self._prev_snapshot.robots_blue[r_id]
                    r.vx = (r.x - prev_r.x) / dt
                    r.vy = (r.y - prev_r.y) / dt
                    r.omega = angle_difference(r.orientation, prev_r.orientation) / dt

        self._prev_snapshot = snapshot
        return snapshot
