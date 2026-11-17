import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path

from src.parser.binary_reader import SSLLogReader
from src.recorder import SSLNetworkRecorder


class TestRecorder(unittest.TestCase):
    def test_recorder_loop_and_file_generation(self):
        with tempfile.NamedTemporaryFile(suffix=".log.gz", delete=False) as tmp:
            tmp_path = tmp.name

        try:
            # Pick non-standard ports for testing so there's no conflict
            test_vision_port = 19123
            test_ref_port = 19124

            recorder = SSLNetworkRecorder(
                output_file_path=tmp_path,
                vision_ip="127.0.0.1",
                vision_port=test_vision_port,
                referee_ip="127.0.0.1",
                referee_port=test_ref_port,
            )

            # Run in thread for 1.0 second
            rec_thread = threading.Thread(
                target=recorder.start_recording,
                kwargs={"duration_sec": 1.0},
                daemon=True,
            )
            rec_thread.start()

            time.sleep(0.1)

            # Send a test UDP packet
            client_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            test_payload = b"test_vision_packet_payload_123"
            client_sock.sendto(test_payload, ("127.0.0.1", test_vision_port))
            client_sock.close()

            rec_thread.join(timeout=3.0)

            # Verify file was generated and is a valid SSL log
            self.assertTrue(Path(tmp_path).exists())
            reader = SSLLogReader(tmp_path)
            records = list(reader.read_records())

            self.assertGreaterEqual(len(records), 1)
            self.assertEqual(records[0].payload, test_payload)

        finally:
            Path(tmp_path).unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
