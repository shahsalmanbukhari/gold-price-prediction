#!/bin/bash
# Simple wrapper to run Streamlit dashboard
# Usage: ./run_dashboard_simple.sh

echo "🚀 Starting Gold Price Prediction Dashboard..."
echo ""

cd /Users/developer/PycharmProjects/GoldPricePredicton

# Activate virtual environment
source .venv/bin/activate

# Check if streamlit is installed
if ! .venv/bin/python -c "import streamlit" 2>/dev/null; then
    echo "📦 Installing required packages..."
    .venv/bin/pip install streamlit plotly streamlit-autorefresh -q
fi

echo "✅ Starting dashboard..."
echo "📍 Access at: http://localhost:8501"
echo "⚠️  Press Ctrl+C to stop"
echo ""

# Run streamlit using python module
.venv/bin/python -m streamlit run app/streamlit_app.py

