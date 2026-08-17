import unittest
from datetime import datetime, timedelta, timezone

from src.provider_timestamps import parse_provider_timestamp, AmbiguousProviderTimestamp
from src.market_session import candle_context, is_expected_market_closure
from app.health import compute_health
from config.settings import get_settings


class ProviderTimestampTests(unittest.TestCase):
    def test_iso_z(self):
        self.assertEqual(parse_provider_timestamp("2026-08-17T01:16:31Z"), datetime(2026,8,17,1,16,31,tzinfo=timezone.utc))

    def test_positive_and_negative_offsets_and_day_boundary(self):
        self.assertEqual(parse_provider_timestamp("2026-08-17T06:16:31+05:00").hour,1)
        self.assertEqual(parse_provider_timestamp("2026-08-16T20:16:31-05:00").day,17)
        self.assertEqual(parse_provider_timestamp("2026-08-16T20:16:31-05:00").hour,1)

    def test_epoch_seconds_and_milliseconds(self):
        expected=datetime(2026,8,17,1,16,31,tzinfo=timezone.utc)
        self.assertEqual(parse_provider_timestamp(int(expected.timestamp())),expected)
        self.assertEqual(parse_provider_timestamp(int(expected.timestamp()*1000)),expected)

    def test_naive_rejected(self):
        with self.assertRaises(AmbiguousProviderTimestamp): parse_provider_timestamp("2026-08-17T01:16:31")
        with self.assertRaises(AmbiguousProviderTimestamp): parse_provider_timestamp(datetime(2026,8,17,1,16,31))

    def test_three_and_five_hour_regressions_are_real_instants(self):
        self.assertEqual(parse_provider_timestamp("2026-08-17T04:16:31+03:00").hour,1)
        self.assertEqual(parse_provider_timestamp("2026-08-17T06:16:31+05:00").hour,1)

    def test_future_rejected_by_health_and_small_skew_accepted(self):
        now=datetime(2026,8,17,23,0,tzinfo=timezone.utc)  # market open
        candle=type("C",(),{"candle_time":now-timedelta(minutes=1)})()
        hb=type("H",(),{"last_heartbeat_at":now,"status":"RUNNING","last_error":None})()
        future=type("L",(),{"timestamp":now+timedelta(hours=3)})()
        valid=type("L",(),{"timestamp":now+timedelta(seconds=30)})()
        self.assertEqual(compute_health(future,candle,hb,get_settings(),now).live_quote_status,"INVALID_FUTURE_TIMESTAMP")
        self.assertEqual(compute_health(valid,candle,hb,get_settings(),now).live_quote_status,"FRESH")


class MarketSessionTests(unittest.TestCase):
    def test_weekend_closure_retains_last_session_context(self):
        now=datetime(2026,8,16,12,0,tzinfo=timezone.utc)  # Sunday before open
        candle=datetime(2026,8,14,21,58,tzinfo=timezone.utc)
        self.assertTrue(is_expected_market_closure(now))
        status,detail,eligible=candle_context(candle,now,180)
        self.assertEqual(status,"MARKET_CLOSED"); self.assertIn("last market session",detail); self.assertFalse(eligible)

    def test_after_reopen_old_candle_is_stale_and_recent_is_current(self):
        now=datetime(2026,8,16,22,10,tzinfo=timezone.utc)
        old=datetime(2026,8,14,21,58,tzinfo=timezone.utc)
        recent=now-timedelta(minutes=2)
        self.assertEqual(candle_context(old,now,180)[0],"STALE_AFTER_REOPEN")
        self.assertFalse(candle_context(old,now,180)[2])
        self.assertEqual(candle_context(recent,now,180)[0],"CURRENT")
        self.assertTrue(candle_context(recent,now,180)[2])


if __name__ == "__main__": unittest.main()
