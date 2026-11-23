"""
Spatial Heatmap and Kernel Density Estimation (KDE) Engine for RoboCup SSL.
Computes 2D spatial occupation grids for the ball, teams, and individual robots.
"""

from typing import Dict, List, Optional, Tuple
import numpy as np

from src.parser.cleaner import MatchSnapshot


IN_PLAY_COMMANDS = {
    "NORMAL",
    "NORMAL_START",
    "FORCE_START",
    "DIRECT_FREE_YELLOW",
    "DIRECT_FREE_BLUE",
    "INDIRECT_FREE_YELLOW",
    "INDIRECT_FREE_BLUE",
}


def is_match_in_play(referee_command: Optional[str]) -> bool:
    """Verifies whether the match is running and in active play (not stopped, halt, kickoff prep, or timeout)."""
    if not referee_command or referee_command in ("UNKNOWN", ""):
        return True  # Fallback if referee messages are missing in log
    return referee_command in IN_PLAY_COMMANDS


def gaussian_filter_2d(grid: np.ndarray, sigma: float = 1.3) -> np.ndarray:
    """Applies a fast, separable 2D Gaussian filter to a numpy grid using reflection padding."""
    if sigma <= 0.0 or grid.max() <= 0:
        return grid.copy()

    radius = int(np.ceil(3 * sigma))
    x = np.arange(-radius, radius + 1)
    kernel_1d = np.exp(-0.5 * (x / sigma) ** 2)
    kernel_sum = kernel_1d.sum()
    if kernel_sum > 0:
        kernel_1d /= kernel_sum

    # Convolve axis 0 (rows)
    pad_h = np.pad(grid, ((radius, radius), (0, 0)), mode="edge")
    temp = np.zeros_like(grid, dtype=np.float32)
    for i, w in enumerate(kernel_1d):
        temp += w * pad_h[i : i + grid.shape[0], :]

    # Convolve axis 1 (columns)
    pad_w = np.pad(temp, ((0, 0), (radius, radius)), mode="edge")
    out = np.zeros_like(grid, dtype=np.float32)
    for j, w in enumerate(kernel_1d):
        out += w * pad_w[:, j : j + grid.shape[1]]

    return out


