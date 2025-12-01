"""
Main real-time streaming orchestrator
Coordinates WebSocket/REST data ingestion with fallback
"""

import asyncio
import signal
from datetime import datetime
from typing import Optional
from loguru import logger
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from realtime.finnhub_client import FinnhubClient
from realtime.data_handler import DataHandler
from realtime.redis_cache import get_redis_cache


class GoldStreamer:
    """
    Main orchestrator for real-time gold price streaming

    Features:
    - WebSocket primary connection
    - REST polling fallback
    - Automatic failover
    - Graceful shutdown
    """

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize streamer

        Args:
            api_key: Finnhub API key
        """
        self.finnhub_client = FinnhubClient(api_key)
        self.data_handler = DataHandler()
        self.redis_cache = get_redis_cache()

        self.is_running = False
        self.use_websocket = True
        self.polling_interval = int(os.getenv('POLLING_INTERVAL', 10))

        # Statistics
        self.start_time = None
        self.connection_mode = None

        logger.info("Gold streamer initialized")

    async def on_tick_received(self, tick: dict):
        """
        Callback for incoming ticks

        Args:
            tick: Tick data from Finnhub
        """
        try:
            # Log tick
            logger.debug(f"Tick: {tick['symbol']} @ ${tick['price_usd']:.2f}")

            # Process tick
            await self.data_handler.process_tick(tick)

        except Exception as e:
            logger.error(f"Tick processing error: {e}")

    async def on_error(self, error: Exception):
        """
        Callback for errors

        Args:
            error: Exception that occurred
        """
        logger.error(f"Stream error: {error}")

        # Switch to polling fallback
        if self.use_websocket:
            logger.warning("Switching to REST polling fallback...")
            self.use_websocket = False

    async def start_websocket_stream(self):
        """Start WebSocket streaming"""
        logger.info("Starting WebSocket stream...")
        self.connection_mode = 'websocket'

        try:
            await self.finnhub_client.listen_websocket(
                on_tick=self.on_tick_received,
                on_error=self.on_error
            )
        except Exception as e:
            logger.error(f"WebSocket stream error: {e}")
            self.use_websocket = False

    async def start_polling_stream(self):
        """Start REST polling fallback"""
        logger.info(f"Starting REST polling (interval: {self.polling_interval}s)...")
        self.connection_mode = 'polling'

        try:
            await self.finnhub_client.polling_loop(
                on_tick=self.on_tick_received,
                interval=self.polling_interval
            )
        except Exception as e:
            logger.error(f"Polling error: {e}")

    async def run(self):
        """Main run loop"""
        self.is_running = True
        self.start_time = datetime.now()

        logger.info("="*60)
        logger.info("GOLD PRICE REAL-TIME STREAMER")
        logger.info("="*60)
        logger.info(f"Started at: {self.start_time}")
        logger.info(f"Redis available: {self.redis_cache.is_available()}")
        logger.info("="*60)

        while self.is_running:
            try:
                if self.use_websocket:
                    # Try WebSocket
                    await self.start_websocket_stream()

                    # If we exit, switch to polling
                    if self.is_running:
                        logger.warning("WebSocket disconnected, switching to polling...")
                        self.use_websocket = False
                        await asyncio.sleep(5)
                else:
                    # Use REST polling
                    await self.start_polling_stream()

            except KeyboardInterrupt:
                logger.info("Keyboard interrupt received")
                break
            except Exception as e:
                logger.error(f"Stream error: {e}")
                await asyncio.sleep(10)

        logger.info("Streamer stopped")

    async def stop(self):
        """Stop streaming"""
        logger.info("Stopping streamer...")
        self.is_running = False

        # Disconnect WebSocket
        if self.finnhub_client.is_connected:
            await self.finnhub_client.disconnect_websocket()

        # Close data handler
        self.data_handler.close()

        # Print statistics
        stats = self.data_handler.get_statistics()
        uptime = (datetime.now() - self.start_time).total_seconds() if self.start_time else 0

        logger.info("="*60)
        logger.info("STREAMER STATISTICS")
        logger.info("="*60)
        logger.info(f"Uptime: {uptime:.2f} seconds")
        logger.info(f"Connection mode: {self.connection_mode}")
        logger.info(f"Ticks processed: {stats['ticks_processed']}")
        logger.info(f"Ticks stored: {stats['ticks_stored']}")
        logger.info(f"Success rate: {stats['success_rate']:.2f}%")
        logger.info("="*60)

    def get_status(self) -> dict:
        """Get current streamer status"""
        return {
            'is_running': self.is_running,
            'connection_mode': self.connection_mode,
            'use_websocket': self.use_websocket,
            'redis_available': self.redis_cache.is_available(),
            'uptime_seconds': (datetime.now() - self.start_time).total_seconds() if self.start_time else 0,
            'statistics': self.data_handler.get_statistics()
        }


async def main():
    """Main entry point"""
    # Create streamer
    streamer = GoldStreamer()

    # Setup signal handlers for graceful shutdown
    loop = asyncio.get_event_loop()

    def signal_handler():
        logger.info("Shutdown signal received")
        asyncio.create_task(streamer.stop())

    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, signal_handler)

    try:
        # Run streamer
        await streamer.run()
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
    finally:
        await streamer.stop()


if __name__ == "__main__":
    # Configure logging
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="INFO"
    )

    # Run
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nStreamer stopped by user")

