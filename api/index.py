"""
Vercel serverless entry point.
Imports the FastAPI app from the main application module.
"""
import sys
import os

# Add project root to path so `app` package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app  # noqa: F401 — Vercel needs the `app` name
