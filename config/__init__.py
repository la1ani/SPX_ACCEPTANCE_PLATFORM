"""Configuration package.

This package exposes a `get_settings()` function that loads configuration
from environment variables and provides sensible defaults.  All
configuration values are type hinted for IDE support and static
analysis.
"""

from .settings import Settings, get_settings  # noqa: F401
