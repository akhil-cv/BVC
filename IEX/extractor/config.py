"""
Extractor agent configuration - imports from shared config.
"""
import sys
from pathlib import Path

# Add parent directory to path BEFORE any config imports
parent_dir = Path(__file__).parent.parent
sys.path.insert(0, str(parent_dir))

# Now import the shared config module using importlib to avoid circular issues
import importlib.util
shared_config_path = parent_dir / "config.py"
spec = importlib.util.spec_from_file_location("shared_config", shared_config_path)
shared_config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(shared_config)

EXT_CONFIG = shared_config.EXT_CONFIG
SHARED_CONFIG = shared_config.SHARED_CONFIG
TRADE_FMT = shared_config.TRADE_FMT
TRADE_SIZE = shared_config.TRADE_SIZE
QUOTE_FMT = shared_config.QUOTE_FMT
QUOTE_SIZE = shared_config.QUOTE_SIZE
MSG_TRADE = shared_config.MSG_TRADE
MSG_QUOTE = shared_config.MSG_QUOTE

# Re-export for backward compatibility
__all__ = [
    "EXT_CONFIG",
    "SHARED_CONFIG", 
    "TRADE_FMT", "TRADE_SIZE",
    "QUOTE_FMT", "QUOTE_SIZE",
    "MSG_TRADE", "MSG_QUOTE",
]