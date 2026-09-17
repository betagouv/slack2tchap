"""Root pytest configuration to set safe development environment variables for the test suite."""

import os

os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault(
    "SECRET_ENCRYPTION_KEY",
    "32_bytes_super_secret_test_key_for_cipher!",
)
