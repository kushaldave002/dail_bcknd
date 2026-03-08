"""
Vercel serverless entry point.
Routes all traffic to the FastAPI application defined in app/main.py.
Vercel's @vercel/python builder automatically makes the project root available,
so `app` is importable directly.
"""
import sys
import os

# Ensure project root is on the path so `from app.xxx import ...` works
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.main import app  # noqa: E402 — must be after sys.path setup
