"""
Tactical Formations and Team Geometry Engine for RoboCup SSL.
Calculates team centroids, convex hulls, stretch index, width, length,
and support passing triangles for collective spatial evaluation.
"""

import itertools
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from src.parser.cleaner import MatchSnapshot
from src.parser.proto_decoder import RobotState


def convex_hull_2d(points: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """Computes the 2D convex hull of a list of (x, y) coordinates
    using Andrew's monotone chain algorithm (O(N log N)).
    Returns vertices ordered counter-clockwise.
    """
    unique_pts = sorted(set(points))
    if len(unique_pts) <= 1:
        return unique_pts

    def cross(o: Tuple[float, float], a: Tuple[float, float], b: Tuple[float, float]) -> float:
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])

    # Build lower hull
    lower = []
    for p in unique_pts:
        while len(lower) >= 2 and cross(lower[-2], lower[-1], p) <= 0.0:
            lower.pop()
        lower.append(p)

    # Build upper hull
    upper = []
    for p in reversed(unique_pts):
        while len(upper) >= 2 and cross(upper[-2], upper[-1], p) <= 0.0:
            upper.pop()
        upper.append(p)

    return lower[:-1] + upper[:-1]


def polygon_area(hull: List[Tuple[float, float]]) -> float:
    """Calculates the area of a polygon using the Shoelace formula (Gauss's area formula)."""
    n = len(hull)
    if n < 3:
        return 0.0

    area = 0.0
    for i in range(n):
        j = (i + 1) % n
        area += hull[i][0] * hull[j][1]
        area -= hull[j][0] * hull[i][1]

    return abs(area) / 2.0


@dataclass
class TeamShapeSnapshot:
    """Spatial and geometric configuration of a team at a single timestamp."""

    timestamp: float
    team: str
    centroid_x: float
    centroid_y: float
    width_m: float  # lateral spread: max(y) - min(y)
    length_m: float  # longitudinal depth: max(x) - min(x)
    area_m2: float  # convex hull area
    stretch_index_m: float  # mean radial distance from centroid
    hull_points: List[Tuple[float, float]]
    robot_count: int


@dataclass
class SupportTriangle:
    """Passing / support triangle formed by 3 cooperative teammates."""

    robot_ids: Tuple[int, int, int]
    area_m2: float
    perimeter_m: float
    centroid: Tuple[float, float]


@dataclass
class TeamFormationStats:
    """Aggregated match statistics for team formation and geometric structure."""

    team: str
    total_samples: int = 0
    sum_centroid_x: float = 0.0
    sum_centroid_y: float = 0.0
    sum_width_m: float = 0.0
    sum_length_m: float = 0.0
    sum_area_m2: float = 0.0
    sum_stretch_index_m: float = 0.0
    max_area_m2: float = 0.0
    min_area_m2: float = float("inf")

    @property
    def avg_centroid_x(self) -> float:
        return self.sum_centroid_x / max(1, self.total_samples)

    @property
    def avg_centroid_y(self) -> float:
        return self.sum_centroid_y / max(1, self.total_samples)

    @property
    def avg_width_m(self) -> float:
        return self.sum_width_m / max(1, self.total_samples)

    @property
    def avg_length_m(self) -> float:
        return self.sum_length_m / max(1, self.total_samples)

    @property
    def avg_area_m2(self) -> float:
        return self.sum_area_m2 / max(1, self.total_samples)

    @property
    def avg_stretch_index_m(self) -> float:
        return self.sum_stretch_index_m / max(1, self.total_samples)


