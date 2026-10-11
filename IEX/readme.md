# IEX TOPS Data Pipeline

Complete pipeline for downloading, extracting, and managing IEX TOPS (Top of Book) historical market data.

## System Overview

```
┌─────────────────┐     .extract_ready      ┌─────────────────┐
│  Download Mgr   │ ──────────────────────▶ │    Extractor    │
│                 │                         │                 │
│ • Fetches TOPS  │                         │ • Parses PCAP   │
│   dates from API│                         │ • Writes Parquet│
│ • Downloads     │                         │ • Filters syms  │
│   .pcap.gz      │                         │ • Progress bar  │
└────────┬────────┘                         └────────┬────────┘
         │                                           │
         │         .md (completion)                  │
         ◀───────────────────────────────────────────┘
```

## Directory Structure

```
C:\IEX\
├── config.py                    # Shared configuration
├── manage.py                    # CLI control tool
├── state.json                   # Persistent state (shared)
├── requirements.txt             # Python dependencies
├── readme.md                    # This file
│
├── download_manager\            # Download Manager agent
│   ├── main.py                  # Entry point
│   ├── downloader.py            # HTTP download with resume + tqdm
│   ├── state.py                 # State management
│   ├── lock.py                  # File-based mutex
│   ├── extractor_hook.py        # Signal extractor via .extract_ready
│   ├── cleanup.py               # Delete PCAP after extraction
│   ├── progress.py              # tqdm progress bars
│   ├── config.py                # DM config (imports shared)
│   └── logger.py                # JSON logging
│
├── extractor\                   # Extractor agent
│   ├── main.py                  # Entry point
│   ├── parser.py                # PCAP → trades/quotes
│   ├── writer.py                # Buffered Parquet writer
│   ├── marker.py                # .md completion markers
│   ├── watcher.py               # Watches for .extract_ready
│   ├── progress.py              # tqdm extraction progress
│   ├── config.py                # Extractor config (imports shared)
│   └── logger.py                # JSON logging
│
├── cache\                       # Runtime (Download Manager)
│   ├── .lock                    # Mutex lock file
│   ├── YYYYMMDD_IEXTP1_TOPS*.pcap.gz  # Active download
│   └── YYYYMMDD.extract_ready   # Signal to extractor
│
├── data\                        # Output (per-date folders)
│   ├── 20161212\
│   │   ├── AAPL_trades_0001.parquet
│   │   ├── AAPL_quotes_0001.parquet
│   │   ├── MSFT_trades_0001.parquet
│   │   ├── ...
│   │   ├── 20161212.extract_ready
│   │   └── 20161212.md          # Completion marker
│   └── 20241025\
│       └── ...
│
├── extracted\                   # Completion markers (for DM)
│   └── YYYYMMDD.md
│
└── logs\
    ├── download_manager.log
    └── extractor.log
```

## Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
# Required: requests, dpkt, pyarrow, pandas, tqdm
```

### 2. Start Agents (Two Terminals)

**Terminal 1 - Extractor:**
```bash
cd C:\IEX\extractor
python main.py
```

**Terminal 2 - Download Manager:**
```bash
cd C:\IEX\download_manager
python main.py
```

### 3. Control via CLI (Any Terminal)
```bash
python manage.py status              # Full status
python manage.py queue --show        # Show pending dates
python manage.py queue --move-top 20241025  # Prioritize date
python manage.py pause               # Pause both agents
python manage.py resume              # Resume processing
python manage.py message-types --enable t q  # Enable trades & quotes
python manage.py symbols --enable AAPL MSFT  # Filter symbols
```

## Configuration (state.json)

Key settings controlled via `manage.py` or direct edit:

```json
{
  "pending_queue": ["20241025", "20241024", ...],  // Processing order
  "paused": false,                                 // Pause/resume
  "message_types": {"trades": true, "quotes": true}, // What to extract
  "symbol_filter": {"enabled": true, "symbols": ["AAPL", "MSFT"]},
  "data_root": "C:\\IEX\\data",                    // Output location
  "show_progress_bars": true,                      // tqdm progress
  "confirm_before_delete": true                    // Prompt before delete
}
```

## CLI Reference

| Command | Description |
|---------|-------------|
| `status` | Full system status |
| `queue --show [--all]` | Show pending dates |
| `queue --move-top <date>` | Prioritize date |
| `queue --move-bottom <date>` | Deprioritize date |
| `queue --remove <date>` | Skip date |
| `queue --reset` | Rebuild queue (latest first) |
| `pause` | Pause both agents |
| `resume` | Resume processing |
| `pause-status` | Check pause state |
| `message-types --show` | Current message filter |
| `message-types --enable t q` | Enable trades & quotes |
| `message-types --disable t` | Disable trades |
| `progress --enable/--disable` | Toggle tqdm bars |
| `confirm-delete --enable/--disable` | Toggle delete prompt |
| `symbols --enable AAPL MSFT` | Filter symbols |
| `data-root D:\Data\IEX` | Change output location |

## Monitoring

### Live Progress (Terminal running agent)
```
DL 20241025:  45%|████████████▌| 304M/672M [00:12<00:15, 24.3MB/s]
Extracting 20241025: 67%|██████████▋| 12.1M/18.0M [02:34<01:18, 89.2k msgs/s]
```

### Status Command
```bash
python manage.py status
```
Shows: queue position, pause state, message types, progress bar setting, data root, symbol filter.

### Lock File (Real-time)
```bash
cat C:\IEX\cache\.lock
```
```json
{"pid": 12345, "current_date": "20241025", "status": "downloading", ...}
```

### Logs
```bash
tail -f C:\IEX\logs\download_manager.log
tail -f C:\IEX\logs\extractor.log
```

## Output Format

### Parquet Files (per symbol)
```
data/20241025/
├── AAPL_trades_0001.parquet
├── AAPL_quotes_0001.parquet
├── MSFT_trades_0001.parquet
└── ...
```

### Completion Marker (.md)
```markdown
# TOPS Data Extraction - 2024-10-25

