"""
Database models and schema for Gold Price Prediction
"""

from sqlalchemy import create_engine, Column, Integer, BigInteger, Float, Numeric, String, DateTime, JSON, Boolean, Text, Index, UniqueConstraint, ForeignKey, func, text
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta, timezone
import os
from dotenv import load_dotenv

load_dotenv()

Base = declarative_base()


class Price(Base):
    """Historical and real-time price data"""
    __tablename__ = 'prices'

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    symbol = Column(String(20), nullable=False, index=True)
    price_usd = Column(Float, nullable=False)

    # OHLC data
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    previous_close = Column(Float)

    # Volume and bid/ask
    volume = Column(Float)
    bid = Column(Float)
    ask = Column(Float)
    spread = Column(Float)

    # Provider information (enhanced for multi-provider support)
    provider = Column(String(50), nullable=False, index=True, default='finnhub')  # metalprice, finnhub
    source = Column(String(50), default='rest')  # rest, websocket, poll
    raw_symbol = Column(String(50))  # Provider-specific symbol (e.g., XAUUSD)

    # Provider-specific metadata
    provider_metadata = Column(JSON)  # Store provider-specific additional data

    provider_timestamp_raw = Column(String(100))
    ingested_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index(
            "uq_prices_live_provider_timestamp", "provider", "raw_symbol", "timestamp",
            unique=True, postgresql_where=text("source = 'live_api'"),
            sqlite_where=text("source = 'live_api'"),
        ),
    )


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
    trained_at = Column(DateTime(timezone=True), nullable=False)
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

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


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

    # Provider information
    provider_name = Column(String(50), index=True)  # Which provider data was used

    # Confidence
    confidence = Column(Float)
    upper_bound = Column(Float)
    lower_bound = Column(Float)

    # Actual outcome (filled later)
    actual_price = Column(Float)
    prediction_error = Column(Float)

    created_at = Column(DateTime, default=datetime.utcnow)


class ProviderStatus(Base):
    """Provider health and status tracking"""
    __tablename__ = 'provider_status'

    id = Column(Integer, primary_key=True, autoincrement=True)
    provider_name = Column(String(50), nullable=False, unique=True, index=True)

    # Status information
    is_active = Column(Boolean, default=True)
    is_healthy = Column(Boolean, default=True)
    status = Column(String(20), default='unknown')  # healthy, degraded, unavailable, unknown

    # Statistics
    total_requests = Column(Integer, default=0)
    successful_requests = Column(Integer, default=0)
    failed_requests = Column(Integer, default=0)

    # Timestamps
    last_success_at = Column(DateTime)
    last_failure_at = Column(DateTime)
    last_check_at = Column(DateTime)

    # Error tracking
    last_error_message = Column(String(500))
    consecutive_failures = Column(Integer, default=0)

    # Performance metrics
    avg_response_time = Column(Float)  # milliseconds
    uptime_percentage = Column(Float)  # last 24 hours

    # Configuration
    config = Column(JSON)  # Provider-specific configuration

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class HorizonPrediction(Base):
    """A live prediction that will be scored when its horizon elapses."""
    __tablename__ = 'horizon_predictions'

    id = Column(Integer, primary_key=True, autoincrement=True)
    batch_id = Column(String(36), nullable=False, index=True)
    symbol = Column(String(20), nullable=False, default="XAUUSD", index=True)
    timeframe = Column(String(10), nullable=False, default="1m")
    provider = Column(String(50), nullable=False, default="legacy_unknown", index=True)
    algorithm_name = Column(String(100), nullable=False, default="legacy_unknown", index=True)
    algorithm_version = Column(String(50), nullable=False, default="legacy-v1")
    feature_schema_version = Column(String(50), nullable=False, default="legacy_unknown")
    prediction_created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    feature_data_until = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    target_at = Column(DateTime(timezone=True), nullable=False, index=True)
    horizon_minutes = Column(Integer, nullable=False, index=True)
    horizon_label = Column(String(50), nullable=False)
    current_price = Column(Float, nullable=False)  # Legacy compatibility.
    reference_price = Column(Numeric(18, 6), nullable=False)
    predicted_price = Column(Numeric(18, 6), nullable=False)
    predicted_return = Column(Numeric(20, 12), nullable=False, default=0)
    baseline_price = Column(Numeric(18, 6), nullable=False)
    confidence = Column(Float)
    lower_bound = Column(Numeric(18, 6))
    upper_bound = Column(Numeric(18, 6))
    interval_method = Column(String(50))
    predicted_trend = Column(String(10))
    model_name = Column(String(100), nullable=False)
    model_version = Column(String(50), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="PENDING", index=True)
    latest_live_price_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    last_completed_candle_at = Column(DateTime(timezone=True), nullable=False)
    missing_period_count = Column(Integer, nullable=False, default=0)
    actual_price = Column(Numeric(18, 6))
    actual_at = Column(DateTime(timezone=True))
    actual_provider = Column(String(50))
    evaluation_delay_seconds = Column(Integer)
    actual_tolerance_seconds = Column(Integer, nullable=False, default=90)
    evaluator_version = Column(String(50))
    absolute_error = Column(Numeric(18, 6))
    percentage_error = Column(Numeric(20, 12))
    baseline_absolute_error = Column(Numeric(18, 6))
    model_improvement_over_baseline = Column(Numeric(18, 6))
    error_amount = Column(Float)
    error_pct = Column(Float)
    accuracy_score = Column(Float)
    actual_trend = Column(String(10))
    direction_correct = Column(Boolean)
    result_class = Column(String(20), index=True)  # accurate, partial, inaccurate
    evaluated_at = Column(DateTime(timezone=True))
    failure_reason = Column(Text)
    retry_count = Column(Integer, nullable=False, default=0)
    direction_threshold = Column(Numeric(20, 12), nullable=False, default=0.0005)
    direction_policy_version = Column(String(50), nullable=False, default="direction_v1")
    context = Column(JSON)

    __table_args__ = (
        UniqueConstraint(
            "symbol", "timeframe", "provider", "algorithm_name", "algorithm_version",
            "model_version", "feature_data_until", "latest_live_price_at", "horizon_minutes",
            name="uq_production_horizon_prediction",
        ),
    )


