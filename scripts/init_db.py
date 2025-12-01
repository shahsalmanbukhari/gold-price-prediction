"""
Database initialization script
Creates all necessary tables and schema
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.database import init_db, get_session
from loguru import logger


def main():
    """Initialize database"""
    print("="*60)
    print("DATABASE INITIALIZATION")
    print("="*60)

    try:
        # Initialize schema
        print("\n1. Creating database schema...")
        engine = init_db()
        print("✓ Schema created successfully")

        # Test connection
        print("\n2. Testing connection...")
        session = get_session(engine)
        print("✓ Connection successful")
        session.close()

        print("\n" + "="*60)
        print("✅ DATABASE READY")
        print("="*60)
        print("\nTables created:")
        print("  - prices (historical and real-time price data)")
        print("  - features (engineered features for ML)")
        print("  - models (ML model metadata)")
        print("  - predictions (prediction history)")

        print("\nNext steps:")
        print("  1. Configure .env with FINNHUB_API_KEY")
        print("  2. Run streamer: python realtime/streamer.py")
        print("  3. Run dashboard: streamlit run app/streamlit_app.py")

        return True

    except Exception as e:
        print(f"\n✗ Error: {e}")
        logger.error(f"Database initialization failed: {e}")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)

