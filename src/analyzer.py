"""
Main SSL Tactical Match Analyzer.
Orchestrates the entire pipeline:
Log Ingestion -> Proto Decoding -> Data Cleaning -> Tactical Metrics Engine -> Visualization & Reports.
"""

from pathlib import Path
from typing import Dict, List, Optional

from src.metrics.passing import PassAnalyzer
from src.metrics.pitch_control import PitchControlAnalyzer, SpatialSnapshotMetrics
from src.metrics.possession import PossessionAnalyzer
from src.metrics.xg import ExpectedGoalsAnalyzer
from src.parser.binary_reader import SSLLogReader
from src.parser.cleaner import MatchSnapshot, SSLDataCleaner
from src.parser.proto_decoder import FieldGeometry, RefereeState, SSLProtoDecoder, VisionFrame
from src.visualizer.pitch_2d import SSLPitchVisualizer
from src.visualizer.report import TacticalReportGenerator


class SSLMatchAnalyzer:
    """End-to-end analyzer for SSL match logs."""

    def __init__(
        self,
        division: str = "B",
        normalize_to_meters: bool = True,
        sample_pitch_control_interval: int = 30,  # compute 2D pitch control every 30 snapshots (~0.5s)
    ):
        self.division = division
        self.field_length = 12.0 if division.upper() == "A" else 9.0
        self.field_width = 9.0 if division.upper() == "A" else 6.0
        self.goal_width = 1.8 if division.upper() == "A" else 1.0

        self.cleaner = SSLDataCleaner(normalize_to_meters=normalize_to_meters)
        self.decoder = SSLProtoDecoder()

        self.possession_analyzer = PossessionAnalyzer(field_length_meters=self.field_length)
        self.pass_analyzer = PassAnalyzer()
        self.pitch_control_analyzer = PitchControlAnalyzer(
            field_length_meters=self.field_length,
            field_width_meters=self.field_width,
        )
        self.xg_analyzer = ExpectedGoalsAnalyzer(
            field_length_meters=self.field_length,
            goal_width_meters=self.goal_width,
        )

        self.pitch_viz = SSLPitchVisualizer(division=division)

        self.spatial_history: List[SpatialSnapshotMetrics] = []
        self.snapshots: List[MatchSnapshot] = []
        self.sample_pitch_control_interval = sample_pitch_control_interval

        self.yellow_team_name = "Yellow Team"
        self.blue_team_name = "Blue Team"

    def analyze_log_file(self, log_path: str):
        """Processes an SSL binary log file (.log or .log.gz)."""
        reader = SSLLogReader(log_path)
        frame_idx = 0

        for raw_record in reader.read_records():
            decoded = self.decoder.decode_record(raw_record)
            if decoded is None:
                continue

            if isinstance(decoded, RefereeState):
                self.cleaner.update_referee(decoded)
                if decoded.yellow.name:
                    self.yellow_team_name = decoded.yellow.name
                if decoded.blue.name:
                    self.blue_team_name = decoded.blue.name

            elif isinstance(decoded, VisionFrame):
                snapshot = self.cleaner.process_frame(decoded)
                if snapshot is not None:
                    self._process_snapshot(snapshot, frame_idx)
                    frame_idx += 1

        final_snapshot = self.cleaner.flush()
        if final_snapshot is not None:
            self._process_snapshot(final_snapshot, frame_idx)

    def _process_snapshot(self, snapshot: MatchSnapshot, idx: int):
        self.snapshots.append(snapshot)
        self.possession_analyzer.process_snapshot(snapshot)
        self.pass_analyzer.process_snapshot(snapshot)
        self.xg_analyzer.process_snapshot(snapshot)

        if idx % self.sample_pitch_control_interval == 0:
            spatial_metric = self.pitch_control_analyzer.process_snapshot(snapshot)
            self.spatial_history.append(spatial_metric)

    def generate_report(self, output_html_path: Optional[str] = None) -> str:
        """Returns terminal report text and optionally generates an HTML report."""
        report_gen = TacticalReportGenerator(
            possession=self.possession_analyzer.stats,
            yellow_passing=self.pass_analyzer.yellow_stats,
            blue_passing=self.pass_analyzer.blue_stats,
            yellow_shots=self.xg_analyzer.yellow_stats,
            blue_shots=self.xg_analyzer.blue_stats,
            spatial_history=self.spatial_history,
            yellow_team_name=self.yellow_team_name,
            blue_team_name=self.blue_team_name,
        )

        if output_html_path:
            report_gen.generate_html_report(output_html_path)

        return report_gen.generate_terminal_summary()

    def export_keyframe_pitch(self, frame_index: int, output_png_path: str):
        """Renders and saves a specific snapshot frame onto the 2D pitch."""
        if 0 <= frame_index < len(self.snapshots):
            snap = self.snapshots[frame_index]
            surface, _, _ = self.pitch_control_analyzer.calculate_control_surface(snap)
            self.pitch_viz.render_snapshot(
                snap,
                output_path=output_png_path,
                pitch_control_surface=surface,
            )
