"""
Binary log reader and writer for RoboCup SSL log files (.log and .log.gz).

Format Specification:
- Header:
    - 12 bytes magic string: b"SSL_LOG_FILE"
    - 4 bytes int32 (big-endian): format version (typically 1)
- Record structure (repeated until EOF):
    - 8 bytes int64 (big-endian): timestamp in nanoseconds
    - 4 bytes int32 (big-endian): message type
    - 4 bytes int32 (big-endian): message size in bytes
    - N bytes: raw protobuf message payload
"""

import gzip
import io
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Generator, Optional, Tuple, Union

# SSL Log Message Type Constants
MESSAGE_SSL_VISION_2010 = 1
MESSAGE_SSL_REFBOX_2013 = 2
MESSAGE_SSL_VISION_2014 = 3


@dataclass
class RawLogRecord:
    timestamp_ns: int
    message_type: int
    payload: bytes

    @property
    def timestamp_sec(self) -> float:
        return self.timestamp_ns / 1e9

    @property
    def timestamp_ms(self) -> float:
        return self.timestamp_ns / 1e6


class SSLLogReader:
    """Reader for RoboCup SSL binary log files."""

    MAGIC_HEADER = b"SSL_LOG_FILE"
    HEADER_STRUCT = struct.Struct(">12si")  # 12-byte magic + 4-byte int32 version
    RECORD_HEADER_STRUCT = struct.Struct(">qii")  # 8-byte timestamp + 4-byte type + 4-byte size

    def __init__(self, file_path_or_buffer: Union[str, Path, BinaryIO, bytes]):
        if isinstance(file_path_or_buffer, bytes):
            self._buffer: Optional[BinaryIO] = io.BytesIO(file_path_or_buffer)
            self._file_path: Optional[Path] = None
        elif isinstance(file_path_or_buffer, (str, Path)):
            self._file_path = Path(file_path_or_buffer)
            self._buffer = None
        else:
            self._buffer = file_path_or_buffer
            self._file_path = None

        self.version: int = 1

    def _open_stream(self) -> BinaryIO:
        if self._buffer is not None:
            self._buffer.seek(0)
            return self._buffer

        assert self._file_path is not None
        if not self._file_path.exists():
            raise FileNotFoundError(f"Arquivo de log não encontrado: {self._file_path}")

        # Check if file is gzipped
        with open(self._file_path, "rb") as test_f:
            magic_two = test_f.read(2)

        if magic_two == b"\x1f\x8b":
            return gzip.open(self._file_path, "rb")
        return open(self._file_path, "rb")

    def read_records(self) -> Generator[RawLogRecord, None, None]:
        """
        Stream records from the log file.
        Yields RawLogRecord instances.
        """
        stream = self._open_stream()
        try:
            # 1. Read and validate header (16 bytes: 12-byte magic + 4-byte version)
            header_bytes = stream.read(self.HEADER_STRUCT.size)
            if len(header_bytes) < self.HEADER_STRUCT.size:
                raise ValueError("Arquivo de log muito curto ou corrompido: cabeçalho ausente.")

            magic, self.version = self.HEADER_STRUCT.unpack(header_bytes)
            if magic != self.MAGIC_HEADER:
                raise ValueError(
                    f"Formato inválido. Identificador esperado: {self.MAGIC_HEADER!r}, "
                    f"obtido: {magic!r}"
                )

            # 2. Sequential record stream
            record_header_size = self.RECORD_HEADER_STRUCT.size
            while True:
                record_header = stream.read(record_header_size)
                if not record_header or len(record_header) < record_header_size:
                    # Normal EOF
                    break

                timestamp_ns, msg_type, msg_size = self.RECORD_HEADER_STRUCT.unpack(record_header)

                if msg_size < 0 or msg_size > 50 * 1024 * 1024:  # sanity limit (50 MB)
                    raise ValueError(f"Tamanho de mensagem inválido no log: {msg_size} bytes")

                payload = stream.read(msg_size)
                if len(payload) < msg_size:
                    # Truncated record at end of file
                    break

                yield RawLogRecord(
                    timestamp_ns=timestamp_ns,
                    message_type=msg_type,
                    payload=payload,
                )
        finally:
            if self._buffer is None:
                stream.close()


class SSLLogWriter:
    """Writer to record or serialize RoboCup SSL binary log files."""

    MAGIC_HEADER = b"SSL_LOG_FILE"
    HEADER_STRUCT = struct.Struct(">12si")
    RECORD_HEADER_STRUCT = struct.Struct(">qii")

    def __init__(self, file_path_or_buffer: Union[str, Path, BinaryIO], version: int = 1, compressed: bool = False):
        self.version = version
        self.compressed = compressed
        if isinstance(file_path_or_buffer, (str, Path)):
            self._file_path = Path(file_path_or_buffer)
            self._buffer: Optional[BinaryIO] = None
        else:
            self._file_path = None
            self._buffer = file_path_or_buffer

        self._stream: Optional[BinaryIO] = None

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def open(self):
        if self._buffer is not None:
            self._stream = self._buffer
        else:
            assert self._file_path is not None
            self._file_path.parent.mkdir(parents=True, exist_ok=True)
            if self.compressed or self._file_path.suffix == ".gz":
                self._stream = gzip.open(self._file_path, "wb")
            else:
                self._stream = open(self._file_path, "wb")

        # Write header
        header_bytes = self.HEADER_STRUCT.pack(self.MAGIC_HEADER, self.version)
        self._stream.write(header_bytes)

    def write_record(self, timestamp_ns: int, message_type: int, payload: bytes):
        if self._stream is None:
            raise RuntimeError("SSLLogWriter não foi aberto. Chame open() ou use gerenciador de contexto.")

        header = self.RECORD_HEADER_STRUCT.pack(timestamp_ns, message_type, len(payload))
        self._stream.write(header)
        self._stream.write(payload)

    def close(self):
        if self._stream is not None:
            if self._buffer is None:
                self._stream.close()
            self._stream = None
