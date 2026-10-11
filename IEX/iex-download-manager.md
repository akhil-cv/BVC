# IEX TOPS Download Manager Agent - Plan

## Overview
A Python daemon that continuously downloads TOPS data from IEX Trading, signals an extractor agent via file markers, waits for extraction completion, then cleans up downloaded files. Uses file-based locking in `C:\IEX\cache` for concurrency control.

---

## Requirements

### Functional
- [ ] Fetch all TOPS dates from `https://iextrading.com/api/1.0/hist` 
- [ ] Maintain persistent state in `C:\IEX\state.json`
- [ ] Acquire exclusive lock via `C:\IEX\cache\.lock` before each download
- [ ] **Create per-date folder `C:\IEX\data\<yyyymmdd>\` for each date**
- [ ] Download one TOPS `.pcap.gz` file at a time to `C:\IEX\cache\`
- [ ] Signal extractor by writing `<date>.extract_ready` marker file (in both cache and data\<date>\)
- [ ] Poll for `<date>.md` marker (written by extractor) with timeout
- [ ] On extraction success: parse tickers from `.md`, update state, delete `.pcap.gz` from cache, keep in data\<date>\
- [ ] On failure: retry (max 3x), then mark failed in state
- [ ] Run as long-running daemon with configurable poll interval

### Non-Functional
- [ ] Crash recovery: state persisted after each step; stale locks auto-expire (30 min)
- [ ] Resumable downloads: HTTP Range requests, verify file size against API
- [ ] Idempotent: safe to restart; skips completed dates
- [ ] Observability: structured JSON logs to `C:\IEX\logs\download_manager.log`
- [ ] Backpressure: only 1 file in cache at a time
- [ ] Decoupled extractor: file-marker protocol only

---

## Directory Structure

```
C:\IEX\
├── download_manager\
│   ├── main.py                 # Daemon entry point
│   ├── lock.py                 # File-based mutex
│   ├── state.py                # State persistence
│   ├── downloader.py           # HTTP download with resume
│   ├── extractor_hook.py       # File marker signaling
│   ├── cleanup.py              # Post-extraction cleanup
│   ├── config.py               # Configuration
│   └── logger.py               # Structured logging
├── cache\                      # Runtime (created by agent)
│   ├── .lock                   # Lock file
│   ├── <date>_IEXTP1_TOPS<ver>.pcap.gz  # Active download
│   └── <date>.extract_ready    # Signal to extractor
├── state.json                  # Persistent state
├── logs\
│   └── download_manager.log
├── extracted\                  # Extractor output (future agent)
│   └── <date>.md               # Marker: TOPS=1, tickers=[...]
└── data\                       # Per-date folders (created by agent)
    ├── 20161212\               # yyyymmdd format folder per date
    │   ├── 20161212_IEXTP1_TOPS1.5.pcap.gz  # Downloaded file (before cleanup)
    │   ├── 20161212.extract_ready           # Extractor signal
    │   └── 20161212.md                      # Completion marker (TOPS=1, tickers)
    ├── 20161213\
    │   └── ...
    └── 20241029\
        └── ...
```

---

## State Schema (`C:\IEX\state.json`)

```json
{
  "all_tops_dates": ["20161212", "20161213", ...],
  "completed": ["20161212", "20161213"],
  "failed": {"20161214": "network timeout after 3 retries"},
  "in_progress": null,
  "extraction_pending": null,
  "last_updated": "2026-10-11T13:00:00Z",
  "stats": {"total": 2414, "done": 2, "pending": 2412, "failed": 0}
}
```

---

## Lock File Schema (`C:\IEX\cache\.lock`)

```json
{
  "pid": 12345,
  "start_time": "2026-10-11T13:00:00Z",
  "current_date": "20241015",
  "status": "downloading|extracting|cleanup",
  "lock_version": 1
}
```

---

## Extractor Marker Protocol

### Signal File: `C:\IEX\cache\<date>.extract_ready`
```json
{
  "date": "20241015",
  "pcap_path": "C:\\IEX\\cache\\20241015_IEXTP1_TOPS1.6.pcap.gz",
  "output_dir": f"C:\\IEX\\{date}",
  "signal_time": "2026-10-11T13:05:00Z"
}
```

### Completion File: `C:\IEX\extracted\<date>.md` (written by extractor)
```markdown
# TOPS Data Extraction - 2024-10-15

TOPS downloaded ==1

