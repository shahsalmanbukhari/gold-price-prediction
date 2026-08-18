"""Compatibility facade for the approved multi-horizon training pipeline.

Legacy 128-feature realtime artifacts are intentionally never loaded here.
New callers should use ``MultiHorizonTrainer`` and ``ModelBundleManager``.
"""

from src.candle_features import build_horizon_dataset
from src.baselines import should_promote
from src.database import get_session
from src.model_pipeline import ModelBundleManager, MultiHorizonTrainer


class RealtimeModelTrainer:
    def __init__(self, *_, **__):
        self.manager = ModelBundleManager()

    @staticmethod
    def prepare_features(data, horizon_minutes=3):
        return build_horizon_dataset(data, horizon_minutes)

    def train_model(self, model_name="linear_regression", use_realtime=False):
        session = get_session()
        try:
            manifest_path = MultiHorizonTrainer(session, self.manager).train_candidate(model_name)
            manifest = self.manager.validate(manifest_path)
            return {
                "candidate_manifest": str(manifest_path),
                "model_version": manifest["model_version"],
                "promoted": False,
                "message": "Candidate created but not promoted; use train_models.py for guarded promotion",
            }
        finally:
            session.close()

    def predict_next_price(self, *_, **__):
        raise RuntimeError(
            "Legacy single-step realtime inference is disabled. "
            "Use HorizonPredictionService with an approved production manifest."
        )
