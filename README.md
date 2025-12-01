# 💰 Gold Price Prediction System

A production-ready real-time machine learning system for predicting gold prices with Finnhub API integration, featuring dual currency support (USD & PKR), technical indicators, and a professional Streamlit dashboard.

---

## 🎯 Features

- **Real-Time Data Streaming** - Live gold prices via Finnhub WebSocket & REST API
- **Dual Currency Support** - USD (per oz) and PKR (per tola) predictions
- **Machine Learning Models** - Linear Regression, Random Forest, XGBoost
- **30+ Technical Indicators** - RSI, MACD, Bollinger Bands, SMA, EMA, and more
- **Interactive Dashboard** - Professional Streamlit UI with live charts
- **Production Ready** - Redis caching, PostgreSQL/SQLite support, error handling
- **Automatic Failover** - WebSocket to REST API switching

---

## 📊 System Architecture

```
Finnhub API (WebSocket/REST)
         ↓
    Data Handler (Validation & Cleaning)
         ↓
    Database (PostgreSQL/SQLite) + Redis Cache
         ↓
    Feature Engineering (30+ Indicators)
         ↓
    ML Models (Linear Regression, Random Forest)
         ↓
    Streamlit Dashboard (Real-Time UI)
```

---

## 🚀 Quick Start

### Prerequisites

- Python 3.8+
- Virtual environment (included)
- Finnhub API key (free tier available)

### Installation

See **SETUP.md** for detailed installation instructions.

Quick install:
```bash
cd /Users/developer/PycharmProjects/GoldPricePredicton
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 📂 Project Structure

```
GoldPricePredicton/
├── app/
│   └── streamlit_app.py          # Main dashboard
├── realtime/
│   ├── finnhub_client.py          # API client
│   ├── redis_cache.py             # Caching layer
│   ├── data_handler.py            # Data processing
│   └── streamer.py                # Real-time orchestrator
├── src/
│   ├── database.py                # Database models
│   ├── data_loader.py             # Historical data
│   ├── preprocessing.py           # Data cleaning
│   ├── features.py                # Feature engineering
│   ├── train.py                   # Model training
│   ├── predict.py                 # Predictions
│   ├── realtime_features.py       # Live features
│   └── realtime_predictor.py      # Live predictions
├── scripts/
│   ├── init_db.py                 # Database initialization
│   └── start_streamer.py          # Streamer starter
├── data/                          # Data storage
├── models/                        # Trained models
├── notebooks/                     # Jupyter notebooks
└── requirements.txt               # Dependencies
```

---

## 🎮 Usage

### 1. Configure API Key

```bash
# Edit .env file
cp .env.example .env
# Add your Finnhub API key: FINNHUB_API_KEY=your_key_here
```

Get free API key: https://finnhub.io/register

### 2. Initialize Database

```bash
python scripts/init_db.py
```

### 3. Train Models (Optional - pre-trained models included)

```bash
python src/train.py
```

### 4. Start Real-Time Streamer

```bash
python scripts/start_streamer.py
```

### 5. Launch Dashboard

```bash
python -m streamlit run app/streamlit_app.py
```

Dashboard opens at: http://localhost:8501

---

## 🤖 Machine Learning Models

### Available Models

1. **Linear Regression** (Recommended)
   - Fast predictions (<100ms)
   - High interpretability
   - Best performance: R² 0.96 (PKR), 0.87 (USD)

2. **Random Forest**
   - Handles non-linearity
   - Feature importance analysis
   - Good for complex patterns

3. **XGBoost** (Optional)
   - Gradient boosting
   - High accuracy
   - Longer training time

### Features Used (103 Total)

- **Price Features**: Open, High, Low, Close
- **Moving Averages**: SMA (7,14,30), EMA (7,14,30)
- **Technical Indicators**: RSI, MACD, Bollinger Bands
- **Momentum**: ROC (5,10,20 days)
- **Volatility**: Rolling standard deviation
- **Lag Features**: Previous 1-14 days prices
- **Time Features**: Day, month, quarter, year

---

## 📊 Dashboard Features

### 🎯 Prediction Tab
- Next-day price forecast
- Current price display
- Price change percentage
- Confidence levels
- Market outlook (Bullish/Bearish)
- Buy/Sell/Hold signals

### 📈 Historical Analysis
- Interactive candlestick charts
- Line chart option
- Date range filtering
- Statistical summaries
- CSV data export

### 🔬 Model Insights
- Performance metrics (RMSE, R², MAE)
- Feature importance
- Model comparison
- Training configuration
- Recommendations

---

## ⚙️ Configuration

### Environment Variables (.env)

```bash
# API Configuration
FINNHUB_API_KEY=your_api_key_here

