"""Canonical completed-candle queries for training and inference."""

from datetime import datetime, timezone
from src.database import GoldPriceCandle, TradingSession
from src.candle_features import candles_to_frame, detect_missing_minutes


class CandleDataService:
    def __init__(self, session):
        self.session = session

    def completed_1m(
        self, provider="histdata", symbol="XAUUSD", limit=None, end=None,
        session_start=None, session_end=None, trading_session_id=None,
    ):
        """Return canonical candles, optionally constrained to a persisted session."""
        if trading_session_id is not None:
            boundary = self.session.query(TradingSession).filter(
                TradingSession.id == trading_session_id,
                TradingSession.provider == provider,
                TradingSession.symbol == symbol,
            ).one_or_none()
            if boundary is None:
                return []
            session_start, session_end = boundary.session_start, boundary.session_end
            if session_start.tzinfo is None:
                session_start = session_start.replace(tzinfo=timezone.utc)
            if session_end.tzinfo is None:
                session_end = session_end.replace(tzinfo=timezone.utc)
        query = self.session.query(GoldPriceCandle).filter(
            GoldPriceCandle.provider == provider,
            GoldPriceCandle.symbol == symbol,
            GoldPriceCandle.timeframe == "1m",
        )
        if end is not None:
            query = query.filter(GoldPriceCandle.candle_time < end)
        if session_start is not None:
            query = query.filter(GoldPriceCandle.candle_time >= session_start)
        if session_end is not None:
            query = query.filter(GoldPriceCandle.candle_time <= session_end)
        query = query.order_by(GoldPriceCandle.candle_time.desc())
        if limit:
            query = query.limit(limit)
        return list(reversed(query.all()))

    def inference_frame(self, limit=300, provider="histdata"):
        frame = candles_to_frame(self.completed_1m(provider=provider, limit=limit))
        return frame, detect_missing_minutes(frame)
