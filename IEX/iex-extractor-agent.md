# IEX TOPS Extractor Agent - Plan

## Overview
A Python daemon that watches for `.extract_ready` marker files, parses TOPS PCAP data, extracts trades and/or quotes based on message type filter, writes Parquet format, and writes completion markers with ticker lists. Includes progress bars and pause/resume support.

---

## Requirements

### Functional
- [ ] Watch `C:\IEX\cache\` for `<date>.extract_ready` marker files
- [ ] Read marker JSON to get `pcap_path`, `date`, and `output_dir`
- [ ] Create per-date output folder `{data_root}\<yyyymmdd>\`
- [ ] Parse PCAP (gzip → pcapng → Ethernet → IP → UDP → TOPS messages)
- [ ] **Message type filter**: Extract trades, quotes, or both (from state.message_types)
- [ ] Extract **trade messages** (type "T"): timestamp, symbol, price, size, trade_id, flags
- [ ] Extract **quote messages** (type "Q"): timestamp, symbol, bid_price, bid_size, ask_price, ask_size
- [ ] Write Parquet files to `{data_root}\<date>\` (partitioned by symbol)
- [ ] Buffer writes (100k rows) for memory efficiency
- [ ] **Progress bar**: tqdm-style progress during PCAP parsing
- [ ] **Pause/Resume**: Respect state.paused flag, release resources when paused
- [ ] Create `<date>.md` marker in `{data_root}\<date>\` with:
  - `TOPS downloaded ==1`
  - Ticker list (all unique symbols found)
  - Trade count, quote count, date range
- [ ] Create `<date>.md` in `C:\IEX\extracted\` (for download manager)
- [ ] Delete `.extract_ready` from cache after completion
- [ ] Handle multiple dates sequentially (one at a time)

### Non-Functional
- [ ] Crash recovery: Parquet writers finalized on interrupt (signal handler)
- [ ] Memory efficient: stream parse, buffer 100k rows per symbol
- [ ] Observability: structured JSON logs to `C:\IEX\logs\extractor.log`
- [ ] Idempotent: safe to re-run on same date (overwrites Parquet)
- [ ] Backpressure: process one date at a time

---

## Directory Structure

```
C:\IEX\
├── extractor\
│   ├── main.py                 # Daemon entry point
│   ├── watcher.py              # File system watcher for .extract_ready
│   ├── parser.py               # PCAP → TOPS message parser
│   ├── writer.py               # Parquet writer (buffered, per-symbol)
│   ├── marker.py               # .md marker read/write
│   ├── config.py               # Configuration
│   └── logger.py               # Structured logging
├── cache\                      # Input markers (from download manager)
│   ├── .lock
│   ├── <date>_IEXTP1_TOPS<ver>.pcap.gz
│   └── <date>.extract_ready    # Signal file (JSON)
├── data\                       # Output (per-date folders)
│   ├── 20161212\
│   │   ├── AAPL_trades_0001.parquet
│   │   ├── AAPL_quotes_0001.parquet
│   │   ├── ...
│   │   ├── 20161212.extract_ready
│   │   └── 20161212.md         # Completion marker
│   └── 20241029\
│       └── ...
├── extracted\                  # Completion markers (for download manager)
│   └── <date>.md
├── state.json                  # Shared with download manager
└── logs\
    └── extractor.log
```

---

## Extractor Marker Protocol

### Input Signal: `C:\IEX\cache\<date>.extract_ready`
```json
{
  "date": "20241015",
  "pcap_path": "C:\\IEX\\cache\\20241015_IEXTP1_TOPS1.6.pcap.gz",
  "output_dir": "C:\\IEX\\data\\20241015",
  "signal_time": "2026-10-11T13:05:00Z"
}
```

### Output Completion: `C:\IEX\data\<date>\<date>.md` AND `C:\IEX\extracted\<date>.md`
```markdown
# TOPS Data Extraction - 2024-10-15

TOPS downloaded ==1

## Summary
- **Date**: 2024-10-15
- **Trade Count**: 12,345,678
- **Quote Count**: 98,765,432
- **Unique Tickers**: 2,847
- **Time Range**: 09:30:00.000000 - 16:00:00.000000 (UTC)
- **Parquet Files**: 5,694 (2,847 symbols × 2)

