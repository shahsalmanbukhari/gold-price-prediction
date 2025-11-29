"""
Prediction Module
Makes predictions using trained models
"""

import pandas as pd
import numpy as np
import joblib
import os
from datetime import datetime, timedelta


class GoldPricePredictor:
    """Make predictions for next-day gold prices"""

    def __init__(self, model_dir='models', data_dir='data/processed'):
        self.model_dir = model_dir
        self.data_dir = data_dir
        self.model = None
        self.scaler = None
        self.feature_cols = None

    def load_model(self, model_name='linear_regression'):
        """Load a trained model"""
        model_path = os.path.join(self.model_dir, f'{model_name}_model.pkl')
        scaler_path = os.path.join(self.model_dir, 'scaler.pkl')

        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model not found: {model_path}")

        self.model = joblib.load(model_path)
        print(f"✓ Loaded {model_name} model")

        # Load scaler if exists (for Linear Regression models)
        if 'linear_regression' in model_name and os.path.exists(scaler_path):
            self.scaler = joblib.load(scaler_path)
            print(f"✓ Loaded scaler")

        return self.model

    def get_latest_data(self):
        """Get the latest data point for prediction"""
        # Try new filename first, then fallback
        filepath = os.path.join(self.data_dir, 'features_usd_pkr.csv')
        if not os.path.exists(filepath):
            filepath = os.path.join(self.data_dir, 'gold_prices_featured.csv')

        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Featured data not found: {filepath}")

        df = pd.read_csv(filepath)
        df['Date'] = pd.to_datetime(df['Date'])

        # Get the last row (most recent data)
        latest_row = df.iloc[-1:].copy()

        # Prepare features
        exclude_cols = ['Date', 'target', 'target_PKR', 'target_USD',
                       'Close_PKR_per_tola', 'Open_PKR_per_tola',
                       'High_PKR_per_tola', 'Low_PKR_per_tola', 'Close_PKR_per_gram',
                       'Close_USD_per_oz', 'Open_USD_per_oz', 'High_USD_per_oz', 'Low_USD_per_oz',
                       'Close_PKR_per_oz', 'Open_PKR_per_oz', 'High_PKR_per_oz', 'Low_PKR_per_oz',
                       'Close_USD_per_gram', 'Adj Close', 'Volume']
        # NOTE: USD_PKR_Rate is kept as a feature (not excluded)

        self.feature_cols = [col for col in df.columns if col not in exclude_cols]

        X_latest = latest_row[self.feature_cols]

        return X_latest, latest_row

    def predict_next_day(self, model_name='linear_regression', currency='PKR'):
        """
        Predict next day's gold price

        Args:
            model_name: Base model name ('linear_regression', 'random_forest')
            currency: 'PKR' or 'USD'

        Returns:
            dict: Prediction results
        """
        # Construct full model name with currency suffix
        full_model_name = f"{model_name}_{currency.lower()}"

        # Try loading with currency suffix first, fallback to base name
        try:
            self.load_model(full_model_name)
        except FileNotFoundError:
            print(f"⚠ Model {full_model_name} not found, trying {model_name}")
            full_model_name = model_name
            self.load_model(full_model_name)

        # Get latest data
        X_latest, latest_row = self.get_latest_data()

        # Determine price column
        if currency == 'USD':
            price_col = 'Close_USD_per_oz'
        else:
            price_col = 'Close_PKR_per_tola'

        if price_col not in latest_row.columns:
            raise ValueError(f"Price column {price_col} not found in data")

        # Scale if needed (for linear regression models)
        if self.scaler is not None and 'linear_regression' in model_name:
            X_latest_scaled = self.scaler.transform(X_latest)
            prediction = self.model.predict(X_latest_scaled)[0]
        else:
            prediction = self.model.predict(X_latest)[0]

        latest_date = latest_row['Date'].values[0]
        latest_price = latest_row[price_col].values[0]

        result = {
            'model': full_model_name,
            'currency': currency,
            'latest_date': pd.to_datetime(latest_date),
            'latest_price': latest_price,
            'predicted_price': prediction,
            'prediction_date': pd.to_datetime(latest_date) + timedelta(days=1),
            'price_change': prediction - latest_price,
            'price_change_pct': ((prediction - latest_price) / latest_price) * 100
        }

        return result

    def predict_both_currencies(self, model_name='linear_regression'):
        """
        Predict next day's gold price in both PKR and USD

        Args:
            model_name: Base model name

        Returns:
            dict: Predictions for both currencies
        """
        results = {}

        # Try PKR prediction
        try:
            results['PKR'] = self.predict_next_day(model_name, currency='PKR')
        except Exception as e:
            print(f"⚠ PKR prediction failed: {e}")
            results['PKR'] = None

        # Try USD prediction
        try:
            results['USD'] = self.predict_next_day(model_name, currency='USD')
        except Exception as e:
            print(f"⚠ USD prediction failed: {e}")
            results['USD'] = None

        return results

    def predict_custom(self, features_dict, model_name='linear_regression'):
        """Make prediction with custom feature values"""
        # Load model
        self.load_model(model_name)

        # Create DataFrame from features
        X_custom = pd.DataFrame([features_dict])

        # Ensure all required features are present
        if self.feature_cols is None:
            # Load feature columns from data
            _, _ = self.get_latest_data()

        # Reorder columns to match training
        X_custom = X_custom[self.feature_cols]

        # Scale if needed
        if self.scaler is not None and model_name == 'linear_regression':
            X_custom_scaled = self.scaler.transform(X_custom)
            prediction = self.model.predict(X_custom_scaled)[0]
        else:
            prediction = self.model.predict(X_custom)[0]

        return prediction


def main():
    """Example usage"""
    predictor = GoldPricePredictor()

    print("\n" + "="*60)
    print("GOLD PRICE PREDICTION (USD + PKR)")
    print("="*60)

    # Predict both currencies with Linear Regression
    results = predictor.predict_both_currencies('linear_regression')

    # PKR Results
    if results['PKR']:
        result_pkr = results['PKR']
        print(f"\n{'='*60}")
        print("PKR PREDICTION (Linear Regression)")
        print(f"{'='*60}")
        print(f"Latest Date: {result_pkr['latest_date'].date()}")
        print(f"Latest Price: PKR {result_pkr['latest_price']:,.2f} per tola")
        print(f"\nPrediction for: {result_pkr['prediction_date'].date()}")
        print(f"Predicted Price: PKR {result_pkr['predicted_price']:,.2f} per tola")
        print(f"Expected Change: PKR {result_pkr['price_change']:,.2f} ({result_pkr['price_change_pct']:+.2f}%)")

    # USD Results
    if results['USD']:
        result_usd = results['USD']
        print(f"\n{'='*60}")
        print("USD PREDICTION (Linear Regression)")
        print(f"{'='*60}")
        print(f"Latest Date: {result_usd['latest_date'].date()}")
        print(f"Latest Price: ${result_usd['latest_price']:,.2f} per oz")
        print(f"\nPrediction for: {result_usd['prediction_date'].date()}")
        print(f"Predicted Price: ${result_usd['predicted_price']:,.2f} per oz")
        print(f"Expected Change: ${result_usd['price_change']:,.2f} ({result_usd['price_change_pct']:+.2f}%)")

    print("\n" + "="*60)


if __name__ == "__main__":
    main()

