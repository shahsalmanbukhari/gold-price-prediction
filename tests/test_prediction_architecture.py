import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pandas as pd
import joblib
import numpy as np
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from realtime.providers.gold_api_provider import GoldApiProvider
from src.candle_features import FEATURE_COLUMNS, FEATURE_SCHEMA_VERSION, build_horizon_dataset, candles_to_frame
from src.candle_data_service import CandleDataService
from src.database import Base, GoldPriceCandle, HorizonPrediction, Price
from src.horizon_prediction_service import HorizonPredictionService
from src.live_price_service import LiveGoldPriceService, LivePriceUnavailable
from src.model_pipeline import (
    CandidateRejectedError, ModelBundleManager, MultiHorizonTrainer,
    chronological_split, regression_metrics,
)


class PredictionArchitectureTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.session = sessionmaker(bind=self.engine)()

    def tearDown(self):
        self.session.close()

    @staticmethod
    def frame(count=800, gap_at=None):
        start = datetime(2026, 1, 5, tzinfo=timezone.utc)
        rows = []
        for i in range(count):
            minute = i + (1 if gap_at is not None and i >= gap_at else 0)
            close = 4000 + i * .01 + ((i % 11) - 5) * .002
            rows.append({"Date": start + timedelta(minutes=minute), "Open": close-.01,
                         "High": close+.02, "Low": close-.02, "Close": close, "Volume": None})
        return pd.DataFrame(rows)

    def add_candles(self, frame):
        for row in frame.itertuples():
            self.session.add(GoldPriceCandle(
                candle_time=row.Date, symbol="XAUUSD", timeframe="1m", provider="histdata",
                open_price=Decimal(str(row.Open)), high_price=Decimal(str(row.High)),
                low_price=Decimal(str(row.Low)), close_price=Decimal(str(row.Close)),
            ))
        self.session.commit()

    def prediction(self, target, provider="gold_api", status="PENDING"):
        now = target - timedelta(minutes=3)
        row = HorizonPrediction(
            batch_id="batch", symbol="XAUUSD", timeframe="1m", provider=provider,
            algorithm_name="trained_multi_horizon", algorithm_version="trained_horizon_bundle_v1",
            model_name="linear_regression", model_version="v1", feature_schema_version=FEATURE_SCHEMA_VERSION,
            prediction_created_at=now, created_at=now, feature_data_until=now,
            target_at=target, horizon_minutes=3, horizon_label="Ultra-short term",
            current_price=4000, reference_price=Decimal("4000"), predicted_price=Decimal("4010"),
            predicted_return=Decimal("0.0025"), predicted_trend="up", baseline_price=Decimal("4000"),
            status=status, last_completed_candle_at=now, missing_period_count=0,
            actual_tolerance_seconds=90, direction_threshold=Decimal("0.0005"),
            direction_policy_version="direction_0.0005_v1",
        )
        self.session.add(row)
        self.session.commit()
        return row

    def test_exact_horizon_targets_and_gap_rejection(self):
        frame = self.frame()
        for horizon in (3, 5, 15, 30, 60, 240):
            dataset = build_horizon_dataset(frame, horizon)
            self.assertTrue((dataset.target_time - dataset.Date).eq(pd.Timedelta(minutes=horizon)).all())
        gapped = build_horizon_dataset(self.frame(gap_at=100), 3)
        forbidden = pd.Timestamp(datetime(2026, 1, 5, tzinfo=timezone.utc) + timedelta(minutes=99))
        self.assertNotIn(forbidden, set(gapped.Date))

    def test_split_is_chronological_purged_and_target_bounded(self):
        dataset = build_horizon_dataset(self.frame(6000), 240)
        train, validation, test = chronological_split(dataset)
        self.assertLess(train.Date.max(), validation.Date.min())
        self.assertLess(validation.Date.max(), test.Date.min())
        self.assertLessEqual(train.target_time.max(), train.Date.max() + timedelta(minutes=240))
        self.assertGreater(validation.Date.min() - train.Date.max(), timedelta(minutes=240))

    def test_five_hour_timestamp_offset_and_stale_are_rejected(self):
        provider = GoldApiProvider()
        data = {"price": 4000, "symbol": "XAU", "currency": "USD",
                "updatedAt": (datetime.now(timezone.utc) + timedelta(hours=5)).isoformat()}
        quote = provider._parse_quote(data, "XAU", "USD")
        service = LiveGoldPriceService(provider, session=self.session, maximum_age_seconds=180)
        provider.get_quote = AsyncMock(return_value=quote)
        with self.assertRaises(LivePriceUnavailable):
            import asyncio
            asyncio.run(service.refresh())

    def test_evaluation_tolerance_provider_and_formulas(self):
        target = datetime.now(timezone.utc) - timedelta(minutes=2)
        prediction = self.prediction(target)
        # Wrong provider and a matching quote outside tolerance must be ignored.
        self.session.add_all([
            Price(timestamp=target, ingested_at=target, symbol="XAUUSD", raw_symbol="XAU", provider="other",
                  source="live_api", price_usd=4020),
            Price(timestamp=target+timedelta(seconds=91), ingested_at=target+timedelta(seconds=91),
                  symbol="XAUUSD", raw_symbol="XAU", provider="gold_api", source="live_api", price_usd=4020),
            Price(timestamp=target, ingested_at=target, symbol="WRONG", raw_symbol="XAU", provider="gold_api",
                  source="live_api", price_usd=4020),
        ])
        self.session.commit()
        service = HorizonPredictionService.__new__(HorizonPredictionService)
        changed = service.evaluate_due(self.session, now=target+timedelta(seconds=92))
        self.assertEqual(changed, 1)
        self.session.refresh(prediction)
        self.assertEqual(prediction.status, "UNRESOLVABLE")
        self.assertIsNone(prediction.actual_price)

        target2 = target + timedelta(minutes=10)
        p2 = self.prediction(target2)
        self.session.add(Price(timestamp=target2+timedelta(seconds=30), ingested_at=target2+timedelta(seconds=30),
                               symbol="XAUUSD", raw_symbol="XAU", provider="gold_api",
                               source="live_api", price_usd=Decimal("4020")))
        self.session.commit()
        self.assertEqual(service.evaluate_due(self.session, now=target2+timedelta(seconds=31)), 1)
        self.session.refresh(p2)
        self.assertEqual(p2.status, "EVALUATED")
        self.assertEqual(p2.absolute_error, Decimal("10.000000"))
        self.assertEqual(p2.percentage_error, Decimal("0.250000000000"))
        self.assertEqual(p2.baseline_absolute_error, Decimal("20.000000"))
        self.assertEqual(p2.model_improvement_over_baseline, Decimal("10.000000"))
        self.assertEqual(p2.evaluation_delay_seconds, 30)
        self.assertTrue(p2.direction_correct)
        self.assertEqual(service.evaluate_due(self.session, now=target2+timedelta(seconds=60)), 0)

        # Exact-target quotes are eligible.
        target3 = target2 + timedelta(minutes=10)
        p3 = self.prediction(target3)
        self.session.add(Price(timestamp=target3, ingested_at=target3, symbol="XAUUSD", raw_symbol="XAU",
                               provider="gold_api", source="live_api", price_usd=Decimal("4010")))
        self.session.commit()
        self.assertEqual(service.evaluate_due(self.session, now=target3), 1)
        self.session.refresh(p3)
        self.assertEqual(p3.evaluation_delay_seconds, 0)

    def test_future_dated_actual_is_not_accepted(self):
        target = datetime.now(timezone.utc) - timedelta(minutes=2)
        prediction = self.prediction(target)
        self.session.add(Price(timestamp=target+timedelta(seconds=30), ingested_at=target-timedelta(hours=5),
                               symbol="XAUUSD", raw_symbol="XAU", provider="gold_api",
                               source="live_api", price_usd=Decimal("4020")))
        self.session.commit()
        service = HorizonPredictionService.__new__(HorizonPredictionService)
        service.evaluate_due(self.session, now=target+timedelta(seconds=91))
        self.session.refresh(prediction)
        self.assertEqual(prediction.status, "UNRESOLVABLE")

    def test_prediction_uniqueness(self):
        target = datetime.now(timezone.utc) + timedelta(minutes=3)
        first = self.prediction(target)
        duplicate = HorizonPrediction(**{
            column.name: getattr(first, column.name) for column in first.__table__.columns
            if column.name != "id"
        })
        self.session.add(duplicate)
        with self.assertRaises(IntegrityError):
            self.session.commit()
        self.session.rollback()

    def test_legacy_prediction_is_never_evaluated(self):
        target = datetime.now(timezone.utc) - timedelta(minutes=2)
        legacy = self.prediction(target, status="LEGACY")
        service = HorizonPredictionService.__new__(HorizonPredictionService)
        self.assertEqual(service.evaluate_due(self.session), 0)
        self.session.refresh(legacy)
        self.assertEqual(legacy.status, "LEGACY")


