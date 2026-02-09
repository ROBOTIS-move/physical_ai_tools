#!/bin/bash

# Get the directory where the script is located
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
CONTAINER_NAME="physical_ai_server"

# Auto-detect architecture for correct Dockerfile selection
MACHINE_ARCH=$(uname -m)
if [ "$MACHINE_ARCH" = "aarch64" ] || [ "$MACHINE_ARCH" = "arm64" ]; then
    export ARCH="arm64"
    echo "Detected ARM64 architecture (Jetson)"
else
    export ARCH="amd64"
    echo "Detected AMD64 architecture (x86_64)"
fi


# Function to display help
show_help() {
    echo "Usage: $0 [command]"
    echo ""
    echo "Commands:"
    echo "  help                    Show this help message"
    echo "  start                   Start the container"
    echo "  enter                   Enter the running container"
    echo "  stop                    Stop the container"
    echo ""
    echo "Examples:"
    echo "  $0 start                Start container"
    echo "  $0 enter                Enter the running container"
    echo "  $0 stop                 Stop the container"
}

# Function to start the container
start_container() {
    # Set up X11 forwarding only if DISPLAY is set
    if [ -n "$DISPLAY" ]; then
        echo "Setting up X11 forwarding..."
        xhost +local:docker || true
    else
        echo "Warning: DISPLAY environment variable is not set. X11 forwarding will not be available."
    fi

    echo "Starting physical_ai_server container..."

    # Pull the latest images (ignore errors for images that need to be built locally)
    docker compose -f "${SCRIPT_DIR}/docker-compose.yml" pull --ignore-pull-failures || true

    # Run docker-compose (build if image doesn't exist)
    docker compose -f "${SCRIPT_DIR}/docker-compose.yml" up -d --build
}

# Function to enter the container
enter_container() {
    # Set up X11 forwarding only if DISPLAY is set
    if [ -n "$DISPLAY" ]; then
        echo "Setting up X11 forwarding..."
        xhost +local:docker || true
    else
        echo "Warning: DISPLAY environment variable is not set. X11 forwarding will not be available."
    fi

    if ! docker ps | grep -q "$CONTAINER_NAME"; then
        echo "Error: Container is not running"
        exit 1
    fi
    docker exec -it "$CONTAINER_NAME" bash
}

# Function to stop the container
stop_container() {
    if ! docker ps | grep -q "$CONTAINER_NAME"; then
        echo "Error: Container is not running"
        exit 1
    fi

    echo "Warning: This will stop and remove the container. All unsaved data in the container will be lost."
    read -p "Are you sure you want to continue? [y/N] " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        docker compose -f "${SCRIPT_DIR}/docker-compose.yml" down
    else
        echo "Operation cancelled."
        exit 0
    fi
}

# Main command handling
case "$1" in
    "help")
        show_help
        ;;
    "start")
        start_container
        ;;
    "enter")
        enter_container
        ;;
    "stop")
        stop_container
        ;;
    *)
        echo "Error: Unknown command"
        show_help
        exit 1
        ;;
esac
