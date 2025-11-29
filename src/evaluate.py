"""
Model Evaluation Module
Evaluates trained models on test set with detailed metrics and visualizations
"""

import pandas as pd
import numpy as np
import os
import joblib
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
import matplotlib.pyplot as plt
import seaborn as sns
from datetime import datetime

# Set style for plots
sns.set_style('whitegrid')
plt.rcParams['figure.figsize'] = (12, 6)


class GoldPriceEvaluator:
    """Evaluate gold price prediction models"""

    def __init__(self, data_dir='data/processed', model_dir='models', report_dir='reports'):
        self.data_dir = data_dir
        self.model_dir = model_dir
        self.report_dir = report_dir
        os.makedirs(report_dir, exist_ok=True)

        self.models = {}
        self.scaler = None
        self.evaluation_results = {}

    def load_models(self):
        """Load all trained models"""
        print(f"\n{'='*60}")
        print("LOADING TRAINED MODELS")
        print(f"{'='*60}")

        # Load scaler
        scaler_path = os.path.join(self.model_dir, 'scaler.pkl')
        if os.path.exists(scaler_path):
            self.scaler = joblib.load(scaler_path)
            print(f"✓ Loaded scaler from: {scaler_path}")

        # Load models
        model_files = [f for f in os.listdir(self.model_dir) if f.endswith('_model.pkl')]

        for model_file in model_files:
            model_name = model_file.replace('_model.pkl', '')
            model_path = os.path.join(self.model_dir, model_file)
            self.models[model_name] = joblib.load(model_path)
            print(f"✓ Loaded {model_name} model")

        print(f"\n✓ Loaded {len(self.models)} models")

        return self.models

    def load_test_data(self, filename='gold_prices_featured.csv'):
        """Load and prepare test data"""
        print(f"\n{'='*60}")
        print("LOADING TEST DATA")
        print(f"{'='*60}")

        filepath = os.path.join(self.data_dir, filename)
        df = pd.read_csv(filepath)
        df['Date'] = pd.to_datetime(df['Date'])

        # Sort by date
        df = df.sort_values('Date').reset_index(drop=True)

        # Split (same as training: 70% train, 15% val, 15% test)
        n = len(df)
        train_end = int(n * 0.7)
        val_end = int(n * 0.85)

        test_df = df.iloc[val_end:].copy()

        print(f"✓ Test set: {len(test_df)} records")
        print(f"✓ Date range: {test_df['Date'].min().date()} to {test_df['Date'].max().date()}")

        # Prepare features
        exclude_cols = ['Date', 'target', 'Close_PKR_per_tola', 'Open_PKR_per_tola',
                       'High_PKR_per_tola', 'Low_PKR_per_tola', 'Close_PKR_per_gram',
                       'Close_USD_per_oz', 'Close_PKR_per_oz', 'Adj Close', 'Volume']

        feature_cols = [col for col in df.columns if col not in exclude_cols]

        X_test = test_df[feature_cols]
        y_test = test_df['target']

        return test_df, X_test, y_test

    def calculate_metrics(self, y_true, y_pred, model_name):
        """Calculate evaluation metrics"""
        rmse = np.sqrt(mean_squared_error(y_true, y_pred))
        mae = mean_absolute_error(y_true, y_pred)
        mape = np.mean(np.abs((y_true - y_pred) / y_true)) * 100
        r2 = r2_score(y_true, y_pred)

        metrics = {
            'Model': model_name,
            'RMSE': rmse,
            'MAE': mae,
            'MAPE (%)': mape,
            'R²': r2
        }

        return metrics

    def evaluate_model(self, model, model_name, X_test, y_test, test_df, scale=False):
        """Evaluate a single model"""
        print(f"\n{'='*60}")
        print(f"EVALUATING {model_name.upper()}")
        print(f"{'='*60}")

        # Scale if needed (Linear Regression uses scaled features)
        if scale and self.scaler is not None:
            X_test_input = self.scaler.transform(X_test)
        else:
            X_test_input = X_test

        # Make predictions
        y_pred = model.predict(X_test_input)

        # Calculate metrics
        metrics = self.calculate_metrics(y_test, y_pred, model_name)

        print(f"Test Set Performance:")
        print(f"  - RMSE: PKR {metrics['RMSE']:,.2f}")
        print(f"  - MAE: PKR {metrics['MAE']:,.2f}")
        print(f"  - MAPE: {metrics['MAPE (%)']:.2f}%")
        print(f"  - R²: {metrics['R²']:.4f}")

        # Store results
        self.evaluation_results[model_name] = {
            'metrics': metrics,
            'y_true': y_test,
            'y_pred': y_pred,
            'dates': test_df['Date'].values
        }

        return metrics, y_pred

    def plot_predictions(self, model_name, save=True):
        """Plot actual vs predicted prices"""
        if model_name not in self.evaluation_results:
            print(f"⚠ No results for {model_name}")
            return

        results = self.evaluation_results[model_name]
        y_true = results['y_true']
        y_pred = results['y_pred']
        dates = pd.to_datetime(results['dates'])

        fig, axes = plt.subplots(2, 1, figsize=(14, 10))

        # Plot 1: Time series comparison
        axes[0].plot(dates, y_true.values, label='Actual', color='blue', linewidth=2, alpha=0.7)
        axes[0].plot(dates, y_pred, label='Predicted', color='red', linewidth=2, alpha=0.7)
        axes[0].set_xlabel('Date', fontsize=12)
        axes[0].set_ylabel('Gold Price (PKR per tola)', fontsize=12)
        axes[0].set_title(f'{model_name.replace("_", " ").title()} - Actual vs Predicted', fontsize=14, fontweight='bold')
        axes[0].legend(fontsize=11)
        axes[0].grid(True, alpha=0.3)
        axes[0].tick_params(axis='x', rotation=45)

        # Plot 2: Scatter plot
        axes[1].scatter(y_true, y_pred, alpha=0.6, edgecolors='k', linewidth=0.5)
        axes[1].plot([y_true.min(), y_true.max()], [y_true.min(), y_true.max()],
                     'r--', linewidth=2, label='Perfect Prediction')
        axes[1].set_xlabel('Actual Price (PKR per tola)', fontsize=12)
        axes[1].set_ylabel('Predicted Price (PKR per tola)', fontsize=12)
        axes[1].set_title('Prediction Accuracy Scatter Plot', fontsize=14, fontweight='bold')
        axes[1].legend(fontsize=11)
        axes[1].grid(True, alpha=0.3)

        plt.tight_layout()

        if save:
            filepath = os.path.join(self.report_dir, f'{model_name}_predictions.png')
            plt.savefig(filepath, dpi=300, bbox_inches='tight')
            print(f"✓ Saved plot to: {filepath}")

        plt.close()

    def plot_residuals(self, model_name, save=True):
        """Plot residual analysis"""
        if model_name not in self.evaluation_results:
            print(f"⚠ No results for {model_name}")
            return

        results = self.evaluation_results[model_name]
        y_true = results['y_true']
        y_pred = results['y_pred']
        residuals = y_true.values - y_pred

        fig, axes = plt.subplots(1, 2, figsize=(14, 5))

        # Plot 1: Residuals over time
        dates = pd.to_datetime(results['dates'])
        axes[0].scatter(dates, residuals, alpha=0.6, edgecolors='k', linewidth=0.5)
        axes[0].axhline(y=0, color='r', linestyle='--', linewidth=2)
        axes[0].set_xlabel('Date', fontsize=12)
        axes[0].set_ylabel('Residuals (PKR)', fontsize=12)
        axes[0].set_title(f'{model_name.replace("_", " ").title()} - Residuals Over Time', fontsize=14, fontweight='bold')
        axes[0].grid(True, alpha=0.3)
        axes[0].tick_params(axis='x', rotation=45)

        # Plot 2: Residual distribution
        axes[1].hist(residuals, bins=30, edgecolor='black', alpha=0.7)
        axes[1].axvline(x=0, color='r', linestyle='--', linewidth=2)
        axes[1].set_xlabel('Residuals (PKR)', fontsize=12)
        axes[1].set_ylabel('Frequency', fontsize=12)
        axes[1].set_title('Residual Distribution', fontsize=14, fontweight='bold')
        axes[1].grid(True, alpha=0.3)

        plt.tight_layout()

        if save:
            filepath = os.path.join(self.report_dir, f'{model_name}_residuals.png')
            plt.savefig(filepath, dpi=300, bbox_inches='tight')
            print(f"✓ Saved plot to: {filepath}")

        plt.close()

    def plot_feature_importance(self, model_name, feature_cols, top_n=20, save=True):
        """Plot feature importance for tree-based models"""
        if model_name not in self.models:
            print(f"⚠ Model {model_name} not found")
            return

        model = self.models[model_name]

        # Check if model has feature_importances_
        if not hasattr(model, 'feature_importances_'):
            print(f"⚠ {model_name} does not have feature importance")
            return

        print(f"\n{'='*60}")
        print(f"FEATURE IMPORTANCE - {model_name.upper()}")
        print(f"{'='*60}")

        importances = model.feature_importances_

        # Create DataFrame
        feature_importance_df = pd.DataFrame({
            'Feature': feature_cols,
            'Importance': importances
        })

        feature_importance_df = feature_importance_df.sort_values('Importance', ascending=False)

        # Print top features
        print(f"\nTop {top_n} Most Important Features:")
        for i, row in feature_importance_df.head(top_n).iterrows():
            print(f"  {row['Feature']}: {row['Importance']:.4f}")

        # Plot
        plt.figure(figsize=(10, 8))
        top_features = feature_importance_df.head(top_n)
        plt.barh(range(len(top_features)), top_features['Importance'])
        plt.yticks(range(len(top_features)), top_features['Feature'])
        plt.xlabel('Importance', fontsize=12)
        plt.ylabel('Features', fontsize=12)
        plt.title(f'{model_name.replace("_", " ").title()} - Top {top_n} Feature Importances',
                 fontsize=14, fontweight='bold')
        plt.gca().invert_yaxis()
        plt.grid(True, alpha=0.3, axis='x')
        plt.tight_layout()

        if save:
            filepath = os.path.join(self.report_dir, f'{model_name}_feature_importance.png')
            plt.savefig(filepath, dpi=300, bbox_inches='tight')
            print(f"✓ Saved plot to: {filepath}")

        plt.close()

        # Save to CSV
        csv_path = os.path.join(self.report_dir, f'{model_name}_feature_importance.csv')
        feature_importance_df.to_csv(csv_path, index=False)
        print(f"✓ Saved feature importance to: {csv_path}")

    def create_comparison_table(self):
        """Create comparison table of all models"""
        print(f"\n{'='*60}")
        print("MODEL COMPARISON ON TEST SET")
        print(f"{'='*60}")

        comparison = []
        for model_name, results in self.evaluation_results.items():
            comparison.append(results['metrics'])

        df_comparison = pd.DataFrame(comparison)
        df_comparison = df_comparison.sort_values('RMSE')

        print("\n" + df_comparison.to_string(index=False))

        # Save comparison
        filepath = os.path.join(self.report_dir, 'test_set_evaluation.csv')
        df_comparison.to_csv(filepath, index=False)
        print(f"\n✓ Saved evaluation results to: {filepath}")

        return df_comparison

    def evaluation_pipeline(self):
        """Complete evaluation pipeline"""
        print("\n" + "="*60)
        print("GOLD PRICE PREDICTION - MODEL EVALUATION - Stage 5")
        print("="*60)

        # Load models
        self.load_models()

        # Load test data
        test_df, X_test, y_test = self.load_test_data()

        # Get feature columns
        feature_cols = list(X_test.columns)

        # Evaluate each model
        for model_name, model in self.models.items():
            # Determine if scaling is needed (Linear Regression uses scaled features)
            scale = (model_name == 'linear_regression')

            metrics, y_pred = self.evaluate_model(model, model_name, X_test, y_test, test_df, scale=scale)

            # Create visualizations
            self.plot_predictions(model_name)
            self.plot_residuals(model_name)

            # Feature importance for tree-based models
            if model_name in ['random_forest', 'xgboost']:
                self.plot_feature_importance(model_name, feature_cols, top_n=20)

        # Create comparison table
        comparison = self.create_comparison_table()

        print("\n" + "="*60)
        print("MODEL EVALUATION COMPLETE")
        print("="*60)
        print(f"✓ Evaluated {len(self.models)} models on test set")
        print(f"✓ Best model (lowest RMSE): {comparison.iloc[0]['Model']}")
        print(f"✓ Best RMSE: PKR {comparison.iloc[0]['RMSE']:,.2f}")
        print(f"✓ Best MAPE: {comparison.iloc[0]['MAPE (%)']:.2f}%")

        return self.evaluation_results, comparison


if __name__ == "__main__":
    # Run evaluation pipeline
    evaluator = GoldPriceEvaluator()

    try:
        results, comparison = evaluator.evaluation_pipeline()
        print("\n✓ Evaluation Stage 5 complete!")
        print("✓ Next step: Create Streamlit app (app/streamlit_app.py)")
    except Exception as e:
        print(f"\n✗ Error during evaluation: {e}")
        import traceback
        traceback.print_exc()