class BundleTests(unittest.TestCase):
    def test_candidate_manifest_promotion_and_legacy_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            engine = create_engine("sqlite:///:memory:")
            Base.metadata.create_all(engine)
            session = sessionmaker(bind=engine)()
            start = datetime.now(timezone.utc) - timedelta(minutes=5000)
            for i in range(5000):
                price = Decimal("4000") + Decimal(i) / Decimal("100") + Decimal((i % 17)-8)/Decimal("1000")
                session.add(GoldPriceCandle(candle_time=start+timedelta(minutes=i), symbol="XAUUSD",
                    timeframe="1m", provider="histdata", open_price=price, high_price=price+1,
                    low_price=price-1, close_price=price))
            session.commit()
            manager = ModelBundleManager(directory)
            candidate = MultiHorizonTrainer(session, manager).train_candidate("ridge_regression")
            manifest = manager.validate(candidate)
            self.assertEqual(manifest["feature_names"], FEATURE_COLUMNS)
            self.assertEqual(set(manifest["horizons"]), {"3", "5", "15", "30", "60", "240"})
            raw = candles_to_frame(CandleDataService(session).completed_1m())
            dataset = build_horizon_dataset(raw, 3)
            train, _, _ = chronological_split(dataset)
            scaler = joblib.load(candidate.parent / manifest["horizons"]["3"]["scaler_file"])
            np.testing.assert_allclose(scaler.mean_, train[FEATURE_COLUMNS].mean().to_numpy(), rtol=1e-10)
            # The compact synthetic fixture cannot span six calendar folds. Add
            # explicit accepted evidence so this test can exercise atomic bundle
            # promotion/inference; real candidate training may not fabricate it.
            approved = json.loads(candidate.read_text())
            for item in approved["horizons"].values():
                item["metrics"]["test"].update(
                    mae=.5, persistence_mae=1.0, directional_accuracy=60.0,
                    mae_improvement_over_persistence=.5,
                )
                item["walk_forward_validation"] = {
                    "folds": [{"fold_id": index} for index in range(1, 7)],
                    "stability": {"stable": True},
                }
            candidate.write_text(json.dumps(approved))
            promoted = manager.promote(candidate, initial=True)
            self.assertEqual(promoted["model_version"], manager.load_manifest()["model_version"])
            session.add(Price(timestamp=datetime.now(timezone.utc)-timedelta(seconds=2),
                              ingested_at=datetime.now(timezone.utc)-timedelta(seconds=1),
                              symbol="XAUUSD", raw_symbol="XAU", provider="gold_api",
                              source="live_api", price_usd=Decimal("4050")))
            session.commit()
            service = HorizonPredictionService.__new__(HorizonPredictionService)
            service.bundle_manager = manager
            service.last_unavailable_reason = None
            with patch("src.horizon_prediction_service.is_expected_market_closure", return_value=False):
                predictions = service.generate(session)
            self.assertEqual(len(predictions), 6)
            self.assertTrue(all(p.algorithm_name == "trained_multi_horizon" for p in predictions))
            self.assertTrue(all(p.model_version == promoted["model_version"] for p in predictions))
            # A later valid provider quote produces another persisted batch;
            # generation is not a one-time application-start action.
            session.add(Price(timestamp=datetime.now(timezone.utc), ingested_at=datetime.now(timezone.utc),
                              symbol="XAUUSD", raw_symbol="XAU", provider="gold_api",
                              source="live_api", price_usd=Decimal("4051")))
            session.commit()
            with patch("src.horizon_prediction_service.is_expected_market_closure", return_value=False):
                second_batch = service.generate(session)
            self.assertEqual(len(second_batch), 6)
            self.assertNotEqual(predictions[0].batch_id, second_batch[0].batch_id)
            self.assertEqual(session.query(HorizonPrediction).count(), 12)
            for item in promoted["horizons"].values():
                self.assertEqual(len(item["walk_forward_validation"]["folds"]), 6)
            # A legacy-shaped fake artifact cannot enter production.
            bad = json.loads(candidate.read_text())
            bad["feature_names"] = [f"legacy_{i}" for i in range(128)]
            bad_path = candidate.parent / "bad_manifest.json"
            bad_path.write_text(json.dumps(bad))
            with self.assertRaisesRegex(ValueError, "Ordered feature names"):
                manager.validate(bad_path)
            self.assertTrue(manager.production_manifest_path.exists())
            original_version = manager.load_manifest()["model_version"]
            rejected = json.loads(candidate.read_text())
            rejected["model_version"] = "deliberately-worse"
            rejected["horizons"]["3"]["metrics"]["test"]["mae"] = 1.1
            rejected["horizons"]["3"]["metrics"]["test"]["mae_improvement_over_persistence"] = -1
            rejected_path = candidate.parent / "rejected_manifest.json"
            rejected_path.write_text(json.dumps(rejected))
            with self.assertRaises(CandidateRejectedError) as rejection:
                manager.promote(rejected_path, initial=False)
            self.assertEqual(rejection.exception.reasons[0]["horizon"], 3)
            self.assertIn("candidate_mae", rejection.exception.reasons[0])
            self.assertTrue(any("persistence_mae" in reason for reason in rejection.exception.reasons))
            self.assertEqual(rejection.exception.candidate_path, str(candidate.parent))
            self.assertEqual(manager.load_manifest()["model_version"], original_version)
            session.close()

    def test_metric_baselines(self):
        actual = np.array([.01, -.02, .0])
        predicted = np.array([.005, -.01, .0])
        metrics = regression_metrics(actual, predicted, common_direction=1)
        self.assertAlmostEqual(metrics["persistence_mae"], np.mean(np.abs(actual)))
        self.assertAlmostEqual(
            metrics["mae_improvement_over_persistence"],
            metrics["persistence_mae"] - metrics["mae"],
        )


if __name__ == "__main__":
    unittest.main()
