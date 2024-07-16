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

from config import config as system_config


class EDRProvider:
    """Base class for EDR providers."""

    NAME = "name"

    def __init__(self):
        """Initialize the EDR provider.

        Args:

        Attributes:
            config: The configuration for the EDR provider.

        Raises:
            Exception: If the EDR provider is not configured.
        """
        # Load the provider config from the system config
        config_from_settings = system_config.get("edr").get(self.NAME)
        if not config_from_settings:
            raise Exception(f"{self.NAME} config not found")

        self.config = config_from_settings

    def get_endpoints(self) -> str:
        """Get all endpoints.

        Returns:
            List of endpoints.
        """
        raise NotImplementedError()
