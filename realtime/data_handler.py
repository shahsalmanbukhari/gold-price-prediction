"""
Data handler for cleaning, validating, and storing real-time ticks
"""

import asyncio
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from loguru import logger
from sqlalchemy.orm import Session

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import save_price, get_session
from realtime.redis_cache import get_redis_cache


class DataHandler:
    """
    Handles incoming tick data processing

    Responsibilities:
    - Validate tick data
    - Clean and normalize
    - Store in PostgreSQL
    - Cache in Redis
    - Publish to subscribers
    """

    def __init__(self, db_session: Optional[Session] = None):
        """
        Initialize data handler

        Args:
            db_session: Database session (optional, creates new if None)
        """
        self.db_session = db_session or get_session()
        self.redis_cache = get_redis_cache()

        # Statistics
        self.ticks_processed = 0
        self.ticks_stored = 0
        self.ticks_rejected = 0
        self.errors = 0

        logger.info("Data handler initialized")

    def validate_tick(self, tick: Dict[str, Any]) -> bool:
        """
        Validate tick data

        Args:
            tick: Raw tick data

        Returns:
            True if valid, False otherwise
        """
        try:
            # Required fields
            required_fields = ['timestamp', 'symbol', 'price_usd']
            for field in required_fields:
                if field not in tick:
                    logger.warning(f"Missing required field: {field}")
                    return False

            # Validate timestamp
            if not isinstance(tick['timestamp'], datetime):
                logger.warning("Invalid timestamp type")
                return False

            # Validate price
            price = float(tick['price_usd'])
            if price <= 0 or price > 10000:  # Sanity check for gold price
                logger.warning(f"Invalid price: {price}")
                return False

            # Validate symbol
            if not isinstance(tick['symbol'], str) or len(tick['symbol']) == 0:
                logger.warning("Invalid symbol")
                return False

            return True

        except (ValueError, TypeError) as e:
            logger.warning(f"Validation error: {e}")
            return False

    def clean_tick(self, tick: Dict[str, Any]) -> Dict[str, Any]:
        """
        Clean and normalize tick data

        Args:
            tick: Raw validated tick

        Returns:
            Cleaned tick
        """
        cleaned = {
            'timestamp': tick['timestamp'],
            'symbol': tick['symbol'].strip().upper(),
            'price_usd': float(tick['price_usd']),
            'volume': float(tick.get('volume', 0)),
            'bid': float(tick['bid']) if tick.get('bid') else None,
            'ask': float(tick['ask']) if tick.get('ask') else None,
            'source': tick.get('source', 'unknown')
        }

        return cleaned

    async def process_tick(self, tick: Dict[str, Any]) -> bool:
        """
        Process a single tick (validate, clean, store)

        Args:
            tick: Raw tick data

        Returns:
            Success boolean
        """
        self.ticks_processed += 1

        try:
            # Validate
            if not self.validate_tick(tick):
                self.ticks_rejected += 1
                return False

            # Clean
            cleaned_tick = self.clean_tick(tick)

            # Store in database (async operation)
            try:
                save_price(
                    self.db_session,
                    timestamp=cleaned_tick['timestamp'],
                    symbol=cleaned_tick['symbol'],
                    price_usd=cleaned_tick['price_usd'],
                    volume=cleaned_tick['volume'],
                    bid=cleaned_tick['bid'],
                    ask=cleaned_tick['ask']
                )
                self.ticks_stored += 1
            except Exception as e:
                logger.error(f"Database storage error: {e}")
                self.errors += 1

            # Cache in Redis
            if self.redis_cache.is_available():
                self.redis_cache.set_latest_tick(cleaned_tick['symbol'], cleaned_tick)
                self.redis_cache.add_to_buffer(cleaned_tick['symbol'], cleaned_tick)
                self.redis_cache.publish_tick('gold.ticks', cleaned_tick)

            return True

        except Exception as e:
            logger.error(f"Tick processing error: {e}")
            self.errors += 1
            return False

    async def process_batch(self, ticks: list) -> Dict[str, int]:
        """
        Process multiple ticks in batch

        Args:
            ticks: List of tick dicts

        Returns:
            Statistics dict
        """
        results = {
            'processed': 0,
            'stored': 0,
            'rejected': 0,
            'errors': 0
        }

        for tick in ticks:
            success = await self.process_tick(tick)
            results['processed'] += 1
            if success:
                results['stored'] += 1
            else:
                results['rejected'] += 1

        return results

    def get_statistics(self) -> Dict[str, int]:
        """Get processing statistics"""
        return {
            'ticks_processed': self.ticks_processed,
            'ticks_stored': self.ticks_stored,
            'ticks_rejected': self.ticks_rejected,
            'errors': self.errors,
            'success_rate': (self.ticks_stored / self.ticks_processed * 100) if self.ticks_processed > 0 else 0
        }

    def reset_statistics(self):
        """Reset processing statistics"""
        self.ticks_processed = 0
        self.ticks_stored = 0
        self.ticks_rejected = 0
        self.errors = 0
        logger.info("Statistics reset")

    def close(self):
        """Close database session"""
        if self.db_session:
            self.db_session.close()
            logger.info("Data handler closed")


# Test
async def test_handler():
    """Test data handler"""
    handler = DataHandler()

    # Test tick
    test_tick = {
        'timestamp': datetime.now(timezone.utc),
        'symbol': 'OANDA:XAU_USD',
        'price_usd': 2055.50,
        'volume': 100.5,
        'source': 'test'
    }

    print("\n=== Testing Data Handler ===")
    print(f"Test tick: {test_tick}")

    # Process
    success = await handler.process_tick(test_tick)
    print(f"✓ Processing success: {success}")

    # Statistics
    stats = handler.get_statistics()
    print(f"✓ Statistics: {stats}")

    # Cleanup
    handler.close()


if __name__ == "__main__":
    asyncio.run(test_handler())

