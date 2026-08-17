"""
Finnhub Provider Implementation
Refactored to extend BaseProvider interface
Supports WebSocket streaming and REST API fallback
"""

import asyncio
import websockets
import json
import ssl
import certifi
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, Callable
from loguru import logger
import os
import aiohttp

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


class FinnhubProvider(BaseProvider):
    """
    Finnhub API provider for gold prices

    Features:
    - WebSocket streaming (primary)
    - REST API polling (fallback)
    - Real-time trade data
    - Historical candles

    Free Tier Limits:
    - 60 API calls/minute
    - WebSocket available
    """

    WS_URL = "wss://ws.finnhub.io"
    REST_URL = "https://finnhub.io/api/v1"

    # Symbol mapping: Standard -> Finnhub
    SYMBOL_MAP = {
        'XAU': 'XAUUSD',  # Gold in USD
        'XAG': 'XAGUSD',  # Silver in USD
    }

    # Reverse mapping: Finnhub -> Standard
    SYMBOL_MAP_REVERSE = {v: k for k, v in SYMBOL_MAP.items()}

    def __init__(self, api_key: Optional[str] = None, config: Optional[Dict[str, Any]] = None):
        """
        Initialize Finnhub provider

        Args:
            api_key: Finnhub API key
            config: Additional configuration
        """
        super().__init__(api_key, config)

        if not self.api_key:
            self.api_key = os.getenv('FINNHUB_API_KEY')

        if not self.api_key:
            raise ProviderAuthError("FINNHUB_API_KEY not found")

        self.ws_connection = None
        self.http_session = None
        self.subscribed_symbols = set()

        # WebSocket settings
        self.reconnect_delay = self.config.get('reconnect_delay', 30)
        self.max_retries = self.config.get('max_retries', 5)
        self.ping_interval = self.config.get('ping_interval', 30)

        logger.info("Finnhub provider initialized")

    @property
    def name(self) -> str:
        return "finnhub"

    @property
    def supports_streaming(self) -> bool:
        return True

    def normalize_symbol(self, symbol: str) -> str:
        """Convert standard symbol to Finnhub format"""
        return self.SYMBOL_MAP.get(symbol, symbol)

    def standardize_symbol(self, provider_symbol: str) -> str:
        """Convert Finnhub symbol to standard format"""
        return self.SYMBOL_MAP_REVERSE.get(provider_symbol, provider_symbol)

    async def connect(self) -> bool:
        """Establish WebSocket and HTTP connections"""
        try:
            # Create HTTP session with SSL support
            if not self.http_session:
                try:
                    ssl_context = ssl.create_default_context(cafile=certifi.where())
                    connector = aiohttp.TCPConnector(ssl=ssl_context)
                    self.http_session = aiohttp.ClientSession(connector=connector)
                    logger.info("✓ Using certifi CA bundle for SSL verification")
                except Exception as e:
                    logger.warning(f"Certifi not available ({e}), using fallback SSL")
                    ssl_context = ssl.create_default_context()
                    ssl_context.check_hostname = False
                    ssl_context.verify_mode = ssl.CERT_NONE
                    connector = aiohttp.TCPConnector(ssl=ssl_context)
                    self.http_session = aiohttp.ClientSession(connector=connector)

            # Test connection with health check
            is_healthy = await self.health_check()

            if is_healthy:
                self.is_connected = True
                self._status = ProviderStatus.HEALTHY
                logger.info("✓ Finnhub connected (HTTP)")
                return True
            else:
                self._status = ProviderStatus.UNAVAILABLE
                return False

        except Exception as e:
            logger.error(f"✗ Finnhub connection failed: {e}")
            self.record_error(ProviderConnectionError(str(e)))
            return False

    async def _connect_websocket(self) -> bool:
        """Establish WebSocket connection"""
        try:
            # Create SSL context (skip verification for macOS compatibility)
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

            ws_url = f"{self.WS_URL}?token={self.api_key}"

            self.ws_connection = await websockets.connect(
                ws_url,
                ssl=ssl_context,
                ping_interval=self.ping_interval
            )

            logger.info("✓ Finnhub WebSocket connected")
            return True

        except Exception as e:
            logger.error(f"✗ Finnhub WebSocket connection failed: {e}")
            self.record_error(ProviderConnectionError(str(e)))
            return False

    async def disconnect(self):
        """Close connections"""
        # Close WebSocket
        if self.ws_connection:
            await self.ws_connection.close()
            self.ws_connection = None

        # Close HTTP session
        if self.http_session:
            await self.http_session.close()
            self.http_session = None

        self.is_connected = False
        self.subscribed_symbols.clear()
        logger.info("Finnhub disconnected")

    async def _subscribe_symbol(self, symbol: str):
        """Subscribe to symbol on WebSocket"""
        if not self.ws_connection:
            return

        finnhub_symbol = self.normalize_symbol(symbol)

        subscribe_msg = {
            "type": "subscribe",
            "symbol": finnhub_symbol
        }

        await self.ws_connection.send(json.dumps(subscribe_msg))
        self.subscribed_symbols.add(finnhub_symbol)
        logger.info(f"✓ Subscribed to {finnhub_symbol}")

    async def _unsubscribe_symbol(self, symbol: str):
        """Unsubscribe from symbol on WebSocket"""
        if not self.ws_connection:
            return

        finnhub_symbol = self.normalize_symbol(symbol)

        unsubscribe_msg = {
            "type": "unsubscribe",
            "symbol": finnhub_symbol
        }

        await self.ws_connection.send(json.dumps(unsubscribe_msg))
        self.subscribed_symbols.discard(finnhub_symbol)
        logger.info(f"✓ Unsubscribed from {finnhub_symbol}")

    async def get_quote(self, symbol: str = 'XAU', currency: str = 'USD') -> Optional[ProviderResponse]:
        """
        Get current quote via REST API

        Args:
            symbol: Standard symbol
            currency: Target currency (ignored for Finnhub, uses pairs)

        Returns:
            ProviderResponse
        """
        try:
            if not self.http_session:
                await self.connect()

            finnhub_symbol = self.normalize_symbol(symbol)

            url = f"{self.REST_URL}/quote"
            params = {
                'symbol': finnhub_symbol,
                'token': self.api_key
            }

            async with self.http_session.get(url, params=params, timeout=10) as response:
                if response.status == 401:
                    error = ProviderAuthError("Invalid API key")
                    self.record_error(error)
                    raise error

                if response.status == 429:
                    error = ProviderRateLimitError("Rate limit exceeded")
                    self.record_error(error)
                    raise error

                if response.status != 200:
                    error = ProviderError(f"API error: {response.status}")
                    self.record_error(error)
                    raise error

                data = await response.json()

                # Parse Finnhub quote response
                # Format: {"c": current, "h": high, "l": low, "o": open, "pc": previous_close, "t": timestamp}
                current_price = data.get('c')

                if not current_price:
                    raise ProviderDataError("No price in response")

                response_obj = ProviderResponse(
                    timestamp=datetime.fromtimestamp(data.get('t', datetime.now().timestamp()), tz=timezone.utc),
                    symbol=symbol,  # Use standardized symbol
                    price_usd=float(current_price),
                    open=data.get('o'),
                    high=data.get('h'),
                    low=data.get('l'),
                    previous_close=data.get('pc'),
                    provider_name=self.name,
                    raw_symbol=finnhub_symbol,
                    source_type='rest',
                    metadata=data
                )

                self.record_success()
                logger.debug(f"Finnhub quote: {symbol} = ${current_price:.2f}")
                return response_obj

        except ProviderError:
            raise
        except Exception as e:
            logger.error(f"Error getting Finnhub quote: {e}")
            self.record_error(ProviderDataError(str(e)))
            return None

    def _process_trade_tick(self, tick: Dict[str, Any]) -> Optional[ProviderResponse]:
        """Process raw WebSocket trade tick"""
        try:
            finnhub_symbol = tick['s']
            standard_symbol = self.standardize_symbol(finnhub_symbol)

            return ProviderResponse(
                timestamp=datetime.fromtimestamp(tick['t'] / 1000, tz=timezone.utc),
                symbol=standard_symbol,
                price_usd=float(tick['p']),
                volume=tick.get('v', 0),
                provider_name=self.name,
                raw_symbol=finnhub_symbol,
                source_type='websocket',
                metadata={
                    'conditions': tick.get('c', [])
                }
            )
        except KeyError as e:
            logger.warning(f"Missing field in tick: {e}")
            return None

    async def stream_prices(
        self,
        symbol: str = 'XAU',
        on_price: Optional[Callable[[ProviderResponse], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None
    ):
        """
        Stream real-time prices via WebSocket

        Args:
            symbol: Standard symbol
            on_price: Callback for price updates
            on_error: Callback for errors
        """
        logger.info(f"Starting Finnhub WebSocket stream for {symbol}")

        retry_count = 0

        while retry_count < self.max_retries and self.is_connected:
            try:
                # Connect WebSocket
                connected = await self._connect_websocket()
                if not connected:
                    retry_count += 1
                    await asyncio.sleep(self.reconnect_delay)
                    continue

                retry_count = 0  # Reset on successful connection

                # Subscribe to symbol
                await self._subscribe_symbol(symbol)

                # Listen for messages
                async for message in self.ws_connection:
                    try:
                        data = json.loads(message)

                        if data.get('type') == 'trade':
                            # Process each trade tick
                            for tick in data.get('data', []):
                                processed = self._process_trade_tick(tick)

                                if processed and on_price:
                                    if asyncio.iscoroutinefunction(on_price):
                                        await on_price(processed)
                                    else:
                                        on_price(processed)

                            self.record_success()

                        elif data.get('type') == 'ping':
                            # Respond to ping
                            await self.ws_connection.send(json.dumps({"type": "pong"}))

                    except json.JSONDecodeError as e:
                        logger.warning(f"Invalid JSON: {e}")
                        continue

            except websockets.exceptions.ConnectionClosed:
                logger.warning("WebSocket closed, reconnecting...")
                retry_count += 1
                await asyncio.sleep(self.reconnect_delay)

            except Exception as e:
                logger.error(f"WebSocket stream error: {e}")
                self.record_error(e)

                if on_error:
                    if asyncio.iscoroutinefunction(on_error):
                        await on_error(e)
                    else:
                        on_error(e)

                retry_count += 1
                await asyncio.sleep(self.reconnect_delay)

        logger.error(f"Max retries reached for WebSocket stream")

    async def get_historical(
        self,
        symbol: str = 'XAU',
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        interval: str = '1d',
        limit: int = 100
    ) -> Optional[HistoricalData]:
        """
        Get historical candles via REST API

        Args:
            symbol: Standard symbol
            start_date: Start date
            end_date: End date
            interval: Resolution (1, 5, 15, 30, 60, D, W, M)
            limit: Max records

        Returns:
            HistoricalData
        """
        try:
            if not self.http_session:
                await self.connect()

            # Default dates
            if not end_date:
                end_date = datetime.now(timezone.utc)
            if not start_date:
                # Calculate based on interval and limit
                days = limit if interval == 'D' else limit // 24
                start_date = end_date - timedelta(days=days)

            finnhub_symbol = self.normalize_symbol(symbol)

            # Map interval to Finnhub resolution
            resolution_map = {
                '1m': '1', '5m': '5', '15m': '15', '30m': '30',
                '1h': '60', '1d': 'D', '1w': 'W', '1M': 'M'
            }
            resolution = resolution_map.get(interval, 'D')

            url = f"{self.REST_URL}/stock/candle"
            params = {
                'symbol': finnhub_symbol,
                'resolution': resolution,
                'from': int(start_date.timestamp()),
                'to': int(end_date.timestamp()),
                'token': self.api_key
            }

            async with self.http_session.get(url, params=params, timeout=15) as response:
                if response.status != 200:
                    raise ProviderError(f"API error: {response.status}")

                data = await response.json()

                if data.get('s') != 'ok':
                    logger.warning(f"No candle data: {data.get('s')}")
                    return None

                # Convert to standard format
                timestamps = [datetime.fromtimestamp(t, tz=timezone.utc) for t in data['t']]

                historical = HistoricalData(
                    symbol=symbol,
                    timestamps=timestamps,
                    open=data['o'],
                    high=data['h'],
                    low=data['l'],
                    close=data['c'],
                    volume=data.get('v'),
                    provider_name=self.name
                )

                self.record_success()
                logger.info(f"Retrieved {len(timestamps)} candles from Finnhub")
                return historical

        except Exception as e:
            logger.error(f"Error getting historical data: {e}")
            self.record_error(ProviderDataError(str(e)))
            return None

    async def health_check(self) -> bool:
        """Check Finnhub API availability"""
        try:
            quote = await self.get_quote('XAU')
            return quote is not None
        except Exception as e:
            logger.warning(f"Finnhub health check failed: {e}")
            return False

    def __del__(self):
        """Cleanup on deletion"""
        if self.ws_connection or (self.http_session and not self.http_session.closed):
            try:
                asyncio.create_task(self.disconnect())
            except RuntimeError:
                pass


# Test function
async def test_finnhub_provider():
    """Test Finnhub provider"""
    print("\n" + "="*60)
    print("TESTING FINNHUB PROVIDER")
    print("="*60)

    provider = FinnhubProvider()

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
    quote = await provider.get_quote('XAU')
    if quote:
        print(f"✓ Current Gold Price: ${quote.price_usd:.2f}")
        print(f"  Timestamp: {quote.timestamp}")
        print(f"  Provider: {quote.provider_name}")
        print(f"  Source: {quote.source_type}")
    else:
        print("✗ Failed to get quote")

    # Test historical data
    print("\n3. Testing historical data...")
    historical = await provider.get_historical('XAU', limit=5, interval='1d')
    if historical:
        print(f"✓ Retrieved {len(historical.close)} candles")
        print(f"  Latest close: ${historical.close[-1]:.2f}")
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
    asyncio.run(test_finnhub_provider())

