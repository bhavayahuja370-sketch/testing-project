import sys
import os

# Make the project root importable so we can reuse the existing app.py
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import app  # noqa: E402

# Vercel's Python runtime looks for a variable named "app" (WSGI app)
