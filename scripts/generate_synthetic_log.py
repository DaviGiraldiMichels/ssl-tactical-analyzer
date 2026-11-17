"""
Generates a realistic synthetic SSL match log file (.log.gz).
Simulates referee commands and 10 seconds of 60 Hz vision frames:
- Yellow robot 0 conducts the ball
- Yellow robot 0 passes to Yellow robot 1
- Yellow robot 1 receives the pass and shoots on Blue's goal
"""

import math
import sys
from pathlib import Path

# Ensure src is on sys.path
root_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root_dir))
sys.path.insert(0, str(root_dir / "src"))

from src.proto import detection_pb2, referee_pb2, wrapper_pb2
from src.parser.binary_reader import (
    MESSAGE_SSL_REFBOX_2013,
    MESSAGE_SSL_VISION_2014,
    SSLLogWriter,
)


def create_referee_packet(
    timestamp_ns: int,
    yellow_score: int = 1,
    blue_score: int = 0,
) -> bytes:
    ref = referee_pb2.SSL_Referee()
    ref.packet_timestamp = timestamp_ns // 1000
    ref.stage = referee_pb2.SSL_Referee.Stage.NORMAL_FIRST_HALF
    ref.stage_time_left = 600000000
    ref.command = referee_pb2.SSL_Referee.Command.FORCE_START
    ref.command_counter = 1
    ref.command_timestamp = timestamp_ns // 1000

    ref.yellow.name = "UDESC Robotics"
    ref.yellow.score = yellow_score
    ref.yellow.red_cards = 0
    ref.yellow.yellow_cards = 0
    ref.yellow.timeouts = 4
    ref.yellow.timeout_time = 300000000
    ref.yellow.goalkeeper = 0

    ref.blue.name = "ER-Force"
    ref.blue.score = blue_score
    ref.blue.red_cards = 0
    ref.blue.yellow_cards = 0
    ref.blue.timeouts = 4
    ref.blue.timeout_time = 300000000
    ref.blue.goalkeeper = 0

    return ref.SerializeToString()