## Tickers (==1)
AAPL, MSFT, GOOGL, AMZN, NVDA, ...
```

---

## Configuration (`config.py`)

```python
EXT_CONFIG = {
    "cache_dir": r"C:\IEX\cache",
    "data_root": r"C:\IEX\data",        # From state.data_root
    "extracted_dir": r"C:\IEX\extracted",
    "log_file": r"C:\IEX\logs\extractor.log",
    "buffer_size": 100_000,
    "watch_poll_sec": 5,
    "parquet_compression": "snappy",
    "parse_trades": True,               # Overridden by state.message_types
    "parse_quotes": False,              # Overridden by state.message_types
    "show_progress_bars": true,
    "progress_bar_format": "{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}]",
}
```

---

## State Integration (read from shared state.json)

```json
{
  "message_types": {"trades": true, "quotes": false},
  "paused": false,
  "data_root": "C:\\IEX\\data",
  "symbol_filter": {"enabled": false, "symbols": []}
}
```

Extractor reads:
- `state.message_types` → determines parse_trades/parse_quotes
- `state.paused` → pauses processing loop
- `state.data_root` → output directory base
- `state.symbol_filter` → symbol filtering

---

## Module Specifications

### `watcher.py` - FileWatcher
| Method | Description |
|--------|-------------|
| `get_pending_dates()` | Return list of (date, signal) for `.extract_ready` files |
| `mark_processed(date)` | Track processed dates in session |

### `parser.py` - TOPSParser
| Method | Description |
|--------|-------------|
| `__init__(symbol_filter, parse_trades, parse_quotes)` | Initialize with filters |
| `parse_pcap(pcap_path, date)` | Generator yielding (msg_type, record) |
| `get_stats()` | Return {trade_count, quote_count, symbols, time_range} |

### `writer.py` - ParquetWriter
| Method | Description |
|--------|-------------|
| `buffer_trade(symbol, record)` | Add to trade buffer, flush at buffer_size |
| `buffer_quote(symbol, record)` | Add to quote buffer, flush at buffer_size |
| `flush_all()` | Write all buffers, close writers |
| `get_stats()` | Return per-symbol counts |

### `marker.py` - MarkerFile
| Method | Description |
|--------|-------------|
| `write_completion(date, output_dir, stats)` | Write `.md` to data_root/date/ and extracted/ |
| `read_completion(date)` | Parse `.md` for tickers/stats |

### `main.py` - ExtractorAgent
```python
def run():
    while running:
        if load_state().is_paused():
            time.sleep(30)
            continue
        
        pending = watcher.get_pending_dates()
        for date, signal in pending:
            # Load message types from state
            state = load_state()
            parse_trades = state.get_message_types()["trades"]
            parse_quotes = state.get_message_types()["quotes"]
            
            parser = TOPSParser(
                symbol_filter=state.get_symbol_filter()["symbols"] if enabled else None,
                parse_trades=parse_trades,
                parse_quotes=parse_quotes
            )
            
            # Parse with progress bar
            with tqdm(total=estimate_packets(pcap_path), desc=f"Extracting {date}") as pbar:
                for msg_type, record in parser.parse_pcap(pcap_path, date):
                    if msg_type == "trade":
                        writer.buffer_trade(record["symbol"], record)
                    elif msg_type == "quote":
                        writer.buffer_quote(record["symbol"], record)
                    pbar.update(1)
            
            writer.flush_all()
            marker.write_completion(date, output_dir, parser.get_stats())
            marker.cleanup_signal(date)
```

---

## Progress Bar Implementation

```python
# progress.py
from tqdm import tqdm

def extraction_progress(pcap_path, parse_trades, parse_quotes):
    """Estimate total messages and wrap parser with tqdm."""
    # Quick scan to estimate packet count
    estimated = estimate_packets(pcap_path)
    
    parser = TOPSParser(...)
    with tqdm(total=estimated, desc="Parsing PCAP", unit="msgs") as pbar:
        for msg_type, record in parser.parse_pcap(pcap_path, date):
            yield msg_type, record
            pbar.update(1)

def download_progress(url, dest_path, total_size):
    """Wrap requests stream with tqdm."""
    with requests.get(url, stream=True) as resp:
        with tqdm(total=total_size, unit="B", unit_scale=True, desc="Downloading") as pbar:
            with open(dest_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
                    pbar.update(len(chunk))
```

---

## Pause/Resume Logic

```python
# In main loop
def run():
    while running:
        state = load_state()
        
        if state.is_paused():
            logger.info("Extractor paused. Waiting...")
            time.sleep(30)
            continue
        
        # Process dates...
```

User controls via state.json:
```bash
# Pause
python manage.py state --set paused true

# Resume  
python manage.py state --set paused false
```

---

## Testing Plan

1. **Unit tests**: parser (trade/quote filtering), writer (buffer flush), marker (MD format)
2. **Integration test**: Process 1-day PCAP with trades only, quotes only, both
3. **Progress bar test**: Verify tqdm output during parsing
4. **Pause/resume test**: Set paused=true, verify agent stops; set false, verify resumes
5. **Message type filter test**: Verify only trades parsed when quotes=false
5. **Schema validation**: Read back Parquet, verify columns/types
6. **Marker verification**: Download manager reads `.md` from extracted\

---

## Implementation Order

1. `config.py`, `logger.py` - Foundation
2. `progress.py` - NEW: tqdm utilities for extraction/download
3. `parser.py` - Core PCAP parsing with message type filter
4. `writer.py` - Buffered Parquet writing
5. `marker.py` - Completion marker I/O
6. `watcher.py` - File system polling
7. `main.py` - Daemon orchestration with pause/resume
8. Unit tests + integration test
9. Deploy as Windows service alongside download manager

---

## Dependencies

```toml
# pyproject.toml / requirements.txt
dpkt >= 1.9.8
pyarrow >= 14.0.0
pandas >= 2.0.0
tqdm >= 4.66.0
```

---

## Notes

- **Shared state.json** with download manager for coordination
- **Message types** from state: trades=true/false, quotes=true/false
- **Symbol filter** from state: enabled + symbols list
- **Progress bars** use `tqdm` with configurable format
- **Pause/Resume** via state.paused flag (checked each loop iteration)
- **Two daemons** run independently, communicate via file markers