class RetrainingRun(Base):
    """Audit history and manual-request queue for background retraining."""
    __tablename__ = 'retraining_runs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    requested_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)
    started_at = Column(DateTime(timezone=True))
    completed_at = Column(DateTime(timezone=True))
    trigger = Column(String(30), nullable=False)  # manual, accuracy, outcomes, scheduled
    status = Column(String(20), nullable=False, default='pending', index=True)
    model_name = Column(String(100), nullable=False, default='linear_regression')
    previous_version = Column(String(50))
    new_version = Column(String(50))
    candidate_path = Column(String(500))
    production_changed = Column(Boolean)
    accuracy_before = Column(Float)
    accuracy_after = Column(Float)
    metrics = Column(JSON)
    error_analysis = Column(JSON)
    error_message = Column(Text)


class TrainingSchedulerState(Base):
    """Durable scheduler watermarks shared by all streamer processes."""
    __tablename__ = "training_scheduler_state"

    id = Column(Integer, primary_key=True)
    last_candle_id = Column(BigInteger, nullable=False, default=0)
    last_outcome_id = Column(BigInteger, nullable=False, default=0)
    last_successful_training_at = Column(DateTime(timezone=True))
    last_training_attempt_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class ServiceHeartbeat(Base):
    __tablename__ = "service_heartbeats"
    service_name = Column(String(100), primary_key=True)
    instance_id = Column(String(100), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=False)
    last_heartbeat_at = Column(DateTime(timezone=True), nullable=False, index=True)
    status = Column(String(20), nullable=False)
    last_live_quote_at = Column(DateTime(timezone=True))
    last_prediction_at = Column(DateTime(timezone=True))
    last_evaluation_at = Column(DateTime(timezone=True))
    last_training_at = Column(DateTime(timezone=True))
    last_error = Column(Text)
    version = Column(String(50), nullable=False)


