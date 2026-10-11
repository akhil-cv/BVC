"""
File system watcher for .extract_ready markers.
"""
import json
import time
from pathlib import Path
from typing import Dict, List, Generator, Tuple

from config import EXT_CONFIG
from logger import get_logger

logger = get_logger(__name__)


class FileWatcher:
    """Watches cache directory for .extract_ready marker files."""

    def __init__(self, cache_dir: str = None, poll_interval: int = 5):
        self.cache_dir = Path(cache_dir or EXT_CONFIG["cache_dir"])
        self.poll_interval = poll_interval
        self._processed: set = set()  # Track processed dates in this session

    def get_pending_dates(self) -> List[Tuple[str, Dict]]:
        """Get list of dates with .extract_ready markers."""
        pending = []

        if not self.cache_dir.exists():
            return pending

        for marker in self.cache_dir.glob("*.extract_ready"):
            date = marker.stem
            if date in self._processed:
                continue

            try:
                with open(marker, "r") as f:
                    signal = json.load(f)
                signal["marker_path"] = str(marker)
                pending.append((date, signal))
            except Exception as e:
                logger.warning(f"Failed to read marker {marker}: {e}")

        # Sort by date (oldest first)
        pending.sort(key=lambda x: x[0])
        return pending

    def mark_processed(self, date: str):
        """Mark a date as processed in this session."""
        self._processed.add(date)

    def wait_for_signal(self, poll_interval: int = None) -> Generator[Tuple[str, Dict], None, None]:
        """Generator that yields new signals as they appear."""
        poll = poll_interval or self.poll_interval
        logger.info(f"Watching {self.cache_dir} for .extract_ready files (poll={poll}s)")

        while True:
            pending = self.get_pending_dates()
            for date, signal in pending:
                yield date, signal

            time.sleep(poll)