class TacticalFormationsAnalyzer:
    """Analyzes collective team shapes, compactness (Convex Hull), centroids, and support triangles."""

    IN_PLAY_COMMANDS = {
        "NORMAL",
        "NORMAL_START",
        "FORCE_START",
        "DIRECT_FREE_YELLOW",
        "DIRECT_FREE_BLUE",
        "INDIRECT_FREE_YELLOW",
        "INDIRECT_FREE_BLUE",
    }

    def __init__(self, field_length: float = 12.0, field_width: float = 9.0):
        self.field_length = field_length
        self.field_width = field_width

        self.yellow_stats = TeamFormationStats(team="yellow")
        self.blue_stats = TeamFormationStats(team="blue")

        self.history_yellow: List[TeamShapeSnapshot] = []
        self.history_blue: List[TeamShapeSnapshot] = []

    def is_in_play(self, cmd: Optional[str]) -> bool:
        if not cmd or cmd in ("UNKNOWN", ""):
            return True
        return cmd in self.IN_PLAY_COMMANDS

    def calculate_shape(
        self,
        robots: Dict[int, RobotState],
        timestamp: float,
        team: str,
        exclude_goalkeeper: bool = False,
    ) -> Optional[TeamShapeSnapshot]:
        """Calculates centroid, width, length, convex hull, and stretch index for a set of robots."""
        if not robots:
            return None

        # Optionally filter out goalkeeper (ID 0 or robot closest to own goal line)
        pts_list: List[Tuple[float, float]] = []
        for r_id, bot in robots.items():
            if exclude_goalkeeper and r_id == 0:
                continue
            pts_list.append((round(bot.x, 3), round(bot.y, 3)))

        if not pts_list:
            return None

        n = len(pts_list)
        xs = [p[0] for p in pts_list]
        ys = [p[1] for p in pts_list]

        centroid_x = sum(xs) / n
        centroid_y = sum(ys) / n

        width = max(ys) - min(ys)
        length = max(xs) - min(xs)

        stretch_index = sum(math.hypot(x - centroid_x, y - centroid_y) for x, y in pts_list) / n

        hull = convex_hull_2d(pts_list)
        area = polygon_area(hull)

        return TeamShapeSnapshot(
            timestamp=timestamp,
            team=team,
            centroid_x=round(centroid_x, 3),
            centroid_y=round(centroid_y, 3),
            width_m=round(width, 2),
            length_m=round(length, 2),
            area_m2=round(area, 2),
            stretch_index_m=round(stretch_index, 2),
            hull_points=hull,
            robot_count=n,
        )

    def detect_support_triangles(
        self,
        robots: Dict[int, RobotState],
        min_area: float = 0.4,
        max_dist: float = 4.5,
    ) -> List[SupportTriangle]:
        """Detects passing / support triangles formed by 3 cooperative teammates within reachable distance."""
        if len(robots) < 3:
            return []

        triangles: List[SupportTriangle] = []
        bot_ids = list(robots.keys())

        for id1, id2, id3 in itertools.combinations(bot_ids, 3):
            r1, r2, r3 = robots[id1], robots[id2], robots[id3]
            p1 = (r1.x, r1.y)
            p2 = (r2.x, r2.y)
            p3 = (r3.x, r3.y)

            d12 = math.hypot(p1[0] - p2[0], p1[1] - p2[1])
            d23 = math.hypot(p2[0] - p3[0], p2[1] - p3[1])
            d31 = math.hypot(p3[0] - p1[0], p3[1] - p1[1])

            # Ensure all sides are within mutual pass range
            if max(d12, d23, d31) <= max_dist:
                hull = [p1, p2, p3]
                area = polygon_area(hull)
                if area >= min_area:
                    triangles.append(
                        SupportTriangle(
                            robot_ids=(id1, id2, id3),
                            area_m2=round(area, 2),
                            perimeter_m=round(d12 + d23 + d31, 2),
                            centroid=(
                                round((p1[0] + p2[0] + p3[0]) / 3.0, 2),
                                round((p1[1] + p2[1] + p3[1]) / 3.0, 2),
                            ),
                        )
                    )

        # Sort by compactness/area
        triangles.sort(key=lambda t: t.area_m2, reverse=True)
        return triangles[:5]

    def process_snapshot(self, snapshot: MatchSnapshot):
        """Processes a match snapshot and updates formation metrics if in play."""
        if not self.is_in_play(snapshot.referee_command):
            return

        t = snapshot.timestamp_sec

        # 1. Yellow Team
        y_shape = self.calculate_shape(snapshot.robots_yellow, t, "yellow")
        if y_shape is not None:
            self._update_stats(self.yellow_stats, y_shape)
            self.history_yellow.append(y_shape)

        # 2. Blue Team
        b_shape = self.calculate_shape(snapshot.robots_blue, t, "blue")
        if b_shape is not None:
            self._update_stats(self.blue_stats, b_shape)
            self.history_blue.append(b_shape)

    def _update_stats(self, stats: TeamFormationStats, shape: TeamShapeSnapshot):
        stats.total_samples += 1
        stats.sum_centroid_x += shape.centroid_x
        stats.sum_centroid_y += shape.centroid_y
        stats.sum_width_m += shape.width_m
        stats.sum_length_m += shape.length_m
        stats.sum_area_m2 += shape.area_m2
        stats.sum_stretch_index_m += shape.stretch_index_m

        if shape.area_m2 > stats.max_area_m2:
            stats.max_area_m2 = shape.area_m2
        if shape.area_m2 < stats.min_area_m2:
            stats.min_area_m2 = shape.area_m2

    def export_summary(self) -> dict:
        """Exports aggregated formation KPIs for both teams."""
        y_min = self.yellow_stats.min_area_m2 if self.yellow_stats.min_area_m2 != float("inf") else 0.0
        b_min = self.blue_stats.min_area_m2 if self.blue_stats.min_area_m2 != float("inf") else 0.0

        return {
            "yellow": {
                "avg_centroid": [round(self.yellow_stats.avg_centroid_x, 2), round(self.yellow_stats.avg_centroid_y, 2)],
                "avg_width_m": round(self.yellow_stats.avg_width_m, 2),
                "avg_length_m": round(self.yellow_stats.avg_length_m, 2),
                "avg_area_m2": round(self.yellow_stats.avg_area_m2, 2),
                "max_area_m2": round(self.yellow_stats.max_area_m2, 2),
                "min_area_m2": round(y_min, 2),
                "avg_stretch_index_m": round(self.yellow_stats.avg_stretch_index_m, 2),
            },
            "blue": {
                "avg_centroid": [round(self.blue_stats.avg_centroid_x, 2), round(self.blue_stats.avg_centroid_y, 2)],
                "avg_width_m": round(self.blue_stats.avg_width_m, 2),
                "avg_length_m": round(self.blue_stats.avg_length_m, 2),
                "avg_area_m2": round(self.blue_stats.avg_area_m2, 2),
                "max_area_m2": round(self.blue_stats.max_area_m2, 2),
                "min_area_m2": round(b_min, 2),
                "avg_stretch_index_m": round(self.blue_stats.avg_stretch_index_m, 2),
            },
        }
