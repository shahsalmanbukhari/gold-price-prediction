# 🚀 HOW TO RUN THE PROJECT

## Quick Start Guide - Gold Price Prediction (USD + PKR)

---

## ✅ Prerequisites Check

Your project is **already set up and trained**! All models and data files are ready.

### Verify Installation:
```bash
cd /Users/developer/PycharmProjects/GoldPricePredicton

# Check Python version (should be 3.8+)
python --version

# Verify virtual environment is active
which python
# Should show: /Users/developer/PycharmProjects/GoldPricePredicton/.venv/bin/python
```

---

## 🎯 THREE WAYS TO RUN THE PROJECT

### **Option 1: Launch the Dashboard (RECOMMENDED)** ⭐

This is the easiest way to see everything working!

```bash
cd /Users/developer/PycharmProjects/GoldPricePredicton

# Activate virtual environment (if not already active)
source .venv/bin/activate

# Launch Streamlit dashboard
streamlit run app/streamlit_app.py
```

**What happens:**
1. Browser opens at http://localhost:8501
2. You see the Gold Price Prediction Dashboard
3. Use the sidebar to:
   - Select currency (PKR or USD)
   - Choose model (Linear Regression or Random Forest)
4. View predictions, charts, and statistics

**To stop:** Press `Ctrl+C` in terminal

---

### **Option 2: Make Predictions via Python**

Get predictions programmatically:

```bash
cd /Users/developer/PycharmProjects/GoldPricePredicton

# Activate virtual environment
source .venv/bin/activate

# Run prediction script
python src/predict.py
```

**Expected Output:**
```
============================================================
GOLD PRICE PREDICTION (USD + PKR)
============================================================

============================================================
PKR PREDICTION (Linear Regression)
============================================================
Latest Date: 2025-11-27
Latest Price: PKR 252,611.82 per tola

Prediction for: 2025-11-28
Predicted Price: PKR [calculated] per tola
Expected Change: PKR [calculated] (+X.XX%)

============================================================
USD PREDICTION (Linear Regression)
============================================================
Latest Date: 2025-11-27
Latest Price: $2,677.15 per oz

Prediction for: 2025-11-28
Predicted Price: $[calculated] per oz
Expected Change: $[calculated] (+X.XX%)
```

---

### **Option 3: Use in Your Own Python Code**

```python
# In Python console, Jupyter, or your script
from src.predict import GoldPricePredictor

# Initialize predictor
predictor = GoldPricePredictor()

# Get predictions for both currencies
results = predictor.predict_both_currencies('linear_regression')

# Access PKR prediction
pkr_pred = results['PKR']
print(f"Next-day PKR: {pkr_pred['predicted_price']:,.2f} per tola")
print(f"Change: {pkr_pred['price_change_pct']:+.2f}%")

# Access USD prediction
usd_pred = results['USD']
print(f"Next-day USD: ${usd_pred['predicted_price']:,.2f} per oz")
print(f"Change: {usd_pred['price_change_pct']:+.2f}%")

# Or get single currency
pkr_only = predictor.predict_next_day('linear_regression', currency='PKR')
usd_only = predictor.predict_next_day('linear_regression', currency='USD')
```

---

## 🔄 IF YOU NEED TO REGENERATE DATA/MODELS

Only run these if you want to retrain from scratch:

### Full Pipeline (All Stages):
```bash
cd /Users/developer/PycharmProjects/GoldPricePredicton
source .venv/bin/activate

# Stage 1: Generate new data
python src/data_loader.py

# Stage 2: Preprocess data
python src/preprocessing.py

# Stage 3: Create features
python src/features.py

# Stage 4: Train models (takes ~2 minutes)
python src/train.py

# Stage 5: Test predictions
python src/predict.py
```

### Individual Stages:

**Just regenerate data:**
```bash
python src/data_loader.py
```

**Just retrain models:**
```bash
python src/train.py
```

**Just test predictions:**
```bash
python src/predict.py
```

---

## 📊 WHAT YOU'LL SEE IN THE DASHBOARD

### **Sidebar (Left):**
```
⚙️ Settings
─────────────────
Select Currency:
  ● PKR
  ○ USD
─────────────────
Select Model:
  Linear Regression ▼
```

### **Main Tabs:**

**1. 📈 Prediction Tab:**
- Current gold price
- Next-day prediction
- Expected change (amount and %)
- Price per gram conversion

**2. 📊 Historical Data Tab:**
- Interactive chart (last 180 days)
- Statistics (mean, median, min, max)
- Data table view

**3. ℹ️ Model Info Tab:**
- Model descriptions
- Performance metrics
- Feature explanations

---

## 🐛 TROUBLESHOOTING

