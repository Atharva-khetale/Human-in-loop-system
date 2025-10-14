#!/usr/bin/env python3
"""
Run script for Automated Human-in-Loop System
"""
import uvicorn
import os
import sys
# Add the current directory to Python path
current_dir = os.path.dirname(os.path.abspath('app'))
sys.path.insert(0, current_dir)

if __name__ == "__main__":
    print("🚀 Starting Automated Human-in-Loop System...")
    print("📊 Dashboard: http://localhost:5000")
    print("📚 API Docs: http://localhost:5000/docs")
    print("⏹️  Press Ctrl+C to stop\n")

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=5000,
        reload=True,  # Enable auto-reload
        reload_dirs=["app"],  # Watch app directory for changes
        log_level="info"
    )