# Database (choose one)
DATABASE_URL=sqlite:///data/gold_prediction.db          # SQLite
DATABASE_URL=postgresql://user:pass@localhost/golddb    # PostgreSQL

# Redis (optional)
REDIS_HOST=localhost
REDIS_PORT=6379

# Real-Time Settings
WEBSOCKET_RECONNECT_DELAY=30
POLLING_INTERVAL=10
MAX_RETRIES=5

# Dashboard Settings
AUTO_REFRESH_INTERVAL=2
DEFAULT_CURRENCY=USD
```

---

## 🔧 Advanced Usage

### Train Custom Models

```bash
# Train all models
python src/train.py

# Train specific model
python src/train.py --model linear_regression --currency usd
```

### Run Predictions

```bash
# Single prediction
python src/predict.py

# Batch predictions
python src/predict.py --batch --input data/test.csv
```

### Database Management

```bash
# Initialize database
python scripts/init_db.py

# Reset database
rm data/gold_prediction.db
python scripts/init_db.py
```

---

## 📈 Performance Metrics

### Real-Time Performance
- **Tick Processing**: 100+ ticks/second
- **WebSocket Latency**: <100ms
- **Prediction Speed**: <200ms
- **Dashboard Refresh**: 2 seconds

### Model Performance
- **Linear Regression (PKR)**: R² 0.9613, RMSE 3,062 PKR
- **Linear Regression (USD)**: R² 0.8656, RMSE $28.96
- **Random Forest (PKR)**: R² 0.0935, RMSE 14,827 PKR
- **Random Forest (USD)**: R² 0.6956, RMSE $43.58

---

## 🛠️ Development

### Run Tests

```bash
python test_system.py
```

### Code Quality

```bash
# Format code
black src/ realtime/

# Lint
flake8 src/ realtime/

# Type check
mypy src/ realtime/
```

---

## 🐛 Troubleshooting

### Issue: "streamlit: command not found"
**Solution:**
```bash
source .venv/bin/activate
python -m streamlit run app/streamlit_app.py
```

### Issue: "ModuleNotFoundError"
**Solution:**
```bash
pip install -r requirements.txt
```

### Issue: Database connection error
**Solution:**
```bash
python scripts/init_db.py
```

### Issue: Finnhub API errors
**Solution:**
- Check API key in .env
- Verify free tier limits (60 calls/min)
- Get new key: https://finnhub.io/register

---

## 📚 Documentation

- **SETUP.md** - Complete installation and configuration guide
- **API Documentation** - Finnhub: https://finnhub.io/docs/api
- **Streamlit Docs** - https://docs.streamlit.io

---

## 🤝 Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit changes (`git commit -m 'Add AmazingFeature'`)
4. Push to branch (`git push origin feature/AmazingFeature`)
5. Open Pull Request

---

## 📝 License

This project is for educational purposes.

---

## 🙏 Acknowledgments

- **Finnhub** - Real-time financial data API
- **Streamlit** - Dashboard framework
- **scikit-learn** - Machine learning library
- **Plotly** - Interactive charts

---

## 📞 Support

For detailed setup instructions, see **SETUP.md**

For issues and questions, please open a GitHub issue.

---

## 🎯 Roadmap

- [ ] Add more ML models (LSTM, Prophet)
- [ ] Multi-metal support (Silver, Platinum)
- [ ] Email/SMS alerts
- [ ] Mobile app
- [ ] Cloud deployment guide
- [ ] API endpoints for predictions

---

**Built with ❤️ for Gold Price Prediction**

**Version:** 2.0.0  
**Last Updated:** November 30, 2025  
**Status:** Production Ready ✅

