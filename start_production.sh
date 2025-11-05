#!/bin/bash

echo "🚀 Starting Production Services..."
echo "=================================="

# Start Celery worker in background
echo "📦 Starting Celery Worker..."
celery -A celeryconfig worker --loglevel=info --concurrency=3 &
WORKER_PID=$!
echo "✅ Celery Worker started (PID: $WORKER_PID)"

# Give worker a moment to initialize
sleep 3

# Start Streamlit server in foreground
echo "🌐 Starting Streamlit Server..."
streamlit run app.py --server.port 5000

# If Streamlit exits, kill the worker too
kill $WORKER_PID 2>/dev/null
