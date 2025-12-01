# 🔧 Complete Setup Guide - Gold Price Prediction System

This guide covers everything from installation to training models and integrating with real-time data APIs.

---

## 📋 Table of Contents

1. [Prerequisites](#prerequisites)
2. [Installation](#installation)
3. [Configuration](#configuration)
4. [Database Setup](#database-setup)
5. [Training Models](#training-models)
6. [Real-Time API Integration](#real-time-api-integration)
7. [Running the System](#running-the-system)
8. [Troubleshooting](#troubleshooting)

---

## 1. Prerequisites

### System Requirements

- **Operating System**: macOS, Linux, or Windows
- **Python**: 3.8 or higher
- **RAM**: 4GB minimum, 8GB recommended
- **Disk Space**: 2GB free space

### Check Python Version

```bash
python3 --version
# Should show: Python 3.8.x or higher
```

### Install Python (if needed)

**macOS:**
```bash
brew install python@3.11
```

**Ubuntu/Debian:**
```bash
sudo apt update
sudo apt install python3.11 python3.11-venv
```

---

## 2. Installation

### Step 1: Navigate to Project

```bash
cd /Users/developer/PycharmProjects/GoldPricePredicton
```

### Step 2: Create Virtual Environment (if not exists)

```bash
python3 -m venv .venv
```

### Step 3: Activate Virtual Environment

**macOS/Linux:**
```bash
source .venv/bin/activate
```

**Windows:**
```bash
.venv\Scripts\activate
```

**Verification:** Your terminal prompt should show `(.venv)` prefix.

### Step 4: Upgrade pip

```bash
pip install --upgrade pip
```

### Step 5: Install All Dependencies

```bash
pip install -r requirements.txt
```

This installs ~50 packages including:
- Core ML: pandas, numpy, scikit-learn, xgboost
- Real-Time: finnhub-python, websockets, redis
- Database: sqlalchemy, psycopg2-binary
- Dashboard: streamlit, plotly
- Utilities: loguru, python-dotenv, pydantic

**Installation time:** 3-5 minutes depending on internet speed.

### Step 6: Verify Installation

```bash
python -c "import streamlit, pandas, finnhub; print('✓ All packages installed')"
```

Expected output: `✓ All packages installed`

---

## 3. Configuration

### Step 1: Get Finnhub API Key

1. Visit: https://finnhub.io/register
2. Sign up (free tier available)
3. Verify your email
4. Go to Dashboard
5. Copy your API key (looks like: `ck8v9n2ad3jf0pr8npkg`)

**Free Tier Limits:**
- 60 API calls per minute
- WebSocket available
- Sufficient for development and testing

### Step 2: Create Configuration File

```bash
cp .env.example .env
```

### Step 3: Edit Configuration

Open `.env` in your text editor:

```bash
nano .env
# OR
open .env
# OR
code .env
```

### Step 4: Add Your API Key

**Replace this line:**
```bash
FINNHUB_API_KEY=your_finnhub_api_key_here
```

**With your actual key:**
```bash
FINNHUB_API_KEY=ck8v9n2ad3jf0pr8npkg
```

### Step 5: Configure Database (Choose One)

#### Option A: SQLite (Recommended for Development)

**Easiest - No installation required!**

```bash
DATABASE_URL=sqlite:///data/gold_prediction.db
```

Advantages:
- ✅ No setup needed
- ✅ Single file database
- ✅ Perfect for learning/testing

#### Option B: PostgreSQL (Recommended for Production)

**Install PostgreSQL:**

**macOS:**
```bash
brew install postgresql@15
brew services start postgresql@15
createdb gold_prediction
```

**Ubuntu:**
```bash
sudo apt install postgresql postgresql-contrib
sudo -u postgres createdb gold_prediction
sudo -u postgres createuser golduser
```

**Configure in .env:**
```bash
DATABASE_URL=postgresql://golduser:password@localhost:5432/gold_prediction
```

### Step 6: Optional - Redis Configuration

Redis provides caching for better performance but is **optional**.

**Install Redis:**

**macOS:**
```bash
brew install redis
brew services start redis
```

**Ubuntu:**
```bash
sudo apt install redis-server
sudo systemctl start redis
```

**Docker:**
```bash
docker run -d --name redis-gold -p 6379:6379 redis:alpine
```

**Verify:**
```bash
redis-cli ping
# Should return: PONG
```

**Note:** System works without Redis with graceful degradation.

### Step 7: Verify Configuration

```bash
python << 'EOF'
import os
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv('FINNHUB_API_KEY')
db_url = os.getenv('DATABASE_URL')

if api_key and api_key != 'your_finnhub_api_key_here':
    print(f"✓ API Key configured: {api_key[:10]}...")
else:
    print("✗ API Key not configured")

if db_url:
    print(f"✓ Database URL: {db_url.split('://')[0]}://...")
else:
    print("✗ Database URL not configured")
EOF
```

---

## 4. Database Setup

### Step 1: Initialize Database Schema

```bash
python scripts/init_db.py
```

Expected output:
```
============================================================
DATABASE INITIALIZATION
============================================================

1. Creating database schema...
✓ Database schema initialized
✓ Schema created successfully

2. Testing connection...
✓ Connection successful

============================================================
✅ DATABASE READY
============================================================

Tables created:
  - prices (historical and real-time price data)
  - features (engineered features for ML)
  - models (ML model metadata)
  - predictions (prediction history)
```

### Step 2: Verify Database

```bash
python << 'EOF'
from src.database import get_session, Price

session = get_session()
count = session.query(Price).count()
print(f"✓ Database working. Current records: {count}")
session.close()
EOF
```

### Database Tables Created

1. **prices** - Raw tick data
   - timestamp, symbol, price_usd, volume, bid, ask, spread

2. **features** - Technical indicators
   - timestamp, symbol, SMA, EMA, RSI, MACD, Bollinger Bands, etc.

3. **models** - ML model metadata
   - model_name, version, metrics, hyperparameters, file paths

4. **predictions** - Prediction history
   - timestamp, current_price, predicted_price, confidence, bounds

---

## 5. Training Models

The system includes pre-trained models, but you can train custom models with your data.

### Step 1: Prepare Training Data

The system uses historical gold price data. Data is automatically downloaded during training.

### Step 2: Train All Models

```bash
python src/train.py
```

This trains:
- Linear Regression (PKR)
- Linear Regression (USD)
- Random Forest (PKR)
- Random Forest (USD)

**Training time:** 5-10 minutes

**Expected output:**
```
==================================================
TRAINING GOLD PRICE PREDICTION MODELS
==================================================

Loading data...
✓ Loaded 1795 records

Preprocessing...
✓ Data cleaned and preprocessed

Feature engineering...
✓ Generated 103 features

Training Linear Regression (PKR)...
✓ Model trained - R²: 0.9613, RMSE: 3062.45

Training Random Forest (PKR)...
✓ Model trained - R²: 0.0935, RMSE: 14827.31

Saving models...
✓ Models saved to models/

==================================================
✅ TRAINING COMPLETE
==================================================
```

### Step 3: Verify Trained Models

```bash
ls -lh models/
```

You should see:
```
linear_regression_pkr_model.pkl
linear_regression_usd_model.pkl
random_forest_pkr_model.pkl
random_forest_usd_model.pkl
scaler.pkl
```

### Training Options

#### Train Specific Model

```bash
python src/train.py --model linear_regression
```

#### Train for Specific Currency

```bash
python src/train.py --currency usd
```

#### Adjust Training Parameters

Edit `src/train.py` to modify:
- Train/validation/test split ratios
- Feature selection
- Model hyperparameters
- Evaluation metrics

### Model Performance Metrics

After training, check:
```bash
cat reports/model_comparison.csv
```

Metrics included:
- **RMSE** - Root Mean Squared Error
- **MAE** - Mean Absolute Error
- **MAPE** - Mean Absolute Percentage Error
- **R²** - Coefficient of Determination

---

## 6. Real-Time API Integration

### Understanding the Architecture

```
Finnhub API
    ↓ (WebSocket or REST)
finnhub_client.py (Connection management)
    ↓
data_handler.py (Validation & cleaning)
    ↓
Database + Redis (Storage & caching)
    ↓
realtime_features.py (Technical indicators)
    ↓
realtime_predictor.py (ML predictions)
    ↓
Dashboard (Real-time display)
```

### Step 1: Test Finnhub Connection

```bash
python realtime/finnhub_client.py
```

Expected output:
```
=== Testing REST API ===
✓ Current Gold Price: $2,045.50
  Change: +0.25%

=== Testing Candles ===
✓ Retrieved 5 daily candles
  Latest close: $2,045.50
```

### Step 2: Start Real-Time Streamer

**Terminal 1 - Start Streamer:**

```bash
python scripts/start_streamer.py
```

Expected output:
```
============================================================
GOLD PRICE REAL-TIME STREAMER
============================================================
Started at: 2025-11-30 10:30:45
Redis available: True
============================================================
✓ WebSocket connected to Finnhub
✓ Subscribed to OANDA:XAU_USD
```

**The streamer will:**
1. Connect to Finnhub WebSocket
2. Receive real-time gold price ticks
3. Validate and clean data
4. Store in database
5. Cache in Redis
6. Generate features
7. Make predictions

**Keep this running in the background!**

### Step 3: Monitor Streamer

Press `Ctrl+C` to see statistics:

```
============================================================
STREAMER STATISTICS
============================================================
Uptime: 300.45 seconds
Connection mode: websocket
Ticks processed: 150
Ticks stored: 150
Success rate: 100.00%
============================================================
```

### Streamer Failover Behavior

The system automatically handles failures:

1. **WebSocket Primary** - Real-time streaming
2. **REST Fallback** - If WebSocket fails, switches to polling
3. **Exponential Backoff** - Retries with increasing delays
4. **Graceful Degradation** - Works without Redis

### Step 4: Verify Data Collection

```bash
python << 'EOF'
from src.database import get_session, Price

session = get_session()
latest = session.query(Price).order_by(Price.timestamp.desc()).first()

if latest:
    print(f"✓ Latest price: ${latest.price_usd:.2f}")
    print(f"  Symbol: {latest.symbol}")
    print(f"  Timestamp: {latest.timestamp}")
else:
    print("No data collected yet. Wait a few seconds.")

session.close()
EOF
```

---

## 7. Running the System

### Complete Startup Sequence

#### Terminal 1: Start Streamer

```bash
cd /Users/developer/PycharmProjects/GoldPricePredicton
source .venv/bin/activate
python scripts/start_streamer.py
```

Keep this running to collect real-time data.

#### Terminal 2: Start Dashboard

```bash
cd /Users/developer/PycharmProjects/GoldPricePredicton
source .venv/bin/activate
python -m streamlit run app/streamlit_app.py
```

Or use the helper script:
```bash
bash run_dashboard_simple.sh
```

### Dashboard Opens Automatically

Browser opens to: **http://localhost:8501**

### Dashboard Features

**🎯 Prediction Tab:**
- Live gold price
- Next-day forecast
- Confidence bands
- Buy/Sell/Hold signals
- Market outlook

**📊 Historical Analysis:**
- Interactive candlestick charts
- Date range filtering
- Statistical summaries
- CSV export

**🔬 Model Insights:**
- Performance metrics
- Model comparison
- Feature importance
- Training details

### Stop the System

**Stop Dashboard:**
- Press `Ctrl+C` in Terminal 2

**Stop Streamer:**
- Press `Ctrl+C` in Terminal 1

---

## 8. Troubleshooting

### Issue: "streamlit: command not found"

**Solution:**
```bash
source .venv/bin/activate
python -m streamlit run app/streamlit_app.py
```

### Issue: "ModuleNotFoundError: No module named 'finnhub'"

**Solution:**
```bash
pip install finnhub-python websockets redis sqlalchemy
```

### Issue: "ValueError: FINNHUB_API_KEY not found"

**Solution:**
1. Check `.env` file exists
2. Verify API key is set correctly
3. No spaces around `=` sign
4. Restart terminal after editing

### Issue: Database connection error

**Solution:**
```bash
# Reset database
rm data/gold_prediction.db
python scripts/init_db.py
```

### Issue: WebSocket connection failed

**Solution:**
1. Check internet connection
2. Verify API key is valid
3. Check Finnhub service status
4. System will auto-fallback to REST API

### Issue: Redis connection warnings

**Not a problem!** System works without Redis.

**To install Redis (optional):**
```bash
# macOS
brew install redis
brew services start redis

# Ubuntu
sudo apt install redis-server
```

### Issue: Import errors in streamer

**Solution:**
```bash
cd /Users/developer/PycharmProjects/GoldPricePredicton
source .venv/bin/activate
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
python scripts/start_streamer.py
```

### Issue: Dashboard shows "No data"

**Solution:**
1. Ensure streamer is running
2. Wait 30 seconds for data collection
3. Check database has records:
   ```bash
   python -c "from src.database import *; s=get_session(); print(s.query(Price).count())"
   ```

### Issue: Models not found

**Solution:**
```bash
python src/train.py
```

---

## 📊 Quick Command Reference

### Daily Usage

```bash
# Activate environment
source .venv/bin/activate

# Start streamer (Terminal 1)
python scripts/start_streamer.py

# Start dashboard (Terminal 2)
python -m streamlit run app/streamlit_app.py
```

### Maintenance

```bash
# Update dependencies
pip install -r requirements.txt --upgrade

# Retrain models
python src/train.py

# Reset database
rm data/gold_prediction.db
python scripts/init_db.py

# Run tests
python test_system.py
```

### Monitoring

```bash
# Check database records
python -c "from src.database import *; s=get_session(); print(f'Records: {s.query(Price).count()}')"

# Check Redis
redis-cli ping

# Check model files
ls -lh models/
```

---

## ✅ Installation Checklist

- [ ] Python 3.8+ installed
- [ ] Virtual environment created
- [ ] Dependencies installed (`pip install -r requirements.txt`)
- [ ] Finnhub API key obtained
- [ ] `.env` file configured
- [ ] Database initialized (`python scripts/init_db.py`)
- [ ] Models trained (`python src/train.py`)
- [ ] Streamer tested (`python realtime/finnhub_client.py`)
- [ ] Dashboard working (`python -m streamlit run app/streamlit_app.py`)

---

## 🎓 Next Steps

1. **Explore Dashboard** - Try all features and tabs
2. **Monitor Real-Time Data** - Watch streamer collect data
3. **Analyze Predictions** - Compare with actual prices
4. **Customize Models** - Adjust parameters in `src/train.py`
5. **Add Features** - Extend with your own indicators
6. **Deploy** - Consider cloud deployment for 24/7 operation

---

## 📚 Additional Resources

- **Finnhub API Docs**: https://finnhub.io/docs/api
- **Streamlit Docs**: https://docs.streamlit.io
- **scikit-learn**: https://scikit-learn.org/stable/
- **Plotly**: https://plotly.com/python/

---

## 🆘 Getting Help

1. Check this guide thoroughly
2. Review error messages carefully
3. Verify all configuration steps
4. Check system requirements
5. Ensure API key is valid
6. Try complete reinstallation if needed

---

## 🎉 Success!

If you've completed all steps, you now have:
- ✅ Real-time gold price streaming
- ✅ Machine learning predictions
- ✅ Professional dashboard
- ✅ Production-ready system

**Enjoy your Gold Price Prediction System!** 💰

---

**Setup Guide Version:** 1.0  
**Last Updated:** November 30, 2025  
**System Status:** Production Ready ✅

