import sys
from pathlib import Path

_proto_dir = str(Path(__file__).resolve().parent)
if _proto_dir not in sys.path:
    sys.path.insert(0, _proto_dir)

from . import messages_robocup_ssl_detection_pb2 as detection_pb2
from . import messages_robocup_ssl_geometry_pb2 as geometry_pb2
from . import messages_robocup_ssl_wrapper_pb2 as wrapper_pb2
from . import ssl_referee_pb2 as referee_pb2

__all__ = [
    "detection_pb2",
    "geometry_pb2",
    "wrapper_pb2",
    "referee_pb2",
]
