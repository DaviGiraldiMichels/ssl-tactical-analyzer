"""
2D Pitch Visualizer for RoboCup Small Size League (SSL).
Draws official field geometries (Division A or Division B), robot positions,
orientations, velocities, ball trajectories, and pitch control overlays.
"""

import math
from typing import Dict, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.patches as patches
import matplotlib.pyplot as plt
import numpy as np

from src.parser.cleaner import MatchSnapshot


class SSLPitchVisualizer:
    """Renders 2D representations of an SSL soccer pitch and match snapshots."""

    def __init__(
        self,
        division: str = "B",  # 'A' or 'B'
        field_length_m: Optional[float] = None,
        field_width_m: Optional[float] = None,
    ):
        if division.upper() == "A":
            self.length = field_length_m or 12.0
            self.width = field_width_m or 9.0
            self.goal_width = 1.8
            self.goal_depth = 0.3
            self.penalty_depth = 1.8
            self.penalty_width = 3.6
            self.center_radius = 1.0
        else:  # Division B
            self.length = field_length_m or 9.0
            self.width = field_width_m or 6.0
            self.goal_width = 1.0
            self.goal_depth = 0.2
            self.penalty_depth = 1.0
            self.penalty_width = 2.0
            self.center_radius = 0.5

        self.robot_radius = 0.09  # 9 cm (18 cm diameter)
        self.ball_radius = 0.0215  # standard golf ball

    def create_pitch_figure(self, figsize=(10, 7)) -> Tuple[plt.Figure, plt.Axes]:
        """Creates figure and draws field lines."""
        fig, ax = plt.subplots(figsize=figsize, facecolor="#1e293b")
        ax.set_facecolor("#15803d")  # Soccer green

        hl = self.length / 2.0
        hw = self.width / 2.0

        # Boundary / Field outer rectangle
        ax.plot([-hl, hl, hl, -hl, -hl], [-hw, -hw, hw, hw, -hw], color="white", lw=2)

        # Halfway line
        ax.plot([0, 0], [-hw, hw], color="white", lw=2)

        # Center circle
        center_circle = patches.Circle((0, 0), self.center_radius, fill=False, color="white", lw=2)
        ax.add_patch(center_circle)
        ax.plot(0, 0, marker="o", color="white", markersize=4)

        # Goals and Penalty areas
        # Left (Negative X)
        ax.plot(
            [-hl, -hl - self.goal_depth, -hl - self.goal_depth, -hl],
            [-self.goal_width / 2, -self.goal_width / 2, self.goal_width / 2, self.goal_width / 2],
            color="yellow", lw=2.5,
        )
        ax.plot(
            [-hl, -hl + self.penalty_depth, -hl + self.penalty_depth, -hl],
            [-self.penalty_width / 2, -self.penalty_width / 2, self.penalty_width / 2, self.penalty_width / 2],
            color="white", lw=1.5, ls="--",
        )

        # Right (Positive X)
        ax.plot(
            [hl, hl + self.goal_depth, hl + self.goal_depth, hl],
            [-self.goal_width / 2, -self.goal_width / 2, self.goal_width / 2, self.goal_width / 2],
            color="cyan", lw=2.5,
        )
        ax.plot(
            [hl, hl - self.penalty_depth, hl - self.penalty_depth, hl],
            [-self.penalty_width / 2, -self.penalty_width / 2, self.penalty_width / 2, self.penalty_width / 2],
            color="white", lw=1.5, ls="--",
        )

        margin_x = self.length * 0.1
        margin_y = self.width * 0.1
        ax.set_xlim(-hl - margin_x, hl + margin_x)
        ax.set_ylim(-hw - margin_y, hw + margin_y)
        ax.set_aspect("equal")
        ax.axis("off")

        return fig, ax

    def render_snapshot(
        self,
        snapshot: MatchSnapshot,
        output_path: Optional[str] = None,
        title: Optional[str] = None,
        pitch_control_surface: Optional[np.ndarray] = None,
    ) -> plt.Figure:
        """Renders complete match snapshot onto the field."""
        fig, ax = self.create_pitch_figure()

        hl = self.length / 2.0
        hw = self.width / 2.0

        # Optional Pitch Control surface heatmap
        if pitch_control_surface is not None:
            ax.imshow(
                pitch_control_surface,
                extent=[-hl, hl, -hw, hw],
                origin="lower",
                cmap="RdYlBu_r",
                alpha=0.35,
                interpolation="bilinear",
            )

        # Draw Yellow Robots
        for r_id, r in snapshot.robots_yellow.items():
            circle = patches.Circle((r.x, r.y), self.robot_radius, facecolor="#eab308", edgecolor="#713f12", lw=2)
            ax.add_patch(circle)
            # Heading vector
            dx = 0.15 * math.cos(r.orientation)
            dy = 0.15 * math.sin(r.orientation)
            ax.arrow(r.x, r.y, dx, dy, color="#713f12", head_width=0.04, head_length=0.03, lw=1.5)
            # Label
            ax.text(r.x, r.y, str(r_id), color="black", fontsize=9, fontweight="bold", ha="center", va="center")

        # Draw Blue Robots
        for r_id, r in snapshot.robots_blue.items():
            circle = patches.Circle((r.x, r.y), self.robot_radius, facecolor="#3b82f6", edgecolor="#1e3a8a", lw=2)
            ax.add_patch(circle)
            dx = 0.15 * math.cos(r.orientation)
            dy = 0.15 * math.sin(r.orientation)
            ax.arrow(r.x, r.y, dx, dy, color="#1e3a8a", head_width=0.04, head_length=0.03, lw=1.5)
            ax.text(r.x, r.y, str(r_id), color="white", fontsize=9, fontweight="bold", ha="center", va="center")

        # Draw Ball
        if snapshot.ball is not None:
            ball_circle = patches.Circle(
                (snapshot.ball.x, snapshot.ball.y),
                self.ball_radius * 1.5,
                facecolor="#f97316",
                edgecolor="#7c2d12",
                lw=1.5,
                zorder=10,
            )
            ax.add_patch(ball_circle)
            # Velocity arrow
            b_spd = math.hypot(snapshot.ball.vx, snapshot.ball.vy)
            if b_spd > 0.3:
                scale = min(0.6, b_spd * 0.15)
                ax.arrow(
                    snapshot.ball.x,
                    snapshot.ball.y,
                    snapshot.ball.vx * scale / b_spd,
                    snapshot.ball.vy * scale / b_spd,
                    color="#ea580c",
                    head_width=0.05,
                    head_length=0.05,
                    lw=2,
                    zorder=11,
                )

        header = title or f"Tempo: {snapshot.timestamp_sec:.2f}s | Placar: Y {snapshot.score_yellow} x {snapshot.score_blue} B | Ref: {snapshot.referee_command}"
        ax.set_title(header, color="white", fontsize=12, pad=10)

        if output_path:
            fig.savefig(output_path, dpi=120, bbox_inches="tight")
            plt.close(fig)

        return fig
