#!/bin/bash
# Installation script for Gold Price Prediction System
# This ensures all dependencies are properly installed

set -e  # Exit on error

echo "=============================================="
echo "Installing Gold Price Prediction System"
echo "=============================================="
echo ""

# Navigate to project directory
cd /Users/developer/PycharmProjects/GoldPricePredicton

echo "1. Checking virtual environment..."
if [ ! -d ".venv" ]; then
    echo "   Creating virtual environment..."
    python3 -m venv .venv
    echo "   ✓ Virtual environment created"
else
    echo "   ✓ Virtual environment exists"
fi

echo ""
echo "2. Activating virtual environment..."
source .venv/bin/activate
echo "   ✓ Virtual environment activated"
echo "   Python: $(which python)"

echo ""
echo "3. Upgrading pip..."
python -m pip install --upgrade pip -q
echo "   ✓ Pip upgraded"

echo ""
echo "4. Installing dependencies from requirements.txt..."
echo "   This may take a few minutes..."
pip install -r requirements.txt -q

echo ""
echo "5. Verifying critical packages..."

# Check each critical package
packages=(
    "streamlit"
    "pandas"
    "numpy"
    "finnhub-python"
    "sqlalchemy"
    "plotly"
    "loguru"
)

all_installed=true
for package in "${packages[@]}"; do
    if python -c "import ${package//-/_}" 2>/dev/null; then
        echo "   ✓ $package"
    else
        echo "   ✗ $package (failed)"
        all_installed=false
    fi
done

echo ""
if [ "$all_installed" = true ]; then
    echo "=============================================="
    echo "✅ Installation Complete!"
    echo "=============================================="
    echo ""
    echo "Streamlit location: $(which streamlit)"
    echo "Python location: $(which python)"
    echo ""
    echo "Next steps:"
    echo "1. Activate environment: source .venv/bin/activate"
    echo "2. Run dashboard: streamlit run app/streamlit_app.py"
    echo ""
else
    echo "⚠️  Some packages failed to install"
    echo "Please check the errors above"
    exit 1
fi