class HorizonModelStatus(Base):
    __tablename__ = "horizon_model_status"
    horizon_minutes = Column(Integer, primary_key=True)
    model_version = Column(String(100), nullable=False, primary_key=True)
    algorithm = Column(String(100), nullable=False)
    trust_status = Column(String(20), nullable=False, default="PROBATION")
    offline_test_samples = Column(Integer, nullable=False, default=0)
    offline_improvement_pct = Column(Float)
    rolling_sample_count = Column(Integer, nullable=False, default=0)
    rolling_mae = Column(Float)
    rolling_baseline_mae = Column(Float)
    rolling_directional_accuracy_pct = Column(Float)
    alert_suppression_reason = Column(Text)
    last_prediction_at = Column(DateTime(timezone=True))
    next_target_at = Column(DateTime(timezone=True))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))


class NotificationDelivery(Base):
    __tablename__ = "notification_deliveries"
    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    event_type = Column(String(30), nullable=False, index=True)
    prediction_id = Column(Integer, ForeignKey("horizon_predictions.id"), nullable=False, index=True)
    channel = Column(String(30), nullable=False)
    status = Column(String(20), nullable=False, default="PENDING", index=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    next_attempt_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    sent_at = Column(DateTime(timezone=True))
    last_error = Column(Text)
    payload = Column(JSON, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    __table_args__ = (UniqueConstraint("event_type", "prediction_id", "channel", name="uq_notification_delivery"),)


class PredictionDecision(Base):
    """Immutable audit of forecast alert acceptance/suppression decisions."""
    __tablename__ = "prediction_decisions"
    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    prediction_id = Column(Integer, ForeignKey("horizon_predictions.id"), index=True)
    decision_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), index=True)
    symbol = Column(String(20), nullable=False, default="XAUUSD")
    provider = Column(String(50))
    horizon_minutes = Column(Integer, nullable=False, index=True)
    model_name = Column(String(100))
    model_version = Column(String(100), index=True)
    reference_price = Column(Numeric(18, 6))
    predicted_price = Column(Numeric(18, 6))
    predicted_direction = Column(String(10))
    acceptance_status = Column(String(20), nullable=False, index=True)
    acceptance_reason_code = Column(String(60), nullable=False, index=True)
    acceptance_reason_detail = Column(Text)
    trust_status_at_decision = Column(String(20), index=True)
    required_sample_count = Column(Integer)
    actual_sample_count = Column(Integer)
    required_directional_accuracy = Column(Float)
    actual_directional_accuracy = Column(Float)
    required_baseline_improvement = Column(Float)
    actual_baseline_improvement = Column(Float)
    required_prediction_magnitude = Column(Float)
    actual_prediction_magnitude = Column(Float)
    data_fresh = Column(Boolean)
    missing_period_count = Column(Integer)
    technical_context = Column(JSON)
    __table_args__ = (
        UniqueConstraint("prediction_id", name="uq_prediction_decision_prediction"),
        Index("idx_prediction_decisions_filters", "decision_at", "horizon_minutes", "model_version", "acceptance_status"),
    )


class GoldPriceCandle(Base):
    """Dedicated historical OHLC candle entity."""
    __tablename__ = "gold_price_candles"
    __table_args__ = (
        UniqueConstraint("provider", "symbol", "timeframe", "candle_time", name="uq_gold_price_candle"),
        Index("idx_gold_price_candles_lookup", "symbol", "timeframe", "candle_time"),
    )

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    candle_time = Column(DateTime(timezone=True), nullable=False)
    symbol = Column(String(20), nullable=False)
    timeframe = Column(String(10), nullable=False)
    open_price = Column(Numeric(18, 6), nullable=False)
    high_price = Column(Numeric(18, 6), nullable=False)
    low_price = Column(Numeric(18, 6), nullable=False)
    close_price = Column(Numeric(18, 6), nullable=False)
    volume = Column(Numeric(20, 6))
    provider = Column(String(50), nullable=False)
    source_file = Column(String(255))
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())


