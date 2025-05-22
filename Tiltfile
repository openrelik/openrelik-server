version_settings(constraint=">=0.22.1")

docker_compose("../openrelik/docker-compose.yml")

docker_build(
    # Image name - must match the image in the docker-compose file
    "openrelik-server",
    # Docker context
    ".",
    live_update=[
        # Sync local files into the container.
        sync("./src", "/openrelik/src"),
        # Restart the process to pick up the changed files.
        restart_container(),
    ],
)
