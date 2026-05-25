"""
Pytest configuration and fixtures.
Loads environment variables from .env file before running tests.
"""

import os
from pathlib import Path
import pytest


def pytest_configure(config):
    """Load environment variables from .env file before tests run."""
    env_file = Path(__file__).parent / ".env"
    
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                # Skip empty lines and comments
                if line and not line.startswith("#"):
                    # Split on first occurrence of '='
                    if "=" in line:
                        key, value = line.split("=", 1)
                        os.environ[key.strip()] = value.strip()

