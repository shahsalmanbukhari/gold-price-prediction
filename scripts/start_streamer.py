"""
Start the real-time gold price streamer
Can be run as a background process
"""

import sys
import os
import asyncio

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from realtime.streamer import GoldStreamer, main
from loguru import logger


if __name__ == "__main__":
    print("="*60)
    print("STARTING GOLD PRICE STREAMER")
    print("="*60)
    print("\nPress Ctrl+C to stop\n")

    # Configure logging
    logger.remove()
    logger.add(
        sys.stderr,
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <level>{message}</level>",
        level="INFO"
    )

    # Optional: Log to file
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    logger.add(
        f"{log_dir}/streamer.log",
        rotation="500 MB",
        retention="10 days",
        level="DEBUG"
    )

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nStreamer stopped by user")
    except Exception as e:
        print(f"\n\n✗ Error: {e}")
        sys.exit(1)

