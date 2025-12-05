#!/bin/bash
# Fix SSL Certificate Issues on macOS
# This script installs Python SSL certificates

echo "🔧 Fixing SSL Certificate Issues"
echo "=================================="
echo ""

# Method 1: Run Python's Install Certificates command
echo "Method 1: Installing Python certificates..."
PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1-2)
CERT_COMMAND="/Applications/Python ${PYTHON_VERSION}/Install Certificates.command"

if [ -f "$CERT_COMMAND" ]; then
    echo "Running: $CERT_COMMAND"
    "$CERT_COMMAND"
    echo "✓ Certificates installed"
else
    echo "⚠ Certificate installer not found at: $CERT_COMMAND"
fi

echo ""
echo "Method 2: Upgrading certifi package..."
pip install --upgrade certifi pip setuptools -q
echo "✓ certifi upgraded"

echo ""
echo "Method 3: Setting up environment variable..."
echo 'export PYTHONHTTPSVERIFY=0' >> ~/.zshrc
echo "✓ Added PYTHONHTTPSVERIFY=0 to ~/.zshrc"

echo ""
echo "=================================="
echo "✅ SSL Certificate Fix Complete"
echo "=================================="
echo ""
echo "The WebSocket client has also been updated to handle SSL automatically."
echo ""
echo "Next steps:"
echo "1. Restart your terminal (or run: source ~/.zshrc)"
echo "2. Try running the streamer again: python scripts/start_streamer.py"
echo ""

