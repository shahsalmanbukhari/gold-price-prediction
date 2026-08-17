"""Canonical completed-candle queries for training and inference."""

from datetime import datetime
from sqlalchemy import and_

from src.database import GoldPriceCandle
from src.candle_features import candles_to_frame, detect_missing_minutes


class CandleDataService:
    def __init__(self, session):
        self.session = session

    def completed_1m(self, provider="histdata", symbol="XAUUSD", limit=None, end=None):
        query = self.session.query(GoldPriceCandle).filter(
            GoldPriceCandle.provider == provider,
            GoldPriceCandle.symbol == symbol,
            GoldPriceCandle.timeframe == "1m",
        )
        if end is not None:
            query = query.filter(GoldPriceCandle.candle_time < end)
        query = query.order_by(GoldPriceCandle.candle_time.desc())
        if limit:
            query = query.limit(limit)
        return list(reversed(query.all()))

    def inference_frame(self, limit=300, provider="histdata"):
        frame = candles_to_frame(self.completed_1m(provider=provider, limit=limit))
        return frame, detect_missing_minutes(frame)
