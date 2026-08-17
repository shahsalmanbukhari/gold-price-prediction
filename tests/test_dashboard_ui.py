import inspect
import unittest
from pathlib import Path
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import patch

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import dashboard_data
from app.ui.charts import comparison_figure, line
from app.ui.cards import badge
from app.health import compute_health
from config.settings import get_settings
from src.background_lifecycle import HeartbeatService
from src.database import Base, HorizonPrediction, PredictionDecision, ServiceHeartbeat


def prediction(model, version, target, predicted=101):
    created=target-timedelta(minutes=3)
    return HorizonPrediction(
        batch_id=f"{model}-{target.timestamp()}",symbol="XAUUSD",timeframe="1m",provider="gold_api",
        algorithm_name="trained_multi_horizon",algorithm_version="v1",model_name=model,model_version=version,
        feature_schema_version="candle_features_v1",prediction_created_at=created,created_at=created,
        feature_data_until=created,target_at=target,horizon_minutes=3,horizon_label="3m",current_price=100,
        reference_price=100,predicted_price=predicted,predicted_return=.01,baseline_price=100,
        predicted_trend="up",status="EVALUATED",latest_live_price_at=created,
        last_completed_candle_at=created,missing_period_count=0,actual_price=102,actual_at=target,
        actual_provider="gold_api",evaluation_delay_seconds=0,actual_tolerance_seconds=90,
        evaluator_version="bounded_live_quote_v1",absolute_error=abs(102-predicted),percentage_error=1,
        baseline_absolute_error=2,model_improvement_over_baseline=1,direction_correct=True,
        evaluated_at=target,direction_threshold=.0005,direction_policy_version="v1",
    )


