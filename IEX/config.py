"""
Shared configuration for IEX TOPS Download Manager and Extractor.
Single source of truth for both agents.
"""
import os

# Base directory - can be overridden via environment variable
BASE_DIR = os.environ.get("IEX_BASE_DIR", r"C:\IEX")

# ============================================================
# SHARED CONFIG - Used by both Download Manager and Extractor
# ============================================================
SHARED_CONFIG = {
    # Root directory where date folders (yyyymmdd) are created
    # Can be changed via manage.py or by editing state.json
    "data_root": os.path.join(BASE_DIR, "data"),
    
    # Date processing order: "desc" = latest first (2024→2016), "asc" = oldest first
    "date_order": "desc",
    
    # Dates to skip (e.g., manually created for data quality)
    "skip_dates": ["20261009"],
    
    # Symbol filter - when enabled, only extract these symbols
    # Empty list = all symbols (default)
    "symbol_filter": {
        "enabled": False,
        "symbols": []
    },
    
    # NEW: Message type filter - what to download/extract
    "message_types": {
        "trades": True,
        "quotes": False
    },
    
    # NEW: Pause/resume control
    "paused": False,
    
    # NEW: Progress bar settings
    "show_progress_bars": True,
    "progress_bar_format": "{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]",
    
    # NEW: Confirm before deleting PCAP files
    "confirm_before_delete": True,
}

# ============================================================
# DOWNLOAD MANAGER CONFIG
# ============================================================
DM_CONFIG = {
    **SHARED_CONFIG,
    
    # Runtime directories
    "cache_dir": os.path.join(BASE_DIR, "cache"),
    "extracted_dir": os.path.join(BASE_DIR, "extracted"),
    "state_file": os.path.join(BASE_DIR, "state.json"),
    "log_file": os.path.join(BASE_DIR, "logs", "download_manager.log"),
    
    # API
    "api_url": "https://iextrading.com/api/1.0/hist",
    
    # Timeouts (seconds)
    "lock_timeout_sec": 1800,         # 30 min - stale lock detection
    "download_timeout_sec": 3600,     # 1 hour - per file download
    "extractor_wait_sec": 7200,       # 2 hours - wait for extraction
    "poll_interval_sec": 30,          # Daemon loop sleep
    
    # Retry policy
    "max_retries": 3,
    "retry_delay_sec": 60,
    
    # Identity
    "user_agent": "IEX-DownloadManager/1.0",
}

# ============================================================
# EXTRACTOR CONFIG
# ============================================================
EXT_CONFIG = {
    **SHARED_CONFIG,
    
    # Runtime directories
    "cache_dir": os.path.join(BASE_DIR, "cache"),
    "extracted_dir": os.path.join(BASE_DIR, "extracted"),
    "log_file": os.path.join(BASE_DIR, "logs", "extractor.log"),
    
    # Processing
    "buffer_size": 100_000,           # Rows per symbol before flush
    "watch_poll_sec": 5,              # Poll interval for .extract_ready
    "parquet_compression": "snappy",  # snappy, zstd, gzip
    
    # Overridden by state.message_types at runtime
    "parse_trades": True,
    "parse_quotes": False,
    
    # Identity
    "user_agent": "IEX-Extractor/1.0",
}

# ============================================================
# TOPS MESSAGE FORMAT CONSTANTS
# ============================================================
# Trade (T): type(1) + flags(1) + timestamp(8) + symbol(8) + size(4) + price(8) + trade_id(8) = 38 bytes
# Quote (Q): type(1) + flags(1) + timestamp(8) + symbol(8) + bid_size(4) + bid_price(8) + ask_size(4) + ask_price(8) = 42 bytes
TRADE_FMT = "<BBQ8sIqQ"
TRADE_SIZE = 38

QUOTE_FMT = "<BBQ8sIqIq"
QUOTE_SIZE = 42

MSG_TRADE = ord('T')
MSG_QUOTE = ord('Q')