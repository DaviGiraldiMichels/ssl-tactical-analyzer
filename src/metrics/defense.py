"""
Tactical Metric: Defensive Actions, Ball Steals (Tackles), and Goalkeeper Saves for SSL.
Tracks direct dispossessions, loose ball recoveries, and goalkeeper intervention efficiency.
"""

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from src.parser.cleaner import MatchSnapshot


@dataclass
class DefensiveEvent:
    timestamp: float
    team: str  # team that performed the defensive action ('yellow' or 'blue')
    actor_id: int
    event_type: str  # 'tackle' (roubo direto), 'recovery' (recuperação), 'goalkeeper_save' (defesa)
    target_opponent_id: Optional[int] = None
    x: float = 0.0
    y: float = 0.0
    shot_xg_saved: float = 0.0


@dataclass
class DefensiveStats:
    tackles_won: int = 0  # Roubos de bola diretos (desarmes)
    interceptions: int = 0  # Interceptações de passes
    recoveries: int = 0  # Recuperações de bola solta
    goalkeeper_saves: int = 0  # Defesas realizadas pelo goleiro
    goals_conceded: int = 0  # Gols sofridos
    goals_prevented_xg: float = 0.0  # xG total dos chutes defendidos

    tackles_by_robot: Dict[int, int] = field(default_factory=dict)
    recoveries_by_robot: Dict[int, int] = field(default_factory=dict)
    saves_by_robot: Dict[int, int] = field(default_factory=dict)


class DefenseAnalyzer:
    """Detects steals, tackles, loose ball recoveries, and goalkeeper saves."""

    def __init__(
        self,
        field_length_meters: float = 9.0,  # Div B default
        goal_width_meters: float = 1.0,
        penalty_depth_meters: float = 1.0,
        dribbler_dist: float = 0.18,
    ):
        self.field_length = field_length_meters
        self.goal_width = goal_width_meters
        self.penalty_depth = penalty_depth_meters
        self.dribbler_dist = dribbler_dist

        self.yellow_stats = DefensiveStats()
        self.blue_stats = DefensiveStats()
        self.events: List[DefensiveEvent] = []

        self._prev_possessor: Optional[Tuple[str, int]] = None
        self._loose_duration: float = 0.0
        self._prev_time: Optional[float] = None

        # Tracking active shots for goalkeeper save detection
        # (shooter_team, xg, shot_time)
        self._active_shot: Optional[Tuple[str, float, float]] = None

    def register_incoming_shot(self, shooter_team: str, xg: float, timestamp: float):
        """Called when a shot towards goal is detected."""
        self._active_shot = (shooter_team, xg, timestamp)

    def _is_in_penalty_area(self, x: float, y: float, team: str) -> bool:
        """Checks if coordinate is inside team's defensive penalty area."""
        half_len = self.field_length / 2.0
        hw = self.goal_width / 2.0 + 0.5  # penalty area width margin
        if team == "yellow":  # yellow defends negative X
            return (-half_len <= x <= -half_len + self.penalty_depth) and (-hw <= y <= hw)
        else:  # blue defends positive X
            return (half_len - self.penalty_depth <= x <= half_len) and (-hw <= y <= hw)

    def process_snapshot(
        self,
        snapshot: MatchSnapshot,
        current_possession_team: str,
        current_possession_robot: Optional[int],
    ):
        if snapshot.ball is None:
            return

        t = snapshot.timestamp_sec
        dt = (t - self._prev_time) if self._prev_time is not None else 0.0166
        self._prev_time = t

        bx, by = snapshot.ball.x, snapshot.ball.y
        b_speed = math.hypot(snapshot.ball.vx, snapshot.ball.vy)

        # 1. Check for Goalkeeper Saves
        if self._active_shot is not None:
            shot_team, shot_xg, shot_time = self._active_shot
            defending_team = "blue" if shot_team == "yellow" else "yellow"

            # Shot expired after 1.5s
            if t - shot_time > 1.5:
                self._active_shot = None
            else:
                defending_robots = (
                    snapshot.robots_yellow if defending_team == "yellow" else snapshot.robots_blue
                )
                for r_id, r in defending_robots.items():
                    dist_to_ball = math.hypot(r.x - bx, r.y - by)
                    in_box = self._is_in_penalty_area(r.x, r.y, defending_team)

                    # Goalkeeper intervention: robot in box makes contact or stops fast ball
                    if dist_to_ball <= self.dribbler_dist and (in_box or dist_to_ball < 0.15):
                        # Save executed!
                        stats = self.yellow_stats if defending_team == "yellow" else self.blue_stats
                        stats.goalkeeper_saves += 1
                        stats.goals_prevented_xg += shot_xg
                        stats.saves_by_robot[r_id] = stats.saves_by_robot.get(r_id, 0) + 1

                        self.events.append(
                            DefensiveEvent(
                                timestamp=t,
                                team=defending_team,
                                actor_id=r_id,
                                event_type="goalkeeper_save",
                                x=r.x,
                                y=r.y,
                                shot_xg_saved=shot_xg,
                            )
                        )
                        self._active_shot = None
                        break

        # 2. Check for Tackles (Roubo de bola) and Loose Ball Recoveries
        if current_possession_team in ("yellow", "blue") and current_possession_robot is not None:
            new_team = current_possession_team
            new_bot = current_possession_robot

            if self._prev_possessor is not None:
                old_team, old_bot = self._prev_possessor

                # Possessão mudou diretamente de um time para outro!
                if old_team != new_team:
                    # Desarme direto / Roubo de bola (Tackle/Steal)
                    # Não foi chute longo (velocidade da bola média ou baixa)
                    if b_speed < 2.0 and self._loose_duration < 0.3:
                        stats = self.yellow_stats if new_team == "yellow" else self.blue_stats
                        stats.tackles_won += 1
                        stats.tackles_by_robot[new_bot] = stats.tackles_by_robot.get(new_bot, 0) + 1

                        self.events.append(
                            DefensiveEvent(
                                timestamp=t,
                                team=new_team,
                                actor_id=new_bot,
                                event_type="tackle",
                                target_opponent_id=old_bot,
                                x=bx,
                                y=by,
                            )
                        )

            # Se a bola estava solta por mais de 0.5s e um time dominou: Recuperação de bola
            elif self._loose_duration >= 0.5:
                stats = self.yellow_stats if new_team == "yellow" else self.blue_stats
                stats.recoveries += 1
                stats.recoveries_by_robot[new_bot] = stats.recoveries_by_robot.get(new_bot, 0) + 1

                self.events.append(
                    DefensiveEvent(
                        timestamp=t,
                        team=new_team,
                        actor_id=new_bot,
                        event_type="recovery",
                        x=bx,
                        y=by,
                    )
                )

            self._prev_possessor = (new_team, new_bot)
            self._loose_duration = 0.0

        elif current_possession_team == "loose":
            self._loose_duration += dt
            if self._loose_duration > 0.4:
                self._prev_possessor = None
