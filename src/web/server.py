"""
HTTP Server and API Backend for the SSL Tactical Dashboard and 2D Pitch Player.
Provides match list, parses matches into structured event feeds and 25-30 FPS animation frames.
"""

import gzip
import json
import mimetypes
import os
import traceback
import urllib.parse
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Dict, List, Optional

from src.analyzer import SSLMatchAnalyzer


def is_ssl_binary_log(p: Path) -> bool:
    """Verifies whether a file is a valid SSL binary log (plain or gzipped)."""
    try:
        if not p.is_file() or p.stat().st_size < 16:
            return False

        with open(p, "rb") as f:
            header = f.read(16)

        if header[:2] == b"\x1f\x8b":
            with gzip.open(p, "rb") as gf:
                header = gf.read(16)

        return header[:12] == b"SSL_LOG_FILE"
    except Exception:
        return False


class MatchCache:
    """In-memory cache for parsed match data to make web interactions instant."""

    def __init__(self):
        self._cache: Dict[str, dict] = {}

    def get_or_parse(self, log_path_str: str, max_fps: int = 25) -> dict:
        log_path = Path(log_path_str)
        if not log_path.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: {log_path_str}")

        mtime = log_path.stat().st_mtime
        cache_key = f"{log_path_str}_{mtime}_{max_fps}"

        if cache_key in self._cache:
            return self._cache[cache_key]

        print(f"[*] Processando e gerando dados para o Player Web: {log_path.name}...")
        analyzer = SSLMatchAnalyzer(division="B")
        analyzer.analyze_log_file(str(log_path))

        # Downsample snapshots for web animation (target ~25 FPS)
        total_snaps = len(analyzer.snapshots)
        duration = analyzer.possession_analyzer.stats.total_time_sec
        step = 1
        if duration > 0 and total_snaps > 0:
            actual_fps = total_snaps / duration
            if actual_fps > max_fps:
                step = max(1, int(round(actual_fps / max_fps)))

        web_frames = []
        for i in range(0, total_snaps, step):
            s = analyzer.snapshots[i]
            b_data = None
            if s.ball:
                b_data = [
                    round(s.ball.x, 3),
                    round(s.ball.y, 3),
                    round(s.ball.vx, 2),
                    round(s.ball.vy, 2),
                ]

            y_bots = [
                [r_id, round(r.x, 3), round(r.y, 3), round(r.orientation, 3)]
                for r_id, r in s.robots_yellow.items()
            ]
            b_bots = [
                [r_id, round(r.x, 3), round(r.y, 3), round(r.orientation, 3)]
                for r_id, r in s.robots_blue.items()
            ]

            web_frames.append(
                {
                    "t": round(s.timestamp_sec, 2),
                    "cmd": s.referee_command,
                    "ball": b_data,
                    "y": y_bots,
                    "b": b_bots,
                }
            )

        # Assemble Events feed for quick jumping
        events_feed = []

        # 1. Passes
        for p in analyzer.pass_analyzer.detected_passes:
            events_feed.append(
                {
                    "type": "pass",
                    "t": round(p.timestamp_start, 2),
                    "team": p.team,
                    "desc": f"Passe #{p.passer_id} -> #{p.receiver_id} ({p.outcome.capitalize()}, {p.distance:.1f}m)",
                    "outcome": p.outcome,
                }
            )

        # 2. Shots
        for s in analyzer.xg_analyzer.yellow_stats.shots:
            events_feed.append(
                {
                    "type": "shot",
                    "t": round(s.timestamp, 2),
                    "team": "yellow",
                    "desc": f"Finalização Amarela #{s.shooter_id} (xG: {s.xg:.2f}, {s.distance_to_goal:.1f}m)",
                    "xg": round(s.xg, 2),
                }
            )
        for s in analyzer.xg_analyzer.blue_stats.shots:
            events_feed.append(
                {
                    "type": "shot",
                    "t": round(s.timestamp, 2),
                    "team": "blue",
                    "desc": f"Finalização Azul #{s.shooter_id} (xG: {s.xg:.2f}, {s.distance_to_goal:.1f}m)",
                    "xg": round(s.xg, 2),
                }
            )

        # 3. Defensive Saves & Tackles
        for d in analyzer.defense_analyzer.events:
            if d.event_type == "goalkeeper_save":
                events_feed.append(
                    {
                        "type": "save",
                        "t": round(d.timestamp, 2),
                        "team": d.team,
                        "desc": f"Defesa do Goleiro #{d.actor_id} (xG Salvo: {d.shot_xg_saved:.2f})",
                    }
                )
            elif d.event_type == "tackle":
                events_feed.append(
                    {
                        "type": "tackle",
                        "t": round(d.timestamp, 2),
                        "team": d.team,
                        "desc": f"Roubo de Bola #{d.actor_id} sobre #{d.target_opponent_id}",
                    }
                )

        events_feed.sort(key=lambda e: e["t"])

        # Player Robot Profiles
        y_profiles = {}
        for r_id, p in analyzer.kinematics_analyzer.yellow_stats.profiles.items():
            y_profiles[str(r_id)] = {
                "dist": round(p.total_distance_m, 1),
                "max_spd": round(p.max_speed_ms, 2),
                "avg_spd": round(p.avg_speed_ms, 2),
                "sprints": p.sprints_count,
                "passes": analyzer.pass_analyzer.yellow_stats.passes_by_robot.get(r_id, 0),
                "pos_sec": round(
                    analyzer.possession_analyzer.stats.robot_possession_sec["yellow"].get(r_id, 0.0), 1
                ),
                "tackles": analyzer.defense_analyzer.yellow_stats.tackles_by_robot.get(r_id, 0),
                "saves": analyzer.defense_analyzer.yellow_stats.saves_by_robot.get(r_id, 0),
            }

        b_profiles = {}
        for r_id, p in analyzer.kinematics_analyzer.blue_stats.profiles.items():
            b_profiles[str(r_id)] = {
                "dist": round(p.total_distance_m, 1),
                "max_spd": round(p.max_speed_ms, 2),
                "avg_spd": round(p.avg_speed_ms, 2),
                "sprints": p.sprints_count,
                "passes": analyzer.pass_analyzer.blue_stats.passes_by_robot.get(r_id, 0),
                "pos_sec": round(
                    analyzer.possession_analyzer.stats.robot_possession_sec["blue"].get(r_id, 0.0), 1
                ),
                "tackles": analyzer.defense_analyzer.blue_stats.tackles_by_robot.get(r_id, 0),
                "saves": analyzer.defense_analyzer.blue_stats.saves_by_robot.get(r_id, 0),
            }

        # Pass Networks (Nodes at average positions, weighted directed edges)
        y_pass_network = {
            "nodes": [
                {
                    "id": r_id,
                    "x": round(prof.avg_x, 3),
                    "y": round(prof.avg_y, 3),
                    "total_passes": analyzer.pass_analyzer.yellow_stats.passes_by_robot.get(r_id, 0)
                    + analyzer.pass_analyzer.yellow_stats.receptions_by_robot.get(r_id, 0),
                }
                for r_id, prof in analyzer.kinematics_analyzer.yellow_stats.profiles.items()
            ],
            "edges": [
                {"from": p_id, "to": r_id, "count": cnt}
                for p_id, targets in analyzer.pass_analyzer.yellow_stats.pass_matrix.items()
                for r_id, cnt in targets.items()
                if p_id != r_id
            ],
        }

        b_pass_network = {
            "nodes": [
                {
                    "id": r_id,
                    "x": round(prof.avg_x, 3),
                    "y": round(prof.avg_y, 3),
                    "total_passes": analyzer.pass_analyzer.blue_stats.passes_by_robot.get(r_id, 0)
                    + analyzer.pass_analyzer.blue_stats.receptions_by_robot.get(r_id, 0),
                }
                for r_id, prof in analyzer.kinematics_analyzer.blue_stats.profiles.items()
            ],
            "edges": [
                {"from": p_id, "to": r_id, "count": cnt}
                for p_id, targets in analyzer.pass_analyzer.blue_stats.pass_matrix.items()
                for r_id, cnt in targets.items()
                if p_id != r_id
            ],
        }

        result = {
            "metadata": {
                "yellow_name": analyzer.yellow_team_name,
                "blue_name": analyzer.blue_team_name,
                "duration_sec": round(duration, 1),
                "division": analyzer.division,
                "field_length": analyzer.field_length,
                "field_width": analyzer.field_width,
                "goal_width": analyzer.goal_width,
                "total_frames": len(web_frames),
            },
            "kpis": {
                "possession_y": round(analyzer.possession_analyzer.stats.yellow_possession_pct, 1),
                "possession_b": round(analyzer.possession_analyzer.stats.blue_possession_pct, 1),
                "possession_y_sec": round(analyzer.possession_analyzer.stats.yellow_time_sec, 1),
                "possession_b_sec": round(analyzer.possession_analyzer.stats.blue_time_sec, 1),
                "passes_y_total": analyzer.pass_analyzer.yellow_stats.total_passes,
                "passes_y_ok": analyzer.pass_analyzer.yellow_stats.completed_passes,
                "passes_y_acc": round(analyzer.pass_analyzer.yellow_stats.accuracy_pct, 1),
                "passes_b_total": analyzer.pass_analyzer.blue_stats.total_passes,
                "passes_b_ok": analyzer.pass_analyzer.blue_stats.completed_passes,
                "passes_b_acc": round(analyzer.pass_analyzer.blue_stats.accuracy_pct, 1),
                "shots_y": analyzer.xg_analyzer.yellow_stats.total_shots,
                "shots_b": analyzer.xg_analyzer.blue_stats.total_shots,
                "xg_y": round(analyzer.xg_analyzer.yellow_stats.total_xg, 2),
                "xg_b": round(analyzer.xg_analyzer.blue_stats.total_xg, 2),
                "tackles_y": analyzer.defense_analyzer.yellow_stats.tackles_won,
                "tackles_b": analyzer.defense_analyzer.blue_stats.tackles_won,
                "saves_y": analyzer.defense_analyzer.yellow_stats.goalkeeper_saves,
                "saves_b": analyzer.defense_analyzer.blue_stats.goalkeeper_saves,
                "goals_prevented_y": round(analyzer.defense_analyzer.yellow_stats.goals_prevented_xg, 2),
                "goals_prevented_b": round(analyzer.defense_analyzer.blue_stats.goals_prevented_xg, 2),
                "dist_y": round(analyzer.kinematics_analyzer.yellow_stats.total_team_distance_m, 1),
                "dist_b": round(analyzer.kinematics_analyzer.blue_stats.total_team_distance_m, 1),
                "max_spd_y": round(analyzer.kinematics_analyzer.yellow_stats.max_team_speed_ms, 2),
                "max_spd_b": round(analyzer.kinematics_analyzer.blue_stats.max_team_speed_ms, 2),
            },
            "events": events_feed,
            "profiles": {"yellow": y_profiles, "blue": b_profiles},
            "pass_network": {"yellow": y_pass_network, "blue": b_pass_network},
            "heatmaps": analyzer.heatmap_analyzer.export_all_heatmaps(),
            "frames": web_frames,
        }

        self._cache[cache_key] = result
        print(f"[+] Partida pronta para o Player ({len(web_frames)} quadros a ~{max_fps} fps).")
        return result