class SpatialHeatmapAnalyzer:
    """Calculates spatial density and heatmaps for SSL matches."""

    def __init__(
        self,
        field_length: float = 12.0,
        field_width: float = 9.0,
        grid_nx: int = 48,
        grid_ny: int = 36,
        sigma: float = 1.4,
    ):
        self.field_length = field_length
        self.field_width = field_width
        self.grid_nx = grid_nx
        self.grid_ny = grid_ny
        self.sigma = sigma

        self._reset_grids()

    def update_dimensions(self, field_length: float, field_width: float):
        """Updates field geometry and resets the grid if dimensions changed."""
        if abs(self.field_length - field_length) > 0.1 or abs(self.field_width - field_width) > 0.1:
            self.field_length = field_length
            self.field_width = field_width
            # Maintain roughly square grid cells
            self.grid_ny = max(20, int(round(self.grid_nx * (field_width / field_length))))
            self._reset_grids()

    def _reset_grids(self):
        self.ball_grid = np.zeros((self.grid_ny, self.grid_nx), dtype=np.float32)
        self.yellow_grid = np.zeros((self.grid_ny, self.grid_nx), dtype=np.float32)
        self.blue_grid = np.zeros((self.grid_ny, self.grid_nx), dtype=np.float32)
        self.yellow_robots: Dict[int, np.ndarray] = {}
        self.blue_robots: Dict[int, np.ndarray] = {}
        self.total_frames = 0

    def _pos_to_grid(self, x: float, y: float) -> Tuple[int, int]:
        """Converts pitch coordinates (m) to grid cell (row, col).
        Row 0 is top (y = +width/2), Col 0 is left (x = -length/2).
        """
        # Column (x-axis: -L/2 to +L/2)
        norm_x = (x + self.field_length / 2.0) / max(0.1, self.field_length)
        col = int(norm_x * self.grid_nx)
        col = max(0, min(self.grid_nx - 1, col))

        # Row (y-axis: +W/2 at top to -W/2 at bottom)
        norm_y = (self.field_width / 2.0 - y) / max(0.1, self.field_width)
        row = int(norm_y * self.grid_ny)
        row = max(0, min(self.grid_ny - 1, row))

        return row, col

    def process_snapshot(self, snapshot: MatchSnapshot):
        """Accumulates position counts only when the match is actively in play according to the referee."""
        # If match is stopped by referee (HALT, STOP, TIMEOUT, PREPARE_KICKOFF, BALL_PLACEMENT, etc.), skip frame completely
        if not is_match_in_play(snapshot.referee_command):
            return

        self.total_frames += 1

        # 1. Ball
        if snapshot.ball is not None:
            r, c = self._pos_to_grid(snapshot.ball.x, snapshot.ball.y)
            self.ball_grid[r, c] += 1.0

        # 2. Yellow Robots
        for r_id, bot in snapshot.robots_yellow.items():
            r, c = self._pos_to_grid(bot.x, bot.y)
            self.yellow_grid[r, c] += 1.0
            if r_id not in self.yellow_robots:
                self.yellow_robots[r_id] = np.zeros((self.grid_ny, self.grid_nx), dtype=np.float32)
            self.yellow_robots[r_id][r, c] += 1.0

        # 3. Blue Robots
        for r_id, bot in snapshot.robots_blue.items():
            r, c = self._pos_to_grid(bot.x, bot.y)
            self.blue_grid[r, c] += 1.0
            if r_id not in self.blue_robots:
                self.blue_robots[r_id] = np.zeros((self.grid_ny, self.grid_nx), dtype=np.float32)
            self.blue_robots[r_id][r, c] += 1.0

    def get_normalized_grid(
        self,
        raw_grid: np.ndarray,
        sigma: Optional[float] = None,
        gamma: float = 0.5,
    ) -> List[List[float]]:
        """Applies Gaussian smoothing, normalizes to [0.0, 1.0], applies power-law dynamic range compression,
        and returns a nested list."""
        s = self.sigma if sigma is None else sigma
        smoothed = gaussian_filter_2d(raw_grid, sigma=s)
        max_val = float(np.max(smoothed))

        if max_val > 0.0:
            # Use 99th percentile cutoff to avoid solitary stationary points compressing the entire dynamic range
            non_zero = smoothed[smoothed > 0.0]
            cutoff = float(np.percentile(non_zero, 99.0)) if len(non_zero) > 10 else max_val
            cutoff = max(cutoff, max_val * 0.5)
            linear = np.clip(smoothed / cutoff, 0.0, 1.0)
            if gamma != 1.0:
                compressed = np.power(linear, gamma)
            else:
                compressed = linear
        else:
            compressed = np.zeros_like(smoothed)

        return np.round(compressed, 3).tolist()

    def export_all_heatmaps(self) -> dict:
        """Exports all heatmaps formatted for JSON transmission."""
        y_bot_maps = {}
        for r_id, grid in sorted(self.yellow_robots.items()):
            y_bot_maps[str(r_id)] = self.get_normalized_grid(grid, gamma=0.5)

        b_bot_maps = {}
        for r_id, grid in sorted(self.blue_robots.items()):
            b_bot_maps[str(r_id)] = self.get_normalized_grid(grid, gamma=0.5)

        return {
            "nx": self.grid_nx,
            "ny": self.grid_ny,
            "field_length": round(self.field_length, 2),
            "field_width": round(self.field_width, 2),
            "ball": self.get_normalized_grid(self.ball_grid, sigma=self.sigma * 0.9, gamma=0.5),
            "yellow": self.get_normalized_grid(self.yellow_grid, gamma=0.5),
            "blue": self.get_normalized_grid(self.blue_grid, gamma=0.5),
            "yellow_robots": y_bot_maps,
            "blue_robots": b_bot_maps,
        }
