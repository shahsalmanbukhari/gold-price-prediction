"""
Real-time ML prediction engine
Makes live predictions on streaming gold price data
"""

import os
import sys
import joblib
import numpy as np
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Tuple
from loguru import logger

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.realtime_features import RealtimeFeatureEngine
from src.database import save_prediction, get_session
from realtime.redis_cache import get_redis_cache


class RealtimePredictor:
    """
    Real-time prediction engine

    Features:
    - Load trained ML models
    - Generate features from live data
    - Make predictions with confidence bounds
    - Cache predictions in Redis
    - Store predictions in database
    """

    def __init__(self, model_dir: str = 'models'):
        """
        Initialize predictor

        Args:
            model_dir: Directory containing trained models
        """
        self.model_dir = model_dir
        self.feature_engine = RealtimeFeatureEngine()
        self.redis_cache = get_redis_cache()
        self.db_session = get_session()

        # Models
        self.models = {}
        self.scalers = {}
        self.active_model = None

        # Statistics
        self.predictions_made = 0

        logger.info("Realtime predictor initialized")

    def load_model(self, model_name: str = 'linear_regression', currency: str = 'usd'):
        """
        Load a trained model

        Args:
            model_name: Model type (linear_regression, random_forest, xgboost)
            currency: usd or pkr

        Returns:
            Success boolean
        """
        try:
            model_key = f"{model_name}_{currency.lower()}"
            model_path = os.path.join(self.model_dir, f'{model_key}_model.pkl')
            scaler_path = os.path.join(self.model_dir, 'scaler.pkl')

            if not os.path.exists(model_path):
                logger.error(f"Model not found: {model_path}")
                return False

            # Load model
            self.models[model_key] = joblib.load(model_path)
            logger.info(f"✓ Loaded model: {model_key}")

            # Load scaler if exists (for linear regression)
            if 'linear' in model_name and os.path.exists(scaler_path):
                self.scalers[model_key] = joblib.load(scaler_path)
                logger.info(f"✓ Loaded scaler for {model_key}")

            self.active_model = model_key
            return True

        except Exception as e:
            logger.error(f"Model loading error: {e}")
            return False

    def prepare_features(self, features: Dict[str, Any]) -> Optional[np.ndarray]:
        """
        Prepare feature vector for prediction

        Args:
            features: Feature dictionary

        Returns:
            Numpy array or None
        """
        try:
            # Exclude non-feature fields
            exclude_fields = ['timestamp', 'symbol', 'current_price']

            # Extract feature values
            feature_values = []
            for key, value in features.items():
                if key not in exclude_fields:
                    feature_values.append(float(value))

            # Convert to numpy array
            X = np.array(feature_values).reshape(1, -1)

            # Scale if scaler is available
            if self.active_model in self.scalers:
                X = self.scalers[self.active_model].transform(X)

            return X

        except Exception as e:
            logger.error(f"Feature preparation error: {e}")
            return None

    def calculate_confidence_bounds(self, prediction: float, current_price: float,
                                   std_dev: float = 0.02) -> Tuple[float, float]:
        """
        Calculate prediction confidence bounds

        Args:
            prediction: Predicted price
            current_price: Current price
            std_dev: Standard deviation multiplier (default 2%)

        Returns:
            (lower_bound, upper_bound)
        """
        # Simple confidence band based on standard deviation
        spread = current_price * std_dev

        lower_bound = prediction - spread
        upper_bound = prediction + spread

        return (lower_bound, upper_bound)

    def predict(self, symbol: str = 'OANDA:XAU_USD', horizon: str = '1min') -> Optional[Dict[str, Any]]:
        """
        Make a real-time prediction

        Args:
            symbol: Trading symbol
            horizon: Prediction horizon (1min, 5min, 1hour, 1day)

        Returns:
            Prediction dict or None
        """
        try:
            if not self.active_model:
                logger.warning("No model loaded")
                return None

            # Generate features
            features = self.feature_engine.generate_features(symbol)
            if not features:
                logger.warning("Feature generation failed")
                return None

            current_price = features['current_price']
            timestamp = features['timestamp']

            # Prepare features
            X = self.prepare_features(features)
            if X is None:
                logger.warning("Feature preparation failed")
                return None

            # Make prediction
            model = self.models[self.active_model]
            predicted_price = float(model.predict(X)[0])

            # Calculate change
            price_change = predicted_price - current_price
            price_change_pct = (price_change / current_price) * 100 if current_price > 0 else 0

            # Confidence bounds
            lower_bound, upper_bound = self.calculate_confidence_bounds(predicted_price, current_price)

            # Calculate confidence score (0-1)
            # Simple heuristic: higher confidence if change is small
            confidence = max(0.5, min(1.0, 1.0 - abs(price_change_pct) / 10))

            prediction = {
                'timestamp': timestamp,
                'symbol': symbol,
                'current_price': current_price,
                'predicted_price': predicted_price,
                'price_change': price_change,
                'price_change_pct': price_change_pct,
                'prediction_horizon': horizon,
                'model_name': self.active_model,
                'model_type': self.active_model.split('_')[0],
                'confidence': confidence,
                'lower_bound': lower_bound,
                'upper_bound': upper_bound,
                'direction': 'UP' if price_change > 0 else 'DOWN',
                'signal': 'BUY' if price_change > 0 else 'SELL' if price_change < -0.5 else 'HOLD'
            }

            # Store in database
            try:
                save_prediction(
                    self.db_session,
                    timestamp=timestamp,
                    symbol=symbol,
                    current_price=current_price,
                    predicted_price=predicted_price,
                    model_name=self.active_model,
                    model_type=self.active_model.split('_')[0],
                    confidence=confidence,
                    upper_bound=upper_bound,
                    lower_bound=lower_bound,
                    horizon=horizon
                )
            except Exception as e:
                logger.warning(f"Database save error: {e}")

            # Cache in Redis
            if self.redis_cache.is_available():
                self.redis_cache.set_prediction(symbol, prediction)

            self.predictions_made += 1
            logger.info(f"Prediction: {symbol} ${current_price:.2f} → ${predicted_price:.2f} ({price_change_pct:+.2f}%)")

            return prediction

        except Exception as e:
            logger.error(f"Prediction error: {e}")
            return None

    def get_cached_prediction(self, symbol: str = 'OANDA:XAU_USD') -> Optional[Dict[str, Any]]:
        """
        Get cached prediction from Redis

        Args:
            symbol: Trading symbol

        Returns:
            Cached prediction or None
        """
        if self.redis_cache.is_available():
            return self.redis_cache.get_prediction(symbol)
        return None

    def get_statistics(self) -> Dict[str, Any]:
        """Get predictor statistics"""
        return {
            'predictions_made': self.predictions_made,
            'active_model': self.active_model,
            'models_loaded': list(self.models.keys()),
            'scalers_loaded': list(self.scalers.keys())
        }

    def close(self):
        """Close resources"""
        self.feature_engine.close()
        if self.db_session:
            self.db_session.close()
        logger.info("Realtime predictor closed")


# Test
if __name__ == "__main__":
    predictor = RealtimePredictor()

    print("\n=== Testing Realtime Predictor ===")

    # Load model
    print("\n1. Loading model...")
    success = predictor.load_model('linear_regression', 'usd')
    print(f"✓ Model loaded: {success}")

    if success:
        # Make prediction
        print("\n2. Making prediction...")
        prediction = predictor.predict()

        if prediction:
            print(f"✓ Prediction made!")
            print(f"  Current: ${prediction['current_price']:.2f}")
            print(f"  Predicted: ${prediction['predicted_price']:.2f}")
            print(f"  Change: {prediction['price_change_pct']:+.2f}%")
            print(f"  Confidence: {prediction['confidence']:.2f}")
            print(f"  Signal: {prediction['signal']}")
        else:
            print("✗ Prediction failed (need historical data first)")

    # Statistics
    print("\n3. Statistics:")
    stats = predictor.get_statistics()
    print(f"  {stats}")

    predictor.close()

