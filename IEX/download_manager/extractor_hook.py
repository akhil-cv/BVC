"""
Extractor signaling via file markers.
"""
import json
import os
import time
from pathlib import Path
from typing import Dict, List, Optional

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DM_CONFIG
from logger import get_logger

logger = get_logger(__name__)


class ExtractorSignal:
    """Handles file-marker protocol with extractor agent."""

    def __init__(self, cache_dir: str = None, extracted_dir: str = None, data_root: str = None):
        self.cache_dir = Path(cache_dir or DM_CONFIG["cache_dir"])
        self.extracted_dir = Path(extracted_dir or DM_CONFIG["extracted_dir"])
        self.data_root = Path(data_root or DM_CONFIG["data_root"])

    def signal_ready(self, date: str, pcap_path: str, data_root: str = None) -> bool:
        """Write .extract_ready marker to cache and data_root/<date>/."""
        # Use provided data_root or fall back to config
        root = Path(data_root or self.data_root)
        
        signal = {
            "date": date,
            "pcap_path": pcap_path,
            "output_dir": str(root / date),
            "signal_time": time.time(),
            "signal_time_iso": datetime.utcnow().isoformat() + "Z",
        }

        # Write to cache (primary signal for extractor)
        cache_marker = self.cache_dir / f"{date}.extract_ready"
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            with open(cache_marker, "w") as f:
                json.dump(signal, f, indent=2)
            logger.info(f"Extract signal written: {cache_marker}")
        except Exception as e:
            logger.error(f"Failed to write cache signal: {e}")
            return False

        # Also write to data_root/<date>/ for record
        data_date_dir = root / date
        data_date_dir.mkdir(parents=True, exist_ok=True)
        data_marker = data_date_dir / f"{date}.extract_ready"
        try:
            with open(data_marker, "w") as f:
                json.dump(signal, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to write data signal: {e}")

        return True

    def wait_for_completion(self, date: str, timeout: int = 7200, poll_interval: int = 10) -> bool:
        """Poll for .md completion marker in extracted directory."""
        marker_path = self.extracted_dir / f"{date}.md"
        start = time.time()

        logger.info(f"Waiting for extraction completion: {marker_path} (timeout={timeout}s)")

        while time.time() - start < timeout:
            if marker_path.exists():
                # Verify it has content
                try:
                    content = marker_path.read_text(encoding="utf-8")
                    if "TOPS downloaded ==1" in content:
                        logger.info(f"Extraction completed for {date}")
                        return True
                except Exception:
                    pass

            time.sleep(poll_interval)

        logger.error(f"Extraction timeout for {date} after {timeout}s")
        return False

    def read_marker(self, date: str) -> Optional[Dict]:
        """Parse .md marker for ticker list and stats."""
        marker_path = self.extracted_dir / f"{date}.md"
        if not marker_path.exists():
            return None

        try:
            content = marker_path.read_text(encoding="utf-8")
            return self._parse_marker(content, date)
        except Exception as e:
            logger.error(f"Failed to read marker: {e}")
            return None

    def _parse_marker(self, content: str, date: str) -> Dict:
        """Parse markdown marker for tickers and stats."""
        result = {
            "date": date,
            "tops_downloaded": False,
            "tickers": [],
            "trade_count": 0,
            "quote_count": 0,
            "ticker_count": 0,
        }

        lines = content.split("\n")
        in_tickers = False

        for line in lines:
            line = line.strip()

            # Check TOPS downloaded flag
            if "TOPS downloaded ==" in line:
                try:
                    result["tops_downloaded"] = "==1" in line
                except Exception:
                    pass

            # Parse summary stats
            if line.startswith("- **Trade Count**:"):
                try:
                    result["trade_count"] = int(line.split(":")[1].strip().replace(",", ""))
                except Exception:
                    pass
            elif line.startswith("- **Quote Count**:"):
                try:
                    result["quote_count"] = int(line.split(":")[1].strip().replace(",", ""))
                except Exception:
                    pass
            elif line.startswith("- **Unique Tickers**:"):
                try:
                    result["ticker_count"] = int(line.split(":")[1].strip().replace(",", ""))
                except Exception:
                    pass

            # Parse ticker list
            if line.startswith("## Tickers"):
                in_tickers = True
                continue

            if in_tickers and line and not line.startswith("#"):
                # Ticker line: AAPL, MSFT, GOOGL, ...
                tickers = [t.strip() for t in line.split(",") if t.strip()]
                result["tickers"].extend(tickers)

        result["tickers"] = sorted(set(result["tickers"]))
        result["ticker_count"] = len(result["tickers"])

        return result

    def cleanup_signal(self, date: str) -> bool:
        """Remove .extract_ready from cache after extraction."""
        cache_marker = self.cache_dir / f"{date}.extract_ready"
        try:
            if cache_marker.exists():
                cache_marker.unlink()
                logger.info(f"Cleaned up signal: {cache_marker}")
            return True
        except Exception as e:
            logger.warning(f"Failed to cleanup signal: {e}")
            return False


from datetime import datetime