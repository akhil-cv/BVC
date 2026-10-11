"""
Persistent state management for Download Manager.
New schema with pending_queue (latest-first), symbol_filter, data_root, message_types, pause/resume.
"""
import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DM_CONFIG, SHARED_CONFIG
from logger import get_logger

logger = get_logger(__name__)


class DownloadState:
    """Manages download state with atomic persistence."""

    def __init__(self, state_file: str):
        self.state_file = Path(state_file)
        self.state = self._default_state()

    def _default_state(self) -> Dict[str, Any]:
        return {
            "all_tops_dates": [],           # All dates from API (sorted)
            "pending_queue": [],            # Dates to process (ordered by priority)
            "completed": [],                # Fully done dates
            "failed": {},                   # Failed dates with errors
            "in_progress": None,            # Currently downloading
            "extraction_pending": None,     # Waiting for extractor
            "data_root": SHARED_CONFIG["data_root"],
            "symbol_filter": SHARED_CONFIG["symbol_filter"].copy(),
            "message_types": SHARED_CONFIG["message_types"].copy(),
            "paused": SHARED_CONFIG["paused"],
            "show_progress_bars": SHARED_CONFIG["show_progress_bars"],
            "confirm_before_delete": SHARED_CONFIG["confirm_before_delete"],
            "last_updated": None,
            "stats": {"total": 0, "done": 0, "pending": 0, "failed": 0},
        }

    def load(self) -> "DownloadState":
        """Load state from file with migration."""
        if self.state_file.exists():
            try:
                with open(self.state_file, "r") as f:
                    self.state = json.load(f)
                self._migrate()
                logger.info(f"State loaded: {self.state['stats']}")
            except Exception as e:
                logger.error(f"Failed to load state: {e}")
                self.state = self._default_state()
        else:
            logger.info("No state file found, starting fresh")
        return self

    def _migrate(self):
        """Migrate old state schema to new schema."""
        # Ensure all keys exist
        default = self._default_state()
        for key, val in default.items():
            if key not in self.state:
                self.state[key] = val
                logger.info(f"Added missing state key: {key}")

        # Migrate from old schema: if pending_queue empty but all_tops_dates exists
        if not self.state["pending_queue"] and self.state["all_tops_dates"]:
            self._initialize_queue()
            logger.info("Migrated: initialized pending_queue from all_tops_dates")

        # Ensure data_root is set
        if not self.state.get("data_root"):
            self.state["data_root"] = SHARED_CONFIG["data_root"]

        # Ensure symbol_filter structure
        if "symbol_filter" not in self.state:
            self.state["symbol_filter"] = SHARED_CONFIG["symbol_filter"].copy()
        elif isinstance(self.state["symbol_filter"], list):
            # Old format was just a list
            self.state["symbol_filter"] = {
                "enabled": len(self.state["symbol_filter"]) > 0,
                "symbols": self.state["symbol_filter"]
            }

        # Ensure message_types structure
        if "message_types" not in self.state:
            self.state["message_types"] = SHARED_CONFIG["message_types"].copy()
        elif isinstance(self.state["message_types"], list):
            self.state["message_types"] = {
                "trades": "trades" in self.state["message_types"],
                "quotes": "quotes" in self.state["message_types"]
            }

        # Ensure paused field
        if "paused" not in self.state:
            self.state["paused"] = SHARED_CONFIG["paused"]

        # Ensure progress bar settings
        if "show_progress_bars" not in self.state:
            self.state["show_progress_bars"] = SHARED_CONFIG["show_progress_bars"]
        if "confirm_before_delete" not in self.state:
            self.state["confirm_before_delete"] = SHARED_CONFIG["confirm_before_delete"]

        self._update_stats()

    def _initialize_queue(self):
        """Initialize pending_queue from all_tops_dates (latest-first by default)."""
        skip_dates = set(DM_CONFIG.get("skip_dates", []))
        completed = set(self.state["completed"])
        failed = set(self.state["failed"].keys())

        dates = [
            d for d in self.state["all_tops_dates"]
            if d not in skip_dates and d not in completed and d not in failed
        ]

        if DM_CONFIG.get("date_order", "desc") == "desc":
            dates = list(reversed(dates))  # Latest first

        self.state["pending_queue"] = dates
        logger.info(f"Initialized pending_queue with {len(dates)} dates (order={DM_CONFIG.get('date_order')})")

    def save(self) -> bool:
        """Save state atomically."""
        self.state["last_updated"] = time.time()
        self.state["last_updated_iso"] = datetime.utcnow().isoformat() + "Z"
        self._update_stats()

        try:
            self.state_file.parent.mkdir(parents=True, exist_ok=True)
            tmp_file = self.state_file.with_suffix(".tmp")
            with open(tmp_file, "w") as f:
                json.dump(self.state, f, indent=2)
            tmp_file.replace(self.state_file)
            return True
        except Exception as e:
            logger.error(f"Failed to save state: {e}")
            return False

    def _update_stats(self):
        total = len(self.state["all_tops_dates"])
        done = len(self.state["completed"])
        failed = len(self.state["failed"])
        pending = len(self.state["pending_queue"])
        if self.state["in_progress"]:
            pending += 1
        self.state["stats"] = {
            "total": total,
            "done": done,
            "pending": pending,
            "failed": failed,
        }

    def set_all_dates(self, dates: List[str]):
        """Set the complete list of TOPS dates from API."""
        self.state["all_tops_dates"] = sorted(dates)
        # Re-initialize queue if empty
        if not self.state["pending_queue"]:
            self._initialize_queue()
        self._update_stats()

    def get_next_pending(self) -> Optional[str]:
        """Get the next date from pending_queue (respects priority order)."""
        if not self.state["pending_queue"]:
            return None

        # Skip if already in progress
        in_progress = self.state["in_progress"]
        if in_progress and in_progress in self.state["pending_queue"]:
            # Still processing, return it
            return in_progress

        return self.state["pending_queue"][0]

    def pop_next_pending(self) -> Optional[str]:
        """Remove and return the next date from pending_queue."""
        if not self.state["pending_queue"]:
            return None

        date = self.state["pending_queue"].pop(0)
        self.state["in_progress"] = date
        return date

    def requeue_date(self, date: str, position: int = 0):
        """Put a date back into pending_queue at specified position (0=front)."""
        if date in self.state["pending_queue"]:
            self.state["pending_queue"].remove(date)
        self.state["pending_queue"].insert(position, date)
        if self.state["in_progress"] == date:
            self.state["in_progress"] = None

    def move_date_in_queue(self, date: str, new_position: int) -> bool:
        """Move a date to a new position in the queue."""
        if date not in self.state["pending_queue"]:
            return False
        self.state["pending_queue"].remove(date)
        self.state["pending_queue"].insert(new_position, date)
        return True

    def remove_from_queue(self, date: str) -> bool:
        """Remove a date from pending_queue (mark as skipped)."""
        if date in self.state["pending_queue"]:
            self.state["pending_queue"].remove(date)
            return True
        return False

    def mark_in_progress(self, date: str):
        """Mark date as currently downloading."""
        self.state["in_progress"] = date
        self.state["extraction_pending"] = None

    def mark_completed(self, date: str):
        """Mark date as fully completed (downloaded + extracted)."""
        if date not in self.state["completed"]:
            self.state["completed"].append(date)
        self.state["completed"].sort()
        # Remove from queue if present
        if date in self.state["pending_queue"]:
            self.state["pending_queue"].remove(date)
        self.state["in_progress"] = None
        self.state["extraction_pending"] = None

    def mark_failed(self, date: str, error: str):
        """Mark date as failed with error message."""
        self.state["failed"][date] = {
            "error": error,
            "timestamp": time.time(),
            "timestamp_iso": datetime.utcnow().isoformat() + "Z",
        }
        # Remove from queue if present
        if date in self.state["pending_queue"]:
            self.state["pending_queue"].remove(date)
        self.state["in_progress"] = None
        self.state["extraction_pending"] = None

    def mark_extraction_pending(self, date: str):
        """Mark date as waiting for extractor."""
        self.state["extraction_pending"] = date

    def mark_extracted(self, date: str, tickers: List[str]):
        """Mark date as extracted with ticker list."""
        if date not in self.state["completed"]:
            self.state["completed"].append(date)
        self.state["completed"].sort()
        if "extracted_info" not in self.state:
            self.state["extracted_info"] = {}
        self.state["extracted_info"][date] = {
            "tickers": sorted(tickers),
            "ticker_count": len(tickers),
            "extracted_at": time.time(),
            "extracted_at_iso": datetime.utcnow().isoformat() + "Z",
        }
        self.state["in_progress"] = None
        self.state["extraction_pending"] = None

    def is_completed(self, date: str) -> bool:
        return date in self.state["completed"]

    def is_failed(self, date: str) -> bool:
        return date in self.state["failed"]

    def get_failed_dates(self) -> List[str]:
        return list(self.state["failed"].keys())

    def retry_failed(self, date: str) -> bool:
        """Move a failed date back to pending (front of queue)."""
        if date in self.state["failed"]:
            del self.state["failed"][date]
            self.requeue_date(date, position=0)
            return True
        return False

    def get_symbol_filter(self) -> Dict:
        """Get current symbol filter config."""
        return self.state.get("symbol_filter", {"enabled": False, "symbols": []})

    def set_symbol_filter(self, enabled: bool, symbols: List[str] = None):
        """Update symbol filter."""
        self.state["symbol_filter"] = {
            "enabled": enabled,
            "symbols": sorted(set(symbols)) if symbols else []
        }

    def get_message_types(self) -> Dict:
        """Get current message type filter."""
        return self.state.get("message_types", {"trades": True, "quotes": False})

    def set_message_types(self, trades: bool = True, quotes: bool = False):
        """Update message type filter."""
        self.state["message_types"] = {
            "trades": trades,
            "quotes": quotes
        }

    def is_paused(self) -> bool:
        """Check if processing is paused."""
        return self.state.get("paused", False)

    def set_paused(self, paused: bool):
        """Pause or resume processing."""
        self.state["paused"] = paused

    def get_progress_bar_setting(self) -> bool:
        """Get progress bar setting."""
        return self.state.get("show_progress_bars", True)

    def set_progress_bar_setting(self, enabled: bool):
        """Enable/disable progress bars."""
        self.state["show_progress_bars"] = enabled

    def get_confirm_delete_setting(self) -> bool:
        """Get confirm before delete setting."""
        return self.state.get("confirm_before_delete", True)

    def set_confirm_delete_setting(self, enabled: bool):
        """Enable/disable confirm before delete."""
        self.state["confirm_before_delete"] = enabled

    def set_data_root(self, path: str):
        """Update data root path."""
        self.state["data_root"] = path
        # Also update shared config for immediate use
        SHARED_CONFIG["data_root"] = path

    def get_data_root(self) -> str:
        """Get current data root."""
        return self.state.get("data_root", SHARED_CONFIG["data_root"])