class HistoricalDataImport(Base):
    """Per-CSV audit entity for historical directory imports."""
    __tablename__ = "historical_data_imports"
    __table_args__ = (
        Index("idx_historical_import_lookup", "provider", "symbol", "timeframe", "source_zip"),
    )

    id = Column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True, autoincrement=True)
    provider = Column(String(50), nullable=False)
    symbol = Column(String(20), nullable=False)
    timeframe = Column(String(10), nullable=False)
    source_zip = Column(String(255), nullable=False)
    source_csv = Column(String(255))
    file_checksum = Column(String(128))
    status = Column(String(30), nullable=False)
    total_rows = Column(BigInteger, nullable=False, default=0, server_default="0")
    inserted_rows = Column(BigInteger, nullable=False, default=0, server_default="0")
    duplicate_rows = Column(BigInteger, nullable=False, default=0, server_default="0")
    invalid_rows = Column(BigInteger, nullable=False, default=0, server_default="0")
    error_message = Column(Text)
    started_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    completed_at = Column(DateTime(timezone=True))


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
def save_price(session, timestamp, symbol, price_usd, volume=None, bid=None, ask=None,
               provider='finnhub', source='rest', raw_symbol=None, metadata=None,
               open_price=None, high=None, low=None, previous_close=None):
    """
    Save price data to database

    Args:
        session: Database session
        timestamp: Price timestamp
        symbol: Standardized symbol (e.g., 'XAU')
        price_usd: Price in USD
        volume: Trading volume
        bid: Bid price
        ask: Ask price
        provider: Provider name (e.g., 'metalprice', 'finnhub')
        source: Source type (e.g., 'rest', 'websocket', 'poll')
        raw_symbol: Provider-specific symbol
        metadata: Additional provider metadata
        open_price: Open price
        high: High price
        low: Low price
        previous_close: Previous close price
    """
    spread = (ask - bid) if (ask and bid) else None

    price = Price(
        timestamp=timestamp,
        symbol=symbol,
        price_usd=price_usd,
        open=open_price,
        high=high,
        low=low,
        previous_close=previous_close,
        volume=volume,
        bid=bid,
        ask=ask,
        spread=spread,
        provider=provider,
        source=source,
        raw_symbol=raw_symbol,
        provider_metadata=metadata
    )

    session.add(price)

    return price


def save_price_from_response(session, response):
    """
    Save price from ProviderResponse object

    Args:
        session: Database session
        response: ProviderResponse object
    """
    return save_price(
        session=session,
        timestamp=response.timestamp,
        symbol='XAUUSD',
        price_usd=response.price_usd,
        volume=response.volume,
        bid=response.bid,
        ask=response.ask,
        provider=response.provider_name,
        source='live_api',
        raw_symbol=response.raw_symbol or response.symbol,
        metadata=response.metadata,
        open_price=response.open,
        high=response.high,
        low=response.low,
        previous_close=response.previous_close
    )


def save_unique_price_from_response(session, response):
    """Idempotently persist one live provider quote, returning the row or None."""
    from config.settings import get_settings
    timestamp = response.timestamp
    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
        raise ValueError("Rejected naive or ambiguous live provider timestamp")
    timestamp = timestamp.astimezone(timezone.utc)
    now = datetime.now(timezone.utc)
    age = (now - timestamp).total_seconds()
    settings = get_settings().streaming
    if age < -settings.live_clock_skew_seconds:
        raise ValueError("Rejected future-dated live quote")
    if age > settings.maximum_live_price_age_seconds:
        raise ValueError("Rejected stale live quote")
    metadata = dict(response.metadata or {})
    metadata.setdefault("parsedProviderTimestampUtc", timestamp.isoformat())
    metadata.setdefault("ingestedAtUtc", now.isoformat())
    values = {
        "timestamp": timestamp,
        "symbol": "XAUUSD",
        "raw_symbol": response.raw_symbol or response.symbol,
        "price_usd": response.price_usd,
        "volume": None, "bid": None, "ask": None, "spread": None,
        "open": None, "high": None, "low": None, "previous_close": None,
        "provider": response.provider_name,
        "source": "live_api",
        "provider_metadata": metadata,
        "provider_timestamp_raw": metadata.get("rawTimestamp") or timestamp.isoformat(),
        "ingested_at": now,
        "created_at": now,
    }
    dialect = session.bind.dialect.name
    if dialect == "postgresql":
        statement = postgresql_insert(Price).values(**values).on_conflict_do_nothing(
            index_elements=["provider", "raw_symbol", "timestamp"],
            index_where=text("source = 'live_api'"),
        ).returning(Price.id)
    elif dialect == "sqlite":
        statement = sqlite_insert(Price).values(**values).on_conflict_do_nothing(
            index_elements=["provider", "raw_symbol", "timestamp"],
            index_where=text("source = 'live_api'"),
        ).returning(Price.id)
    else:
        raise RuntimeError(f"Unsupported live-price database dialect: {dialect}")
    inserted_id = session.execute(statement).scalar_one_or_none()
    return session.get(Price, inserted_id) if inserted_id is not None else None


