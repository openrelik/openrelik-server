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