### Issue: "Command not found: streamlit"
```bash
# Solution: Install Streamlit
pip install streamlit plotly
```

### Issue: "Module not found: src.predict"
```bash
# Solution: Make sure you're in the right directory
cd /Users/developer/PycharmProjects/GoldPricePredicton
pwd  # Should show the project directory
```

### Issue: "Model not found"
```bash
# Solution: Check if models exist
ls -l models/*.pkl

# If missing, retrain:
python src/train.py
```

### Issue: Virtual environment not activated
```bash
# Activate it:
source .venv/bin/activate

# You should see (.venv) in your prompt
```

### Issue: Dashboard shows errors
```bash
# Check if data files exist:
ls -l data/processed/*.csv

# If missing, run preprocessing:
python src/data_loader.py
python src/preprocessing.py
python src/features.py
```

---

## 📦 VERIFY EVERYTHING IS READY

Run this quick check:

```bash
cd /Users/developer/PycharmProjects/GoldPricePredicton

# Check models (should show 7 files)
ls -1 models/*.pkl | wc -l

# Check data files (should show 4+)
ls -1 data/processed/*.csv | wc -l

# Quick Python test
python -c "from src.predict import GoldPricePredictor; print('✓ Ready!')"
```

**Expected output:**
```
7
4
✓ Ready!
```

---

## 🎮 RECOMMENDED FIRST RUN

**For best experience, do this:**

1. **Open terminal**
2. **Navigate to project:**
   ```bash
   cd /Users/developer/PycharmProjects/GoldPricePredicton
   ```

3. **Activate environment:**
   ```bash
   source .venv/bin/activate
   ```

4. **Launch dashboard:**
   ```bash
   streamlit run app/streamlit_app.py
   ```

5. **In browser (http://localhost:8501):**
   - Try PKR predictions
   - Switch to USD
   - Change models
   - Explore historical charts
   - View statistics

6. **When done, press `Ctrl+C` to stop**

---

## 📚 FILES REFERENCE

### Code Files:
- `src/data_loader.py` - Data collection
- `src/preprocessing.py` - Data cleaning
- `src/features.py` - Feature engineering
- `src/train.py` - Model training
- `src/predict.py` - Make predictions
- `app/streamlit_app.py` - Dashboard

### Data Files:
- `data/raw/gold_prices_usd_pkr_sample.csv` - Raw data
- `data/processed/merged_clean.csv` - Cleaned data
- `data/processed/features_usd_pkr.csv` - Featured data

### Model Files:
- `models/linear_regression_pkr_model.pkl` - PKR model ⭐
- `models/linear_regression_usd_model.pkl` - USD model ⭐
- `models/random_forest_pkr_model.pkl` - PKR RF
- `models/random_forest_usd_model.pkl` - USD RF
- `models/scaler.pkl` - Feature scaler

---

## 🎯 COMMON COMMANDS

```bash
# Navigate to project
cd /Users/developer/PycharmProjects/GoldPricePredicton

# Activate environment
source .venv/bin/activate

# Run dashboard
streamlit run app/streamlit_app.py

# Make predictions
python src/predict.py

# Retrain models
python src/train.py

# Check what's running
ps aux | grep streamlit

# Kill dashboard
# Press Ctrl+C in terminal where it's running
```

---

## ✅ SUCCESS CHECKLIST

- [ ] I'm in the project directory
- [ ] Virtual environment is activated (see `.venv` in prompt)
- [ ] I ran `streamlit run app/streamlit_app.py`
- [ ] Browser opened to http://localhost:8501
- [ ] I can see the Gold Price Prediction Dashboard
- [ ] Currency selector works (PKR/USD)
- [ ] Predictions display correctly
- [ ] Charts show historical data

**If all checked, you're good to go!** 🎉

---

## 🆘 NEED HELP?

**Quick checks:**
```bash
# Verify Python
python --version  # Should be 3.8+

# Verify in correct directory
pwd  # Should end with /GoldPricePredicton

# Check dependencies
pip list | grep -E "(streamlit|pandas|sklearn)"

# Test import
python -c "import streamlit; print('Streamlit OK')"
```

**Still having issues?**
1. Check error messages carefully
2. Verify you're in the right directory
3. Make sure virtual environment is active
4. Check if models/data files exist
5. Try regenerating with `python src/train.py`

---

## 🎊 YOU'RE READY!

Your project is **100% operational**. Just run:

```bash
streamlit run app/streamlit_app.py
```

And enjoy your dual-currency gold price prediction system! 🚀

**Pro Tip:** Keep the dashboard running and switch between currencies to see live updates!

---

**Quick Start:** `cd /Users/developer/PycharmProjects/GoldPricePredicton && streamlit run app/streamlit_app.py`

