# 🚀 Gold Price Prediction Platform - Setup Guide

Complete step-by-step instructions to set up and run the Gold Price Prediction Platform.

---

## 📋 Table of Contents

1. [Prerequisites](#prerequisites)
2. [Installation](#installation)
3. [Configuration](#configuration)
4. [Database Setup](#database-setup)
5. [Initial Training](#initial-training)
6. [Starting Services](#starting-services)
7. [Verification](#verification)
8. [Troubleshooting](#troubleshooting)

---

## 1. Prerequisites

### Required Software

#### Python 3.10+
```bash
# Check Python version
python3 --version

# Should output: Python 3.10.x or higher
```

#### PostgreSQL 12+
```bash
# macOS (using Homebrew)
brew install postgresql@14
brew services start postgresql@14

# Or use Postgres.app
# Download from: https://postgresapp.com/
```

#### Redis (Optional but recommended)
```bash
# macOS
brew install redis
brew services start redis

# Linux
sudo apt-get install redis-server
sudo systemctl start redis
```

---

## 2. Installation

### Step 1: Navigate to Project Directory
```bash
cd /Users/developer/PycharmProjects/GoldPricePredicton
```

### Step 2: Create Virtual Environment (REQUIRED for macOS)

**Why Virtual Environment?**
macOS and modern Python installations prevent installing packages system-wide to avoid breaking system Python. A virtual environment creates an isolated Python environment for this project.

```bash
# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
source .venv/bin/activate

# Your prompt should now show (.venv) prefix
# Example: (.venv) developer@macbook GoldPricePredicton %
```

**Important:** You MUST activate the virtual environment every time you open a new terminal:
```bash
cd /Users/developer/PycharmProjects/GoldPricePredicton
source .venv/bin/activate
```

### Step 3: Install Python Dependencies
```bash
# Make sure virtual environment is activated (you should see .venv in prompt)
# Install all required packages
pip install -r requirements.txt

# Note: Use 'pip' not 'pip3' inside virtual environment
```

**If you see "externally-managed-environment" error:**
- You forgot to activate the virtual environment
- Run: `source .venv/bin/activate`
- Then try: `pip install -r requirements.txt` again

**Key Dependencies Installed:**
- pandas, numpy (data processing)
- scikit-learn (machine learning)
- xgboost (advanced ML)
- streamlit (dashboard)
- psycopg2-binary (PostgreSQL)
- sqlalchemy (ORM)
- aiohttp (async HTTP)
- redis (caching)
- loguru (logging)
- python-dotenv (configuration)

### Step 4: Verify Installation
```bash
# Make sure virtual environment is activated
# Test imports
python -c "import pandas, numpy, sklearn, streamlit, psycopg2; print('✅ All packages installed')"
```

**Troubleshooting:**
- If imports fail, make sure virtual environment is activated: `source .venv/bin/activate`
- Check packages installed: `pip list`
- Reinstall if needed: `pip install -r requirements.txt`

---

## 3. Configuration

### Step 1: Create Environment File

```bash
# Copy example env file
cp .env.example .env

# Or create new .env file
nano .env
```

### Step 2: Configure .env File

Add the following content to `.env`:

```env
# =============================================================================
# PROVIDER CONFIGURATION
# =============================================================================

# Default provider (metalprice or finnhub)
DEFAULT_PROVIDER=metalprice

# Enable automatic failover
PROVIDER_FALLBACK_ENABLED=true

# API Keys (Get from providers)
METALPRICE_API_KEY=your_metalprice_api_key_here
FINNHUB_API_KEY=your_finnhub_api_key_here

# =============================================================================
# DATABASE CONFIGURATION
# =============================================================================

# PostgreSQL connection
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/gold_prediction

# Or use SQLite for testing (not recommended for production)
# DATABASE_URL=sqlite:///data/gold_prediction.db

# =============================================================================
# REDIS CONFIGURATION
# =============================================================================

REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0
REDIS_PASSWORD=

# =============================================================================
# REAL-TIME SETTINGS
# =============================================================================

# How often to fetch prices (seconds)
POLLING_INTERVAL=60

# Retrain interval (hours)
RETRAIN_INTERVAL_HOURS=24

# Minimum new samples before retrain
MIN_SAMPLES_FOR_RETRAIN=100

# Check interval (minutes)
CHECK_INTERVAL_MINUTES=60

# =============================================================================
# APPLICATION SETTINGS
# =============================================================================

# Environment (development, production)
ENVIRONMENT=development

# Log level (DEBUG, INFO, WARNING, ERROR)
LOG_LEVEL=INFO
```

### Step 3: Get API Keys

#### MetalpriceAPI (Primary - Required)
1. Visit: https://metalpriceapi.com/
2. Click "Sign Up" or "Get API Key"
3. Choose free tier (1,000 requests/month)
4. Copy your API key
5. Add to `.env`: `METALPRICE_API_KEY=your_key_here`

#### Finnhub (Backup - Optional)
1. Visit: https://finnhub.io/register
2. Create free account
3. Get API key from dashboard
4. Add to `.env`: `FINNHUB_API_KEY=your_key_here`

---

## 4. Database Setup

### Step 1: Create PostgreSQL Database

```bash
# Connect to PostgreSQL
psql -U postgres

# Create database
CREATE DATABASE gold_prediction;

# Grant permissions
GRANT ALL PRIVILEGES ON DATABASE gold_prediction TO postgres;

# Exit
\q
```

### Step 2: Initialize Database Schema

```bash
# Run initialization script
python3 scripts/init_db.py
```

**Expected Output:**
```
======================================================================
DATABASE INITIALIZATION
======================================================================

✅ Database engine created
✅ All tables created successfully
✅ Database initialized

Tables created:
  - prices (real-time and historical price data)
  - predictions (model predictions)
  - models (model metadata)
  - provider_status (provider health tracking)

======================================================================
✅ Database ready!
======================================================================
```

### Step 3: Run Database Migration (if upgrading)

```bash
# Add missing columns (if upgrading from older version)
python3 scripts/migrate_database.py
```

### Step 4: Verify Database

```bash
# Test connection
python3 -c "
from src.database import get_session, Price
session = get_session()
print(f'✅ Database connected')
print(f'Tables ready: {session.query(Price).count()} records')
session.close()
"
```

---

## 5. Initial Training

### Step 1: Verify Historical Data

```bash
# Check if historical data exists
ls -lh data/processed/gold_prices_featured.csv

# Should show a CSV file with ~1,795 records
```

### Step 2: Train Models on Historical Data

```bash
# Train all models (recommended first time)
python3 src/train.py
```

**Expected Output:**
```
============================================================
TRAINING LINEAR REGRESSION (USD)
============================================================
✓ Loaded 1795 samples
✓ Model trained
  - Train RMSE: 24.89
  - Val RMSE: 26.01
  - Train R²: 0.9880
  - Val R²: 0.9275

✅ Models saved to models/
============================================================
```

**Models Created:**
- `models/linear_regression_usd_model.pkl`
- `models/linear_regression_scaler.pkl`
- `models/random_forest_usd_model.pkl` (if available)
- `models/xgboost_usd_model.pkl` (if available)

### Step 3: Verify Models

```bash
# Check saved models
ls -lh models/

# Test prediction
python3 -c "
from src.predict import GoldPricePredictor
predictor = GoldPricePredictor()
predictor.load_model('linear_regression')
print('✅ Model loaded successfully')
"
```

---

## 6. Starting Services

Now start all services to run the complete system.

### Service 1: Real-Time Data Collection

**Terminal 1:**
```bash
cd /Users/developer/PycharmProjects/GoldPricePredicton

# Activate virtual environment
source .venv/bin/activate

# Start data streamer (keeps running)
python scripts/start_streamer_enhanced.py --provider metalprice --log-level INFO
```

**Expected Output:**
```
============================================================
ENHANCED GOLD PRICE STREAMER
============================================================
Symbol: XAU
Mode: auto
Preferred Provider: metalprice
============================================================
✓ Provider factory initialized
✓ Redis connected: localhost:6379
✓ MetalpriceAPI connected
🔄 Starting polling mode...
Polling every 10 seconds

💰 XAU: $4299.92 [metalprice] (Tick #1)
💰 XAU: $4299.92 [metalprice] (Tick #2)
💰 XAU: $4299.92 [metalprice] (Tick #3)
...continues every 10 seconds
```

**Keep this running** - It collects real-time data continuously.

**To run in background:**
```bash
nohup python3 scripts/start_streamer_enhanced.py --provider metalprice > logs/streamer.log 2>&1 &
echo $! > /tmp/streamer_pid.txt
```

---

### Service 2: Continuous Learning (Optional but Recommended)

**Terminal 2:**
```bash
cd /Users/developer/PycharmProjects/GoldPricePredicton

# Activate virtual environment
source .venv/bin/activate

# Start continuous learning service
python scripts/start_continuous_learning.py
```

**Expected Output:**
```
======================================================================
CONTINUOUS LEARNING SERVICE STARTED
======================================================================
Check interval: 60 minutes
Retrain interval: 24 hours
======================================================================

Performing initial training check...
Checking linear_regression...
✅ linear_regression retrained successfully!
   Total samples: 1799
   Historical: 1795
   Real-time: 4
   Val RMSE: 26.01
   Val R²: 0.9275

Waiting for next check (60 minutes)...
```

**Keep this running** - It automatically retrains models with new real-time data.

**To run in background:**
```bash
nohup python3 scripts/start_continuous_learning.py > logs/continuous_learning.log 2>&1 &
echo $! > /tmp/learning_pid.txt
```

---

### Service 3: Web Dashboard

**Terminal 3:**
```bash
cd /Users/developer/PycharmProjects/GoldPricePredicton

# Activate virtual environment
source .venv/bin/activate

# Start Streamlit dashboard
streamlit run app/streamlit_app.py
```

**Expected Output:**
```
  You can now view your Streamlit app in your browser.

  Local URL: http://localhost:8501
  Network URL: http://192.168.x.x:8501
```

**Dashboard Features:**
- Live gold price display
- Interactive price charts
- ML predictions with confidence intervals
- Technical indicators (RSI, MA, etc.)
- Model comparison
- Provider status

**Access Dashboard:**
```
http://localhost:8501
```

---

## 7. Verification

### Check All Services Are Running

```bash
# Check streamer
ps aux | grep start_streamer_enhanced

# Check continuous learning
ps aux | grep start_continuous_learning

# Check dashboard
ps aux | grep streamlit

# All should show running processes
```

### Verify Data Collection

```bash
# Check database has real-time data
python3 -c "
from src.database import get_session, Price
session = get_session()
total = session.query(Price).count()
realtime = session.query(Price).filter(Price.provider=='metalprice').count()
print(f'Total records: {total}')
print(f'Real-time records: {realtime}')
session.close()
"
```

**Expected Output:**
```
Total records: 1799+
Real-time records: 4+ (and growing)
```

### Test Real-Time Learning

```bash
# Run demo to verify complete system
python3 scripts/demo_realtime_learning.py
```

**Expected Output:**
```
================================================================================
 🚀 GOLD PRICE PREDICTION - REAL-TIME LEARNING SYSTEM DEMO
================================================================================

📊 STEP 1: Historical Data
✅ Historical data loaded: 1795 records

📡 STEP 2: Real-Time Data Collection
✅ Real-time data found: 4+ records

🔄 STEP 3: Data Merging
✅ Merged dataset: 1799+ total records

🤖 STEP 4: Model Training
✅ Model trained with BOTH historical and real-time data!

🔮 STEP 5: Price Prediction
Current Price: $4299.92
Predicted Price: $4305.23
...

✅ COMPLETE REAL-TIME LEARNING SYSTEM OPERATIONAL!
================================================================================
```

### Monitor Logs

```bash
# Watch real-time data collection
tail -f logs/streamer.log

# Watch continuous learning
tail -f logs/continuous_learning.log

# Watch dashboard
tail -f logs/streamlit.log
```

---

## 8. Troubleshooting

### Issue 1: Module Not Found

**Error:** `ModuleNotFoundError: No module named 'xxx'`

**Solution:**
```bash
# Install missing package
pip3 install xxx

# Or reinstall all
pip3 install -r requirements.txt

# Verify installation
python3 -c "import xxx; print('✅ Installed')"
```

---

### Issue 2: Database Connection Failed

**Error:** `psycopg2.OperationalError: could not connect to server`

**Solution:**
```bash
# Check PostgreSQL is running
brew services list | grep postgresql

# Start PostgreSQL
brew services start postgresql@14

# Verify connection
psql -U postgres -d gold_prediction -c "SELECT 1"

# Check DATABASE_URL in .env
cat .env | grep DATABASE_URL
```

---

### Issue 3: No Real-Time Data Collecting / "No providers available"

**Error:** 
```
ERROR | No providers available
ERROR | ❌ No providers available - cannot start streaming
WARNING | Provider metalprice connection failed
```

**This is THE MOST COMMON issue!**

**Root Cause:** Your API key is invalid, expired, or you hit the free tier limit.

**Solution:**

**Step 1: Test your API key**
```bash
# Run diagnostic script
python test_metalprice.py
```

**Step 2: Get a NEW API key**
1. Visit: https://metalpriceapi.com/
2. Sign up for a FREE account (or login)
3. Get your NEW API key from dashboard
4. Copy the key

**Step 3: Update .env file**
```bash
# Edit .env file
nano .env

# Replace the old key with your NEW key:
METALPRICE_API_KEY=your_new_api_key_here

# Save and exit (Ctrl+X, then Y, then Enter)
```

**Step 4: Test the new key**
```bash
# Test again
python test_metalprice.py

# Should show: ✅ Direct API call successful!
```

**Step 5: Restart streamer**
```bash
python scripts/start_streamer_enhanced.py --provider metalprice --log-level INFO
```

**Common API Key Issues:**
- ❌ **Expired:** Free tier keys may expire after 30 days
- ❌ **Rate Limit:** Free tier has 1,000 requests/month limit
- ❌ **Invalid:** Check for spaces or typos in .env file
- ❌ **Wrong Format:** Make sure no quotes around the key

---

### Issue 4: Models Not Training

**Error:** `FileNotFoundError: gold_prices_featured.csv`

**Solution:**
```bash
# Check historical data exists
ls -lh data/processed/

# If missing, you need historical data
# Contact project maintainer for data file

# Or use provided sample data
python3 -c "
import pandas as pd
# Generate sample data (for testing only)
dates = pd.date_range('2020-01-01', periods=1795, freq='D')
prices = 2000 + 300 * (pd.Series(range(1795)) / 1795)
df = pd.DataFrame({'Date': dates, 'Close_USD_per_oz': prices})
df.to_csv('data/processed/gold_prices_featured.csv', index=False)
print('✅ Sample data created')
"
```

---

### Issue 5: Dashboard Won't Start

**Error:** `Address already in use: Port 8501`

**Solution:**
```bash
# Check what's using port 8501
lsof -i:8501

# Kill existing process
kill -9 <PID>

# Or use different port
streamlit run app/streamlit_app.py --server.port 8502
```

---

### Issue 6: SSL Certificate Errors

**Error:** `[SSL: CERTIFICATE_VERIFY_FAILED]`

**Solution:**
```bash
# Install/update certifi
pip3 install --upgrade certifi

# Verify SSL
python3 -c "
import certifi
import ssl
print(f'Certifi: {certifi.where()}')
print('✅ SSL configured')
"

# System already handles this automatically
```

---

### Issue 7: Continuous Learning Not Retraining

**Error:** Service runs but models don't update

**Check:**
```bash
# Verify enough data collected
python3 -c "
from src.database import get_session, Price
from datetime import datetime, timedelta
session = get_session()
cutoff = datetime.now() - timedelta(days=1)
recent = session.query(Price).filter(Price.timestamp >= cutoff).count()
print(f'Recent records (24h): {recent}')
print(f'Threshold: 100')
print(f'Will retrain: {recent >= 100}')
session.close()
"

# Check last retrain time
tail logs/continuous_learning.log | grep "retrained successfully"

# Force manual retrain
python3 -c "
from src.realtime_trainer import RealtimeModelTrainer
trainer = RealtimeModelTrainer()
trainer.train_model('linear_regression', use_realtime=True)
print('✅ Manual retrain complete')
"
```

---

## 9. Production Deployment

### Using systemd (Linux)

Create service files:

**`/etc/systemd/system/gold-streamer.service`:**
```ini
[Unit]
Description=Gold Price Streamer
After=network.target postgresql.service

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/GoldPricePredicton
ExecStart=/usr/bin/python3 scripts/start_streamer_enhanced.py --provider metalprice
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**`/etc/systemd/system/gold-learning.service`:**
```ini
[Unit]
Description=Gold Price Continuous Learning
After=network.target postgresql.service gold-streamer.service

[Service]
Type=simple
User=your_user
WorkingDirectory=/path/to/GoldPricePredicton
ExecStart=/usr/bin/python3 scripts/start_continuous_learning.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

**Enable and start:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable gold-streamer gold-learning
sudo systemctl start gold-streamer gold-learning
sudo systemctl status gold-streamer gold-learning
```

---

## 10. Next Steps

After successful setup:

1. **Monitor System**
   ```bash
   # Check data collection
   tail -f logs/streamer.log
   
   # Check learning
   tail -f logs/continuous_learning.log
   
   # Check database growth
   watch 'python3 -c "from src.database import get_session, Price; s = get_session(); print(f\"Records: {s.query(Price).count()}\"); s.close()"'
   ```

2. **Access Dashboard**
   - Open: http://localhost:8501
   - Explore predictions, charts, models

3. **Wait for Data to Accumulate**
   - First 24 hours: Collecting baseline data
   - After 100+ samples: First automatic retrain
   - After 1 week: Rich real-time dataset

4. **Review Performance**
   ```bash
   # Check model performance
   python3 scripts/demo_realtime_learning.py
   ```

---

## 11. Quick Reference

### Start All Services
```bash
# Terminal 1: Data Collection
python3 scripts/start_streamer_enhanced.py --provider metalprice

# Terminal 2: Continuous Learning
python3 scripts/start_continuous_learning.py

# Terminal 3: Dashboard
streamlit run app/streamlit_app.py
```

### Stop All Services
```bash
# Stop streamer
pkill -f start_streamer_enhanced

# Stop continuous learning
pkill -f start_continuous_learning

# Stop dashboard
pkill -f streamlit
```

### Check Status
```bash
# Services running?
ps aux | grep -E "streamer|continuous_learning|streamlit" | grep -v grep

# Database records
python3 -c "from src.database import get_session, Price; s = get_session(); print(f'Records: {s.query(Price).count()}'); s.close()"

# Latest price
python3 -c "from src.database import get_session, Price; s = get_session(); latest = s.query(Price).order_by(Price.timestamp.desc()).first(); print(f'Latest: {latest.timestamp} | \${latest.price_usd:.2f}'); s.close()"
```

---

## 12. Support

### Resources
- **README.md**: Project overview
- **Logs**: Check `logs/` directory
- **Tests**: Run validation scripts in `scripts/`

### Common Commands
```bash
# Test configuration
python3 config/settings.py

# Validate providers
python3 scripts/validate_providers.py

# Test complete system
python3 scripts/demo_realtime_learning.py

# Check database
python3 scripts/init_db.py
```

---

## ✅ Setup Complete!

Your Gold Price Prediction Platform is now ready!

**System Status:**
- ✅ Dependencies installed
- ✅ Database configured
- ✅ Models trained
- ✅ Real-time collection active
- ✅ Continuous learning operational
- ✅ Dashboard online

**Access:**
- Dashboard: http://localhost:8501
- Database: postgresql://localhost:5432/gold_prediction

**Next:** Monitor the system and let it collect real-time data!

---

**Setup Guide Version**: 3.0  
**Last Updated**: December 14, 2025  
**Status**: Complete & Tested ✅

