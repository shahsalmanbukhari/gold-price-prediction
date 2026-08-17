"""Tests for Gold API caching, parsing, fallback, and unique persistence."""

import unittest
from decimal import Decimal
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from realtime.providers.gold_api_provider import GoldApiProvider
from src.database import Base, GoldPriceCandle, HorizonPrediction, Price, save_unique_price_from_response
from src.live_price_service import LiveGoldPriceService, LivePriceUnavailable
from src.candle_data_service import CandleDataService
from src.candle_features import FEATURE_COLUMNS, build_features, candles_to_frame, detect_missing_minutes
from src.realtime_trainer import RealtimeModelTrainer
from src.horizon_prediction_service import HorizonPredictionService


API_RESPONSE = {
    "currency": "USD",
    "currencySymbol": "$",
    "exchangeRate": 1.0,
    "name": "Gold",
    "price": 4377.600098,
    "symbol": "XAU",
    "updatedAt": "2026-08-15T22:41:27Z",
    "updatedAtReadable": "a few seconds ago",
}


class GoldApiProviderTests(unittest.IsolatedAsyncioTestCase):
    async def test_minimum_cache_and_cached_result(self):
        provider = GoldApiProvider(config={"cache_seconds": 1})
        provider._request_json = AsyncMock(return_value=API_RESPONSE)

        first = await provider.get_quote()
        second = await provider.get_quote()

        self.assertEqual(provider.cache_seconds, 35)
        self.assertEqual(first.price_usd, Decimal("4377.600098"))
        self.assertEqual(first.symbol, "XAUUSD")
        self.assertEqual(first.raw_symbol, "XAU")
        self.assertEqual(first.timestamp, datetime(2026, 8, 15, 22, 41, 27, tzinfo=timezone.utc))
        self.assertEqual(first.metadata["providerSymbol"], "XAU")
        self.assertEqual(second.timestamp, first.timestamp)
        self.assertTrue(second.metadata["from_cache"])
        provider._request_json.assert_awaited_once()

    async def test_failure_returns_stale_cached_quote(self):
        provider = GoldApiProvider()
        provider._request_json = AsyncMock(return_value=API_RESPONSE)
        first = await provider.get_quote()
        provider._cache_expires_at = 0
        provider._request_json = AsyncMock(side_effect=RuntimeError("offline"))

        fallback = await provider.get_quote()

        self.assertEqual(fallback.price_usd, first.price_usd)
        self.assertTrue(fallback.metadata["from_cache"])
        self.assertTrue(fallback.metadata["stale"])

    def test_duplicate_price_is_not_stored(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        session = sessionmaker(bind=engine)()
        provider = GoldApiProvider()
        quote = provider._parse_quote(
            dict(API_RESPONSE, updatedAt=datetime.now(timezone.utc).isoformat()), "XAU", "USD"
        )

        self.assertIsNotNone(save_unique_price_from_response(session, quote))
        session.commit()
        self.assertIsNone(save_unique_price_from_response(session, quote))
        session.commit()
        self.assertEqual(session.query(Price).count(), 1)
        row = session.query(Price).one()
        self.assertEqual(row.symbol, "XAUUSD")
        self.assertEqual(row.raw_symbol, "XAU")
        self.assertEqual(row.source, "live_api")
        self.assertIsNone(row.open)
        self.assertEqual(session.query(GoldPriceCandle).count(), 0)

    async def test_public_response_and_recent_cache_fallback(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        session = sessionmaker(bind=engine)()
        data = dict(API_RESPONSE, updatedAt=datetime.now(timezone.utc).isoformat())
        provider = GoldApiProvider()
        provider.get_quote = AsyncMock(return_value=provider._parse_quote(data, "XAU", "USD"))
        service = LiveGoldPriceService(provider, session=session, maximum_age_seconds=60)
        response = await service.get_public()
        self.assertEqual(set(response), {
            "currency", "currencySymbol", "exchangeRate", "name", "price",
            "symbol", "updatedAt", "updatedAtReadable",
        })
        self.assertEqual(response["symbol"], "XAU")
        provider.get_quote = AsyncMock(side_effect=RuntimeError("offline"))
        cached = await service.get_public()
        self.assertEqual(cached["updatedAtReadable"], "cached live price")

    async def test_stale_database_fallback_is_rejected(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        session = sessionmaker(bind=engine)()
        session.add(Price(
            timestamp=datetime.now(timezone.utc) - timedelta(minutes=10), symbol="XAUUSD",
            raw_symbol="XAU", price_usd=Decimal("4377.600098"), provider="gold_api",
            source="live_api", provider_metadata={"currency": "USD"},
        ))
        session.commit()
        provider = GoldApiProvider()
        provider.get_quote = AsyncMock(side_effect=RuntimeError("offline"))
        with self.assertRaises(LivePriceUnavailable):
            await LiveGoldPriceService(provider, session=session, maximum_age_seconds=60).get_public()

    def test_production_prediction_does_not_fall_back_to_adaptive_momentum(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        session = sessionmaker(bind=engine)()
        start = datetime.now(timezone.utc) - timedelta(hours=6)
        for minute in range(40):
            price = Decimal("4300") + Decimal(minute) / Decimal("5")
            session.add(GoldPriceCandle(
                candle_time=start + timedelta(minutes=minute), symbol="XAUUSD", timeframe="1m",
                open_price=price, high_price=price + 1, low_price=price - 1,
                close_price=price, volume=None, provider="histdata",
            ))
        latest_live_time = datetime.now(timezone.utc) - timedelta(seconds=5)
        session.add(Price(timestamp=latest_live_time, symbol="XAUUSD", raw_symbol="XAU",
                          price_usd=Decimal("4310"), provider="gold_api", source="live_api"))
        session.commit()
        service = HorizonPredictionService.__new__(HorizonPredictionService)

        generated = service.generate(session)
        self.assertEqual(generated, [])
        self.assertIn("No approved trained model", service.last_unavailable_reason)

    def test_training_and_inference_share_features_and_detect_gaps(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(engine)
        session = sessionmaker(bind=engine)()
        start = datetime.now(timezone.utc) - timedelta(hours=2)
        for minute in list(range(35)) + [36]:
            price = Decimal("4300") + Decimal(minute)
            session.add(GoldPriceCandle(
                candle_time=start + timedelta(minutes=minute), symbol="XAUUSD", timeframe="1m",
                open_price=price, high_price=price, low_price=price, close_price=price,
                provider="histdata",
            ))
        session.commit()
        candles = CandleDataService(session).completed_1m()
        frame = candles_to_frame(candles)
        self.assertEqual(len(detect_missing_minutes(frame).missing_periods), 1)
        training = RealtimeModelTrainer().prepare_features(frame, 3)
        inference = build_features(frame, include_target=False)
        self.assertEqual([c for c in FEATURE_COLUMNS if c in training], FEATURE_COLUMNS)
        self.assertEqual([c for c in FEATURE_COLUMNS if c in inference], FEATURE_COLUMNS)
        self.assertEqual(session.query(Price).count(), 0)


if __name__ == "__main__":
    unittest.main()