TOPS downloaded ==1

## Summary
- **Date**: 2024-10-25
- **Trade Count**: 1,234,567
- **Quote Count**: 9,876,543
- **Unique Tickers**: 8,342
- **Time Range**: 09:30:00 - 16:00:00 (UTC)

## Tickers (==1)
AAPL, MSFT, GOOGL, AMZN, NVDA, ...
```

## Parquet Schema

### Trades
| Column | Type | Description |
|--------|------|-------------|
| timestamp | int64 | Nanoseconds since epoch |
| symbol | string | Ticker symbol |
| price | float64 | Price in dollars |
| size | int64 | Share quantity |
| trade_id | int64 | Unique trade ID |
| flags | int64 | Trade flags |
| packet_no | int64 | Source packet number |

### Quotes
| Column | Type | Description |
|--------|------|-------------|
| timestamp | int64 | Nanoseconds since epoch |
| symbol | string | Ticker symbol |
| bid_price | float64 | Bid price |
| bid_size | int64 | Bid quantity |
| ask_price | float64 | Ask price |
| ask_size | int64 | Ask quantity |
| flags | int64 | Quote flags |
| packet_no | int64 | Source packet number |

## Pause/Resume Workflow

```bash
# Pause (finishes current date, then waits)
python manage.py pause

# Check status
python manage.py pause-status
# Output: Paused: True

# Resume
python manage.py resume
```

Agents check pause flag every 30 seconds, finish current work, release locks, then sleep.

## Symbol Filtering

```bash
# Enable filter for specific symbols
python manage.py symbols --enable AAPL MSFT NVDA

# Add more symbols
python manage.py symbols --add GOOGL TSLA

# Disable filter (process all)
python manage.py symbols --disable
```

## Changing Data Location

```bash
# Move output to different drive
python manage.py data-root D:\MarketData\IEX
```

## Troubleshooting

| Issue | Solution |
|-------|----------|
| "Could not acquire lock" | Another instance running; check `.lock` file |
| Download stuck | Check network; `max_retries=3` with backoff |
| Extraction timeout | Increase `extractor_wait_sec` in config |
| Progress bars not showing | Ensure interactive terminal; `progress --enable` |
| Permission denied | Run as admin or check folder permissions |

## Requirements

```
requests>=2.31.0
dpkt>=1.9.8
pyarrow>=14.0.0
pandas>=2.0.0
tqdm>=4.66.0
```

## Data Source

- **API**: `https://iextrading.com/api/1.0/hist`
- **Dates**: 2016-12-12 to present (~2,486 trading days)
- **Format**: PCAP (IEX-TP protocol) → gzip compressed
- **Size**: ~100MB-9GB per day
- **Retention**: 12 months rolling (per IEX)

## License

IEX Historical Data Terms of Use apply. By accessing data, you agree to:
https://www.iexexchange.io/legal/hist-data-terms
