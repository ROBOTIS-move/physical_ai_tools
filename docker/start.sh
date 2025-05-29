#!/bin/bash

# Run the web video server
ros2 run web_video_server web_video_server

# Run the rosbridge server
ros2 launch rosbridge_server rosbridge_websocket_launch.xml