"""
File-based mutex for C:/IEX/cache directory.
"""
import json
import os
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Optional

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DM_CONFIG
from logger import get_logger

logger = get_logger(__name__)


class CacheLock:
    """File-based lock with stale detection."""

    def __init__(self, cache_dir: str, timeout_sec: int = 1800):
        self.cache_dir = Path(cache_dir)
        self.lock_file = self.cache_dir / ".lock"
        self.timeout_sec = timeout_sec
        self.pid = os.getpid()
        self.lock_id = str(uuid.uuid4())[:8]
        self._acquired = False

    def acquire(self, current_date: str = "") -> bool:
        """Try to acquire the lock. Returns True if successful."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Check for existing lock
        if self.lock_file.exists():
            holder = self.get_holder()
            if holder:
                # Check if stale
                if self.is_stale(holder):
                    logger.warning(f"Stale lock detected (pid={holder.get('pid')}), forcing release")
                    self.force_release()
                else:
                    logger.info(f"Lock held by pid={holder.get('pid')}, date={holder.get('current_date')}")
                    return False

        # Create lock atomically
        lock_data = {
            "pid": self.pid,
            "lock_id": self.lock_id,
            "start_time": time.time(),
            "start_time_iso": datetime.utcnow().isoformat() + "Z",
            "current_date": current_date,
            "status": "acquired",
            "lock_version": 1,
        }

        try:
            # Atomic write: write to temp, then rename
            tmp_file = self.lock_file.with_suffix(".tmp")
            with open(tmp_file, "w") as f:
                json.dump(lock_data, f)
            tmp_file.replace(self.lock_file)
            self._acquired = True
            logger.info(f"Lock acquired for date={current_date}")
            return True
        except Exception as e:
            logger.error(f"Failed to acquire lock: {e}")
            return False

    def release(self) -> bool:
        """Release the lock."""
        if not self._acquired:
            return True

        try:
            if self.lock_file.exists():
                # Verify we own it
                holder = self.get_holder()
                if holder and holder.get("pid") == self.pid and holder.get("lock_id") == self.lock_id:
                    self.lock_file.unlink()
                    logger.info("Lock released")
                else:
                    logger.warning("Lock owned by another process, not releasing")
                    return False
            self._acquired = False
            return True
        except Exception as e:
            logger.error(f"Failed to release lock: {e}")
            return False

    def update_status(self, status: str, current_date: str = "") -> bool:
        """Update lock status."""
        if not self._acquired:
            return False

        holder = self.get_holder()
        if not holder or holder.get("pid") != self.pid or holder.get("lock_id") != self.lock_id:
            return False

        holder["status"] = status
        holder["current_date"] = current_date
        holder["last_update"] = time.time()

        try:
            tmp_file = self.lock_file.with_suffix(".tmp")
            with open(tmp_file, "w") as f:
                json.dump(holder, f)
            tmp_file.replace(self.lock_file)
            return True
        except Exception as e:
            logger.error(f"Failed to update lock status: {e}")
            return False

    def is_stale(self, holder: Optional[Dict] = None) -> bool:
        """Check if lock is older than timeout."""
        if holder is None:
            holder = self.get_holder()
        if not holder:
            return False

        start_time = holder.get("start_time", 0)
        return (time.time() - start_time) > self.timeout_sec

    def force_release(self) -> bool:
        """Force remove stale lock."""
        try:
            if self.lock_file.exists():
                self.lock_file.unlink()
                logger.info("Stale lock force-released")
            return True
        except Exception as e:
            logger.error(f"Failed to force release lock: {e}")
            return False

    def get_holder(self) -> Optional[Dict]:
        """Get current lock holder info."""
        if not self.lock_file.exists():
            return None

        try:
            with open(self.lock_file, "r") as f:
                return json.load(f)
        except Exception:
            return None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False


from datetime import datetime