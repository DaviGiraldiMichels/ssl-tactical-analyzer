"""
Protobuf Decoder for SSL Log records.
Converts raw serialized protobuf bytes into clean Python dataclasses.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple, Union

from src.proto import detection_pb2, geometry_pb2, referee_pb2, wrapper_pb2
from src.parser.binary_reader import (
    MESSAGE_SSL_REFBOX_2013,
    MESSAGE_SSL_VISION_2010,
    MESSAGE_SSL_VISION_2014,
    RawLogRecord,
)


@dataclass
class BallState:
    x: float  # mm or m (SSL-Vision sends in mm)
    y: float
    z: float = 0.0
    confidence: float = 1.0
    vx: float = 0.0
    vy: float = 0.0


@dataclass
class RobotState:
    robot_id: int
    team: str  # 'yellow' or 'blue'
    x: float
    y: float
    orientation: float  # radians (-pi to pi)
    confidence: float = 1.0
    vx: float = 0.0
    vy: float = 0.0
    omega: float = 0.0  # angular velocity (rad/s)


@dataclass
class VisionFrame:
    timestamp_ns: int
    t_capture: float
    camera_id: int
    frame_number: int
    balls: List[BallState] = field(default_factory=list)
    robots_yellow: Dict[int, RobotState] = field(default_factory=dict)
    robots_blue: Dict[int, RobotState] = field(default_factory=dict)

    @property
    def primary_ball(self) -> Optional[BallState]:
        if not self.balls:
            return None
        # Select ball with highest confidence
        return max(self.balls, key=lambda b: b.confidence)


@dataclass
class TeamRefereeInfo:
    name: str
    score: int
    red_cards: int
    yellow_cards: int
    timeouts: int
    timeout_time: int
    goalkeeper: int


@dataclass
class RefereeState:
    timestamp_ns: int
    packet_timestamp: int
    stage: str
    stage_id: int
    stage_time_left: int
    command: str
    command_id: int
    command_counter: int
    yellow: TeamRefereeInfo
    blue: TeamRefereeInfo
    designated_position: Optional[Tuple[float, float]] = None


@dataclass
class FieldGeometry:
    field_length: int  # mm
    field_width: int   # mm
    goal_width: int    # mm
    goal_depth: int    # mm
    boundary_width: int


class SSLProtoDecoder:
    """Decodes raw binary records into structured SSL data models."""

    def __init__(self):
        self.last_geometry: Optional[FieldGeometry] = None
        self.last_referee: Optional[RefereeState] = None

    def decode_record(
        self, record: RawLogRecord
    ) -> Optional[Union[VisionFrame, RefereeState, FieldGeometry]]:
        """Decode a single RawLogRecord based on its message_type."""
        if record.message_type in (MESSAGE_SSL_VISION_2010, MESSAGE_SSL_VISION_2014):
            return self._decode_vision(record)
        elif record.message_type == MESSAGE_SSL_REFBOX_2013:
            return self._decode_referee(record)
        return None

    def _decode_vision(
        self, record: RawLogRecord
    ) -> Optional[Union[VisionFrame, FieldGeometry]]:
        wrapper = wrapper_pb2.SSL_WrapperPacket()
        try:
            wrapper.ParseFromString(record.payload)
        except Exception:
            return None

        # Check for geometry packet
        if wrapper.HasField("geometry"):
            geom = wrapper.geometry
            field_data = geom.field
            self.last_geometry = FieldGeometry(
                field_length=field_data.field_length,
                field_width=field_data.field_width,
                goal_width=field_data.goal_width,
                goal_depth=field_data.goal_depth,
                boundary_width=field_data.boundary_width,
            )
            return self.last_geometry

        # Check for detection packet
        if wrapper.HasField("detection"):
            det = wrapper.detection
            frame = VisionFrame(
                timestamp_ns=record.timestamp_ns,
                t_capture=det.t_capture,
                camera_id=det.camera_id,
                frame_number=det.frame_number,
            )

            # Balls
            for b in det.balls:
                frame.balls.append(
                    BallState(
                        x=b.x,
                        y=b.y,
                        z=b.z if b.HasField("z") else 0.0,
                        confidence=b.confidence,
                    )
                )

            # Yellow Robots
            for ry in det.robots_yellow:
                r_id = ry.robot_id if ry.HasField("robot_id") else 0
                frame.robots_yellow[r_id] = RobotState(
                    robot_id=r_id,
                    team="yellow",
                    x=ry.x,
                    y=ry.y,
                    orientation=ry.orientation if ry.HasField("orientation") else 0.0,
                    confidence=ry.confidence,
                )

            # Blue Robots
            for rb in det.robots_blue:
                r_id = rb.robot_id if rb.HasField("robot_id") else 0
                frame.robots_blue[r_id] = RobotState(
                    robot_id=r_id,
                    team="blue",
                    x=rb.x,
                    y=rb.y,
                    orientation=rb.orientation if rb.HasField("orientation") else 0.0,
                    confidence=rb.confidence,
                )

            return frame

        return None

    def _decode_referee(self, record: RawLogRecord) -> Optional[RefereeState]:
        ref = referee_pb2.SSL_Referee()
        try:
            ref.ParseFromString(record.payload)
        except Exception:
            return None

        stage_name = referee_pb2.SSL_Referee.Stage.Name(ref.stage)
        command_name = referee_pb2.SSL_Referee.Command.Name(ref.command)

        yellow_info = TeamRefereeInfo(
            name=ref.yellow.name,
            score=ref.yellow.score,
            red_cards=ref.yellow.red_cards,
            yellow_cards=ref.yellow.yellow_cards,
            timeouts=ref.yellow.timeouts,
            timeout_time=ref.yellow.timeout_time,
            goalkeeper=ref.yellow.goalkeeper,
        )

        blue_info = TeamRefereeInfo(
            name=ref.blue.name,
            score=ref.blue.score,
            red_cards=ref.blue.red_cards,
            yellow_cards=ref.blue.yellow_cards,
            timeouts=ref.blue.timeouts,
            timeout_time=ref.blue.timeout_time,
            goalkeeper=ref.blue.goalkeeper,
        )

        desig_pos = None
        if ref.HasField("designated_position"):
            desig_pos = (ref.designated_position.x, ref.designated_position.y)

        ref_state = RefereeState(
            timestamp_ns=record.timestamp_ns,
            packet_timestamp=ref.packet_timestamp,
            stage=stage_name,
            stage_id=ref.stage,
            stage_time_left=ref.stage_time_left if ref.HasField("stage_time_left") else 0,
            command=command_name,
            command_id=ref.command,
            command_counter=ref.command_counter,
            yellow=yellow_info,
            blue=blue_info,
            designated_position=desig_pos,
        )
        self.last_referee = ref_state
        return ref_state
