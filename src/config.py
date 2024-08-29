# Copyright 2024 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import tomllib

project_dir = os.path.normpath(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
settings_from_env = os.getenv("OPENRELIK_SERVER_SETTINGS")
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
