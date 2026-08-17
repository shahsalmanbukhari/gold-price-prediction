"""
Settings and Configuration Management
Centralized configuration using Pydantic V2 for validation
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator
from typing import Optional, List, Dict, Any
import os
from pathlib import Path


class ProviderSettings(BaseSettings):
    """Provider-specific settings"""
    model_config = SettingsConfigDict(env_prefix="")

    enabled: bool = True
    api_key: Optional[str] = None
    timeout: int = 10
    retry_count: int = 3



class MetalpriceSettings(ProviderSettings):
    """MetalpriceAPI specific settings"""
    model_config = SettingsConfigDict(env_prefix="")

    base_currency: str = "XAU"
    polling_interval: int = 60
    rate_limit_delay: float = 2.0


class FinnhubSettings(ProviderSettings):
    """Finnhub specific settings"""
    model_config = SettingsConfigDict(env_prefix="")

    reconnect_delay: int = 30
    max_retries: int = 5
    ping_interval: int = 30
    polling_interval: int = 10


class DatabaseSettings(BaseSettings):
    """Database configuration"""
    model_config = SettingsConfigDict(env_prefix="DATABASE_")

    url: str = Field(default="sqlite:///data/gold_prediction.db", validation_alias="DATABASE_URL")
    echo: bool = Field(default=False, validation_alias="DB_ECHO")
    pool_size: int = Field(default=5, validation_alias="DB_POOL_SIZE")
    max_overflow: int = Field(default=10, validation_alias="DB_MAX_OVERFLOW")


class RedisSettings(BaseSettings):
    """Redis cache configuration"""
    model_config = SettingsConfigDict(env_prefix="REDIS_")

    host: str = Field(default="localhost", validation_alias="REDIS_HOST")
    port: int = Field(default=6379, validation_alias="REDIS_PORT")
    db: int = Field(default=0, validation_alias="REDIS_DB")
    password: Optional[str] = Field(default=None, validation_alias="REDIS_PASSWORD")
    enabled: bool = Field(default=True, validation_alias="REDIS_ENABLED")
    ttl: int = Field(default=60, validation_alias="REDIS_TTL")  # seconds


class StreamingSettings(BaseSettings):
    """Real-time streaming configuration"""
    model_config = SettingsConfigDict(env_prefix="STREAM_")

    websocket_reconnect_delay: int = Field(default=30, validation_alias="WEBSOCKET_RECONNECT_DELAY")
    polling_interval: int = Field(default=10, validation_alias="POLLING_INTERVAL")
    max_retries: int = Field(default=5, validation_alias="MAX_RETRIES")
    buffer_size: int = Field(default=1000, validation_alias="STREAM_BUFFER_SIZE")
    maximum_live_price_age_seconds: int = Field(
        default=180, validation_alias="MAXIMUM_LIVE_PRICE_AGE_SECONDS"
    )
    live_clock_skew_seconds: int = Field(default=120, validation_alias="LIVE_CLOCK_SKEW_SECONDS")
    prediction_actual_tolerance_seconds: int = Field(
        default=90, validation_alias="PREDICTION_ACTUAL_TOLERANCE_SECONDS"
    )
    prediction_candle_max_age_seconds: int = Field(
        default=259200, validation_alias="PREDICTION_CANDLE_MAX_AGE_SECONDS"
    )
    completed_candle_freshness_seconds: int = Field(
        default=180, validation_alias="COMPLETED_CANDLE_FRESHNESS_SECONDS"
    )
    prediction_interval_seconds: int = Field(default=60, validation_alias="PREDICTION_INTERVAL_SECONDS")
    prediction_evaluation_interval_seconds: int = Field(default=30, validation_alias="PREDICTION_EVALUATION_INTERVAL_SECONDS")
    prediction_horizons: str = Field(default="3,5,15,30,60,240", validation_alias="PREDICTION_HORIZONS")
    worker_heartbeat_seconds: int = Field(default=15, validation_alias="WORKER_HEARTBEAT_SECONDS")
    worker_unhealthy_after_seconds: int = Field(default=60, validation_alias="WORKER_UNHEALTHY_AFTER_SECONDS")


class AlertSettings(BaseSettings):
    """Persistent in-app and optional generic webhook notifications."""
    model_config = SettingsConfigDict(env_prefix="")

    enabled: bool = Field(default=True, validation_alias="ALERTS_ENABLED")
    webhook_url: Optional[str] = Field(default=None, validation_alias="ALERT_WEBHOOK_URL")
    timeout_seconds: int = Field(default=10, validation_alias="ALERT_TIMEOUT_SECONDS")
    max_retries: int = Field(default=3, validation_alias="ALERT_MAX_RETRIES")
    cooldown_seconds: int = Field(default=300, validation_alias="ALERT_COOLDOWN_SECONDS")
    min_test_improvement_pct: float = Field(default=0, validation_alias="ALERT_MIN_TEST_IMPROVEMENT_OVER_BASELINE_PCT")
    min_live_samples: int = Field(default=30, validation_alias="ALERT_MIN_LIVE_EVALUATED_SAMPLES")
    min_directional_accuracy_pct: float = Field(default=55, validation_alias="ALERT_MIN_LIVE_DIRECTIONAL_ACCURACY_PCT")
    min_absolute_return_pct: float = Field(default=.05, validation_alias="ALERT_MIN_ABSOLUTE_PREDICTED_RETURN_PCT")
    probation_webhooks_enabled: bool = Field(default=False, validation_alias="ALERT_PROBATION_WEBHOOKS_ENABLED")


class MLSettings(BaseSettings):
    """Machine learning configuration"""
    model_config = SettingsConfigDict(env_prefix="ML_")

    model_dir: str = Field(default="models", validation_alias="MODEL_DIR")
    default_model: str = Field(default="benchmark", validation_alias="DEFAULT_MODEL")
    candidate_algorithms: str = Field(default="linear_regression,random_forest,xgboost", validation_alias="CANDIDATE_ALGORITHMS")
    default_currency: str = Field(default="USD", validation_alias="DEFAULT_CURRENCY")
    feature_window: int = Field(default=30, validation_alias="FEATURE_WINDOW")
    prediction_horizon: str = Field(default="1d", validation_alias="PREDICTION_HORIZON")
    min_samples_for_retrain: int = Field(default=50, validation_alias="MIN_SAMPLES_FOR_RETRAIN")
    retrain_interval_hours: int = Field(default=24, validation_alias="RETRAIN_INTERVAL_HOURS")
    retrain_check_interval: int = Field(default=60, validation_alias="RETRAIN_CHECK_INTERVAL")
    training_max_candles: int = Field(default=250000, validation_alias="TRAINING_MAX_CANDLES")
    training_ratio: float = Field(default=0.70, validation_alias="TRAINING_RATIO")
    validation_ratio: float = Field(default=0.15, validation_alias="VALIDATION_RATIO")
    test_ratio: float = Field(default=0.15, validation_alias="TEST_RATIO")
    minimum_test_samples: int = Field(default=100, validation_alias="MINIMUM_TEST_SAMPLES")
    promotion_regression_tolerance: float = Field(
        default=0.02, validation_alias="PROMOTION_REGRESSION_TOLERANCE"
    )
    performance_minimum_samples: int = Field(
        default=50, validation_alias="PERFORMANCE_MINIMUM_SAMPLES"
    )


class DashboardSettings(BaseSettings):
    """Dashboard configuration"""
    model_config = SettingsConfigDict(env_prefix="DASHBOARD_")

    auto_refresh_interval: int = Field(default=2, validation_alias="AUTO_REFRESH_INTERVAL")  # seconds
    default_currency: str = Field(default="USD", validation_alias="DEFAULT_CURRENCY")
    chart_theme: str = Field(default="dark", validation_alias="CHART_THEME")
    show_confidence: bool = Field(default=True, validation_alias="SHOW_CONFIDENCE")
    websocket_port: int = Field(default=8765, validation_alias="WEBSOCKET_PORT")


class HistoricalDataSettings(BaseSettings):
    """Trusted server-side bulk import configuration."""
    model_config = SettingsConfigDict(
        env_prefix="HISTORICAL_DATA_", env_file=".env", env_file_encoding="utf-8",
        populate_by_name=True, extra="ignore",
    )

    allowed_import_root: Path = Field(
        default=Path("data/historical"),
        validation_alias="HISTORICAL_DATA_ALLOWED_IMPORT_ROOT",
    )
    import_directory: Path = Field(
        default=Path("data/historical/xauusd"),
        validation_alias="HISTORICAL_DATA_IMPORT_DIRECTORY",
    )
    batch_size: int = Field(default=10000, validation_alias="HISTORICAL_DATA_BATCH_SIZE")
    maximum_uncompressed_file_size: int = Field(
        default=2 * 1024 ** 3,
        validation_alias="HISTORICAL_DATA_MAXIMUM_UNCOMPRESSED_FILE_SIZE",
    )
    maximum_archive_uncompressed_size: int = Field(
        default=4 * 1024 ** 3,
        validation_alias="HISTORICAL_DATA_MAXIMUM_ARCHIVE_UNCOMPRESSED_SIZE",
    )
    maximum_compression_ratio: float = Field(
        default=200.0,
        validation_alias="HISTORICAL_DATA_MAXIMUM_COMPRESSION_RATIO",
    )
    maximum_archive_entries: int = Field(
        default=100,
        validation_alias="HISTORICAL_DATA_MAXIMUM_ARCHIVE_ENTRIES",
    )


class Settings(BaseSettings):
    """
    Main application settings
    Loads from environment variables and .env file
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # Environment
    environment: str = Field(default="development", validation_alias="ENVIRONMENT")
    debug: bool = Field(default=False, validation_alias="DEBUG")
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")

    # Provider settings
    default_provider: str = Field(default="gold_api", validation_alias="DEFAULT_PROVIDER")
    provider_fallback_enabled: bool = Field(default=True, validation_alias="PROVIDER_FALLBACK_ENABLED")

    # API Keys
    metalprice_api_key: Optional[str] = Field(default=None, validation_alias="METALPRICE_API_KEY")
    finnhub_api_key: Optional[str] = Field(default=None, validation_alias="FINNHUB_API_KEY")

    # Sub-settings
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    redis: RedisSettings = Field(default_factory=RedisSettings)
    streaming: StreamingSettings = Field(default_factory=StreamingSettings)
    ml: MLSettings = Field(default_factory=MLSettings)
    dashboard: DashboardSettings = Field(default_factory=DashboardSettings)
    historical_data: HistoricalDataSettings = Field(default_factory=HistoricalDataSettings)
    alerts: AlertSettings = Field(default_factory=AlertSettings)

    # Paths
    project_root: Path = Field(default_factory=lambda: Path(__file__).parent.parent)
    config_dir: Path = Field(default_factory=lambda: Path(__file__).parent)
    data_dir: Path = Field(default_factory=lambda: Path("data"))

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level"""
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if v.upper() not in valid_levels:
            raise ValueError(f"Invalid log level. Must be one of {valid_levels}")
        return v.upper()

    @field_validator("environment")
    @classmethod
    def validate_environment(cls, v: str) -> str:
        """Validate environment"""
        valid_envs = ["development", "staging", "production"]
        if v.lower() not in valid_envs:
            raise ValueError(f"Invalid environment. Must be one of {valid_envs}")
        return v.lower()

    def get_provider_config(self, provider_name: str) -> Dict[str, Any]:
        """Get configuration for specific provider"""
        configs = {
            'gold_api': {
                'enabled': True,
                'polling_interval': 60,
                'cache_seconds': 35,
                'timeout': 10,
                'retry_count': 3
            },
            'metalprice': {
                'api_key': self.metalprice_api_key,
                'enabled': True,
                'base_currency': 'XAU',
                'polling_interval': 60,
                'rate_limit_delay': 2.0,
                'timeout': 10
            },
            'finnhub': {
                'api_key': self.finnhub_api_key,
                'enabled': True,
                'reconnect_delay': self.streaming.websocket_reconnect_delay,
                'max_retries': self.streaming.max_retries,
                'ping_interval': 30,
                'polling_interval': self.streaming.polling_interval,
                'timeout': 10
            }
        }
        return configs.get(provider_name, {})

    def is_production(self) -> bool:
        """Check if running in production"""
        return self.environment == "production"

    def __repr__(self) -> str:
        return f"<Settings(env={self.environment}, provider={self.default_provider})>"


# Global settings instance
settings = Settings()


# Convenience functions
def get_settings() -> Settings:
    """Get global settings instance"""
    return settings


def reload_settings():
    """Reload settings from environment"""
    global settings
    settings = Settings()
    return settings


if __name__ == "__main__":
    # Test settings loading
    print("="*60)
    print("CONFIGURATION SETTINGS")
    print("="*60)

    settings = get_settings()

    print(f"\nEnvironment: {settings.environment}")
    print(f"Debug: {settings.debug}")
    print(f"Log Level: {settings.log_level}")

    print(f"\nDefault Provider: {settings.default_provider}")
    print(f"Fallback Enabled: {settings.provider_fallback_enabled}")

    print(f"\nDatabase URL: {settings.database.url}")
    print(f"Redis Host: {settings.redis.host}:{settings.redis.port}")

    print(f"\nModel Directory: {settings.ml.model_dir}")
    print(f"Default Model: {settings.ml.default_model}")

    print("\nProvider Configurations:")
    for provider in ['metalprice', 'finnhub']:
        config = settings.get_provider_config(provider)
        has_key = bool(config.get('api_key'))
        print(f"  {provider}: API Key {'✓' if has_key else '✗'}")

    print("\n" + "="*60)
