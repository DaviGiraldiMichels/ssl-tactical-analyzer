import io
import unittest
from src.parser.binary_reader import (
    MESSAGE_SSL_REFBOX_2013,
    MESSAGE_SSL_VISION_2014,
    RawLogRecord,
    SSLLogReader,
    SSLLogWriter,
)


class TestBinaryReader(unittest.TestCase):
    def test_write_and_read_in_memory(self):
        buffer = io.BytesIO()

        # Write records
        writer = SSLLogWriter(buffer)
        writer.open()

        payload1 = b"dummy_vision_payload_12345"
        payload2 = b"dummy_referee_payload_67890"

        writer.write_record(1_000_000_000, MESSAGE_SSL_VISION_2014, payload1)
        writer.write_record(1_016_666_666, MESSAGE_SSL_REFBOX_2013, payload2)
        writer.close()

        # Read back
        reader = SSLLogReader(buffer.getvalue())
        records = list(reader.read_records())

        self.assertEqual(len(records), 2)
        self.assertEqual(reader.version, 1)

        self.assertEqual(records[0].timestamp_ns, 1_000_000_000)
        self.assertAlmostEqual(records[0].timestamp_sec, 1.0)
        self.assertEqual(records[0].message_type, MESSAGE_SSL_VISION_2014)
        self.assertEqual(records[0].payload, payload1)

        self.assertEqual(records[1].timestamp_ns, 1_016_666_666)
        self.assertEqual(records[1].message_type, MESSAGE_SSL_REFBOX_2013)
        self.assertEqual(records[1].payload, payload2)

    def test_invalid_header_raises_error(self):
        corrupt_data = b"NOT_A_LOG_FILE" + b"\x00" * 10
        reader = SSLLogReader(corrupt_data)
        with self.assertRaises(ValueError):
            list(reader.read_records())


if __name__ == "__main__":
    unittest.main()
