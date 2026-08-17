"""Live quote orchestration with compatible presentation and bounded fallback."""

from datetime import datetime, timezone
from decimal import Decimal

from config.settings import get_settings
from src.database import Price, get_session, save_unique_price_from_response, latest_valid_live_price


class LivePriceUnavailable(RuntimeError):
    pass


class LiveGoldPriceService:
    def __init__(self, provider, session=None, maximum_age_seconds=None):
        self.provider = provider
        self.session = session or get_session()
        self.owns_session = session is None
        self.maximum_age_seconds = maximum_age_seconds or get_settings().streaming.maximum_live_price_age_seconds

    @staticmethod
    def _aware(value):
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)

    def latest(self):
        return latest_valid_live_price(self.session)

    def _is_recent(self, timestamp):
        age = (datetime.now(timezone.utc) - self._aware(timestamp)).total_seconds()
        return -get_settings().streaming.live_clock_skew_seconds <= age <= self.maximum_age_seconds

    async def refresh(self):
        quote = await self.provider.get_quote("XAU", "USD")
        if quote is None:
            raise LivePriceUnavailable("Live provider returned no quote")
        future_seconds = (self._aware(quote.timestamp) - datetime.now(timezone.utc)).total_seconds()
        if future_seconds > get_settings().streaming.live_clock_skew_seconds:
            raise LivePriceUnavailable("Live provider timestamp is beyond the allowed future clock skew")
        if not self._is_recent(quote.timestamp):
            raise LivePriceUnavailable("Live provider quote is older than the configured maximum age")
        row = save_unique_price_from_response(self.session, quote)
        self.session.commit()
        stored = row or self.latest()
        return stored, row is not None

    async def get_public(self):
        stale = False
        try:
            row, _ = await self.refresh()
        except Exception as exc:
            row = self.latest()
            if row is None or not self._is_recent(row.timestamp):
                raise LivePriceUnavailable("No sufficiently recent live gold price is available") from exc
            stale = True
        timestamp = self._aware(row.timestamp)
        metadata = row.provider_metadata or {}
        result = {
            "currency": metadata.get("currency", "USD"),
            "currencySymbol": metadata.get("currencySymbol", "$"),
            "exchangeRate": metadata.get("exchangeRate", 1),
            "name": metadata.get("name", "Gold"),
            "price": float(Decimal(str(row.price_usd))),
            "symbol": row.raw_symbol or "XAU",
            "updatedAt": timestamp.isoformat().replace("+00:00", "Z"),
            "updatedAtReadable": "cached live price" if stale else "a few seconds ago",
        }
        return result

    def close(self):
        if self.owns_session:
            self.session.close()
