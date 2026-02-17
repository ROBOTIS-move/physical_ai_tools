"""
robot_client - High-level abstraction for robot sensor data and control.

Provides RobotClient (sensor reading + action output) and
RobotServiceServer (training/inference service framework)
on top of zenoh_ros2_sdk.
"""
from .robot_client import RobotClient
from .service_server import RobotServiceServer

__all__ = ["RobotClient", "RobotServiceServer"]
__version__ = "0.1.0"