def generate_synthetic_match(output_file: str, duration_sec: float = 10.0, fps: int = 60):
    out_path = Path(output_file)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    dt = 1.0 / fps
    total_frames = int(duration_sec * fps)

    writer = SSLLogWriter(out_path, compressed=True)
    writer.open()

    start_timestamp_ns = 1_700_000_000_000_000_000

    # 1. Send initial RefBox command
    ref_bytes = create_referee_packet(start_timestamp_ns)
    writer.write_record(start_timestamp_ns, MESSAGE_SSL_REFBOX_2013, ref_bytes)

    # Initial positions (in mm, as SSL-Vision uses mm)
    # Yellow team
    y0_x, y0_y = -2000.0, 0.0
    y1_x, y1_y = 1000.0, 1000.0
    y2_x, y2_y = -3500.0, 0.0  # Goalie

    # Blue team
    b0_x, b0_y = 3500.0, 0.0   # Goalie
    b1_x, b1_y = 500.0, 0.0
    b2_x, b2_y = 1800.0, -1000.0

    # Ball
    ball_x, ball_y = -1900.0, 0.0
    ball_vx, ball_vy = 0.0, 0.0

    print(f"[*] Gerando {total_frames} frames de partida simulada SSL...")

    for i in range(total_frames):
        t_sec = i * dt
        curr_ts_ns = start_timestamp_ns + int(t_sec * 1e9)

        # Simulation Timeline:
        # 0s - 3s: Robot 0 dribbles towards (0.0, 0.0)
        if t_sec < 3.0:
            y0_x += 400.0 * dt  # 0.4 m/s
            ball_x = y0_x + 90.0
            ball_y = y0_y
            y0_orient = 0.0

        # 3s - 4.5s: Robot 0 kicks pass to Robot 1 at (1000, 1000)
        elif 3.0 <= t_sec < 4.5:
            if t_sec == 3.0:
                # Impulse towards y1
                dx = y1_x - ball_x
                dy = y1_y - ball_y
                dist = math.hypot(dx, dy)
                speed = 2200.0  # 2.2 m/s in mm/s
                ball_vx = (dx / dist) * speed
                ball_vy = (dy / dist) * speed

            ball_x += ball_vx * dt
            ball_y += ball_vy * dt
            y0_orient = math.atan2(y1_y - y0_y, y1_x - y0_x)

        # 4.5s - 7s: Robot 1 controls the ball and turns to goal
        elif 4.5 <= t_sec < 7.0:
            ball_x = y1_x + 90.0 * math.cos(0.2)
            ball_y = y1_y + 90.0 * math.sin(0.2)
            y1_x += 300.0 * dt
            y1_y -= 100.0 * dt
            y0_orient = 0.0

        # 7s - 8s: Robot 1 shoots towards opponent goal (4500, 0)
        elif 7.0 <= t_sec < 8.0:
            if t_sec == 7.0:
                dx = 4500.0 - ball_x
                dy = 0.0 - ball_y
                dist = math.hypot(dx, dy)
                speed = 4500.0  # 4.5 m/s shot
                ball_vx = (dx / dist) * speed
                ball_vy = (dy / dist) * speed

            ball_x += ball_vx * dt
            ball_y += ball_vy * dt

        # 8s - 10s: Ball is inside goal or stopped
        else:
            ball_x = 4600.0
            ball_y = 0.0

        # Create Protobuf Detection Frame
        wrapper = wrapper_pb2.SSL_WrapperPacket()
        det = wrapper.detection
        det.frame_number = i
        det.t_capture = t_sec
        det.t_sent = t_sec + 0.002
        det.camera_id = 0

        # Ball
        b_proto = det.balls.add()
        b_proto.confidence = 0.98
        b_proto.x = ball_x
        b_proto.y = ball_y
        b_proto.z = 0.0
        b_proto.pixel_x = 320.0
        b_proto.pixel_y = 240.0

        # Yellow robots
        ry0 = det.robots_yellow.add()
        ry0.robot_id = 0
        ry0.x = y0_x
        ry0.y = y0_y
        ry0.orientation = 0.0
        ry0.confidence = 0.99
        ry0.pixel_x = 100.0
        ry0.pixel_y = 100.0

        ry1 = det.robots_yellow.add()
        ry1.robot_id = 1
        ry1.x = y1_x
        ry1.y = y1_y
        ry1.orientation = 0.2
        ry1.confidence = 0.99
        ry1.pixel_x = 200.0
        ry1.pixel_y = 200.0

        ry2 = det.robots_yellow.add()
        ry2.robot_id = 2
        ry2.x = y2_x
        ry2.y = y2_y
        ry2.orientation = 0.0
        ry2.confidence = 0.99
        ry2.pixel_x = 50.0
        ry2.pixel_y = 50.0

        # Blue robots
        rb0 = det.robots_blue.add()
        rb0.robot_id = 0
        rb0.x = b0_x
        rb0.y = b0_y
        rb0.orientation = math.pi
        rb0.confidence = 0.99
        rb0.pixel_x = 500.0
        rb0.pixel_y = 500.0

        rb1 = det.robots_blue.add()
        rb1.robot_id = 1
        rb1.x = b1_x
        rb1.y = b1_y
        rb1.orientation = math.pi
        rb1.confidence = 0.99
        rb1.pixel_x = 400.0
        rb1.pixel_y = 400.0

        rb2 = det.robots_blue.add()
        rb2.robot_id = 2
        rb2.x = b2_x
        rb2.y = b2_y
        rb2.orientation = math.pi
        rb2.confidence = 0.99
        rb2.pixel_x = 450.0
        rb2.pixel_y = 450.0

        # Serialize
        payload = wrapper.SerializeToString()
        writer.write_record(curr_ts_ns, MESSAGE_SSL_VISION_2014, payload)

    writer.close()
    print(f"[+] Arquivo sintético gerado com sucesso: {out_path} ({out_path.stat().st_size} bytes)")


if __name__ == "__main__":
    target = "data/sample_matches/synthetic_match.log.gz"
    generate_synthetic_match(target, duration_sec=10.0, fps=60)
