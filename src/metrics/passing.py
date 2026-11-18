"""
Tactical Metric: Pass Detection, Pass Network, and Interception Modeling in SSL.
Identifies kick origins, trajectories, destinations, and builds team passing matrices.
"""

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from src.parser.cleaner import MatchSnapshot


@dataclass
class PassEvent:
    timestamp_start: float
    timestamp_end: float
    team: str  # 'yellow' or 'blue'
    passer_id: int
    receiver_id: Optional[int]
    outcome: str  # 'completed', 'intercepted', 'incomplete'
    start_x: float
    start_y: float
    end_x: float
    end_y: float
    distance: float
    duration: float


@dataclass
class PassingStats:
    total_passes: int = 0
    completed_passes: int = 0
    intercepted_passes: int = 0
    incomplete_passes: int = 0

    # pass_matrix[from_id][to_id] = count
    pass_matrix: Dict[int, Dict[int, int]] = field(default_factory=dict)
    passes_by_robot: Dict[int, int] = field(default_factory=dict)
    receptions_by_robot: Dict[int, int] = field(default_factory=dict)

    @property
    def accuracy_pct(self) -> float:
        return (self.completed_passes / self.total_passes * 100.0) if self.total_passes > 0 else 0.0


class PassAnalyzer:
    """Detects and categorizes pass events across match snapshots."""

    def __init__(
        self,
        kick_min_speed: float = 0.8,         # m/s
        min_pass_distance: float = 0.4,       # meters
        possession_dist: float = 0.18,        # meters
        max_pass_duration_sec: float = 3.0,   # seconds before timing out as incomplete
    ):
        self.kick_min_speed = kick_min_speed
        self.min_pass_distance = min_pass_distance
        self.possession_dist = possession_dist
        self.max_pass_duration = max_pass_duration_sec

        self.yellow_stats = PassingStats()
        self.blue_stats = PassingStats()
        self.detected_passes: List[PassEvent] = []

        self._active_pass_team: Optional[str] = None
        self._active_passer_id: Optional[int] = None
        self._pass_start_time: float = 0.0
        self._pass_start_pos: Tuple[float, float] = (0.0, 0.0)

        self._last_possessor: Optional[Tuple[str, int]] = None

    def _find_nearest_robot(
        self, bx: float, by: float, robots: Dict[int, any]
    ) -> Tuple[Optional[int], float]:
        closest_id = None
        min_d = float("inf")
        for r_id, r in robots.items():
            d = math.hypot(bx - r.x, by - r.y)
            if d < min_d:
                min_d = d
                closest_id = r_id
        return closest_id, min_d

    def process_snapshot(self, snapshot: MatchSnapshot):
        if snapshot.ball is None:
            return

        bx, by = snapshot.ball.x, snapshot.ball.y
        b_speed = math.hypot(snapshot.ball.vx, snapshot.ball.vy)
        t = snapshot.timestamp_sec

        # Find who is currently near the ball
        y_id, y_dist = self._find_nearest_robot(bx, by, snapshot.robots_yellow)
        b_id, b_dist = self._find_nearest_robot(bx, by, snapshot.robots_blue)

        current_possessor: Optional[Tuple[str, int]] = None
        if y_dist <= self.possession_dist and y_dist < b_dist:
            current_possessor = ("yellow", y_id)
        elif b_dist <= self.possession_dist and b_dist < y_dist:
            current_possessor = ("blue", b_id)

        # State 1: A pass is currently in flight
        if self._active_pass_team is not None:
            dt = t - self._pass_start_time
            pass_dist = math.hypot(bx - self._pass_start_pos[0], by - self._pass_start_pos[1])

            # Check if received
            if current_possessor is not None:
                team, r_id = current_possessor
                # Same robot holding it right after kick? Wait until ball leaves
                if team == self._active_pass_team and r_id == self._active_passer_id:
                    if dt < 0.2:
                        pass  # Still at passer
                    else:
                        # Regained ball without teammate intervention (dribble / loose touch)
                        self._active_pass_team = None
                elif team == self._active_pass_team:
                    # Completed pass to a teammate!
                    self._record_pass(
                        PassEvent(
                            timestamp_start=self._pass_start_time,
                            timestamp_end=t,
                            team=self._active_pass_team,
                            passer_id=self._active_passer_id,
                            receiver_id=r_id,
                            outcome="completed",
                            start_x=self._pass_start_pos[0],
                            start_y=self._pass_start_pos[1],
                            end_x=bx,
                            end_y=by,
                            distance=pass_dist,
                            duration=dt,
                        )
                    )
                    self._active_pass_team = None
                else:
                    # Intercepted by opponent!
                    self._record_pass(
                        PassEvent(
                            timestamp_start=self._pass_start_time,
                            timestamp_end=t,
                            team=self._active_pass_team,
                            passer_id=self._active_passer_id,
                            receiver_id=r_id,
                            outcome="intercepted",
                            start_x=self._pass_start_pos[0],
                            start_y=self._pass_start_pos[1],
                            end_x=bx,
                            end_y=by,
                            distance=pass_dist,
                            duration=dt,
                        )
                    )
                    self._active_pass_team = None

            elif dt > self.max_pass_duration or b_speed < 0.2:
                # Incomplete pass
                if pass_dist >= self.min_pass_distance:
                    self._record_pass(
                        PassEvent(
                            timestamp_start=self._pass_start_time,
                            timestamp_end=t,
                            team=self._active_pass_team,
                            passer_id=self._active_passer_id,
                            receiver_id=None,
                            outcome="incomplete",
                            start_x=self._pass_start_pos[0],
                            start_y=self._pass_start_pos[1],
                            end_x=bx,
                            end_y=by,
                            distance=pass_dist,
                            duration=dt,
                        )
                    )
                self._active_pass_team = None

        # State 2: Check for kick initiation
        else:
            if self._last_possessor is not None and b_speed >= self.kick_min_speed:
                # Kick detected from previous possessor
                team, r_id = self._last_possessor
                self._active_pass_team = team
                self._active_passer_id = r_id
                self._pass_start_time = t
                self._pass_start_pos = (bx, by)

        if current_possessor is not None:
            self._last_possessor = current_possessor

    def _record_pass(self, event: PassEvent):
        self.detected_passes.append(event)
        stats = self.yellow_stats if event.team == "yellow" else self.blue_stats
        stats.total_passes += 1

        p_id = event.passer_id
        stats.passes_by_robot[p_id] = stats.passes_by_robot.get(p_id, 0) + 1

        if event.outcome == "completed":
            stats.completed_passes += 1
            if event.receiver_id is not None:
                r_id = event.receiver_id
                stats.receptions_by_robot[r_id] = stats.receptions_by_robot.get(r_id, 0) + 1

                if p_id not in stats.pass_matrix:
                    stats.pass_matrix[p_id] = {}
                stats.pass_matrix[p_id][r_id] = stats.pass_matrix[p_id].get(r_id, 0) + 1

        elif event.outcome == "intercepted":
            stats.intercepted_passes += 1
        else:
            stats.incomplete_passes += 1