class DashboardUITests(unittest.TestCase):
    def setUp(self):
        self.engine=create_engine("sqlite:///:memory:")
        Base.metadata.create_all(self.engine)
        self.Session=sessionmaker(bind=self.engine)
        self.session=self.Session()

    def tearDown(self): self.session.close()

    def factory(self): return self.Session()

    def test_every_page_uses_shared_header_and_footer(self):
        import app.pages as pages
        source=inspect.getsource(pages)
        for name in ("overview","live_forecasts","performance","non_accepted","models_training","historical_data","system_health"):
            body=inspect.getsource(getattr(pages,name))
            self.assertIn("_context(",body)
            self.assertIn("finish()",body)
        self.assertIn("render_app_header",inspect.getsource(__import__("app.ui.layout",fromlist=["x"])))

    def test_selector_is_read_only_and_has_stable_state_keys(self):
        from app.ui import header
        source=inspect.getsource(header)
        for key in ("selected_model_name","selected_model_version","comparison_model_name","comparison_model_version","selected_horizon","selected_date_range"):
            self.assertIn(key,source)
        for forbidden in ("promote(","train_candidate(","HorizonPredictionService", "session.commit"):
            self.assertNotIn(forbidden,source)

    def test_selected_model_filters_query(self):
        now=datetime.now(timezone.utc)
        self.session.add_all([prediction("linear","v1",now),prediction("xgboost","v2",now+timedelta(seconds=1))]);self.session.commit()
        with patch("app.dashboard_data.get_session",self.factory):
            frame=dashboard_data.predictions("linear","v1",3,now-timedelta(days=1),now+timedelta(days=1))
        self.assertEqual(["v1"],frame.model_version.unique().tolist())

    def test_common_timestamp_alignment_is_inner_join(self):
        now=datetime.now(timezone.utc)
        self.session.add_all([prediction("linear","v1",now),prediction("forest","v2",now),prediction("forest","v2",now+timedelta(minutes=1))]);self.session.commit()
        with patch("app.dashboard_data.get_session",self.factory):
            frame=dashboard_data.aligned_comparison("linear","v1","forest","v2",3,now-timedelta(days=1),now+timedelta(days=1))
        self.assertEqual(1,len(frame));self.assertEqual(pd.Timestamp(now),pd.Timestamp(frame.iloc[0].target_at).tz_localize("UTC"))

    def test_nonaccepted_reason_query_and_empty_state_data(self):
        now=datetime.now(timezone.utc)
        self.session.add(PredictionDecision(decision_at=now,symbol="XAUUSD",provider="gold_api",horizon_minutes=3,model_name="linear",model_version="v1",acceptance_status="SUPPRESSED",acceptance_reason_code="MODEL_IN_PROBATION",trust_status_at_decision="PROBATION"));self.session.commit()
        with patch("app.dashboard_data.get_session",self.factory):
            frame=dashboard_data.decisions("linear","v1",3,now-timedelta(days=1),now+timedelta(days=1),True)
            empty=dashboard_data.decisions("missing","none",3,now-timedelta(days=1),now+timedelta(days=1),True)
        self.assertEqual("MODEL_IN_PROBATION",frame.iloc[0].acceptance_reason_code);self.assertTrue(empty.empty)

    def test_mixed_type_chart_protection(self):
        frame=pd.DataFrame({"when":["2026-01-01","bad"],"value":["1.2","not numeric"]})
        self.assertIsNotNone(line(frame,"when","value"))
        aligned=pd.DataFrame({"target_at":[datetime.now(timezone.utc)],"actual_price":[100],"viewing_predicted_price":["101"],"comparison_predicted_price":[None],"baseline_price":[100]})
        self.assertIsNotNone(comparison_figure(aligned))

    def test_worker_down_and_model_badges_include_text(self):
        old=datetime.now(timezone.utc)-timedelta(hours=1)
        row=ServiceHeartbeat(service_name="worker",instance_id="x",started_at=old,last_heartbeat_at=old,status="RUNNING",version="v1")
        self.assertEqual("STOPPED",HeartbeatService.health(row))
        self.assertIn("REJECTED",badge("REJECTED"));self.assertIn("LEGACY",badge("LEGACY"))

    def test_no_misleading_accuracy_formula_or_ui_label(self):
        import app.pages as pages
        source=inspect.getsource(pages)
        self.assertNotIn("100 -",source)
        self.assertNotIn("accuracy_score",source)
        self.assertIn("Directional accuracy",source)

    def test_future_quote_is_never_fresh(self):
        now=datetime.now(timezone.utc)
        live=type("Live",(),{"timestamp":now+timedelta(hours=5)})()
        candle=type("Candle",(),{"candle_time":now-timedelta(minutes=1)})()
        heartbeat=type("Heartbeat",(),{"last_heartbeat_at":now,"status":"RUNNING","last_error":None})()
        result=compute_health(live,candle,heartbeat,get_settings(),now)
        self.assertEqual("INVALID_FUTURE_TIMESTAMP",result.live_quote_status)
        self.assertEqual("INVALID",result.overall_data_status)
        self.assertIsNone(result.quote_age_seconds)
        self.assertIn("5h ahead",result.live_detail)

    def test_stale_candle_produces_warning_not_no_warning(self):
        now=datetime(2026,8,17,23,0,tzinfo=timezone.utc)
        live=type("Live",(),{"timestamp":now})()
        candle=type("Candle",(),{"candle_time":now-timedelta(days=5)})()
        heartbeat=type("Heartbeat",(),{"last_heartbeat_at":now,"status":"RUNNING","last_error":None})()
        result=compute_health(live,candle,heartbeat,get_settings(),now)
        self.assertEqual("STALE_AFTER_REOPEN",result.candle_status)
        self.assertEqual("WARNING",result.overall_data_status)

    def test_compact_navigation_and_model_labels(self):
        from app.ui.header import compact_model_label
        from app.dashboard_data import ModelOption
        label=compact_model_label(ModelOption("adaptive_momentum", "20260816042512", 15, "BASELINE", "ignored"))
        self.assertEqual("Adaptive Momentum · Baseline · 15m",label)
        main=Path("app/main.py").read_text()
        self.assertIn('"Legacy Forecast"',main)
        self.assertNotIn("Legacy experimental model —",main)

    def test_overview_does_not_recompute_freshness(self):
        import app.pages as pages
        body=inspect.getsource(pages.overview)
        self.assertIn('health=context["health"]',body)
        self.assertNotIn('"Fresh" if',body)
        self.assertNotIn('"No warning"',body)


if __name__=="__main__": unittest.main()
