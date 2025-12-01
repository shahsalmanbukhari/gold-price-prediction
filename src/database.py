"""
Database models and schema for Gold Price Prediction
"""

from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime, JSON, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os
from dotenv import load_dotenv

load_dotenv()

Base = declarative_base()


class Price(Base):
    """Historical and real-time price data"""
    __tablename__ = 'prices'

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    price_usd = Column(Float, nullable=False)
    volume = Column(Float)
    bid = Column(Float)
    ask = Column(Float)
    spread = Column(Float)
    source = Column(String(50), default='finnhub')
    created_at = Column(DateTime, default=datetime.utcnow)


class Feature(Base):
    """Engineered features for ML"""
    __tablename__ = 'features'

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    symbol = Column(String(20), nullable=False)

    # Price features
    close = Column(Float)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)

    # Technical indicators
    sma_7 = Column(Float)
    sma_14 = Column(Float)
    sma_30 = Column(Float)
    ema_7 = Column(Float)
    ema_14 = Column(Float)
    ema_30 = Column(Float)
    rsi_14 = Column(Float)
    macd = Column(Float)
    macd_signal = Column(Float)
    macd_histogram = Column(Float)
    bb_upper = Column(Float)
    bb_middle = Column(Float)
    bb_lower = Column(Float)
    bb_width = Column(Float)

    # Lag features (stored as JSON for flexibility)
    lag_features = Column(JSON)

    # Volatility
    volatility_7 = Column(Float)
    volatility_14 = Column(Float)
    volatility_30 = Column(Float)

    created_at = Column(DateTime, default=datetime.utcnow)


class Model(Base):
    """ML model metadata"""
    __tablename__ = 'models'

    id = Column(Integer, primary_key=True, autoincrement=True)
    model_name = Column(String(100), nullable=False)
    model_type = Column(String(50), nullable=False)  # lr, rf, xgb
    version = Column(String(20), nullable=False)

    # Training metadata
    trained_at = Column(DateTime, nullable=False)
    training_samples = Column(Integer)
    features_count = Column(Integer)

    # Performance metrics
    train_rmse = Column(Float)
    train_r2 = Column(Float)
    val_rmse = Column(Float)
    val_r2 = Column(Float)
    test_rmse = Column(Float)
    test_r2 = Column(Float)

    # Model parameters (stored as JSON)
    hyperparameters = Column(JSON)

    # Model file path
    model_path = Column(String(500))
    scaler_path = Column(String(500))

    # Status
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)


class Prediction(Base):
    """Real-time predictions"""
    __tablename__ = 'predictions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False, index=True)
    symbol = Column(String(20), nullable=False)

    # Prediction details
    current_price = Column(Float, nullable=False)
    predicted_price = Column(Float, nullable=False)
    prediction_horizon = Column(String(20))  # 1min, 5min, 1hour, 1day

    # Change metrics
    price_change = Column(Float)
    price_change_pct = Column(Float)

    # Model info
    model_id = Column(Integer)
    model_name = Column(String(100))
    model_type = Column(String(50))

    # Confidence
    confidence = Column(Float)
    upper_bound = Column(Float)
    lower_bound = Column(Float)

    # Actual outcome (filled later)
    actual_price = Column(Float)
    prediction_error = Column(Float)

    created_at = Column(DateTime, default=datetime.utcnow)


# Database connection and session management
def get_engine(database_url=None):
    """Create database engine"""
    if database_url is None:
        database_url = os.getenv('DATABASE_URL', 'sqlite:///data/gold_prediction.db')

    # If PostgreSQL URL but psycopg2 not installed, fall back to SQLite
    if database_url.startswith('postgresql'):
        try:
            import psycopg2
        except ImportError:
            print("⚠️  psycopg2 not installed. Falling back to SQLite.")
            print("   To use PostgreSQL, install: pip install psycopg2-binary")
            database_url = 'sqlite:///data/gold_prediction.db'

    # Create SQLite data directory if needed
    if database_url.startswith('sqlite'):
        os.makedirs('data', exist_ok=True)

    return create_engine(database_url, echo=False)


def init_db(database_url=None):
    """Initialize database schema"""
    engine = get_engine(database_url)
    Base.metadata.create_all(engine)
    print("✓ Database schema initialized")
    return engine


def get_session(engine=None):
    """Get database session"""
    if engine is None:
        engine = get_engine()
    Session = sessionmaker(bind=engine)
    return Session()


# Utility functions
def save_price(session, timestamp, symbol, price_usd, volume=None, bid=None, ask=None):
    """Save price data to database"""
    spread = (ask - bid) if (ask and bid) else None

    price = Price(
        timestamp=timestamp,
        symbol=symbol,
        price_usd=price_usd,
        volume=volume,
        bid=bid,
        ask=ask,
        spread=spread
    )

    session.add(price)
    session.commit()
    return price


def save_prediction(session, timestamp, symbol, current_price, predicted_price,
                   model_name, model_type, confidence=None, upper_bound=None,
                   lower_bound=None, horizon='1min'):
    """Save prediction to database"""
    price_change = predicted_price - current_price
    price_change_pct = (price_change / current_price) * 100 if current_price > 0 else 0

    prediction = Prediction(
        timestamp=timestamp,
        symbol=symbol,
        current_price=current_price,
        predicted_price=predicted_price,
        prediction_horizon=horizon,
        price_change=price_change,
        price_change_pct=price_change_pct,
        model_name=model_name,
        model_type=model_type,
        confidence=confidence,
        upper_bound=upper_bound,
        lower_bound=lower_bound
    )

    session.add(prediction)
    session.commit()
    return prediction


def get_latest_price(session, symbol='OANDA:XAU_USD', limit=1):
    """Get latest price from database"""
    return session.query(Price).filter(
        Price.symbol == symbol
    ).order_by(Price.timestamp.desc()).limit(limit).all()


def get_recent_predictions(session, symbol='OANDA:XAU_USD', limit=100):
    """Get recent predictions"""
    return session.query(Prediction).filter(
        Prediction.symbol == symbol
    ).order_by(Prediction.timestamp.desc()).limit(limit).all()


if __name__ == "__main__":
    # Test database initialization
    print("Initializing database...")
    engine = init_db()
    print("✓ Database ready!")

    # Test session
    session = get_session(engine)
    print(f"✓ Session created: {session}")
    session.close()

