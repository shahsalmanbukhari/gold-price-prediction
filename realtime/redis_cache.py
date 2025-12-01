"""
Redis cache handler for real-time tick storage and pub/sub
"""

import redis
import json
import os
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List
from loguru import logger
from dotenv import load_dotenv

load_dotenv()


class RedisCache:
    """
    Redis cache for real-time gold price data

    Features:
    - Latest tick storage
    - Pub/Sub for live updates
    - Time-series buffer
    """

    def __init__(self, host: Optional[str] = None, port: Optional[int] = None,
                 db: Optional[int] = None, password: Optional[str] = None):
        """
        Initialize Redis connection

        Args:
            host: Redis host
            port: Redis port
            db: Redis database number
            password: Redis password
        """
        self.host = host or os.getenv('REDIS_HOST', 'localhost')
        self.port = int(port or os.getenv('REDIS_PORT', 6379))
        self.db = int(db or os.getenv('REDIS_DB', 0))
        self.password = password or os.getenv('REDIS_PASSWORD', None)

        try:
            self.client = redis.Redis(
                host=self.host,
                port=self.port,
                db=self.db,
                password=self.password if self.password else None,
                decode_responses=True,
                socket_connect_timeout=5
            )

            # Test connection
            self.client.ping()
            logger.info(f"✓ Redis connected: {self.host}:{self.port}")

        except redis.ConnectionError as e:
            logger.warning(f"⚠ Redis connection failed: {e}")
            logger.warning("Running without Redis caching")
            self.client = None

    def is_available(self) -> bool:
        """Check if Redis is available"""
        return self.client is not None

    def set_latest_tick(self, symbol: str, tick: Dict[str, Any]) -> bool:
        """
        Store latest tick for a symbol

        Args:
            symbol: Trading symbol
            tick: Tick data dict

        Returns:
            Success boolean
        """
        if not self.is_available():
            return False

        try:
            # Convert datetime to ISO string for JSON serialization
            tick_copy = tick.copy()
            if isinstance(tick_copy.get('timestamp'), datetime):
                tick_copy['timestamp'] = tick_copy['timestamp'].isoformat()

            key = f"gold:latest:{symbol}"
            self.client.set(key, json.dumps(tick_copy))

            # Set expiration (5 minutes)
            self.client.expire(key, 300)

            return True

        except Exception as e:
            logger.error(f"Redis set error: {e}")
            return False

    def get_latest_tick(self, symbol: str) -> Optional[Dict[str, Any]]:
        """
        Get latest tick for a symbol

        Args:
            symbol: Trading symbol

        Returns:
            Tick dict or None
        """
        if not self.is_available():
            return None

        try:
            key = f"gold:latest:{symbol}"
            data = self.client.get(key)

            if data:
                tick = json.loads(data)
                # Convert ISO string back to datetime
                if 'timestamp' in tick:
                    tick['timestamp'] = datetime.fromisoformat(tick['timestamp'])
                return tick

            return None

        except Exception as e:
            logger.error(f"Redis get error: {e}")
            return None

    def publish_tick(self, channel: str, tick: Dict[str, Any]) -> bool:
        """
        Publish tick to a channel

        Args:
            channel: Pub/Sub channel name
            tick: Tick data

        Returns:
            Success boolean
        """
        if not self.is_available():
            return False

        try:
            tick_copy = tick.copy()
            if isinstance(tick_copy.get('timestamp'), datetime):
                tick_copy['timestamp'] = tick_copy['timestamp'].isoformat()

            self.client.publish(channel, json.dumps(tick_copy))
            return True

        except Exception as e:
            logger.error(f"Redis publish error: {e}")
            return False

    def subscribe_to_ticks(self, channel: str = 'gold.ticks'):
        """
        Subscribe to tick updates

        Args:
            channel: Pub/Sub channel

        Yields:
            Tick dicts
        """
        if not self.is_available():
            return

        try:
            pubsub = self.client.pubsub()
            pubsub.subscribe(channel)

            logger.info(f"✓ Subscribed to {channel}")

            for message in pubsub.listen():
                if message['type'] == 'message':
                    try:
                        tick = json.loads(message['data'])
                        if 'timestamp' in tick:
                            tick['timestamp'] = datetime.fromisoformat(tick['timestamp'])
                        yield tick
                    except json.JSONDecodeError:
                        continue

        except Exception as e:
            logger.error(f"Redis subscribe error: {e}")

    def add_to_buffer(self, symbol: str, tick: Dict[str, Any], max_size: int = 1000) -> bool:
        """
        Add tick to time-series buffer

        Args:
            symbol: Trading symbol
            tick: Tick data
            max_size: Maximum buffer size

        Returns:
            Success boolean
        """
        if not self.is_available():
            return False

        try:
            tick_copy = tick.copy()
            if isinstance(tick_copy.get('timestamp'), datetime):
                tick_copy['timestamp'] = tick_copy['timestamp'].isoformat()

            key = f"gold:buffer:{symbol}"

            # Add to list
            self.client.lpush(key, json.dumps(tick_copy))

            # Trim to max size
            self.client.ltrim(key, 0, max_size - 1)

            return True

        except Exception as e:
            logger.error(f"Redis buffer error: {e}")
            return False

    def get_buffer(self, symbol: str, limit: int = 100) -> List[Dict[str, Any]]:
        """
        Get recent ticks from buffer

        Args:
            symbol: Trading symbol
            limit: Number of ticks to retrieve

        Returns:
            List of tick dicts
        """
        if not self.is_available():
            return []

        try:
            key = f"gold:buffer:{symbol}"
            data = self.client.lrange(key, 0, limit - 1)

            ticks = []
            for item in data:
                tick = json.loads(item)
                if 'timestamp' in tick:
                    tick['timestamp'] = datetime.fromisoformat(tick['timestamp'])
                ticks.append(tick)

            return ticks

        except Exception as e:
            logger.error(f"Redis buffer get error: {e}")
            return []

    def set_prediction(self, symbol: str, prediction: Dict[str, Any]) -> bool:
        """
        Store latest prediction

        Args:
            symbol: Trading symbol
            prediction: Prediction data

        Returns:
            Success boolean
        """
        if not self.is_available():
            return False

        try:
            pred_copy = prediction.copy()
            if isinstance(pred_copy.get('timestamp'), datetime):
                pred_copy['timestamp'] = pred_copy['timestamp'].isoformat()

            key = f"gold:prediction:{symbol}"
            self.client.set(key, json.dumps(pred_copy))
            self.client.expire(key, 300)  # 5 min expiry

            return True

        except Exception as e:
            logger.error(f"Redis prediction set error: {e}")
            return False

    def get_prediction(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get latest prediction for a symbol"""
        if not self.is_available():
            return None

        try:
            key = f"gold:prediction:{symbol}"
            data = self.client.get(key)

            if data:
                pred = json.loads(data)
                if 'timestamp' in pred:
                    pred['timestamp'] = datetime.fromisoformat(pred['timestamp'])
                return pred

            return None

        except Exception as e:
            logger.error(f"Redis prediction get error: {e}")
            return None


# Singleton instance
_redis_cache = None

def get_redis_cache() -> RedisCache:
    """Get Redis cache singleton"""
    global _redis_cache
    if _redis_cache is None:
        _redis_cache = RedisCache()
    return _redis_cache


# Test
if __name__ == "__main__":
    cache = RedisCache()

    print(f"\nRedis Available: {cache.is_available()}")

    if cache.is_available():
        # Test set/get
        test_tick = {
            'timestamp': datetime.now(timezone.utc),
            'symbol': 'OANDA:XAU_USD',
            'price_usd': 2050.00,
            'volume': 100
        }

        print("\nTesting set/get...")
        cache.set_latest_tick('OANDA:XAU_USD', test_tick)
        retrieved = cache.get_latest_tick('OANDA:XAU_USD')
        print(f"✓ Retrieved: {retrieved}")