## Tickers (==1)
'NU','GRAB', 'NVDA', 'AGNC', 'INTC', 'RIG', 'NFLX', 'NOK', 'CLF', 'KO'
```

---

## Configuration (`config.py`)

```python
CONFIG = {
    "cache_dir": r"C:\IEX\cache",
    "state_file": r"C:\IEX\state.json",
    "extracted_dir": r"C:\IEX\extracted",
    "log_file": r"C:\IEX\logs\download_manager.log",
    "api_url": "https://iextrading.com/api/1.0/hist",
    "lock_timeout_sec": 1800,         # 30 min
    "download_timeout_sec": 3600,     # 1 hour
    "extractor_wait_sec": 7200,       # 2 hours
    "poll_interval_sec": 30,          # Daemon loop sleep
    "max_retries": 3,
    "retry_delay_sec": 60,
    "user_agent": "IEX-DownloadManager/1.0",
}
```

---

## Module Specifications

### `lock.py` - CacheLock
| Method | Description |
|--------|-------------|
| `acquire(date)` | Create `.lock` atomically; return True if acquired |
| `release()` | Delete `.lock` file |
| `is_stale()` | Check if lock older than `lock_timeout_sec` |
| `force_release()` | Remove stale lock |
| `get_holder()` | Return lock JSON if exists |

### `state.py` - DownloadState
| Method | Description |
|--------|-------------|
| `load()` | Read state.json, initialize if missing |
| `save()` | Atomic write (write to .tmp, rename) |
| `get_next_pending()` | Return oldest date not in completed/failed/in_progress |
| `mark_in_progress(date)` | Set in_progress, save |
| `mark_completed(date)` | Move to completed, clear in_progress, save |
| `mark_failed(date, error)` | Add to failed, clear in_progress, save |
| `mark_extraction_pending(date)` | Set extraction_pending, save |
| `mark_extracted(date, tickers)` | Move to completed with tickers, save |

### `downloader.py` - TOPSDownloader
| Method | Description |
|--------|-------------|
| `fetch_hist_index()` | GET API, return list of {date, link, size, version, protocol} for TOPS |
| `download(date, dest_path)` | Stream download with Range header resume; verify size |
| `verify_size(date, path)` | Compare actual bytes vs API size |

### `extractor_hook.py` - ExtractorSignal
| Method | Description |
|--------|-------------|
| `signal_ready(date, pcap_path)` | Write `<date>.extract_ready` JSON to cache |
| `wait_for_completion(date, timeout)` | Poll for `<date>.md` in extracted_dir |
| `read_marker(date)` | Parse `.md` for tickers list |

### `cleanup.py` - CleanupManager
| Method | Description |
|--------|-------------|
| `delete_pcap(path)` | Remove downloaded `.pcap.gz` |
| `cleanup_stale_cache()` | Remove orphaned files on startup |

### `logger.py` - Structured Logging
- JSON lines format: `{"timestamp": "...", "level": "INFO", "date": "20241015", "stage": "download", "message": "..."}`
- Rotate daily, keep 7 days

---

## Daemon Main Loop (`main.py`)

```python
def daemon_loop():
    cleanup.cleanup_stale_cache()
    downloader.fetch_hist_index()  # Populate state.all_tops_dates on first run
    
    while True:
        try:
            with CacheLock(CONFIG["cache_dir"], CONFIG["lock_timeout_sec"]) as lock:
                state = DownloadState.load(CONFIG["state_file"])
                
                date = state.get_next_pending()
                if not date:
                    logger.info("All dates completed. Sleeping 5 min.")
                    time.sleep(300)
                    continue
                
                # Download phase
                state.mark_in_progress(date)
                state.save()
                lock.update_status("downloading", date)
                
                pcap_path = downloader.download(date, CONFIG["cache_dir"])
                if not pcap_path:
                    state.mark_failed(date, "download failed after retries")
                    state.save()
                    continue
                
                # Extraction phase
                state.mark_extraction_pending(date)
                state.save()
                lock.update_status("extracting", date)
                
                extractor.signal_ready(date, pcap_path)
                
                if extractor.wait_for_completion(date, CONFIG["extractor_wait_sec"]):
                    marker = extractor.read_marker(date)
                    state.mark_extracted(date, marker["tickers"])
                    
                    lock.update_status("cleanup", date)
                    cleanup.delete_pcap(pcap_path)
                else:
                    state.mark_failed(date, "extraction timeout")
                
                state.save()
                
        except Exception as e:
            logger.error(f"Daemon error: {e}")
            time.sleep(CONFIG["poll_interval_sec"])
```

---

## Error Handling Matrix

| Error Type | Detection | Recovery Action |
|------------|-----------|-----------------|
| Stale lock | `lock.is_stale()` | `force_release()`, acquire new |
| Download timeout | `requests` timeout | Retry with exponential backoff |
| Size mismatch | `verify_size()` | Delete partial, re-download |
| Network error | Exception | Retry (max 3), then mark failed |
| Extractor timeout | `wait_for_completion()` returns False | Mark failed, cleanup, alert |
| Disk full | `OSError: [Errno 28]` | Pause loop, log critical, retry |
| API rate limit | HTTP 429 | Exponential backoff (60s, 120s, 300s) |

---

## Testing Plan

1. **Unit tests** for each module (lock, state, downloader, extractor_hook, cleanup)
2. **Integration test** with last 5 trading dates (2024-10-23 to 2024-10-29)
3. **Failure injection**: kill process mid-download, verify recovery
4. **Extractor simulation**: mock extractor that writes `.md` after 10s
5. **Full backlog test**: run against 100 dates, verify state consistency

---

## Future Extractor Agent (Separate Plan)

- Watches `C:\IEX\cache\*.extract_ready`
- Parses PCAP using `pcap2csv` or `iex2h5`
- Extracts unique tickers from TOPS messages
- Writes `C:\IEX\extracted\<date>.md` with `TOPS downloaded ==1` and ticker list
- Deletes `.extract_ready` after writing `.md`

---

## Implementation Order

1. `config.py`, `logger.py` - Foundation
2. `lock.py`, `state.py` - Core persistence
3. `downloader.py` - HTTP logic
4. `extractor_hook.py`, `cleanup.py` - Integration points
5. `main.py` - Daemon orchestration
6. Unit tests + integration test
7. Deploy as Windows service (NSSM) or systemd

---

## Notes

- **C:\IEX is empty** - no existing downloads or state
- **2,414 TOPS dates** available from 2016-12-12 to 2024-10-29
- **Extractor agent** to be built separately per future plan
- **No external dependencies** beyond Python stdlib + `requests`


