# 💰 Gold Price Prediction - ML Project

A comprehensive machine learning project for predicting next-day gold prices in **both USD and PKR** (Pakistani Rupees per tola / US Dollars per troy ounce).

![Python](https://img.shields.io/badge/Python-3.8%2B-blue)
![License](https://img.shields.io/badge/License-MIT-green)
![Status](https://img.shields.io/badge/Status-Active-success)
![USD Support](https://img.shields.io/badge/USD-Supported-gold)
![PKR Support](https://img.shields.io/badge/PKR-Supported-green)

## 📋 Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Project Structure](#project-structure)
- [Installation](#installation)
- [Usage](#usage)
- [Models](#models)
- [Results](#results)
- [Dashboard](#dashboard)
- [Contributing](#contributing)
- [License](#license)

## 🎯 Overview

This project predicts next-day gold prices in **both USD and PKR** using historical data and machine learning models. It includes:

- **Dual Currency Support:** Predict in USD (per ounce) AND PKR (per tola)
- **Data Collection:** Automated download of 5+ years of gold prices + USD/PKR exchange rates
- **Feature Engineering:** 103 technical indicators (46 PKR + 46 USD + 9 time-based)
- **Multiple Models:** Linear Regression, Random Forest (separate models for each currency)
- **Interactive Dashboard:** Streamlit web app with currency selector
- **Comprehensive Evaluation:** RMSE, MAE, MAPE, and R² metrics for both currencies

## ✨ Features

### Technical Indicators
- **RSI (Relative Strength Index):** 14-period momentum oscillator
- **MACD (Moving Average Convergence Divergence):** Trend-following indicator
- **Bollinger Bands:** Volatility bands with upper/lower bounds
- **EMA (Exponential Moving Average):** 7, 14, and 30-day periods
- **Momentum Indicators:** 5, 10, and 20-day rate of change
- **Volatility Measures:** Rolling standard deviation of returns

### Lag Features
- Previous 1-14 days' closing prices
- Captures short-term patterns and trends

### Rolling Statistics
- Moving averages: 3, 7, 14, 30 days
- Rolling standard deviation, min, and max
- Helps identify trends and volatility

### Time-Based Features
- Day of week, month, quarter, year
- Cyclical encoding (sin/cos) for periodic patterns

## 📁 Project Structure

```
FakeTransectionDetection/
├── data/
│   ├── raw/                    # Raw downloaded data
│   │   ├── gold_prices_yahoo.csv
│   │   └── gold_prices_sample.csv
│   └── processed/              # Cleaned and featured data
│       ├── gold_prices_clean.csv
│       ├── gold_prices_featured.csv
│       └── feature_list.txt
├── src/
│   ├── data_loader.py          # Data download and collection
│   ├── preprocessing.py        # Data cleaning and preprocessing
│   ├── features.py             # Feature engineering
│   ├── train.py                # Model training
│   ├── evaluate.py             # Model evaluation
│   └── predict.py              # Prediction module
├── notebooks/                  # Jupyter notebooks (optional)
├── models/                     # Trained model files
│   ├── linear_regression_model.pkl
│   ├── random_forest_model.pkl
│   ├── xgboost_model.pkl
│   └── scaler.pkl
├── app/
│   └── streamlit_app.py        # Interactive web dashboard
├── reports/                    # Evaluation reports and plots
│   ├── model_comparison.csv
│   ├── linear_regression_predictions.png
│   ├── linear_regression_residuals.png
│   └── random_forest_feature_importance.png
├── requirements.txt            # Python dependencies
└── README.md                   # This file
```

## 🚀 Installation

### Prerequisites
- Python 3.8 or higher
- pip package manager

### Setup

1. **Clone the repository:**
```bash
cd /Users/developer/PycharmProjects/GoldPricePredicton
```

2. **Create virtual environment (optional but recommended):**
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. **Install dependencies:**
```bash
pip install -r requirements.txt
```

## 📖 Usage

### Step 1: Data Collection
Download historical gold price data:

```bash
python src/data_loader.py
```

**Output:** `data/raw/gold_prices_yahoo.csv` (or sample data if download fails)

### Step 2: Data Preprocessing
Clean and prepare the data:

```bash
python src/preprocessing.py
```

**Output:** `data/processed/gold_prices_clean.csv`

### Step 3: Feature Engineering
Create technical indicators and features:

```bash
python src/features.py
```

**Output:** `data/processed/gold_prices_featured.csv` with 56+ features

### Step 4: Model Training
Train multiple machine learning models:

```bash
python src/train.py
```

**Models Trained:**
- Linear Regression
- Random Forest (100 trees, max_depth=10)
- XGBoost (100 estimators, max_depth=6)

**Output:** Trained models saved in `models/` directory

### Step 5: Model Evaluation
Evaluate models on test set:

```bash
python src/evaluate.py
```

**Output:** 
- Performance metrics in `reports/model_comparison.csv`
- Visualization plots in `reports/` directory

### Step 6: Make Predictions
Predict next-day gold price:

```bash
python src/predict.py
```

### Step 7: Launch Dashboard
Run the interactive Streamlit web app:

```bash
streamlit run app/streamlit_app.py
```

Access the dashboard at: `http://localhost:8501`

## 🤖 Models

### 1. Linear Regression
- **Type:** Statistical regression model
- **Advantages:** Fast training, interpretable coefficients
- **Best for:** Baseline predictions, linear trends

### 2. Random Forest
- **Type:** Ensemble of decision trees
- **Parameters:** 100 estimators, max_depth=10
- **Advantages:** Handles non-linear relationships, robust to outliers
- **Best for:** Feature importance analysis, complex patterns

### 3. XGBoost (Optional)
- **Type:** Gradient boosting framework
- **Parameters:** 100 estimators, max_depth=6, learning_rate=0.1
- **Advantages:** High performance, handles missing values
- **Best for:** Competitive accuracy, large datasets

## 📊 Results

### Dataset Statistics
- **Total Records:** 1,795 (after feature engineering)
- **Date Range:** 5 years of daily data
- **Train/Val/Test Split:** 70% / 15% / 15% (time-series split, no shuffling)

### Model Performance (Test Set)

| Model             | RMSE (PKR) | MAE (PKR) | MAPE (%) | R²     |
|-------------------|------------|-----------|----------|--------|
| Linear Regression | 2,656.20   | ~2,100    | ~1.0%    | 0.9693 |
| Random Forest     | 8,610.46   | ~6,500    | ~3.0%    | 0.6775 |

**Best Model:** Linear Regression (lowest RMSE)

### Key Insights
- Linear Regression performs best on this dataset due to strong linear trends in gold prices
- Random Forest shows overfitting (Train RMSE: 1,085 vs Val RMSE: 8,610)
- Technical indicators (RSI, MACD) and lag features are most important predictors

## 🎨 Dashboard

The Streamlit dashboard provides:

### Features
✅ **Real-time Predictions:** Select model and get instant next-day price forecast  
✅ **Historical Charts:** Interactive Plotly visualizations of gold price trends  
✅ **Model Comparison:** View performance metrics for all models  
✅ **Price Conversions:** Automatic per-gram calculations  
✅ **Statistics:** Mean, median, min, max prices for selected date range  

### Screenshots

![Dashboard Preview](https://via.placeholder.com/800x400.png?text=Gold+Price+Prediction+Dashboard)

## 🔧 Configuration

### Hyperparameter Tuning

Edit `src/train.py` to adjust model parameters:

```python
# Random Forest
model = RandomForestRegressor(
    n_estimators=100,      # Number of trees
    max_depth=10,          # Maximum tree depth
    random_state=42
)

# XGBoost
model = xgb.XGBRegressor(
    n_estimators=100,      # Number of boosting rounds
    max_depth=6,           # Maximum tree depth
    learning_rate=0.1,     # Step size shrinkage
    random_state=42
)
```

### Feature Engineering

Edit `src/features.py` to add/remove features:

```python
# Add more lag features
df = self.add_lag_features(df, max_lag=20)  # Increase from 14 to 20

# Add custom rolling windows
df = self.add_rolling_features(df, windows=[5, 10, 20, 50])
```

## 📈 Future Improvements

- [ ] Add LSTM/GRU neural network models for sequence prediction
- [ ] Incorporate external features (USD/PKR exchange rate, international gold prices)
- [ ] Implement ensemble methods (stacking, voting)
- [ ] Add real-time data updates via APIs
- [ ] Deploy dashboard to cloud (Heroku, AWS, Streamlit Cloud)
- [ ] Add model retraining pipeline with new data
- [ ] Implement hyperparameter optimization (GridSearch, Optuna)
- [ ] Add confidence intervals for predictions

## 🧪 Testing

Run unit tests (if implemented):

```bash
pytest tests/
```

## 📝 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🤝 Contributing

Contributions are welcome! Please follow these steps:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 👥 Authors

- **Project Lead** - Semester ML Project

## 🙏 Acknowledgments

- Yahoo Finance for historical gold price data
- Scikit-learn, XGBoost, and Streamlit communities
- Technical analysis indicators from TA-Lib

## 📞 Contact

For questions or support, please open an issue on GitHub.

---

**⚠️ Disclaimer:** This project is for educational purposes only. Gold prices are influenced by numerous factors including global markets, geopolitical events, and currency fluctuations. Always consult financial experts before making investment decisions.

---

Made with ❤️ for Machine Learning Education

