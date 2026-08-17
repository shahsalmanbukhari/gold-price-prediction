"""
Provider Factory - Dynamic provider instantiation and management
Handles provider selection, configuration, and failover
"""

from typing import Optional, Dict, Any, List
from loguru import logger
import os
import yaml
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

from realtime.providers.base_provider import BaseProvider
from realtime.providers.metalprice_provider import MetalpriceProvider
from realtime.providers.finnhub_provider import FinnhubProvider
from realtime.providers.gold_api_provider import GoldApiProvider


class ProviderFactory:
    """
    Factory for creating and managing market data providers

    Features:
    - Dynamic provider instantiation
    - Configuration loading
    - Provider registry
    - Failover management
    """

    # Registry of available providers
    PROVIDERS = {
        'gold_api': GoldApiProvider,
        'metalprice': MetalpriceProvider,
        'finnhub': FinnhubProvider,
    }

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize provider factory

        Args:
            config_path: Path to providers.yaml config file
        """
        self.config_path = config_path
        self.config = self._load_config()
        self.active_providers: Dict[str, BaseProvider] = {}

        logger.info("Provider factory initialized")

    def _load_config(self) -> Dict[str, Any]:
        """
        Load provider configuration from YAML or environment

        Returns:
            Configuration dictionary
        """
        config = {
            'default_provider': os.getenv('DEFAULT_PROVIDER', 'gold_api'),
            'fallback_enabled': os.getenv('PROVIDER_FALLBACK_ENABLED', 'true').lower() == 'true',
            'providers': {}
        }

        # Try loading from YAML
        if self.config_path and os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    yaml_config = yaml.safe_load(f)
                    if yaml_config:
                        config.update(yaml_config)
                        logger.info(f"✓ Loaded config from {self.config_path}")
            except Exception as e:
                logger.warning(f"Failed to load YAML config: {e}")

        # Override with environment variables
        for provider_name in self.PROVIDERS.keys():
            env_key = f"{provider_name.upper()}_API_KEY"
            api_key = os.getenv(env_key)

            if api_key:
                if provider_name not in config['providers']:
                    config['providers'][provider_name] = {}
                config['providers'][provider_name]['api_key'] = api_key

        return config

    def create_provider(
        self,
        provider_name: str,
        api_key: Optional[str] = None,
        config: Optional[Dict[str, Any]] = None
    ) -> Optional[BaseProvider]:
        """
        Create a provider instance

        Args:
            provider_name: Name of provider ('metalprice', 'finnhub')
            api_key: API key (optional, will use config/env if not provided)
            config: Additional provider configuration

        Returns:
            Provider instance or None
        """
        provider_name = provider_name.lower()

        if provider_name not in self.PROVIDERS:
            logger.error(f"Unknown provider: {provider_name}")
            logger.info(f"Available providers: {list(self.PROVIDERS.keys())}")
            return None

        try:
            # Get provider class
            provider_class = self.PROVIDERS[provider_name]

            # Get API key from config if not provided
            if not api_key:
                provider_config = self.config.get('providers', {}).get(provider_name, {})
                api_key = provider_config.get('api_key')

            # Merge configurations
            provider_config = self.config.get('providers', {}).get(provider_name, {}).copy()
            if config:
                provider_config.update(config)

            # Create instance
            provider = provider_class(api_key=api_key, config=provider_config)

            logger.info(f"✓ Created provider: {provider_name}")
            return provider

        except Exception as e:
            logger.error(f"Failed to create provider {provider_name}: {e}")
            return None

    async def get_provider(
        self,
        provider_name: Optional[str] = None,
        auto_connect: bool = True
    ) -> Optional[BaseProvider]:
        """
        Get or create a provider instance

        Args:
            provider_name: Name of provider (uses default if None)
            auto_connect: Automatically connect the provider

        Returns:
            Connected provider instance or None
        """
        # Use default provider if not specified
        if not provider_name:
            provider_name = self.config['default_provider']

        provider_name = provider_name.lower()

        # Return existing instance if already active
        if provider_name in self.active_providers:
            provider = self.active_providers[provider_name]
            if provider.is_connected:
                return provider

        # Create new provider
        provider = self.create_provider(provider_name)

        if not provider:
            return None

        # Connect if requested
        if auto_connect:
            try:
                connected = await provider.connect()
                if not connected:
                    logger.warning(f"Provider {provider_name} connection failed")
                    return None
            except Exception as e:
                logger.error(f"Error connecting to {provider_name}: {e}")
                return None

        # Store in active providers
        self.active_providers[provider_name] = provider

        return provider

    async def get_provider_with_fallback(
        self,
        preferred_provider: Optional[str] = None
    ) -> Optional[BaseProvider]:
        """
        Get provider with automatic fallback

        Tries preferred provider first, then falls back to alternatives

        Args:
            preferred_provider: Preferred provider name

        Returns:
            Connected provider or None
        """
        # Build priority list
        priority_list = []

        if preferred_provider:
            priority_list.append(preferred_provider)

        # Add default provider
        default = self.config['default_provider']
        if default not in priority_list:
            priority_list.append(default)

        # Add all other providers as fallback
        if self.config.get('fallback_enabled', True):
            for name in self.PROVIDERS.keys():
                if name not in priority_list:
                    priority_list.append(name)

        # Try each provider in order
        for provider_name in priority_list:
            logger.info(f"Trying provider: {provider_name}")

            provider = await self.get_provider(provider_name, auto_connect=True)

            if provider and provider.is_connected:
                # Health check
                try:
                    is_healthy = await provider.health_check()
                    if is_healthy:
                        logger.info(f"✓ Using provider: {provider_name}")
                        return provider
                    else:
                        logger.warning(f"Provider {provider_name} health check failed")
                except Exception as e:
                    logger.warning(f"Provider {provider_name} health check error: {e}")

        logger.error("No providers available")
        return None

    async def switch_provider(
        self,
        new_provider_name: str,
        disconnect_current: bool = True
    ) -> Optional[BaseProvider]:
        """
        Switch to a different provider

        Args:
            new_provider_name: Name of new provider
            disconnect_current: Disconnect current active providers

        Returns:
            New provider instance or None
        """
        logger.info(f"Switching to provider: {new_provider_name}")

        # Get new provider
        new_provider = await self.get_provider(new_provider_name, auto_connect=True)

        if not new_provider:
            logger.error(f"Failed to switch to {new_provider_name}")
            return None

        # Disconnect other providers if requested
        if disconnect_current:
            for name, provider in list(self.active_providers.items()):
                if name != new_provider_name and provider.is_connected:
                    try:
                        await provider.disconnect()
                        logger.info(f"✓ Disconnected provider: {name}")
                    except Exception as e:
                        logger.warning(f"Error disconnecting {name}: {e}")

        return new_provider

    def get_available_providers(self) -> List[str]:
        """Get list of available provider names"""
        return list(self.PROVIDERS.keys())

    def get_active_providers(self) -> Dict[str, BaseProvider]:
        """Get currently active provider instances"""
        return {
            name: provider
            for name, provider in self.active_providers.items()
            if provider.is_connected
        }

    async def disconnect_all(self):
        """Disconnect all active providers"""
        for name, provider in list(self.active_providers.items()):
            try:
                await provider.disconnect()
                logger.info(f"✓ Disconnected provider: {name}")
            except Exception as e:
                logger.warning(f"Error disconnecting {name}: {e}")

        self.active_providers.clear()

    def get_stats(self) -> Dict[str, Any]:
        """Get factory statistics"""
        return {
            'default_provider': self.config['default_provider'],
            'fallback_enabled': self.config['fallback_enabled'],
            'available_providers': self.get_available_providers(),
            'active_providers': list(self.get_active_providers().keys()),
            'provider_stats': {
                name: provider.get_stats()
                for name, provider in self.active_providers.items()
            }
        }


# Test function
async def test_provider_factory():
    """Test provider factory"""
    import asyncio

    print("\n" + "="*60)
    print("TESTING PROVIDER FACTORY")
    print("="*60)

    factory = ProviderFactory()

    # Test available providers
    print("\n1. Available providers:")
    for provider in factory.get_available_providers():
        print(f"  - {provider}")

    # Test default provider
    print(f"\n2. Default provider: {factory.config['default_provider']}")

    # Test creating provider
    print("\n3. Testing provider with fallback...")
    provider = await factory.get_provider_with_fallback()

    if provider:
        print(f"✓ Got provider: {provider.name}")
        print(f"  Status: {provider.status.value}")

        # Test getting quote
        quote = await provider.get_quote('XAU')
        if quote:
            print(f"✓ Current Gold Price: ${quote.price_usd:.2f}")
            print(f"  Provider: {quote.provider_name}")
    else:
        print("✗ No provider available")

    # Test factory stats
    print("\n4. Factory statistics:")
    stats = factory.get_stats()
    print(f"  Default: {stats['default_provider']}")
    print(f"  Fallback enabled: {stats['fallback_enabled']}")
    print(f"  Active providers: {stats['active_providers']}")

    # Cleanup
    await factory.disconnect_all()
    print("\n✓ Test complete")


if __name__ == "__main__":
    import asyncio
    asyncio.run(test_provider_factory())
