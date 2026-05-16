# tests/conftest.py
# Pytest configuration and shared fixtures for the TSS wallet test suite
import os
import sys
# Ensure project root is on sys.path for all test modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