cache = MatchCache()


class SSLWebHandler(SimpleHTTPRequestHandler):
    """Custom request handler for the SSL Tactical Web Dashboard."""

    def __init__(self, *args, **kwargs):
        static_dir = str(Path(__file__).resolve().parent / "static")
        super().__init__(*args, directory=static_dir, **kwargs)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # 1. API: List available match files
        if path == "/api/matches":
            self._handle_api_matches()
            return

        # 2. API: Load and return parsed match data
        elif path == "/api/match_data":
            self._handle_api_match_data(query)
            return

        # 3. Serve Frontend HTML / Static files
        if path == "/" or path == "":
            self.path = "/index.html"
        return super().do_GET()

    def _handle_api_matches(self):
        root = Path(__file__).resolve().parent.parent.parent
        match_dirs = [root / "data" / "raw", root / "data" / "sample_matches"]

        files_found = []
        for d in match_dirs:
            if not d.exists():
                continue
            for f in sorted(d.iterdir()):
                if is_ssl_binary_log(f):
                    size_mb = f.stat().st_size / (1024.0 * 1024.0)
                    mtime = datetime.fromtimestamp(f.stat().st_mtime).strftime("%d/%m/%Y %H:%M")
                    rel_path = str(f.relative_to(root))
                    files_found.append(
                        {
                            "name": f.name,
                            "path": rel_path,
                            "size_mb": round(size_mb, 2),
                            "modified": mtime,
                        }
                    )

        # Sort so real matches appear first
        files_found.sort(key=lambda x: (x["size_mb"] < 0.1, x["name"]))
        self._send_json(files_found)

    def _handle_api_match_data(self, query):
        if "path" not in query:
            self._send_json({"error": "Parâmetro 'path' obrigatório."}, status=400)
            return

        raw_path = query["path"][0]
        root = Path(__file__).resolve().parent.parent.parent
        log_file = root / raw_path

        try:
            data = cache.get_or_parse(str(log_file))
            self._send_json(data)
        except Exception as e:
            traceback.print_exc()
            self._send_json({"error": f"Erro ao processar partida: {e}"}, status=500)

    def _send_json(self, data_obj, status: int = 200):
        payload = json.dumps(data_obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(payload)


def run_web_dashboard(port: int = 8080):
    server_address = ("0.0.0.0", port)
    httpd = HTTPServer(server_address, SSLWebHandler)
    print("=" * 65)
    print("      DASHBOARD WEB E PLAYER 2D INTERATIVO - ROBOCUP SSL")
    print("=" * 65)
    print(f"[*] Servidor rodando em: http://localhost:{port}")
    print(f"[*] Acesse pelo navegador para assistir às partidas e analisar a tática.")
    print("=" * 65)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[!] Encerrando servidor web...")
        httpd.server_close()


if __name__ == "__main__":
    run_web_dashboard(port=8080)