def latest_valid_live_price(session, symbol="XAUUSD", provider=None, now=None):
    """Latest operational quote, excluding persisted future/stale legacy rows."""
    from config.settings import get_settings
    now = now or datetime.now(timezone.utc)
    settings = get_settings().streaming
    query = session.query(Price).filter(
        Price.symbol == symbol, Price.source == "live_api",
        Price.timestamp >= now - timedelta(seconds=settings.maximum_live_price_age_seconds),
        Price.timestamp <= now + timedelta(seconds=settings.live_clock_skew_seconds),
    )
    if provider:
        query = query.filter(Price.provider == provider)
    return query.order_by(Price.timestamp.desc(), Price.id.desc()).first()


def update_provider_status(session, provider_name, is_success=True, error_message=None, response_time=None):
    """
    Update provider status tracking

    Args:
        session: Database session
        provider_name: Name of provider
        is_success: Whether the request was successful
        error_message: Error message if failed
        response_time: Response time in milliseconds
    """
    # Get or create provider status
    status = session.query(ProviderStatus).filter_by(provider_name=provider_name).first()

    if not status:
        status = ProviderStatus(provider_name=provider_name)
        session.add(status)

    # Update statistics (handle None values)
    status.total_requests = (status.total_requests or 0) + 1
    status.last_check_at = datetime.utcnow()

    if is_success:
        status.successful_requests = (status.successful_requests or 0) + 1
        status.last_success_at = datetime.utcnow()
        status.consecutive_failures = 0
        status.is_healthy = True
        status.status = 'healthy'
    else:
        status.failed_requests = (status.failed_requests or 0) + 1
        status.last_failure_at = datetime.utcnow()
        status.consecutive_failures = (status.consecutive_failures or 0) + 1
        status.last_error_message = error_message

        # Update health status based on consecutive failures
        if status.consecutive_failures >= 3:
            status.is_healthy = False
            status.status = 'unavailable'
        else:
            status.status = 'degraded'

    # Update response time (moving average)
    if response_time is not None:
        if status.avg_response_time is None:
            status.avg_response_time = response_time
        else:
            # Simple moving average
            status.avg_response_time = (status.avg_response_time * 0.8) + (response_time * 0.2)

    # Calculate uptime percentage
    if status.total_requests > 0:
        status.uptime_percentage = (status.successful_requests / status.total_requests) * 100

    status.updated_at = datetime.utcnow()

    return status


def get_provider_status(session, provider_name):
    """
    Get provider status

    Args:
        session: Database session
        provider_name: Name of provider

    Returns:
        ProviderStatus object or None
    """
    return session.query(ProviderStatus).filter_by(provider_name=provider_name).first()


def get_all_provider_stats(session):
    """
    Get statistics for all providers

    Args:
        session: Database session

    Returns:
        Dictionary of provider stats
    """
    providers = session.query(ProviderStatus).all()

    return {
        provider.provider_name: {
            'is_active': provider.is_active,
            'is_healthy': provider.is_healthy,
            'status': provider.status,
            'total_requests': provider.total_requests,
            'success_rate': (provider.successful_requests / provider.total_requests * 100)
                           if provider.total_requests > 0 else 0,
            'consecutive_failures': provider.consecutive_failures,
            'last_success': provider.last_success_at,
            'last_failure': provider.last_failure_at,
            'avg_response_time': provider.avg_response_time,
            'uptime_percentage': provider.uptime_percentage
        }
        for provider in providers
    }
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
