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
import sys

import tomllib
from fastapi import HTTPException
from openrelik_ai_common.providers import manager


def get_config() -> dict:
    """Load the settings from the settings.toml file."""
    project_dir = os.path.normpath(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    settings_from_env = os.getenv("OPENRELIK_SERVER_SETTINGS")
    # To ensure tests can be loaded even if we don't have a settings.toml file
    # or we didn't set the environment variable (e.g. vanilla VScode devcontainer)
    if "pytest" in sys.modules:
        settings_file = os.path.join(project_dir, "settings_example.toml")
    else:
        settings_file = os.path.join(project_dir, "settings.toml")
    # Read path to settings file from the environment and use that is available.
    if settings_from_env and os.path.isfile(settings_from_env):
        settings_file = settings_from_env

    with open(settings_file, "rb") as fh:
        config = tomllib.load(fh)
    return config


def get_active_llms() -> dict:
    """Get active LLM providers from the LLM manager."""
    llm_manager = manager.LLMManager()
    llm_providers = list(llm_manager.get_providers())
    active_llms = [provider_class().to_dict() for _, provider_class in llm_providers]
    return active_llms


def get_active_llm() -> dict:
    """Get the first active LLM provider from the LLM manager.
    TODO: Make this selection more user configurable.
    """
    llm_manager = manager.LLMManager()
    llm_providers = list(llm_manager.get_providers())
    if not llm_providers:
        return None
    provider_class = llm_providers[0][1]
    return provider_class().to_dict()


def get_ui_server_url() -> str:
    """Get the UI server URL from the config."""
    ui_server_url = config.get("server", {}).get("ui_server_url")
    if not ui_server_url:
        raise HTTPException(status_code=500, detail="UI server URL is not configured.")
    return ui_server_url


config = get_config()
