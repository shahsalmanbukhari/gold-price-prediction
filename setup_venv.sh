#!/bin/bash
# Quick Setup Script for Gold Price Prediction Platform
# Fixes the "externally-managed-environment" error on macOS

echo "================================================================================"
echo "🚀 Gold Price Prediction Platform - Quick Setup"
echo "================================================================================"
echo ""

# Navigate to project directory
cd "$(dirname "$0")"
PROJECT_DIR=$(pwd)

echo "📁 Project directory: $PROJECT_DIR"
echo ""

# Step 1: Create virtual environment
echo "Step 1: Creating virtual environment..."
if [ -d ".venv" ]; then
    echo "   ✅ Virtual environment already exists"
else
    python3 -m venv .venv
    if [ $? -eq 0 ]; then
        echo "   ✅ Virtual environment created at .venv/"
    else
        echo "   ❌ Failed to create virtual environment"
        exit 1
    fi
fi

echo ""

# Step 2: Activate virtual environment
echo "Step 2: Activating virtual environment..."
source .venv/bin/activate

if [ $? -eq 0 ]; then
    echo "   ✅ Virtual environment activated"
else
    echo "   ❌ Failed to activate virtual environment"
    exit 1
fi

echo ""

# Step 3: Upgrade pip
echo "Step 3: Upgrading pip..."
pip install --upgrade pip > /dev/null 2>&1
echo "   ✅ pip upgraded"

echo ""

# Step 4: Install requirements
echo "Step 4: Installing Python packages..."
echo "   This may take a few minutes..."
pip install -r requirements.txt

if [ $? -eq 0 ]; then
    echo "   ✅ All packages installed successfully!"
else
    echo "   ❌ Failed to install some packages"
    exit 1
fi

echo ""

# Step 5: Verify installation
echo "Step 5: Verifying installation..."
python -c "import pandas, numpy, sklearn, streamlit, psycopg2; print('   ✅ Core packages verified')" 2>/dev/null

if [ $? -ne 0 ]; then
    echo "   ⚠️  Some packages may not be installed correctly"
fi

echo ""
echo "================================================================================"
echo "✅ SETUP COMPLETE!"
echo "================================================================================"
echo ""
echo "📝 Next Steps:"
echo ""
echo "1. To use the virtual environment in future terminal sessions, run:"
echo "   cd $PROJECT_DIR"
echo "   source .venv/bin/activate"
echo ""
echo "2. Configure your .env file with API keys (see SETUP.md)"
echo ""
echo "3. Initialize database:"
echo "   python scripts/init_db.py"
echo ""
echo "4. Train models:"
echo "   python src/train.py"
echo ""
echo "5. Start services (3 separate terminals):"
echo "   Terminal 1: python scripts/start_streamer_enhanced.py --provider metalprice"
echo "   Terminal 2: python scripts/start_continuous_learning.py"
echo "   Terminal 3: streamlit run app/streamlit_app.py"
echo ""
echo "6. Access dashboard at: http://localhost:8501"
echo ""
echo "================================================================================"
echo ""
echo "💡 TIP: Your virtual environment is now activated (notice '.venv' in prompt)"
echo "    Run 'deactivate' to exit the virtual environment"
echo ""

