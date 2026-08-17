"""
Base Provider Interface - Abstract class for all market data providers
All providers must implement this interface for consistent behavior
"""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List, Callable
from decimal import Decimal
from datetime import datetime, timezone
from dataclasses import dataclass
from enum import Enum
import asyncio


class ProviderStatus(Enum):
    """Provider health status"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class ProviderError(Exception):
    """Base exception for provider errors"""
    pass


class ProviderConnectionError(ProviderError):
    """Connection related errors"""
    pass


class ProviderAuthError(ProviderError):
    """Authentication errors"""
    pass


class ProviderRateLimitError(ProviderError):
    """Rate limit exceeded"""
    pass


class ProviderDataError(ProviderError):
    """Data format or validation errors"""
    pass


@dataclass
class ProviderResponse:
    """
    Standardized response format from all providers
    Ensures consistent data structure across different sources
    """
    timestamp: datetime
    symbol: str  # Normalized symbol (e.g., 'XAU')
    price_usd: Decimal

    # Optional fields
    volume: Optional[float] = None
    bid: Optional[float] = None
    ask: Optional[float] = None
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    previous_close: Optional[float] = None

    # Provider metadata
    provider_name: str = None
    raw_symbol: Optional[str] = None  # Original provider-specific symbol
    source_type: Optional[str] = None  # 'websocket', 'rest', 'poll'

    # Additional data
    metadata: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database storage"""
        return {
            'timestamp': self.timestamp,
            'symbol': self.symbol,
            # Redis/JSON transport uses a JSON number; Decimal remains the
            # application/persistence representation up to this boundary.
            'price_usd': float(self.price_usd),
            'volume': self.volume,
            'bid': self.bid,
            'ask': self.ask,
            'open': self.open,
            'high': self.high,
            'low': self.low,
            'previous_close': self.previous_close,
            'provider_name': self.provider_name,
            'raw_symbol': self.raw_symbol,
            'source_type': self.source_type,
            'metadata': self.metadata
        }


@dataclass
class HistoricalData:
    """Standardized historical/candle data"""
    symbol: str
    timestamps: List[datetime]
    open: List[float]
    high: List[float]
    low: List[float]
    close: List[float]
    volume: Optional[List[float]] = None
    provider_name: str = None


class BaseProvider(ABC):
    """
    Abstract base class for all market data providers

    All providers must implement:
    - connect(): Establish connection to provider
    - disconnect(): Clean shutdown
    - get_quote(): Get current price (REST/polling)
    - stream_prices(): Real-time streaming (if supported)
    - get_historical(): Historical OHLC data
    - health_check(): Provider availability check
    """

    def __init__(self, api_key: Optional[str] = None, config: Optional[Dict[str, Any]] = None):
        """
        Initialize provider

        Args:
            api_key: Provider API key
            config: Additional configuration parameters
        """
        self.api_key = api_key
        self.config = config or {}
        self.is_connected = False
        self.last_error = None
        self.error_count = 0
        self.success_count = 0
        self._status = ProviderStatus.UNKNOWN

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider name (e.g., 'metalprice', 'finnhub')"""
        pass

    @property
    @abstractmethod
    def supports_streaming(self) -> bool:
        """Whether provider supports WebSocket/streaming"""
        pass

    @property
    def status(self) -> ProviderStatus:
        """Current provider health status"""
        return self._status

    @abstractmethod
    async def connect(self) -> bool:
        """
        Establish connection to provider

        Returns:
            Success boolean
        """
        pass

    @abstractmethod
    async def disconnect(self):
        """Close connection and cleanup"""
        pass

    @abstractmethod
    async def get_quote(self, symbol: str = 'XAU', currency: str = 'USD') -> Optional[ProviderResponse]:
        """
        Get current quote/price (REST API or polling)

        Args:
            symbol: Trading symbol (normalized, e.g., 'XAU')
            currency: Target currency (default: 'USD')

        Returns:
            ProviderResponse or None on error
        """
        pass

    @abstractmethod
    async def stream_prices(
        self,
        symbol: str = 'XAU',
        on_price: Optional[Callable[[ProviderResponse], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None
    ):
        """
        Stream real-time prices (WebSocket or polling loop)

        Args:
            symbol: Trading symbol
            on_price: Callback for each price update
            on_error: Callback for errors
        """
        pass

    @abstractmethod
    async def get_historical(
        self,
        symbol: str = 'XAU',
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        interval: str = '1d',
        limit: int = 100
    ) -> Optional[HistoricalData]:
        """
        Get historical OHLC data

        Args:
            symbol: Trading symbol
            start_date: Start date (optional)
            end_date: End date (optional)
            interval: Time interval ('1m', '5m', '1h', '1d', etc.)
            limit: Maximum number of records

        Returns:
            HistoricalData or None on error
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check provider availability and health

        Returns:
            True if healthy, False otherwise
        """
        pass

    # Utility methods (common implementation)

    def normalize_symbol(self, symbol: str) -> str:
        """
        Normalize symbol to provider-specific format
        Override in subclass if needed

        Args:
            symbol: Standard symbol (e.g., 'XAU')

        Returns:
            Provider-specific symbol
        """
        return symbol

    def standardize_symbol(self, provider_symbol: str) -> str:
        """
        Convert provider-specific symbol to standard format
        Override in subclass if needed

        Args:
            provider_symbol: Provider's symbol format

        Returns:
            Standard symbol (e.g., 'XAU')
        """
        return provider_symbol

    def record_success(self):
        """Record successful operation"""
        self.success_count += 1
        self.last_error = None
        self._status = ProviderStatus.HEALTHY

    def record_error(self, error: Exception):
        """Record error"""
        self.error_count += 1
        self.last_error = error

        # Update status based on error type
        if isinstance(error, (ProviderConnectionError, ProviderAuthError)):
            self._status = ProviderStatus.UNAVAILABLE
        else:
            self._status = ProviderStatus.DEGRADED

    def get_stats(self) -> Dict[str, Any]:
        """Get provider statistics"""
        return {
            'name': self.name,
            'status': self.status.value,
            'is_connected': self.is_connected,
            'success_count': self.success_count,
            'error_count': self.error_count,
            'last_error': str(self.last_error) if self.last_error else None,
            'supports_streaming': self.supports_streaming
        }

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(name={self.name}, status={self.status.value})>"
