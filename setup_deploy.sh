#!/bin/bash
# Simple deployment script for Dr. Donut app

echo "🍩 Dr. Donut Deployment Setup"
echo "============================="

# Install requirements
echo "📦 Installing requirements..."
pip install -r requirements.txt

echo ""
echo "🚀 Testing deployment options:"
echo ""

# Test direct Python approach (recommended)
echo "✅ Option 1: Direct Python (RECOMMENDED)"
echo "Command: python web_app.py"
echo "This is the simplest and most reliable option for deployment."
echo ""

# Test if gevent is available
python -c "import gevent; print('✅ Gevent available')" 2>/dev/null
if [ $? -eq 0 ]; then
    echo "✅ Option 2: Gunicorn + Gevent"
    echo "Command: gunicorn --worker-class gevent -w 1 --bind 0.0.0.0:\$PORT web_app:app"
else
    echo "❌ Option 2: Gevent not available - install with: pip install gevent==23.9.1"
fi
echo ""

# Test if eventlet is available
python -c "import eventlet; print('✅ Eventlet available')" 2>/dev/null
if [ $? -eq 0 ]; then
    echo "✅ Option 3: Gunicorn + Eventlet"
    echo "Command: gunicorn --worker-class eventlet -w 1 --bind 0.0.0.0:\$PORT web_app:app"
else
    echo "❌ Option 3: Eventlet not available - install with: pip install eventlet==0.35.2"
fi
echo ""

echo "💡 For local testing, use:"
echo "export PORT=5000"
echo "python web_app.py"
echo ""

echo "🌐 For Render deployment, use start command:"
echo "python web_app.py"
echo ""

echo "🎉 Setup complete! Use 'python web_app.py' to start the app."