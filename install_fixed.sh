#!/bin/bash
# Fixed installation script with proper dependency resolution
# Installs packages in correct order to avoid conflicts

set -e

echo "=============================================="
echo "Gold Price Prediction - Fixed Installation"
echo "=============================================="
echo ""

cd /Users/developer/PycharmProjects/GoldPricePredicton

# Check virtual environment
if [ ! -d ".venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

echo "Activating virtual environment..."
source .venv/bin/activate

echo "Upgrading pip, setuptools, and wheel..."
pip install --upgrade pip setuptools wheel -q

echo ""
echo "Installing dependencies in phases..."
echo ""

# Phase 1: Core dependencies (no conflicts)
echo "Phase 1/5: Core dependencies..."
pip install numpy==1.26.2 -q
pip install pandas==2.1.4 -q
echo "✓ Core installed"

# Phase 2: ML libraries
echo "Phase 2/5: Machine learning libraries..."
pip install scikit-learn==1.3.2 -q
pip install xgboost==2.0.3 -q
pip install joblib==1.3.2 -q
echo "✓ ML libraries installed"

# Phase 3: Data collection
echo "Phase 3/5: Data collection..."
pip install requests==2.31.0 -q
pip install yfinance==0.2.33 -q
pip install python-dateutil==2.8.2 -q
echo "✓ Data collection installed"

# Phase 4: Real-time system
echo "Phase 4/5: Real-time system..."
pip install finnhub-python==2.4.19 -q
pip install websockets==12.0 -q
pip install redis==5.0.1 -q
pip install sqlalchemy==2.0.23 -q
pip install python-dotenv==1.0.0 -q
pip install loguru==0.7.2 -q
echo "✓ Real-time system installed"

# Phase 5: Dashboard
echo "Phase 5/5: Dashboard and visualization..."
pip install plotly==5.18.0 -q
pip install streamlit==1.29.0 -q
echo "✓ Dashboard installed"

# Phase 6: Optional packages (non-critical)
echo ""
echo "Installing optional packages..."
pip install ta==0.11.0 -q 2>/dev/null || echo "⚠ ta skipped"
pip install matplotlib==3.8.2 -q 2>/dev/null || echo "⚠ matplotlib skipped"
pip install seaborn==0.13.0 -q 2>/dev/null || echo "⚠ seaborn skipped"

echo ""
echo "=============================================="
echo "✅ Installation Complete!"
echo "=============================================="
echo ""
echo "Installed packages:"
pip list | grep -E "streamlit|pandas|numpy|finnhub|plotly|scikit-learn|xgboost"
echo ""
echo "Next steps:"
echo "1. Configure .env file"
echo "2. Run: python scripts/init_db.py"
echo "3. Run: python -m streamlit run app/streamlit_app.py"
echo ""

