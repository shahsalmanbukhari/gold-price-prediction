"""
Feature Engineering Module
Creates technical indicators and lag features for gold price prediction
"""

import pandas as pd
import numpy as np
import os
from datetime import datetime


class GoldFeatureEngineer:
    """Create features for gold price prediction model"""

    def __init__(self, input_dir='data/processed', output_dir='data/processed'):
        self.input_dir = input_dir
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        self.feature_list = []

    def load_clean_data(self, filename='merged_clean.csv'):
        """Load cleaned data (USD + PKR)"""
        filepath = os.path.join(self.input_dir, filename)

        # Try alternative filenames
        if not os.path.exists(filepath):
            filepath = os.path.join(self.input_dir, 'gold_prices_clean.csv')

        print(f"\n{'='*60}")
        print(f"Loading cleaned data from: {filepath}")
        print(f"{'='*60}")

        df = pd.read_csv(filepath)
        df['Date'] = pd.to_datetime(df['Date'])

        print(f"✓ Loaded {len(df)} records")
        print(f"✓ Date range: {df['Date'].min().date()} to {df['Date'].max().date()}")

        # Detect which price columns are available
        has_usd = 'Close_USD_per_oz' in df.columns
        has_pkr = 'Close_PKR_per_tola' in df.columns
        print(f"✓ USD prices available: {has_usd}")
        print(f"✓ PKR prices available: {has_pkr}")

        return df

    def add_lag_features(self, df, column='Close_PKR_per_tola', max_lag=14):
        """
        Add lag features (previous N days' prices)

        Args:
            df: DataFrame
            column: Column to create lags for
            max_lag: Maximum number of lag days (1 to max_lag)
        """
        print(f"\n{'='*60}")
        print(f"CREATING LAG FEATURES (1-{max_lag} days)")
        print(f"{'='*60}")

        for lag in range(1, max_lag + 1):
            feature_name = f'{column}_lag_{lag}'
            df[feature_name] = df[column].shift(lag)
            self.feature_list.append(feature_name)

        print(f"✓ Created {max_lag} lag features")

        return df

    def add_rolling_features(self, df, column='Close_PKR_per_tola', windows=[3, 7, 14, 30]):
        """
        Add rolling mean, std, min, max features

        Args:
            df: DataFrame
            column: Column to calculate rolling statistics
            windows: List of window sizes
        """
        print(f"\n{'='*60}")
        print(f"CREATING ROLLING FEATURES (windows: {windows})")
        print(f"{'='*60}")

        feature_count = 0

        for window in windows:
            # Rolling mean
            feature_name = f'{column}_rolling_mean_{window}'
            df[feature_name] = df[column].rolling(window=window).mean()
            self.feature_list.append(feature_name)
            feature_count += 1

            # Rolling std
            feature_name = f'{column}_rolling_std_{window}'
            df[feature_name] = df[column].rolling(window=window).std()
            self.feature_list.append(feature_name)
            feature_count += 1

            # Rolling min
            feature_name = f'{column}_rolling_min_{window}'
            df[feature_name] = df[column].rolling(window=window).min()
            self.feature_list.append(feature_name)
            feature_count += 1

            # Rolling max
            feature_name = f'{column}_rolling_max_{window}'
            df[feature_name] = df[column].rolling(window=window).max()
            self.feature_list.append(feature_name)
            feature_count += 1

        print(f"✓ Created {feature_count} rolling statistical features")

        return df

    def add_exponential_moving_average(self, df, column='Close_PKR_per_tola', spans=[7, 14, 30]):
        """
        Add Exponential Moving Average (EMA) features

        Args:
            df: DataFrame
            column: Column to calculate EMA
            spans: List of span values for EMA
        """
        print(f"\n{'='*60}")
        print(f"CREATING EXPONENTIAL MOVING AVERAGES (spans: {spans})")
        print(f"{'='*60}")

        for span in spans:
            feature_name = f'{column}_ema_{span}'
            df[feature_name] = df[column].ewm(span=span, adjust=False).mean()
            self.feature_list.append(feature_name)

        print(f"✓ Created {len(spans)} EMA features")

        return df

    def add_rsi(self, df, column='Close_PKR_per_tola', period=14):
        """
        Add Relative Strength Index (RSI)

        RSI = 100 - (100 / (1 + RS))
        where RS = Average Gain / Average Loss over period

        Args:
            df: DataFrame
            column: Column to calculate RSI
            period: RSI period (default 14)
        """
        print(f"\n{'='*60}")
        print(f"CREATING RSI INDICATOR (period={period})")
        print(f"{'='*60}")

        # Calculate price changes
        delta = df[column].diff()

        # Separate gains and losses
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)

        # Calculate average gain and loss
        avg_gain = gain.rolling(window=period).mean()
        avg_loss = loss.rolling(window=period).mean()

        # Calculate RS and RSI
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        feature_name = f'{column}_rsi_{period}'
        df[feature_name] = rsi
        self.feature_list.append(feature_name)

        print(f"✓ Created RSI feature")
        print(f"  - RSI range: {rsi.min():.2f} to {rsi.max():.2f}")

        return df

    def add_macd(self, df, column='Close_PKR_per_tola', fast=12, slow=26, signal=9):
        """
        Add MACD (Moving Average Convergence Divergence) indicator

        MACD = EMA(fast) - EMA(slow)
        Signal = EMA(MACD, signal period)
        Histogram = MACD - Signal

        Args:
            df: DataFrame
            column: Column to calculate MACD
            fast: Fast EMA period (default 12)
            slow: Slow EMA period (default 26)
            signal: Signal line period (default 9)
        """
        print(f"\n{'='*60}")
        print(f"CREATING MACD INDICATOR (fast={fast}, slow={slow}, signal={signal})")
        print(f"{'='*60}")

        # Calculate EMAs
        ema_fast = df[column].ewm(span=fast, adjust=False).mean()
        ema_slow = df[column].ewm(span=slow, adjust=False).mean()

        # Calculate MACD line
        macd = ema_fast - ema_slow
        feature_name = f'{column}_macd'
        df[feature_name] = macd
        self.feature_list.append(feature_name)

        # Calculate signal line
        macd_signal = macd.ewm(span=signal, adjust=False).mean()
        feature_name = f'{column}_macd_signal'
        df[feature_name] = macd_signal
        self.feature_list.append(feature_name)

        # Calculate MACD histogram
        macd_histogram = macd - macd_signal
        feature_name = f'{column}_macd_histogram'
        df[feature_name] = macd_histogram
        self.feature_list.append(feature_name)

        print(f"✓ Created 3 MACD features (line, signal, histogram)")

        return df

    def add_momentum_features(self, df, column='Close_PKR_per_tola', periods=[5, 10, 20]):
        """
        Add momentum (rate of change) features

        Momentum = Current Price - Price N periods ago

        Args:
            df: DataFrame
            column: Column to calculate momentum
            periods: List of periods
        """
        print(f"\n{'='*60}")
        print(f"CREATING MOMENTUM FEATURES (periods: {periods})")
        print(f"{'='*60}")

        for period in periods:
            feature_name = f'{column}_momentum_{period}'
            df[feature_name] = df[column] - df[column].shift(period)
            self.feature_list.append(feature_name)

        print(f"✓ Created {len(periods)} momentum features")

        return df

    def add_volatility_features(self, df, column='Close_PKR_per_tola', windows=[7, 14, 30]):
        """
        Add volatility (rolling standard deviation of returns) features

        Args:
            df: DataFrame
            column: Column to calculate volatility
            windows: List of window sizes
        """
        print(f"\n{'='*60}")
        print(f"CREATING VOLATILITY FEATURES (windows: {windows})")
        print(f"{'='*60}")

        # Calculate returns if not already present
        if 'Daily_Return' not in df.columns:
            df['Daily_Return'] = df[column].pct_change() * 100

        for window in windows:
            feature_name = f'volatility_{window}'
            df[feature_name] = df['Daily_Return'].rolling(window=window).std()
            self.feature_list.append(feature_name)

        print(f"✓ Created {len(windows)} volatility features")

        return df

    def add_bollinger_bands(self, df, column='Close_PKR_per_tola', window=20, num_std=2):
        """
        Add Bollinger Bands features

        Upper Band = SMA(window) + num_std * StdDev(window)
        Lower Band = SMA(window) - num_std * StdDev(window)

        Args:
            df: DataFrame
            column: Column to calculate Bollinger Bands
            window: Window size (default 20)
            num_std: Number of standard deviations (default 2)
        """
        print(f"\n{'='*60}")
        print(f"CREATING BOLLINGER BANDS (window={window}, std={num_std})")
        print(f"{'='*60}")

        # Calculate middle band (SMA)
        sma = df[column].rolling(window=window).mean()
        std = df[column].rolling(window=window).std()

        # Upper and lower bands
        feature_name = f'{column}_bb_upper'
        df[feature_name] = sma + (num_std * std)
        self.feature_list.append(feature_name)

        feature_name = f'{column}_bb_lower'
        df[feature_name] = sma - (num_std * std)
        self.feature_list.append(feature_name)

        feature_name = f'{column}_bb_middle'
        df[feature_name] = sma
        self.feature_list.append(feature_name)

        # Bollinger Band Width
        feature_name = f'{column}_bb_width'
        df[feature_name] = (df[f'{column}_bb_upper'] - df[f'{column}_bb_lower']) / df[f'{column}_bb_middle']
        self.feature_list.append(feature_name)

        print(f"✓ Created 4 Bollinger Band features")

        return df

    def add_time_features(self, df):
        """Add time-based features (day of week, month, quarter)"""
        print(f"\n{'='*60}")
        print("CREATING TIME-BASED FEATURES")
        print(f"{'='*60}")

        df['day_of_week'] = df['Date'].dt.dayofweek  # 0=Monday, 6=Sunday
        df['day_of_month'] = df['Date'].dt.day
        df['month'] = df['Date'].dt.month
        df['quarter'] = df['Date'].dt.quarter
        df['year'] = df['Date'].dt.year

        # Cyclical encoding for day of week and month
        df['day_of_week_sin'] = np.sin(2 * np.pi * df['day_of_week'] / 7)
        df['day_of_week_cos'] = np.cos(2 * np.pi * df['day_of_week'] / 7)
        df['month_sin'] = np.sin(2 * np.pi * df['month'] / 12)
        df['month_cos'] = np.cos(2 * np.pi * df['month'] / 12)

        time_features = ['day_of_week', 'day_of_month', 'month', 'quarter', 'year',
                        'day_of_week_sin', 'day_of_week_cos', 'month_sin', 'month_cos']
        self.feature_list.extend(time_features)

        print(f"✓ Created {len(time_features)} time-based features")

        return df

    def create_target_variable(self, df):
        """
        Create target variables for both PKR and USD (next day's prices)

        Args:
            df: DataFrame
        """
        print(f"\n{'='*60}")
        print("CREATING TARGET VARIABLES")
        print(f"{'='*60}")

        targets_created = []

        # PKR target
        if 'Close_PKR_per_tola' in df.columns:
            df['target_PKR'] = df['Close_PKR_per_tola'].shift(-1)
            targets_created.append('target_PKR (PKR per tola)')
            print(f"✓ Created target_PKR: next day's Close_PKR_per_tola")

        # USD target
        if 'Close_USD_per_oz' in df.columns:
            df['target_USD'] = df['Close_USD_per_oz'].shift(-1)
            targets_created.append('target_USD (USD per oz)')
            print(f"✓ Created target_USD: next day's Close_USD_per_oz")

        # Backward compatibility
        if 'target_PKR' in df.columns:
            df['target'] = df['target_PKR']

        if targets_created:
            print(f"✓ Targets created: {', '.join(targets_created)}")
            print(f"  - Each target will have 1 NaN at the end (expected)")
        else:
            print("⚠ No target variables created (missing price columns)")

        return df

    def remove_na_rows(self, df):
        """Remove rows with NaN values created by feature engineering"""
        print(f"\n{'='*60}")
        print("REMOVING ROWS WITH MISSING VALUES")
        print(f"{'='*60}")

        initial_count = len(df)
        df = df.dropna()
        removed_count = initial_count - len(df)

        print(f"✓ Removed {removed_count} rows with NaN values")
        print(f"✓ Final dataset: {len(df)} rows")

        return df

    def save_featured_data(self, df, filename='features_usd_pkr.csv'):
        """Save data with engineered features"""
        filepath = os.path.join(self.output_dir, filename)
        df.to_csv(filepath, index=False)

        print(f"\n✓ Saved featured data to: {filepath}")

        # Also save with old filename for backward compatibility
        if filename == 'features_usd_pkr.csv':
            compat_path = os.path.join(self.output_dir, 'gold_prices_featured.csv')
            df.to_csv(compat_path, index=False)
            print(f"✓ Also saved as: {compat_path} (backward compatibility)")

        # Save feature list
        feature_list_path = os.path.join(self.output_dir, 'feature_list.txt')
        with open(feature_list_path, 'w') as f:
            f.write("ENGINEERED FEATURES LIST\n")
            f.write("="*60 + "\n")
            f.write(f"Total features: {len(self.feature_list)}\n")
            f.write(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            for i, feature in enumerate(self.feature_list, 1):
                f.write(f"{i}. {feature}\n")

        print(f"✓ Saved feature list to: {feature_list_path}")

        return filepath

    def feature_engineering_pipeline(self):
        """Complete feature engineering pipeline for USD + PKR"""
        print("\n" + "="*60)
        print("GOLD DATA FEATURE ENGINEERING (USD + PKR) - Stage 3")
        print("="*60)

        # Load cleaned data
        df = self.load_clean_data()

        # Determine which price columns are available
        has_pkr = 'Close_PKR_per_tola' in df.columns
        has_usd = 'Close_USD_per_oz' in df.columns

        # Create features for PKR
        if has_pkr:
            print(f"\n{'='*60}")
            print("CREATING PKR FEATURES")
            print(f"{'='*60}")

            df = self.add_lag_features(df, column='Close_PKR_per_tola', max_lag=14)
            df = self.add_rolling_features(df, column='Close_PKR_per_tola', windows=[3, 7, 14, 30])
            df = self.add_exponential_moving_average(df, column='Close_PKR_per_tola', spans=[7, 14, 30])
            df = self.add_rsi(df, column='Close_PKR_per_tola', period=14)
            df = self.add_macd(df, column='Close_PKR_per_tola')
            df = self.add_momentum_features(df, column='Close_PKR_per_tola', periods=[5, 10, 20])

            # Volatility needs Daily_Return
            if 'Daily_Return_PKR' in df.columns:
                print(f"\n{'='*60}")
                print(f"CREATING PKR VOLATILITY FEATURES")
                print(f"{'='*60}")
                for window in [7, 14, 30]:
                    feature_name = f'volatility_PKR_{window}'
                    df[feature_name] = df['Daily_Return_PKR'].rolling(window=window).std()
                    self.feature_list.append(feature_name)
                print(f"✓ Created 3 PKR volatility features")

            df = self.add_bollinger_bands(df, column='Close_PKR_per_tola', window=20)

        # Create features for USD
        if has_usd:
            print(f"\n{'='*60}")
            print("CREATING USD FEATURES")
            print(f"{'='*60}")

            df = self.add_lag_features(df, column='Close_USD_per_oz', max_lag=14)
            df = self.add_rolling_features(df, column='Close_USD_per_oz', windows=[3, 7, 14, 30])
            df = self.add_exponential_moving_average(df, column='Close_USD_per_oz', spans=[7, 14, 30])
            df = self.add_rsi(df, column='Close_USD_per_oz', period=14)
            df = self.add_macd(df, column='Close_USD_per_oz')
            df = self.add_momentum_features(df, column='Close_USD_per_oz', periods=[5, 10, 20])

            # Volatility needs Daily_Return
            if 'Daily_Return_USD' in df.columns:
                print(f"\n{'='*60}")
                print(f"CREATING USD VOLATILITY FEATURES")
                print(f"{'='*60}")
                for window in [7, 14, 30]:
                    feature_name = f'volatility_USD_{window}'
                    df[feature_name] = df['Daily_Return_USD'].rolling(window=window).std()
                    self.feature_list.append(feature_name)
                print(f"✓ Created 3 USD volatility features")

            df = self.add_bollinger_bands(df, column='Close_USD_per_oz', window=20)

        # Create time-based features (shared)
        df = self.add_time_features(df)

        # Create target variables
        df = self.create_target_variable(df)

        # Remove rows with NaN
        df = self.remove_na_rows(df)

        print(f"\n{'='*60}")
        print("FEATURE ENGINEERING SUMMARY")
        print(f"{'='*60}")
        print(f"Total features created: {len(self.feature_list)}")
        print(f"Final dataset shape: {df.shape}")
        print(f"Columns: {df.shape[1]}")
        print(f"Rows: {df.shape[0]}")

        # Save featured data
        output_path = self.save_featured_data(df)

        print("\n" + "="*60)
        print("FEATURE ENGINEERING COMPLETE")
        print("="*60)
        print(f"✓ Featured dataset ready at: {output_path}")

        return df


if __name__ == "__main__":
    # Run feature engineering pipeline
    engineer = GoldFeatureEngineer()

    try:
        df_featured = engineer.feature_engineering_pipeline()
        print("\n✓ Feature Engineering Stage 3 complete!")
        print("✓ Next step: Run train.py for model training")
    except Exception as e:
        print(f"\n✗ Error during feature engineering: {e}")
        import traceback
        traceback.print_exc()

