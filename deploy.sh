#!/bin/bash
# Deploy script for Dr. Donut Voice Ordering System

echo "🍩 Dr. Donut Voice Ordering - Deployment Script"
echo "================================================"

# Check Python version
python_version=$(python3 --version 2>&1)
if [[ $? -eq 0 ]]; then
    echo "✅ Found Python: $python_version"
else
    echo "❌ Python3 not found. Please install Python 3.8+"
    exit 1
fi

# Install dependencies
echo "📦 Installing dependencies..."
pip3 install -r requirements.txt

# Check if we have API key
if [[ -z "$ULTRAVOX_API_KEY" ]]; then
    echo "🔑 Setting default API key..."
    export ULTRAVOX_API_KEY="PRAv5rQr.O2580pzU9yHuWiA0vx3Mgs4H5f6WraM6"
fi

echo "🔑 Using API Key: ${ULTRAVOX_API_KEY:0:10}..."

# Test the cart engine first
echo "🧪 Testing cart engine..."
python3 -c "from cart_engine import CartNormalizer; from menu_data import get_menu; print('✅ Cart engine OK')"

if [[ $? -ne 0 ]]; then
    echo "❌ Cart engine test failed"
    exit 1
fi

# Check if this is Heroku or local
if [[ -n "$DYNO" ]]; then
    echo "☁️ Running on Heroku"
    PORT=${PORT:-5000}
    gunicorn --worker-class eventlet -w 1 --bind 0.0.0.0:$PORT web_app:app
else
    echo "💻 Running locally"
    PORT=${PORT:-5000}
    
    # Check if port is available
    if lsof -Pi :$PORT -sTCP:LISTEN -t >/dev/null ; then
        echo "⚠️ Port $PORT is in use. Trying port $((PORT+1))"
        PORT=$((PORT+1))
    fi
    
    echo "🚀 Starting Dr. Donut Voice Ordering System on http://localhost:$PORT"
    echo ""
    echo "📱 Open these URLs in your browser:"
    echo "   Main App: http://localhost:$PORT"
    echo "   Test Page: http://localhost:$PORT/test"
    echo "   Debug API: http://localhost:$PORT/api/debug_sessions"
    echo ""
    echo "🎤 Instructions:"
    echo "   1. Click 'Connect to Ultravox'"
    echo "   2. Click 'Start Recording'"
    echo "   3. Say your order (e.g., 'I want a chocolate donut and a coffee')"
    echo "   4. Watch the cart update in real-time!"
    echo ""
    
    python3 web_app.py
fi