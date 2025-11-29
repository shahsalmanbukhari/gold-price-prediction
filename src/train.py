"""
Model Training Module
Trains multiple models for gold price prediction with proper time-series splits
"""

import pandas as pd
import numpy as np
import os
import joblib
from datetime import datetime
from sklearn.linear_model import LinearRegression
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
import matplotlib.pyplot as plt
import seaborn as sns

try:
    import xgboost as xgb
    XGBOOST_AVAILABLE = True
except (ImportError, Exception) as e:
    XGBOOST_AVAILABLE = False
    xgb = None
    print(f"⚠ XGBoost not available: {type(e).__name__}")


class GoldPriceTrainer:
    """Train machine learning models for gold price prediction"""

    def __init__(self, data_dir='data/processed', model_dir='models', report_dir='reports'):
        self.data_dir = data_dir
        self.model_dir = model_dir
        self.report_dir = report_dir
        os.makedirs(model_dir, exist_ok=True)
        os.makedirs(report_dir, exist_ok=True)

        self.models = {}
        self.scalers = {}
        self.results = {}

        # Set random seed for reproducibility
        np.random.seed(42)

    def load_featured_data(self, filename='features_usd_pkr.csv'):
        """Load data with engineered features (USD + PKR)"""
        filepath = os.path.join(self.data_dir, filename)

        # Try alternative filenames
        if not os.path.exists(filepath):
            filepath = os.path.join(self.data_dir, 'gold_prices_featured.csv')

        print(f"\n{'='*60}")
        print(f"Loading featured data from: {filepath}")
        print(f"{'='*60}")

        df = pd.read_csv(filepath)
        df['Date'] = pd.to_datetime(df['Date'])

        print(f"✓ Loaded {len(df)} records")
        print(f"✓ Shape: {df.shape}")
        print(f"✓ Date range: {df['Date'].min().date()} to {df['Date'].max().date()}")

        # Detect available targets
        has_pkr_target = 'target_PKR' in df.columns or 'target' in df.columns
        has_usd_target = 'target_USD' in df.columns
        print(f"✓ PKR target available: {has_pkr_target}")
        print(f"✓ USD target available: {has_usd_target}")

        return df

    def prepare_train_test_split(self, df, target_currency='PKR', train_ratio=0.7, val_ratio=0.15, test_ratio=0.15):
        """
        Split data into train, validation, and test sets (time-series split - no shuffling)

        Args:
            df: DataFrame with features
            target_currency: 'PKR' or 'USD' to determine which target to use
            train_ratio: Proportion for training (default 0.7)
            val_ratio: Proportion for validation (default 0.15)
            test_ratio: Proportion for testing (default 0.15)
        """
        print(f"\n{'='*60}")
        print(f"CREATING TRAIN/VAL/TEST SPLITS (no shuffling) - Target: {target_currency}")
        print(f"{'='*60}")

        # Sort by date to ensure chronological order
        df = df.sort_values('Date').reset_index(drop=True)

        # Define split indices
        n = len(df)
        train_end = int(n * train_ratio)
        val_end = int(n * (train_ratio + val_ratio))

        # Split data
        train_df = df.iloc[:train_end].copy()
        val_df = df.iloc[train_end:val_end].copy()
        test_df = df.iloc[val_end:].copy()

        print(f"Total records: {n}")
        print(f"\nTrain set: {len(train_df)} records ({len(train_df)/n*100:.1f}%)")
        print(f"  - Date range: {train_df['Date'].min().date()} to {train_df['Date'].max().date()}")

        print(f"\nValidation set: {len(val_df)} records ({len(val_df)/n*100:.1f}%)")
        print(f"  - Date range: {val_df['Date'].min().date()} to {val_df['Date'].max().date()}")

        print(f"\nTest set: {len(test_df)} records ({len(test_df)/n*100:.1f}%)")
        print(f"  - Date range: {test_df['Date'].min().date()} to {test_df['Date'].max().date()}")

        # Determine target column
        if target_currency == 'USD':
            target_col = 'target_USD' if 'target_USD' in df.columns else 'target'
        else:  # PKR
            target_col = 'target_PKR' if 'target_PKR' in df.columns else 'target'

        print(f"✓ Using target column: {target_col}")

        # Prepare features and target
        # Exclude non-feature columns
        exclude_cols = ['Date', 'target', 'target_PKR', 'target_USD',
                       'Close_PKR_per_tola', 'Open_PKR_per_tola',
                       'High_PKR_per_tola', 'Low_PKR_per_tola', 'Close_PKR_per_gram',
                       'Close_USD_per_oz', 'Open_USD_per_oz', 'High_USD_per_oz', 'Low_USD_per_oz',
                       'Close_PKR_per_oz', 'Open_PKR_per_oz', 'High_PKR_per_oz', 'Low_PKR_per_oz',
                       'Close_USD_per_gram', 'Adj Close', 'Volume']

        feature_cols = [col for col in df.columns if col not in exclude_cols]

        print(f"✓ Using {len(feature_cols)} features for training")

        X_train = train_df[feature_cols]
        y_train = train_df[target_col]

        X_val = val_df[feature_cols]
        y_val = val_df[target_col]

        X_test = test_df[feature_cols]
        y_test = test_df[target_col]

        return X_train, X_val, X_test, y_train, y_val, y_test, train_df, val_df, test_df, feature_cols

    def scale_features(self, X_train, X_val, X_test):
        """Scale features using StandardScaler"""
        print(f"\n{'='*60}")
        print("SCALING FEATURES")
        print(f"{'='*60}")

        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_val_scaled = scaler.transform(X_val)
        X_test_scaled = scaler.transform(X_test)

        print(f"✓ Features scaled using StandardScaler")
        print(f"  - Mean: {scaler.mean_[:5]}")
        print(f"  - Std: {scaler.scale_[:5]}")

        self.scalers['standard'] = scaler

        return X_train_scaled, X_val_scaled, X_test_scaled

    def train_linear_regression(self, X_train, y_train, X_val, y_val):
        """Train Linear Regression model"""
        print(f"\n{'='*60}")
        print("TRAINING LINEAR REGRESSION")
        print(f"{'='*60}")

        model = LinearRegression()
        model.fit(X_train, y_train)

        # Predictions
        y_train_pred = model.predict(X_train)
        y_val_pred = model.predict(X_val)

        # Metrics
        train_rmse = np.sqrt(mean_squared_error(y_train, y_train_pred))
        val_rmse = np.sqrt(mean_squared_error(y_val, y_val_pred))
        train_r2 = r2_score(y_train, y_train_pred)
        val_r2 = r2_score(y_val, y_val_pred)

        print(f"✓ Model trained")
        print(f"  - Train RMSE: {train_rmse:,.2f}")
        print(f"  - Val RMSE: {val_rmse:,.2f}")
        print(f"  - Train R²: {train_r2:.4f}")
        print(f"  - Val R²: {val_r2:.4f}")

        self.models['linear_regression'] = model
        self.results['linear_regression'] = {
            'train_rmse': train_rmse,
            'val_rmse': val_rmse,
            'train_r2': train_r2,
            'val_r2': val_r2,
            'y_train_pred': y_train_pred,
            'y_val_pred': y_val_pred
        }

        return model

    def train_random_forest(self, X_train, y_train, X_val, y_val, n_estimators=100, max_depth=10):
        """Train Random Forest model"""
        print(f"\n{'='*60}")
        print(f"TRAINING RANDOM FOREST (n_estimators={n_estimators}, max_depth={max_depth})")
        print(f"{'='*60}")

        model = RandomForestRegressor(
            n_estimators=n_estimators,
            max_depth=max_depth,
            random_state=42,
            n_jobs=-1,
            verbose=0
        )
        model.fit(X_train, y_train)

        # Predictions
        y_train_pred = model.predict(X_train)
        y_val_pred = model.predict(X_val)

        # Metrics
        train_rmse = np.sqrt(mean_squared_error(y_train, y_train_pred))
        val_rmse = np.sqrt(mean_squared_error(y_val, y_val_pred))
        train_r2 = r2_score(y_train, y_train_pred)
        val_r2 = r2_score(y_val, y_val_pred)

        print(f"✓ Model trained")
        print(f"  - Train RMSE: {train_rmse:,.2f}")
        print(f"  - Val RMSE: {val_rmse:,.2f}")
        print(f"  - Train R²: {train_r2:.4f}")
        print(f"  - Val R²: {val_r2:.4f}")

        self.models['random_forest'] = model
        self.results['random_forest'] = {
            'train_rmse': train_rmse,
            'val_rmse': val_rmse,
            'train_r2': train_r2,
            'val_r2': val_r2,
            'y_train_pred': y_train_pred,
            'y_val_pred': y_val_pred,
            'feature_importance': model.feature_importances_
        }

        return model

    def train_xgboost(self, X_train, y_train, X_val, y_val, n_estimators=100, max_depth=6, learning_rate=0.1):
        """Train XGBoost model"""
        if not XGBOOST_AVAILABLE:
            print("\n⚠ XGBoost not available. Skipping...")
            return None

        print(f"\n{'='*60}")
        print(f"TRAINING XGBOOST (n_estimators={n_estimators}, max_depth={max_depth}, lr={learning_rate})")
        print(f"{'='*60}")

        model = xgb.XGBRegressor(
            n_estimators=n_estimators,
            max_depth=max_depth,
            learning_rate=learning_rate,
            random_state=42,
            n_jobs=-1,
            verbosity=0
        )
        model.fit(X_train, y_train, eval_set=[(X_val, y_val)], verbose=False)

        # Predictions
        y_train_pred = model.predict(X_train)
        y_val_pred = model.predict(X_val)

        # Metrics
        train_rmse = np.sqrt(mean_squared_error(y_train, y_train_pred))
        val_rmse = np.sqrt(mean_squared_error(y_val, y_val_pred))
        train_r2 = r2_score(y_train, y_train_pred)
        val_r2 = r2_score(y_val, y_val_pred)

        print(f"✓ Model trained")
        print(f"  - Train RMSE: {train_rmse:,.2f}")
        print(f"  - Val RMSE: {val_rmse:,.2f}")
        print(f"  - Train R²: {train_r2:.4f}")
        print(f"  - Val R²: {val_r2:.4f}")

        self.models['xgboost'] = model
        self.results['xgboost'] = {
            'train_rmse': train_rmse,
            'val_rmse': val_rmse,
            'train_r2': train_r2,
            'val_r2': val_r2,
            'y_train_pred': y_train_pred,
            'y_val_pred': y_val_pred,
            'feature_importance': model.feature_importances_
        }

        return model

    def save_models(self):
        """Save trained models and scalers"""
        print(f"\n{'='*60}")
        print("SAVING MODELS")
        print(f"{'='*60}")

        for name, model in self.models.items():
            filepath = os.path.join(self.model_dir, f'{name}_model.pkl')
            joblib.dump(model, filepath)
            print(f"✓ Saved {name} model to: {filepath}")

        # Save scaler
        if 'standard' in self.scalers:
            filepath = os.path.join(self.model_dir, 'scaler.pkl')
            joblib.dump(self.scalers['standard'], filepath)
            print(f"✓ Saved scaler to: {filepath}")

    def compare_models(self):
        """Compare all trained models"""
        print(f"\n{'='*60}")
        print("MODEL COMPARISON")
        print(f"{'='*60}")

        comparison = []
        for name, results in self.results.items():
            comparison.append({
                'Model': name,
                'Train RMSE': results['train_rmse'],
                'Val RMSE': results['val_rmse'],
                'Train R²': results['train_r2'],
                'Val R²': results['val_r2']
            })

        df_comparison = pd.DataFrame(comparison)
        df_comparison = df_comparison.sort_values('Val RMSE')

        print("\n" + df_comparison.to_string(index=False))

        # Save comparison
        filepath = os.path.join(self.report_dir, 'model_comparison.csv')
        df_comparison.to_csv(filepath, index=False)
        print(f"\n✓ Saved comparison to: {filepath}")

        return df_comparison

    def training_pipeline(self, train_both=True):
        """
        Complete training pipeline for USD and/or PKR models

        Args:
            train_both: If True, train both USD and PKR models. If False, train only PKR.
        """
        print("\n" + "="*60)
        print("GOLD PRICE PREDICTION - MODEL TRAINING (USD + PKR) - Stage 4")
        print("="*60)

        # Load data
        df = self.load_featured_data()

        # Determine which targets are available
        has_pkr = 'target_PKR' in df.columns or ('target' in df.columns and 'Close_PKR_per_tola' in df.columns)
        has_usd = 'target_USD' in df.columns

        currencies_to_train = []
        if has_pkr:
            currencies_to_train.append('PKR')
        if has_usd and train_both:
            currencies_to_train.append('USD')

        print(f"✓ Will train models for: {', '.join(currencies_to_train)}")

        all_results = {}

        for currency in currencies_to_train:
            print(f"\n{'#'*60}")
            print(f"# TRAINING {currency} MODELS")
            print(f"{'#'*60}")

            # Split data for this currency
            X_train, X_val, X_test, y_train, y_val, y_test, train_df, val_df, test_df, feature_cols = \
                self.prepare_train_test_split(df, target_currency=currency)

            # Save feature columns
            self.feature_cols = feature_cols

            # Scale features
            X_train_scaled, X_val_scaled, X_test_scaled = self.scale_features(X_train, X_val, X_test)

            # Save scaler for this currency
            scaler_name = f'scaler_{currency}'
            self.scalers[scaler_name] = self.scalers['standard']

            # Train models
            model_suffix = f'_{currency.lower()}'

            # Linear Regression
            lr_model = self.train_linear_regression(X_train_scaled, y_train, X_val_scaled, y_val)
            self.models[f'linear_regression{model_suffix}'] = lr_model
            self.results[f'linear_regression{model_suffix}'] = self.results.pop('linear_regression')

            # Random Forest
            rf_model = self.train_random_forest(X_train, y_train, X_val, y_val, n_estimators=100, max_depth=10)
            self.models[f'random_forest{model_suffix}'] = rf_model
            self.results[f'random_forest{model_suffix}'] = self.results.pop('random_forest')

            # XGBoost (optional)
            if XGBOOST_AVAILABLE:
                xgb_model = self.train_xgboost(X_train, y_train, X_val, y_val, n_estimators=100, max_depth=6, learning_rate=0.1)
                if xgb_model:
                    self.models[f'xgboost{model_suffix}'] = xgb_model
                    self.results[f'xgboost{model_suffix}'] = self.results.pop('xgboost')

            # Save test data for this currency
            all_results[currency] = {
                'X_test': X_test_scaled,
                'y_test': y_test,
                'test_df': test_df,
                'X_test_unscaled': X_test
            }

        # Compare all models
        comparison = self.compare_models()

        # Save all models
        self.save_models()

        print("\n" + "="*60)
        print("MODEL TRAINING COMPLETE")
        print("="*60)
        print(f"✓ Trained {len(self.models)} models across {len(currencies_to_train)} currencies")
        print(f"✓ Best overall model (lowest Val RMSE): {comparison.iloc[0]['Model']}")

        return self.models, self.results, all_results


if __name__ == "__main__":
    # Run training pipeline
    trainer = GoldPriceTrainer()

    try:
        models, results, test_data = trainer.training_pipeline()
        print("\n✓ Training Stage 4 complete!")
        print("✓ Next step: Run evaluate.py for model evaluation")
    except Exception as e:
        print(f"\n✗ Error during training: {e}")
        import traceback
        traceback.print_exc()

