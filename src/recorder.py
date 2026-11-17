"""
Live Network Recorder for RoboCup SSL Matches.
Captures real-time UDP multicast packets from SSL-Vision (or grSim) and SSL-Game-Controller,
saving them into official binary .log.gz files compatible with the tactical analyzer.
"""

import argparse
import ipaddress
import select
import signal
import socket
import struct
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from src.parser.binary_reader import (
    MESSAGE_SSL_REFBOX_2013,
    MESSAGE_SSL_VISION_2014,
    SSLLogWriter,
)


class SSLNetworkRecorder:
    """Listens to UDP multicast groups for SSL Vision and Referee packets and writes binary logs."""

    def __init__(
        self,
        output_file_path: str,
        vision_ip: str = "224.5.23.2",
        vision_port: int = 10006,
        referee_ip: str = "224.5.23.1",
        referee_port: int = 10003,
        network_interface_ip: str = "0.0.0.0",
        buffer_size: int = 65536,
    ):
        self.output_path = Path(output_file_path)
        self.vision_ip = vision_ip
        self.vision_port = vision_port
        self.referee_ip = referee_ip
        self.referee_port = referee_port
        self.interface_ip = network_interface_ip
        self.buffer_size = buffer_size

        self.writer: Optional[SSLLogWriter] = None
        self._sockets: List[socket.socket] = []
        self._running = False

        self.vision_packet_count = 0
        self.referee_packet_count = 0
        self.bytes_written = 0
        self.start_time: float = 0.0

    def _create_multicast_socket(self, group_ip: str, port: int) -> socket.socket:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            try:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
            except OSError:
                pass

        sock.bind(("", port))

        # Join Multicast Group if it is a multicast IP address (224.0.0.0 to 239.255.255.255)
        try:
            is_mcast = ipaddress.ip_address(group_ip).is_multicast
        except ValueError:
            is_mcast = False

        if is_mcast:
            mreq = struct.pack("4s4s", socket.inet_aton(group_ip), socket.inet_aton(self.interface_ip))
            sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

        sock.setblocking(False)
        return sock

    def start_recording(self, duration_sec: Optional[float] = None):
        """Starts the capture loop. Can be interrupted with Ctrl+C or when duration expires."""
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.writer = SSLLogWriter(self.output_path, compressed=True)
        self.writer.open()

        print("=" * 65)
        print("          GRAVADOR AO VIVO DE PARTIDAS - ROBOCUP SSL")
        print("=" * 65)
        print(f"[*] Destino do log: {self.output_path}")
        print(f"[*] Escutando Visão (SSL-Vision / grSim): {self.vision_ip}:{self.vision_port}")
        print(f"[*] Escutando Árbitro (Game Controller):   {self.referee_ip}:{self.referee_port}")
        print("[*] Pressione Ctrl + C para encerrar e salvar a gravação.\n")

        # Create sockets
        vision_sock = self._create_multicast_socket(self.vision_ip, self.vision_port)
        referee_sock = self._create_multicast_socket(self.referee_ip, self.referee_port)
        self._sockets = [vision_sock, referee_sock]

        self._running = True
        self.start_time = time.time()
        last_stat_time = self.start_time

        # Handle SIGINT cleanly if running in main thread
        original_sigint = None
        if threading.current_thread() is threading.main_thread():
            def handle_sigint(signum, frame):
                print("\n[!] Sinal de interrupção recebido. Finalizando arquivo de log...")
                self._running = False

            original_sigint = signal.signal(signal.SIGINT, handle_sigint)

        try:
            while self._running:
                now = time.time()
                elapsed = now - self.start_time

                if duration_sec is not None and elapsed >= duration_sec:
                    print(f"\n[+] Duração programada atingida ({duration_sec}s). Encerrando...")
                    break

                # Poll sockets with 0.1s timeout
                readable, _, _ = select.select(self._sockets, [], [], 0.1)

                for sock in readable:
                    data, _ = sock.recvfrom(self.buffer_size)
                    curr_ts_ns = time.time_ns()

                    if sock == vision_sock:
                        self.writer.write_record(curr_ts_ns, MESSAGE_SSL_VISION_2014, data)
                        self.vision_packet_count += 1
                        self.bytes_written += len(data)
                    elif sock == referee_sock:
                        self.writer.write_record(curr_ts_ns, MESSAGE_SSL_REFBOX_2013, data)
                        self.referee_packet_count += 1
                        self.bytes_written += len(data)

                # Periodic status update on same line
                if now - last_stat_time >= 0.5:
                    v_fps = self.vision_packet_count / max(0.1, elapsed)
                    kb_written = self.bytes_written / 1024.0
                    sys.stdout.write(
                        f"\r[Gravando] Tempo: {elapsed:5.1f}s | "
                        f"Quadros Visão: {self.vision_packet_count} ({v_fps:4.1f} fps) | "
                        f"Juiz: {self.referee_packet_count} | "
                        f"Dados: {kb_written:6.1f} KB"
                    )
                    sys.stdout.flush()
                    last_stat_time = now

        finally:
            if original_sigint is not None:
                signal.signal(signal.SIGINT, original_sigint)
            for sock in self._sockets:
                try:
                    sock.close()
                except Exception:
                    pass

            if self.writer is not None:
                self.writer.close()

            total_elapsed = time.time() - self.start_time
            print("\n" + "=" * 65)
            print("                 GRAVAÇÃO CONCLUÍDA")
            print("=" * 65)
            print(f"[+] Duração total: {total_elapsed:.2f} s")
            print(f"[+] Quadros de visão capturados: {self.vision_packet_count}")
            print(f"[+] Mensagens de arbitragem:     {self.referee_packet_count}")
            print(f"[+] Arquivo salvo com sucesso:    {self.output_path}")
            if self.output_path.exists():
                print(f"[+] Tamanho final compactado:     {self.output_path.stat().st_size / 1024:.1f} KB")
            print("=" * 65)


def main():
    default_filename = f"partida_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log.gz"
    default_output = f"data/raw/{default_filename}"

    parser = argparse.ArgumentParser(
        description="Gravador de Partidas SSL em Tempo Real via Rede Multicast"
    )
    parser.add_argument(
        "--output",
        default=default_output,
        help=f"Caminho do arquivo .log.gz de saída (padrão: {default_output})",
    )
    parser.add_argument(
        "--vision-port",
        type=int,
        default=10006,
        help="Porta UDP da visão (padrão: 10006, ou 10020 no grSim)",
    )
    parser.add_argument(
        "--vision-ip",
        default="224.5.23.2",
        help="IP Multicast da visão (padrão: 224.5.23.2)",
    )
    parser.add_argument(
        "--referee-port",
        type=int,
        default=10003,
        help="Porta UDP do Game Controller / RefBox (padrão: 10003)",
    )
    parser.add_argument(
        "--referee-ip",
        default="224.5.23.1",
        help="IP Multicast do Game Controller (padrão: 224.5.23.1)",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=None,
        help="Duração máxima da gravação em segundos (opcional)",
    )
    parser.add_argument(
        "--interface",
        default="0.0.0.0",
        help="IP da interface de rede local para escutar (padrão: 0.0.0.0 para todas)",
    )

    args = parser.parse_args()

    recorder = SSLNetworkRecorder(
        output_file_path=args.output,
        vision_ip=args.vision_ip,
        vision_port=args.vision_port,
        referee_ip=args.referee_ip,
        referee_port=args.referee_port,
        network_interface_ip=args.interface,
    )
    recorder.start_recording(duration_sec=args.duration)


if __name__ == "__main__":
    main()
