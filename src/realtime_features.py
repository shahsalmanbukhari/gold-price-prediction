"""
Real-time feature engineering for live predictions
Calculates technical indicators on streaming data
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from loguru import logger

from realtime.redis_cache import get_redis_cache
from src.database import get_session, get_latest_price


class RealtimeFeatureEngine:
    """
    Generate features from real-time tick data

    Features:
    - Rolling statistics (MA, std, min, max)
    - Technical indicators (RSI, MACD, Bollinger Bands)
    - Momentum indicators
    - Lag features
    """

    def __init__(self, lookback_periods: int = 200):
        """
        Initialize feature engine

        Args:
            lookback_periods: Number of historical periods to keep
        """
        self.lookback_periods = lookback_periods
        self.redis_cache = get_redis_cache()
        self.db_session = get_session()

        logger.info(f"Feature engine initialized (lookback: {lookback_periods})")

    def get_recent_prices(self, symbol: str = 'OANDA:XAU_USD', limit: int = 200) -> pd.DataFrame:
        """
        Get recent price data

        Args:
            symbol: Trading symbol
            limit: Number of records

        Returns:
            DataFrame with price data
        """
        try:
            # Try Redis buffer first (faster)
            if self.redis_cache.is_available():
                buffer = self.redis_cache.get_buffer(symbol, limit=limit)
                if buffer and len(buffer) >= 30:  # Minimum for indicators
                    df = pd.DataFrame(buffer)
                    df = df.sort_values('timestamp')
                    df['close'] = df['price_usd']
                    return df

            # Fallback to database
            prices = get_latest_price(self.db_session, symbol, limit=limit)
            if prices:
                data = [{
                    'timestamp': p.timestamp,
                    'price_usd': p.price_usd,
                    'close': p.price_usd,
                    'volume': p.volume or 0
                } for p in prices]
                df = pd.DataFrame(data)
                df = df.sort_values('timestamp')
                return df

            return pd.DataFrame()

        except Exception as e:
            logger.error(f"Error fetching prices: {e}")
            return pd.DataFrame()

    def calculate_sma(self, prices: pd.Series, period: int) -> float:
        """Calculate Simple Moving Average"""
        if len(prices) < period:
            return None
        return prices.tail(period).mean()

    def calculate_ema(self, prices: pd.Series, period: int) -> float:
        """Calculate Exponential Moving Average"""
        if len(prices) < period:
            return None
        return prices.ewm(span=period, adjust=False).mean().iloc[-1]

    def calculate_rsi(self, prices: pd.Series, period: int = 14) -> float:
        """Calculate Relative Strength Index"""
        if len(prices) < period + 1:
            return None

        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))

        return rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else None

    def calculate_macd(self, prices: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Dict[str, float]:
        """Calculate MACD indicators"""
        if len(prices) < slow + signal:
            return {'macd': None, 'signal': None, 'histogram': None}

        ema_fast = prices.ewm(span=fast, adjust=False).mean()
        ema_slow = prices.ewm(span=slow, adjust=False).mean()

        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line

        return {
            'macd': macd_line.iloc[-1],
            'signal': signal_line.iloc[-1],
            'histogram': histogram.iloc[-1]
        }

    def calculate_bollinger_bands(self, prices: pd.Series, period: int = 20, std_dev: float = 2.0) -> Dict[str, float]:
        """Calculate Bollinger Bands"""
        if len(prices) < period:
            return {'upper': None, 'middle': None, 'lower': None, 'width': None}

        middle = prices.tail(period).mean()
        std = prices.tail(period).std()

        upper = middle + (std_dev * std)
        lower = middle - (std_dev * std)
        width = upper - lower

        return {
            'upper': upper,
            'middle': middle,
            'lower': lower,
            'width': width
        }

    def calculate_volatility(self, prices: pd.Series, period: int) -> float:
        """Calculate price volatility (standard deviation)"""
        if len(prices) < period:
            return None
        return prices.tail(period).std()

    def calculate_momentum(self, prices: pd.Series, period: int) -> float:
        """Calculate momentum (rate of change)"""
        if len(prices) < period + 1:
            return None
        return prices.iloc[-1] - prices.iloc[-period-1]

    def generate_features(self, symbol: str = 'OANDA:XAU_USD') -> Optional[Dict[str, Any]]:
        """
        Generate all features for real-time prediction

        Args:
            symbol: Trading symbol

        Returns:
            Feature dictionary or None
        """
        try:
            # Get recent prices
            df = self.get_recent_prices(symbol, limit=self.lookback_periods)

            if df.empty or len(df) < 30:
                logger.warning(f"Insufficient data for feature generation: {len(df)} records")
                return None

            prices = df['close']
            current_price = prices.iloc[-1]

            features = {
                'timestamp': datetime.now(),
                'symbol': symbol,
                'current_price': current_price,

                # Moving averages
                'sma_7': self.calculate_sma(prices, 7),
                'sma_14': self.calculate_sma(prices, 14),
                'sma_30': self.calculate_sma(prices, 30),
                'ema_7': self.calculate_ema(prices, 7),
                'ema_14': self.calculate_ema(prices, 14),
                'ema_30': self.calculate_ema(prices, 30),

                # RSI
                'rsi_14': self.calculate_rsi(prices, 14),

                # Volatility
                'volatility_7': self.calculate_volatility(prices, 7),
                'volatility_14': self.calculate_volatility(prices, 14),
                'volatility_30': self.calculate_volatility(prices, 30),

                # Momentum
                'momentum_5': self.calculate_momentum(prices, 5),
                'momentum_10': self.calculate_momentum(prices, 10),
                'momentum_20': self.calculate_momentum(prices, 20),
            }

            # MACD
            macd = self.calculate_macd(prices)
            features.update({
                'macd': macd['macd'],
                'macd_signal': macd['signal'],
                'macd_histogram': macd['histogram']
            })

            # Bollinger Bands
            bb = self.calculate_bollinger_bands(prices)
            features.update({
                'bb_upper': bb['upper'],
                'bb_middle': bb['middle'],
                'bb_lower': bb['lower'],
                'bb_width': bb['width']
            })

            # Lag features (last N prices)
            for i in [1, 3, 5, 7, 14]:
                if len(prices) > i:
                    features[f'lag_{i}'] = prices.iloc[-i-1]

            # Rolling stats
            for window in [3, 7, 14]:
                if len(prices) >= window:
                    window_prices = prices.tail(window)
                    features[f'rolling_mean_{window}'] = window_prices.mean()
                    features[f'rolling_std_{window}'] = window_prices.std()
                    features[f'rolling_min_{window}'] = window_prices.min()
                    features[f'rolling_max_{window}'] = window_prices.max()

            # Remove None values (replace with 0 or skip)
            features = {k: (v if v is not None else 0.0) for k, v in features.items()
                       if k in ['timestamp', 'symbol'] or isinstance(v, (int, float))}

            logger.debug(f"Generated {len(features)} features for {symbol}")
            return features

        except Exception as e:
            logger.error(f"Feature generation error: {e}")
            return None

    def get_feature_vector(self, symbol: str = 'OANDA:XAU_USD') -> Optional[np.ndarray]:
        """
        Get feature vector as numpy array for ML model

        Args:
            symbol: Trading symbol

        Returns:
            Numpy array or None
        """
        features = self.generate_features(symbol)

        if not features:
            return None

        # Exclude non-numeric fields
        exclude_fields = ['timestamp', 'symbol', 'current_price']
        feature_values = [v for k, v in features.items() if k not in exclude_fields]

        return np.array(feature_values).reshape(1, -1)

    def close(self):
        """Close database session"""
        if self.db_session:
            self.db_session.close()


# Test
if __name__ == "__main__":
    engine = RealtimeFeatureEngine()

    print("\n=== Testing Feature Engine ===")

    # Generate features
    features = engine.generate_features()

    if features:
        print(f"✓ Generated {len(features)} features")
        print("\nSample features:")
        for key in list(features.keys())[:10]:
            print(f"  {key}: {features[key]}")
    else:
        print("✗ Feature generation failed (need historical data first)")

    engine.close()

