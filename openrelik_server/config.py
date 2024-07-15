import os
import tomllib

project_dir = os.path.normpath(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
settings_from_env = os.getenv("API_SERVER_SETTINGS")
settings_file = os.path.join(project_dir, "settings.toml")

# Read path to settings file from the environment and use that is avalable.
if settings_from_env and os.path.isfile(settings_from_env):
    settings_file = settings_from_env


def get_config() -> dict:
    """Load the settings from the settings.toml file."""
    with open(settings_file, "rb") as fh:
        config = tomllib.load(fh)
    return config


config = get_config()
