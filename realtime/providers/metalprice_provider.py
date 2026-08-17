"""
MetalpriceAPI Provider Implementation
Primary provider for real-time gold prices
API: https://metalpriceapi.com/
"""

import asyncio
import aiohttp
import ssl
import certifi
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, Callable
from loguru import logger
import os

from .base_provider import (
    BaseProvider,
    ProviderResponse,
    HistoricalData,
    ProviderError,
    ProviderConnectionError,
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderDataError,
    ProviderStatus
)


class MetalpriceProvider(BaseProvider):
    """
    MetalpriceAPI provider for gold prices

    Features:
    - Real-time spot prices
    - Historical timeframe data
    - Multi-currency support
    - Rate limiting compliance

    Free Tier Limits:
    - 100 requests/month (adjust based on actual limits)
    - Real-time data
    - Historical data available
    """

    BASE_URL = "https://api.metalpriceapi.com/v1"

    def __init__(self, api_key: Optional[str] = None, config: Optional[Dict[str, Any]] = None):
        """
        Initialize MetalpriceAPI provider

        Args:
            api_key: MetalpriceAPI key
            config: Additional configuration
        """
        super().__init__(api_key, config)

        if not self.api_key:
            self.api_key = os.getenv('METALPRICE_API_KEY')

        if not self.api_key:
            raise ProviderAuthError("METALPRICE_API_KEY not found")

        self.session = None
        self.base_currency = self.config.get('base_currency', 'XAU')
        self.rate_limit_delay = self.config.get('rate_limit_delay', 2.0)  # seconds between calls
        self.last_request_time = None

        logger.info(f"MetalpriceAPI provider initialized")

    @property
    def name(self) -> str:
        return "metalprice"

    @property
    def supports_streaming(self) -> bool:
        return False  # MetalpriceAPI uses REST polling

    async def connect(self) -> bool:
        """Establish HTTP session"""
        try:
            if not self.session:
                # Create SSL context with proper certificate verification
                try:
                    # Try using certifi CA bundle (recommended)
                    ssl_context = ssl.create_default_context(cafile=certifi.where())
                    logger.info("✓ Using certifi CA bundle for SSL verification")
                except Exception as e:
                    # Fallback: disable SSL verification (development only)
                    logger.warning(f"Certifi not available ({e}), disabling SSL verification (not recommended for production)")
                    ssl_context = ssl.create_default_context()
                    ssl_context.check_hostname = False
                    ssl_context.verify_mode = ssl.CERT_NONE

                connector = aiohttp.TCPConnector(ssl=ssl_context)
                self.session = aiohttp.ClientSession(connector=connector)

            # Test connection with health check
            is_healthy = await self.health_check()

            if is_healthy:
                self.is_connected = True
                self._status = ProviderStatus.HEALTHY
                logger.info("✓ MetalpriceAPI connected")
                return True
            else:
                self._status = ProviderStatus.UNAVAILABLE
                return False

        except Exception as e:
            logger.error(f"✗ MetalpriceAPI connection failed: {e}")
            self.record_error(ProviderConnectionError(str(e)))
            return False

    async def disconnect(self):
        """Close HTTP session"""
        if self.session:
            await self.session.close()
            self.session = None

        self.is_connected = False
        logger.info("MetalpriceAPI disconnected")

    async def _rate_limit_wait(self):
        """Enforce rate limiting"""
        if self.last_request_time:
            elapsed = (datetime.now() - self.last_request_time).total_seconds()
            if elapsed < self.rate_limit_delay:
                wait_time = self.rate_limit_delay - elapsed
                await asyncio.sleep(wait_time)

        self.last_request_time = datetime.now()

    async def _make_request(self, endpoint: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Make API request with error handling

        Args:
            endpoint: API endpoint (e.g., '/latest')
            params: Query parameters

        Returns:
            Response JSON
        """
        if not self.session:
            await self.connect()

        # Rate limiting
        await self._rate_limit_wait()

        url = f"{self.BASE_URL}{endpoint}"

        # Add API key to params
        params = params or {}
        params['api_key'] = self.api_key

        try:
            async with self.session.get(url, params=params, timeout=10) as response:

                # Check rate limiting
                if response.status == 429:
                    error = ProviderRateLimitError("Rate limit exceeded")
                    self.record_error(error)
                    raise error

                # Check authentication
                if response.status == 401 or response.status == 403:
                    error = ProviderAuthError("Invalid API key")
                    self.record_error(error)
                    raise error

                # Check success
                if response.status != 200:
                    error_text = await response.text()
                    error = ProviderError(f"API error {response.status}: {error_text}")
                    self.record_error(error)
                    raise error

                data = await response.json()

                # Check API-level success
                if not data.get('success', True):
                    error_msg = data.get('error', {}).get('info', 'Unknown error')
                    error = ProviderError(f"API returned error: {error_msg}")
                    self.record_error(error)
                    raise error

                self.record_success()
                return data

        except aiohttp.ClientError as e:
            error = ProviderConnectionError(f"HTTP request failed: {e}")
            self.record_error(error)
            raise error
        except asyncio.TimeoutError as e:
            error = ProviderConnectionError("Request timeout")
            self.record_error(error)
            raise error

    async def get_quote(self, symbol: str = 'XAU', currency: str = 'USD') -> Optional[ProviderResponse]:
        """
        Get current gold price

        Args:
            symbol: Base metal (default: 'XAU')
            currency: Target currency (default: 'USD')

        Returns:
            ProviderResponse with current price
        """
        try:
            # MetalpriceAPI endpoint: /latest
            # Parameters: base=XAU&currencies=USD
            params = {
                'base': symbol,
                'currencies': currency
            }

            data = await self._make_request('/latest', params)

            # Parse response
            # Expected format: {"success": true, "base": "XAU", "timestamp": 1234567890, "rates": {"USD": 1950.25}}
            timestamp = datetime.fromtimestamp(data['timestamp'], tz=timezone.utc)
            rates = data.get('rates', {})

            if currency not in rates:
                raise ProviderDataError(f"Currency {currency} not in response")

            price = rates[currency]

            # Convert to ounces if needed (API may return per gram or per ounce)
            # MetalpriceAPI typically returns per troy ounce for XAU
            price_usd = float(price)

            response = ProviderResponse(
                timestamp=timestamp,
                symbol=symbol,
                price_usd=price_usd,
                provider_name=self.name,
                raw_symbol=f"{symbol}/{currency}",
                source_type='rest',
                metadata={
                    'base': data.get('base'),
                    'unit': 'troy_ounce'
                }
            )

            logger.debug(f"MetalpriceAPI quote: {symbol} = ${price_usd:.2f}")
            return response

        except ProviderError:
            raise
        except Exception as e:
            logger.error(f"Error getting quote: {e}")
            self.record_error(ProviderDataError(str(e)))
            return None

    async def stream_prices(
        self,
        symbol: str = 'XAU',
        on_price: Optional[Callable[[ProviderResponse], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None
    ):
        """
        Polling loop for real-time prices (MetalpriceAPI doesn't support WebSocket)

        Args:
            symbol: Trading symbol
            on_price: Callback for each price update
            on_error: Callback for errors
        """
        logger.info(f"Starting MetalpriceAPI polling for {symbol}")

        polling_interval = self.config.get('polling_interval', 60)  # Default: 1 minute

        while self.is_connected:
            try:
                quote = await self.get_quote(symbol)

                if quote and on_price:
                    if asyncio.iscoroutinefunction(on_price):
                        await on_price(quote)
                    else:
                        on_price(quote)

                await asyncio.sleep(polling_interval)

            except Exception as e:
                logger.error(f"Polling error: {e}")
                if on_error:
                    if asyncio.iscoroutinefunction(on_error):
                        await on_error(e)
                    else:
                        on_error(e)

                # Back off on errors
                await asyncio.sleep(polling_interval * 2)

    async def get_historical(
        self,
        symbol: str = 'XAU',
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        interval: str = '1d',
        limit: int = 100
    ) -> Optional[HistoricalData]:
        """
        Get historical gold prices

        Args:
            symbol: Trading symbol
            start_date: Start date
            end_date: End date
            interval: Time interval (MetalpriceAPI uses daily data)
            limit: Maximum records

        Returns:
            HistoricalData
        """
        try:
            # Default date range
            if not end_date:
                end_date = datetime.now(timezone.utc)
            if not start_date:
                start_date = end_date - timedelta(days=limit)

            # MetalpriceAPI endpoint: /timeframe
            # Parameters: start_date=YYYY-MM-DD&end_date=YYYY-MM-DD&base=XAU&currencies=USD
            params = {
                'start_date': start_date.strftime('%Y-%m-%d'),
                'end_date': end_date.strftime('%Y-%m-%d'),
                'base': symbol,
                'currencies': 'USD'
            }

            data = await self._make_request('/timeframe', params)

            # Parse response
            # Expected format: {"success": true, "base": "XAU", "start_date": "...", "end_date": "...",
            #                   "rates": {"2024-01-01": {"USD": 2050}, "2024-01-02": {"USD": 2055}}}
            rates_data = data.get('rates', {})

            if not rates_data:
                logger.warning("No historical data returned")
                return None

            # Convert to standardized format
            timestamps = []
            closes = []

            for date_str, currencies in sorted(rates_data.items()):
                if 'USD' in currencies:
                    timestamp = datetime.strptime(date_str, '%Y-%m-%d').replace(tzinfo=timezone.utc)
                    price = float(currencies['USD'])

                    timestamps.append(timestamp)
                    closes.append(price)

            # For daily data, we don't have OHLC, so use close for all
            historical = HistoricalData(
                symbol=symbol,
                timestamps=timestamps,
                open=closes.copy(),   # Use close as approximation
                high=closes.copy(),   # Use close as approximation
                low=closes.copy(),    # Use close as approximation
                close=closes,
                provider_name=self.name
            )

            logger.info(f"Retrieved {len(timestamps)} historical records from MetalpriceAPI")
            return historical

        except ProviderError:
            raise
        except Exception as e:
            logger.error(f"Error getting historical data: {e}")
            self.record_error(ProviderDataError(str(e)))
            return None

    async def health_check(self) -> bool:
        """
        Check API availability

        Returns:
            True if healthy
        """
        try:
            # Try to get a simple quote
            quote = await self.get_quote('XAU', 'USD')
            return quote is not None

        except Exception as e:
            logger.warning(f"Health check failed: {e}")
            return False

    def __del__(self):
        """Cleanup on deletion"""
        if self.session and not self.session.closed:
            # Schedule cleanup
            try:
                asyncio.create_task(self.disconnect())
            except RuntimeError:
                pass  # Event loop may be closed


# Test function
async def test_metalprice_provider():
    """Test MetalpriceAPI provider"""
    print("\n" + "="*60)
    print("TESTING METALPRICE PROVIDER")
    print("="*60)

    provider = MetalpriceProvider()

    # Test connection
    print("\n1. Testing connection...")
    connected = await provider.connect()
    if connected:
        print("✓ Connected successfully")
        print(f"  Status: {provider.status.value}")
    else:
        print("✗ Connection failed")
        return

    # Test current quote
    print("\n2. Testing current quote...")
    quote = await provider.get_quote('XAU', 'USD')
    if quote:
        print(f"✓ Current Gold Price: ${quote.price_usd:.2f}")
        print(f"  Timestamp: {quote.timestamp}")
        print(f"  Provider: {quote.provider_name}")
    else:
        print("✗ Failed to get quote")

    # Test historical data
    print("\n3. Testing historical data...")
    end_date = datetime.now(timezone.utc)
    start_date = end_date - timedelta(days=7)
    historical = await provider.get_historical('XAU', start_date, end_date)
    if historical:
        print(f"✓ Retrieved {len(historical.close)} days of data")
        print(f"  Latest price: ${historical.close[-1]:.2f}")
        print(f"  Date range: {historical.timestamps[0].date()} to {historical.timestamps[-1].date()}")
    else:
        print("✗ Failed to get historical data")

    # Test stats
    print("\n4. Provider statistics:")
    stats = provider.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")

    # Cleanup
    await provider.disconnect()
    print("\n✓ Test complete")


if __name__ == "__main__":
    asyncio.run(test_metalprice_provider())

