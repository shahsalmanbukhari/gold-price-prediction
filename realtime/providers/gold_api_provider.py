"""Provider for the free real-time API at https://api.gold-api.com."""

import asyncio
import os
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Optional
from decimal import Decimal, InvalidOperation

import aiohttp
import certifi
import ssl
from loguru import logger
from src.provider_timestamps import parse_provider_timestamp, timestamp_evidence

from .base_provider import (
    BaseProvider,
    HistoricalData,
    ProviderConnectionError,
    ProviderDataError,
    ProviderError,
    ProviderResponse,
    ProviderStatus,
)


class GoldApiProvider(BaseProvider):
    """Gold API client with a mandatory minimum 35-second request cache."""

    BASE_URL = "https://api.gold-api.com"
    MIN_CACHE_SECONDS = 35.0

    def __init__(self, api_key: Optional[str] = None, config: Optional[Dict[str, Any]] = None):
        super().__init__(api_key, config)
        self.session: Optional[aiohttp.ClientSession] = None
        self.cache_seconds = max(
            self.MIN_CACHE_SECONDS,
            float(self.config.get("cache_seconds", os.getenv("GOLD_API_CACHE_SECONDS", self.MIN_CACHE_SECONDS))),
        )
        self.timeout = float(self.config.get("timeout", 10))
        self.retry_count = max(1, int(self.config.get("retry_count", 3)))
        self.polling_interval = max(
            self.cache_seconds,
            float(self.config.get("polling_interval", os.getenv("GOLD_API_POLLING_INTERVAL", 60))),
        )
        self._cached_quote: Optional[ProviderResponse] = None
        self._cache_expires_at = 0.0
        self._last_request_at = 0.0
        self._request_lock = asyncio.Lock()

    @property
    def name(self) -> str:
        return "gold_api"

    @property
    def supports_streaming(self) -> bool:
        return False

    async def connect(self) -> bool:
        if self.session is None or self.session.closed:
            ssl_context = ssl.create_default_context(cafile=certifi.where())
            self.session = aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(ssl=ssl_context)
            )

        healthy = await self.health_check()
        self.is_connected = healthy
        self._status = ProviderStatus.HEALTHY if healthy else ProviderStatus.UNAVAILABLE
        return healthy

    async def disconnect(self):
        if self.session and not self.session.closed:
            await self.session.close()
        self.session = None
        self.is_connected = False

    async def _respect_request_interval(self):
        """Never send two outbound requests less than 35 seconds apart."""
        elapsed = time.monotonic() - self._last_request_at
        if self._last_request_at and elapsed < self.MIN_CACHE_SECONDS:
            await asyncio.sleep(self.MIN_CACHE_SECONDS - elapsed)
        self._last_request_at = time.monotonic()

    async def _request_json(self, symbol: str, currency: str) -> Dict[str, Any]:
        if self.session is None or self.session.closed:
            ssl_context = ssl.create_default_context(cafile=certifi.where())
            self.session = aiohttp.ClientSession(
                connector=aiohttp.TCPConnector(ssl=ssl_context)
            )

        url = f"{self.BASE_URL}/price/{symbol}/{currency}"
        last_error: Optional[Exception] = None

        for attempt in range(1, self.retry_count + 1):
            await self._respect_request_interval()
            request_started_at = datetime.now(timezone.utc)
            try:
                async with self.session.get(url, timeout=self.timeout) as response:
                    if response.status != 200:
                        body = await response.text()
                        raise ProviderError(f"Gold API returned HTTP {response.status}: {body[:200]}")
                    data = await response.json()
                    data["_requestStartedAt"] = request_started_at
                    data["_requestCompletedAt"] = datetime.now(timezone.utc)
                    return data
            except (aiohttp.ClientError, asyncio.TimeoutError, ProviderError) as exc:
                last_error = exc
                logger.warning(f"Gold API request attempt {attempt}/{self.retry_count} failed: {exc}")

        raise ProviderConnectionError(str(last_error or "Gold API request failed"))

    @staticmethod
    def _parse_timestamp(value: Any) -> datetime:
        return parse_provider_timestamp(value)

    def _parse_quote(self, data: Dict[str, Any], symbol: str, currency: str) -> ProviderResponse:
        try:
            price = Decimal(str(data["price"]))
            if price <= 0:
                raise ValueError("price must be positive")
            response_symbol = str(data.get("symbol", symbol)).upper()
            response_currency = str(data.get("currency", currency)).upper()
            timestamp = self._parse_timestamp(data.get("updatedAt"))
        except (KeyError, TypeError, ValueError) as exc:
            raise ProviderDataError(f"Invalid Gold API response: {exc}") from exc

        request_started = data.get("_requestStartedAt") or datetime.now(timezone.utc)
        request_completed = data.get("_requestCompletedAt") or datetime.now(timezone.utc)
        evidence = timestamp_evidence("updatedAt", data.get("updatedAt"), timestamp, self.name, request_started, request_completed)
        logger.info("Gold API timestamp evidence: {}", evidence)
        return ProviderResponse(
            timestamp=timestamp,
            symbol="XAUUSD",
            price_usd=price,
            provider_name=self.name,
            raw_symbol=response_symbol,
            source_type="live_api",
            metadata={
                "currency": response_currency,
                "currencySymbol": data.get("currencySymbol"),
                "exchangeRate": data.get("exchangeRate"),
                "name": data.get("name"),
                "providerSymbol": response_symbol,
                "rawTimestamp": data.get("updatedAt"),
                "rawTimestampField": "updatedAt",
                "parsedProviderTimestampUtc": timestamp.isoformat(),
                "requestStartedAt": request_started.isoformat(),
                "requestCompletedAt": request_completed.isoformat(),
            },
        )

    def _cached_response(self, stale: bool = False) -> Optional[ProviderResponse]:
        if self._cached_quote is None:
            return None
        metadata = dict(self._cached_quote.metadata or {})
        metadata["from_cache"] = True
        metadata["stale"] = stale
        return ProviderResponse(**{
            **self._cached_quote.__dict__,
            "metadata": metadata,
        })

    async def get_quote(self, symbol: str = "XAU", currency: str = "USD") -> Optional[ProviderResponse]:
        symbol, currency = symbol.upper(), currency.upper()
        now = time.monotonic()
        if self._cached_quote and now < self._cache_expires_at:
            return self._cached_response()

        async with self._request_lock:
            now = time.monotonic()
            if self._cached_quote and now < self._cache_expires_at:
                return self._cached_response()

            try:
                data = await self._request_json(symbol, currency)
                quote = self._parse_quote(data, symbol, currency)
                self._cached_quote = quote
                self._cache_expires_at = time.monotonic() + self.cache_seconds
                self.record_success()
                return quote
            except Exception as exc:
                self.record_error(exc)
                cached = self._cached_response(stale=True)
                if cached:
                    logger.warning("Gold API unavailable; returning the last cached quote")
                    return cached
                raise

    async def stream_prices(
        self,
        symbol: str = "XAU",
        on_price: Optional[Callable[[ProviderResponse], None]] = None,
        on_error: Optional[Callable[[Exception], None]] = None,
    ):
        while self.is_connected:
            try:
                quote = await self.get_quote(symbol)
                if quote and on_price:
                    result = on_price(quote)
                    if asyncio.iscoroutine(result):
                        await result
            except Exception as exc:
                if on_error:
                    result = on_error(exc)
                    if asyncio.iscoroutine(result):
                        await result
            await asyncio.sleep(self.polling_interval)

    async def get_historical(
        self,
        symbol: str = "XAU",
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        interval: str = "1d",
        limit: int = 100,
    ) -> Optional[HistoricalData]:
        logger.info("Gold API real-time provider does not supply historical data")
        return None

    async def health_check(self) -> bool:
        try:
            return await self.get_quote("XAU", "USD") is not None
        except Exception as exc:
            logger.warning(f"Gold API health check failed: {exc}")
            return False
