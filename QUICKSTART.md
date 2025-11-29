# 🚀 Quick Start Guide - Gold Price Prediction

## ⚡ Fast Setup (5 minutes)

### Step 1: Verify Installation
```bash
cd /Users/developer/PycharmProjects/GoldPricePredicton
python --version  # Should be 3.8+
```

### Step 2: Activate Virtual Environment
```bash
source .venv/bin/activate  # Already activated
```

### Step 3: Verify Dependencies
```bash
pip list | grep -E "(pandas|scikit-learn|streamlit)"
```

✅ **Already Installed:** pandas, numpy, scikit-learn, matplotlib, seaborn, xgboost, joblib, streamlit, plotly, yfinance

---

## 🎯 Run the Complete Pipeline

### Option A: Run All Steps Individually

```bash
# Step 1: Download data (already done ✓)
python src/data_loader.py

# Step 2: Preprocess data (already done ✓)
python src/preprocessing.py

# Step 3: Engineer features (already done ✓)
python src/features.py

# Step 4: Train models (already done ✓)
python src/train.py

# Step 5: Evaluate models (optional)
python src/evaluate.py

# Step 6: Make predictions (already done ✓)
python src/predict.py
```

### Option B: Launch Dashboard Directly

```bash
streamlit run app/streamlit_app.py
```

**Access at:** http://localhost:8501

---

## 📊 Current Project Status

✅ **Data Collection:** 1,826 records (5 years)  
✅ **Data Preprocessing:** Clean dataset with 1,826 records  
✅ **Feature Engineering:** 56 features created (1,795 records after NaN removal)  
✅ **Model Training:** 2 models trained (Linear Regression, Random Forest)  
✅ **Model Evaluation:** Best model = Linear Regression (RMSE: 2,656 PKR)  
✅ **Prediction Module:** Working predictions available  
✅ **Dashboard:** Streamlit app ready to launch  

---

## 🔮 Make a Prediction Now

```python
# In Python shell or notebook
from src.predict import GoldPricePredictor

predictor = GoldPricePredictor()
result = predictor.predict_next_day('linear_regression')

print(f"Next-Day Prediction: PKR {result['predicted_price']:,.2f}")
print(f"Expected Change: {result['price_change_pct']:+.2f}%")
```

**Current Prediction (as of 2025-11-27):**
- Model: Linear Regression
- Predicted Price: **PKR 249,307.44** per tola
- Expected Change: **+1,190.85 PKR (+0.48%)**

---

## 📁 Key Files

| File | Description | Status |
|------|-------------|--------|
| `data/raw/gold_prices_sample.csv` | Raw gold price data | ✅ Ready |
| `data/processed/gold_prices_clean.csv` | Cleaned data | ✅ Ready |
| `data/processed/gold_prices_featured.csv` | Data with 56 features | ✅ Ready |
| `models/linear_regression_model.pkl` | Trained Linear Regression | ✅ Ready |
| `models/random_forest_model.pkl` | Trained Random Forest | ✅ Ready |
| `models/scaler.pkl` | Feature scaler | ✅ Ready |
| `reports/model_comparison.csv` | Model performance | ✅ Ready |
| `reports/FINAL_PROJECT_REPORT.md` | Complete documentation | ✅ Ready |

---

## 🎨 Dashboard Features

Launch with: `streamlit run app/streamlit_app.py`

**Available Tabs:**
1. **📈 Prediction** - Get next-day price forecast
2. **📊 Historical Data** - Interactive charts and statistics
3. **ℹ️ Model Info** - Technical details and performance metrics

**Features:**
- Switch between Linear Regression and Random Forest
- View historical price trends with date range selection
- See price per tola and per gram
- Compare model performance metrics

---

## 📈 Model Performance Summary

### Linear Regression (Recommended)
- **Validation RMSE:** 2,656 PKR
- **Validation R²:** 0.9693
- **MAPE:** ~1.0%
- **Best for:** Stable predictions, production use

### Random Forest
- **Validation RMSE:** 8,610 PKR
- **Validation R²:** 0.6775
- **MAPE:** ~3.0%
- **Note:** Shows overfitting, needs tuning

---

## 🔧 Troubleshooting

### Issue: Models not found
```bash
# Re-train models
python src/train.py
```

### Issue: Data not found
```bash
# Re-download and preprocess
python src/data_loader.py
python src/preprocessing.py
python src/features.py
```

### Issue: Streamlit won't start
```bash
# Check installation
pip install streamlit plotly
streamlit run app/streamlit_app.py
```

### Issue: XGBoost errors
XGBoost is optional. The project works fine with Linear Regression and Random Forest.

---

## 📚 Learn More

- **Full Report:** `reports/FINAL_PROJECT_REPORT.md`
- **README:** `README.md`
- **Feature List:** `data/processed/feature_list.txt`
- **Cleaning Report:** `data/processed/cleaning_report.txt`

---

## 🎓 For Presentation/Demo

### Demo Script (5 minutes)

1. **Show Data Collection** (30 sec)
   ```bash
   cat data/raw/gold_prices_sample.csv | head -10
   ```

2. **Show Feature Engineering** (30 sec)
   ```bash
   cat data/processed/feature_list.txt | head -20
   ```

3. **Show Model Performance** (1 min)
   ```bash
   cat reports/model_comparison.csv
   ```

4. **Make Live Prediction** (1 min)
   ```bash
   python src/predict.py
   ```

5. **Launch Dashboard** (2 min)
   ```bash
   streamlit run app/streamlit_app.py
   # Show all 3 tabs, change models, adjust date range
   ```

---

## 💡 Next Steps (Optional)

### Improve Random Forest
```python
# Edit src/train.py, line ~120
# Change: max_depth=10 to max_depth=5
# Re-run: python src/train.py
```

### Add More Data
```python
# Edit src/data_loader.py, line ~170
# Change: years=5 to years=10
# Re-run full pipeline
```

### Deploy to Cloud
```bash
# Streamlit Cloud (free)
# 1. Push to GitHub
# 2. Visit share.streamlit.io
# 3. Connect your repo
```

---

## ✅ Verification Checklist

- [x] Data downloaded (1,826 records)
- [x] Data preprocessed (no missing values)
- [x] Features engineered (56 features)
- [x] Models trained (2 models)
- [x] Models evaluated
- [x] Predictions working
- [x] Dashboard ready
- [x] Documentation complete

---

**🎉 Project Complete! Ready for Presentation/Submission**

**Questions?** Review `reports/FINAL_PROJECT_REPORT.md` for comprehensive documentation.

