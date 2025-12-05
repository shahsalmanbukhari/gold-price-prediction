"""
Finnhub WebSocket and REST API Client
Handles real-time gold price streaming
"""

import asyncio
import websockets
import json
import finnhub
import time
import ssl
from datetime import datetime, timezone
from typing import Optional, Callable, Dict, Any
from loguru import logger
import os
from dotenv import load_dotenv

load_dotenv()


class FinnhubClient:
    """
    Finnhub API client for real-time gold price data

    Supports:
    - WebSocket streaming (primary)
    - REST API polling (fallback)
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Finnhub client

        Args:
            api_key: Finnhub API key (or from .env)
        """
        self.api_key = api_key or os.getenv('FINNHUB_API_KEY')
        if not self.api_key:
            raise ValueError("FINNHUB_API_KEY not found in environment")

        # REST client
        self.rest_client = finnhub.Client(api_key=self.api_key)

        # WebSocket config
        self.ws_url = f"wss://ws.finnhub.io?token={self.api_key}"
        self.ws_connection = None
        self.is_connected = False

        # Symbols to track
        self.symbols = ['XAUUSD']  # Gold in USD

        # Callbacks
        self.on_tick_callback = None
        self.on_error_callback = None

        # Reconnection settings
        self.reconnect_delay = int(os.getenv('WEBSOCKET_RECONNECT_DELAY', 30))
        self.max_retries = int(os.getenv('MAX_RETRIES', 5))

        logger.info("Finnhub client initialized")

    async def connect_websocket(self):
        """Establish WebSocket connection"""
        try:
            # Create SSL context that doesn't verify certificates
            # This fixes the SSL certificate verification error on macOS
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE

            self.ws_connection = await websockets.connect(
                self.ws_url,
                ssl=ssl_context
            )
            self.is_connected = True
            logger.info("✓ WebSocket connected to Finnhub")

            # Subscribe to symbols
            for symbol in self.symbols:
                subscribe_msg = {
                    "type": "subscribe",
                    "symbol": symbol
                }
                await self.ws_connection.send(json.dumps(subscribe_msg))
                logger.info(f"✓ Subscribed to {symbol}")

            return True

        except Exception as e:
            logger.error(f"✗ WebSocket connection failed: {e}")
            self.is_connected = False
            return False

    async def disconnect_websocket(self):
        """Close WebSocket connection"""
        if self.ws_connection:
            await self.ws_connection.close()
            self.is_connected = False
            logger.info("WebSocket disconnected")

    async def listen_websocket(self, on_tick: Callable, on_error: Optional[Callable] = None):
        """
        Listen to WebSocket stream

        Args:
            on_tick: Callback function for each tick (receives dict)
            on_error: Optional error callback
        """
        self.on_tick_callback = on_tick
        self.on_error_callback = on_error

        retry_count = 0

        while retry_count < self.max_retries:
            try:
                # Connect
                connected = await self.connect_websocket()
                if not connected:
                    retry_count += 1
                    await asyncio.sleep(self.reconnect_delay)
                    continue

                retry_count = 0  # Reset on successful connection

                # Listen for messages
                async for message in self.ws_connection:
                    try:
                        data = json.loads(message)

                        if data.get('type') == 'trade':
                            # Process each trade tick
                            for tick in data.get('data', []):
                                processed_tick = self._process_tick(tick)
                                if processed_tick and self.on_tick_callback:
                                    await self.on_tick_callback(processed_tick)

                        elif data.get('type') == 'ping':
                            # Respond to ping
                            await self.ws_connection.send(json.dumps({"type": "pong"}))

                    except json.JSONDecodeError as e:
                        logger.warning(f"Invalid JSON: {e}")
                        continue

            except websockets.exceptions.ConnectionClosed:
                logger.warning("WebSocket connection closed, reconnecting...")
                self.is_connected = False
                retry_count += 1
                await asyncio.sleep(self.reconnect_delay)

            except Exception as e:
                logger.error(f"WebSocket error: {e}")
                if self.on_error_callback:
                    await self.on_error_callback(e)
                retry_count += 1
                await asyncio.sleep(self.reconnect_delay)

        logger.error(f"Max retries ({self.max_retries}) reached, WebSocket listener stopped")

    def _process_tick(self, tick: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Process raw tick from Finnhub

        Args:
            tick: Raw tick data from Finnhub

        Returns:
            Processed tick dict or None
        """
        try:
            return {
                'timestamp': datetime.fromtimestamp(tick['t'] / 1000, tz=timezone.utc),
                'symbol': tick['s'],
                'price_usd': tick['p'],
                'volume': tick.get('v', 0),
                'conditions': tick.get('c', []),
                'source': 'finnhub_ws'
            }
        except KeyError as e:
            logger.warning(f"Missing field in tick: {e}")
            return None

    def get_quote(self, symbol: str = 'XAUUSD') -> Optional[Dict[str, Any]]:
        """
        Get current quote via REST API (polling fallback)

        Args:
            symbol: Trading symbol

        Returns:
            Quote dict or None
        """
        try:
            quote = self.rest_client.quote(symbol)

            return {
                'timestamp': datetime.now(timezone.utc),
                'symbol': symbol,
                'price_usd': quote.get('c'),  # Current price
                'open': quote.get('o'),
                'high': quote.get('h'),
                'low': quote.get('l'),
                'previous_close': quote.get('pc'),
                'change': quote.get('d'),
                'change_pct': quote.get('dp'),
                'source': 'finnhub_rest'
            }

        except Exception as e:
            logger.error(f"REST API error: {e}")
            return None

    def get_candles(self, symbol: str = 'XAUUSD',
                    resolution: str = '1', count: int = 200) -> Optional[Dict[str, Any]]:
        """
        Get historical candles via REST API

        Args:
            symbol: Trading symbol
            resolution: 1, 5, 15, 30, 60, D, W, M
            count: Number of candles

        Returns:
            Candles dict or None
        """
        try:
            end_time = int(time.time())
            start_time = end_time - (count * self._resolution_to_seconds(resolution))

            candles = self.rest_client.stock_candles(
                symbol=symbol,
                resolution=resolution,
                _from=start_time,
                to=end_time
            )

            if candles.get('s') == 'ok':
                return {
                    'symbol': symbol,
                    'resolution': resolution,
                    'timestamps': [datetime.fromtimestamp(t, tz=timezone.utc) for t in candles['t']],
                    'open': candles['o'],
                    'high': candles['h'],
                    'low': candles['l'],
                    'close': candles['c'],
                    'volume': candles['v']
                }
            else:
                logger.warning(f"No candle data: {candles.get('s')}")
                return None

        except Exception as e:
            logger.error(f"Candles API error: {e}")
            return None

    def _resolution_to_seconds(self, resolution: str) -> int:
        """Convert resolution to seconds"""
        mapping = {
            '1': 60,
            '5': 300,
            '15': 900,
            '30': 1800,
            '60': 3600,
            'D': 86400,
            'W': 604800,
            'M': 2592000
        }
        return mapping.get(resolution, 60)

    async def polling_loop(self, on_tick: Callable, interval: int = 10):
        """
        Polling fallback when WebSocket is unavailable

        Args:
            on_tick: Callback for each poll result
            interval: Polling interval in seconds
        """
        logger.info(f"Starting polling loop (interval: {interval}s)")

        while True:
            try:
                for symbol in self.symbols:
                    quote = self.get_quote(symbol)
                    if quote and on_tick:
                        await on_tick(quote)

                await asyncio.sleep(interval)

            except Exception as e:
                logger.error(f"Polling error: {e}")
                await asyncio.sleep(interval)


# Test
async def test_client():
    """Test Finnhub client"""
    client = FinnhubClient()

    # Test REST API
    print("\n=== Testing REST API ===")
    quote = client.get_quote()
    if quote:
        print(f"✓ Current Gold Price: ${quote['price_usd']:.2f}")
        #print(f"  Change: {quote.get('change_pct', 0):.2f}%")

    # Test candles
    print("\n=== Testing Candles ===")
    candles = client.get_candles(resolution='D', count=5)
    if candles:
        print(f"✓ Retrieved {len(candles['close'])} daily candles")
        print(f"  Latest close: ${candles['close'][-1]:.2f}")


if __name__ == "__main__":
    asyncio.run(test_client())

