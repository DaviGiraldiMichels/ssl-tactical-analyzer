"""
Tactical Metric: Pitch Control & Spatial Dominance in SSL.
Calculates space control probability surfaces (Spearman / Fernandez-Bornn model),
team centroids, and compactness metrics using NumPy vectorization.
"""

import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np

from src.parser.cleaner import MatchSnapshot


@dataclass
class SpatialSnapshotMetrics:
    timestamp_sec: float
    yellow_control_pct: float
    blue_control_pct: float
    yellow_centroid: Tuple[float, float]
    blue_centroid: Tuple[float, float]
    yellow_compactness_radius: float  # std dev distance from centroid
    blue_compactness_radius: float


class PitchControlAnalyzer:
    """Evaluates spatial dominance and pitch control across the field."""

    def __init__(
        self,
        field_length_meters: float = 9.0,   # Div B default
        field_width_meters: float = 6.0,
        grid_resolution_x: int = 45,        # 45 x 30 grid (~0.2m resolution)
        grid_resolution_y: int = 30,
        v_max: float = 2.5,                 # m/s omnidirectional speed
        sigmoid_lambda: float = 4.0,        # sharpness of transition
    ):
        self.length = field_length_meters
        self.width = field_width_meters
        self.v_max = v_max
        self.sigmoid_lambda = sigmoid_lambda

        # Precompute coordinate grid
        xs = np.linspace(-self.length / 2.0, self.length / 2.0, grid_resolution_x)
        ys = np.linspace(-self.width / 2.0, self.width / 2.0, grid_resolution_y)
        self.grid_x, self.grid_y = np.meshgrid(xs, ys)  # shape (Ny, Nx)
        self.total_cells = grid_resolution_x * grid_resolution_y

    def calculate_control_surface(
        self, snapshot: MatchSnapshot
    ) -> Tuple[np.ndarray, float, float]:
        """
        Returns (surface, yellow_pct, blue_pct).
        surface is an array of shape (Ny, Nx) with values in [0, 1] (1 = Yellow control, 0 = Blue control).
        """
        yellow_bots = list(snapshot.robots_yellow.values())
        blue_bots = list(snapshot.robots_blue.values())

        if not yellow_bots and not blue_bots:
            surface = np.full_like(self.grid_x, 0.5)
            return surface, 50.0, 50.0
        elif not yellow_bots:
            surface = np.zeros_like(self.grid_x)
            return surface, 0.0, 100.0
        elif not blue_bots:
            surface = np.ones_like(self.grid_x)
            return surface, 100.0, 0.0

        # Vectorized time to target for Yellow
        t_yellow = np.full_like(self.grid_x, 1e9)
        for bot in yellow_bots:
            dist = np.hypot(self.grid_x - bot.x, self.grid_y - bot.y)
            t_bot = dist / self.v_max
            t_yellow = np.minimum(t_yellow, t_bot)

        # Vectorized time to target for Blue
        t_blue = np.full_like(self.grid_x, 1e9)
        for bot in blue_bots:
            dist = np.hypot(self.grid_x - bot.x, self.grid_y - bot.y)
            t_bot = dist / self.v_max
            t_blue = np.minimum(t_blue, t_bot)

        # Sigmoid: P(Yellow) = 1 / (1 + exp(-lambda * (t_blue - t_yellow)))
        dt = t_blue - t_yellow
        surface = 1.0 / (1.0 + np.exp(-np.clip(self.sigmoid_lambda * dt, -20, 20)))

        yellow_pct = float(np.mean(surface) * 100.0)
        blue_pct = 100.0 - yellow_pct

        return surface, yellow_pct, blue_pct

    def calculate_team_spatial_stats(
        self, robots: Dict[int, any]
    ) -> Tuple[Tuple[float, float], float]:
        """Returns ((mean_x, mean_y), spread_radius)."""
        if not robots:
            return (0.0, 0.0), 0.0

        xs = [r.x for r in robots.values()]
        ys = [r.y for r in robots.values()]

        cx, cy = float(np.mean(xs)), float(np.mean(ys))
        dists = [math.hypot(x - cx, y - cy) for x, y in zip(xs, ys)]
        spread = float(np.std(dists)) if len(dists) > 1 else 0.0

        return (cx, cy), spread

    def process_snapshot(self, snapshot: MatchSnapshot) -> SpatialSnapshotMetrics:
        _, y_pct, b_pct = self.calculate_control_surface(snapshot)
        y_cent, y_spr = self.calculate_team_spatial_stats(snapshot.robots_yellow)
        b_cent, b_spr = self.calculate_team_spatial_stats(snapshot.robots_blue)

        return SpatialSnapshotMetrics(
            timestamp_sec=snapshot.timestamp_sec,
            yellow_control_pct=y_pct,
            blue_control_pct=b_pct,
            yellow_centroid=y_cent,
            blue_centroid=b_cent,
            yellow_compactness_radius=y_spr,
            blue_compactness_radius=b_spr,
        )
