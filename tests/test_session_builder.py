import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.candle_data_service import CandleDataService
from src.candle_features import build_horizon_dataset
from src.database import Base, GoldPriceCandle, TradingSession
from src.session_builder import build_sessions, persist_sessions, assert_targets_within_sessions


class SessionBuilderTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(bind=self.engine)()

    def tearDown(self):
        self.db.close()

    @staticmethod
    def frame():
        start = datetime(2026, 8, 14, 20, 0, tzinfo=timezone.utc)
        minutes = list(range(40)) + list(range(45, 85))
        return pd.DataFrame({
            "Date": [start + timedelta(minutes=value) for value in minutes],
            "Open": [4000 + value for value in minutes],
            "High": [4001 + value for value in minutes],
            "Low": [3999 + value for value in minutes],
            "Close": [4000.5 + value for value in minutes],
            "Volume": [None] * len(minutes),
        })

    def test_build_sessions_and_features(self):
        sessions = build_sessions(self.frame())
        self.assertEqual(2, len(sessions))
        self.assertEqual([1, 40], [sessions[0].session_minute.iloc[0], sessions[0].session_minute.iloc[-1]])
        self.assertEqual([0.0, 1.0], [sessions[0].session_minute_pct.iloc[0], sessions[0].session_minute_pct.iloc[-1]])
        self.assertEqual([39, 0], [sessions[0].session_remaining.iloc[0], sessions[0].session_remaining.iloc[-1]])
        self.assertTrue((sessions[0].session_count == 2).all())
        self.assertEqual(sessions[0].session_start.iloc[0], sessions[0].Date.iloc[0])
        self.assertEqual(sessions[1].session_end.iloc[0], sessions[1].Date.iloc[-1])

    def test_threshold_is_exclusive_and_input_is_sorted_deduplicated(self):
        frame = self.frame().iloc[:3]
        duplicate = frame.iloc[[1]].copy()
        duplicate["Close"] = 9999
        frame = pd.concat([frame.iloc[::-1], duplicate], ignore_index=True)
        self.assertEqual(1, len(build_sessions(frame)))
        self.assertEqual(3, len(build_sessions(frame)[0]))
        frame.loc[len(frame)] = frame.iloc[-1]
        frame.loc[len(frame) - 1, "Date"] = pd.Timestamp(frame.Date.max()) + pd.Timedelta(minutes=5)
        self.assertEqual(2, len(build_sessions(frame, gap_threshold_minutes=5)))

    def test_persistence_is_idempotent_and_service_filters_session(self):
        frame = self.frame()
        for row in frame.itertuples():
            self.db.add(GoldPriceCandle(
                candle_time=row.Date, symbol="XAUUSD", timeframe="1m", provider="histdata",
                open_price=Decimal(str(row.Open)), high_price=Decimal(str(row.High)),
                low_price=Decimal(str(row.Low)), close_price=Decimal(str(row.Close)),
            ))
        sessions = build_sessions(frame)
        self.assertEqual(2, persist_sessions(self.db, sessions, "histdata", "XAUUSD"))
        self.db.commit()
        self.assertEqual(0, persist_sessions(self.db, sessions, "histdata", "XAUUSD"))
        boundary = self.db.query(TradingSession).order_by(TradingSession.session_start).first()
        candles = CandleDataService(self.db).completed_1m(trading_session_id=boundary.id)
        self.assertEqual(40, len(candles))
        self.assertTrue(all(boundary.session_start <= candle.candle_time.replace(tzinfo=None) <= boundary.session_end for candle in candles))

    def test_training_targets_never_cross_strict_session(self):
        dataset = build_horizon_dataset(self.frame(), 3)
        assert_targets_within_sessions(dataset)
        self.assertTrue(dataset.session_id.eq(dataset.target_session_id).all())
        self.assertTrue((dataset.target_time - dataset.Date).eq(pd.Timedelta(minutes=3)).all())
        first_after_gap = pd.Timestamp("2026-08-14T20:45:00Z")
        self.assertFalse(((dataset.Date < first_after_gap) & (dataset.target_time >= first_after_gap)).any())

    def test_empty_and_invalid_inputs(self):
        self.assertEqual([], build_sessions(pd.DataFrame(columns=["Date"])))
        with self.assertRaises(ValueError):
            build_sessions(pd.DataFrame({"Close": [1]}))
        with self.assertRaises(ValueError):
            build_sessions(self.frame(), gap_threshold_minutes=1)


if __name__ == "__main__":
    unittest.main()
