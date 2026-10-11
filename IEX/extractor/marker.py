"""
Marker file handling for Extractor agent.
"""
import json
import os
import time
from pathlib import Path
from typing import Dict, List, Optional, Any

from config import EXT_CONFIG
from logger import get_logger

logger = get_logger(__name__)


class MarkerFile:
    """Handles completion marker files (.md) for extractor."""

    def __init__(self, extracted_dir: str = None, data_root: str = None):
        self.extracted_dir = Path(extracted_dir or EXT_CONFIG["extracted_dir"])
        self.data_root = Path(data_root or EXT_CONFIG["data_root"])

    def write_completion(
        self,
        date: str,
        output_dir: str,
        stats: Dict[str, Any]
    ) -> bool:
        """Write completion marker to both extracted/ and data_root/<date>/."""
        tickers = stats.get("symbols", [])
        trade_count = stats.get("trade_count", 0)
        quote_count = stats.get("quote_count", 0)
        time_range = stats.get("time_range", {})

        content = self._format_marker(date, tickers, trade_count, quote_count, time_range)

        # Write to extracted/ (for download manager)
        self.extracted_dir.mkdir(parents=True, exist_ok=True)
        extracted_marker = self.extracted_dir / f"{date}.md"
        try:
            extracted_marker.write_text(content, encoding="utf-8")
            logger.info(f"Completion marker written: {extracted_marker}")
        except Exception as e:
            logger.error(f"Failed to write extracted marker: {e}")
            return False

        # Write to data_root/<date>/ (permanent record)
        data_date_dir = self.data_root / date
        data_date_dir.mkdir(parents=True, exist_ok=True)
        data_marker = data_date_dir / f"{date}.md"
        try:
            data_marker.write_text(content, encoding="utf-8")
            logger.info(f"Data marker written: {data_marker}")
        except Exception as e:
            logger.warning(f"Failed to write data marker: {e}")

        return True

    def _format_marker(
        self,
        date: str,
        tickers: List[str],
        trade_count: int,
        quote_count: int,
        time_range: Dict[str, Any]
    ) -> str:
        """Format markdown completion marker."""
        # Format date for display
        try:
            display_date = f"{date[:4]}-{date[4:6]}-{date[6:8]}"
        except Exception:
            display_date = date

        lines = [
            f"# TOPS Data Extraction - {display_date}",
            "",
            "TOPS downloaded ==1",
            "",
            "## Summary",
            f"- **Date**: {display_date}",
            f"- **Trade Count**: {trade_count:,}",
            f"- **Quote Count**: {quote_count:,}",
            f"- **Unique Tickers**: {len(tickers):,}",
        ]

        if time_range:
            lines.append(f"- **Time Range**: {time_range.get('start_str', '')} - {time_range.get('end_str', '')} (UTC)")

        lines.extend([
            f"- **Parquet Files**: {len(tickers) * 2:,} ({len(tickers):,} symbols × trades + quotes)",
            "",
            "## Tickers (==1)",
        ])

        # Write tickers in chunks for readability
        if tickers:
            for i in range(0, len(tickers), 20):
                chunk = tickers[i:i+20]
                lines.append(", ".join(chunk))
        else:
            lines.append("(none)")

        lines.extend([
            "",
            f"---",
            f"*Extracted at: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC*",
        ])

        return "\n".join(lines)

    def read_completion(self, date: str) -> Optional[Dict]:
        """Read and parse completion marker."""
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
            "time_range": {},
        }

        lines = content.split("\n")
        in_tickers = False

        for line in lines:
            line = line.strip()

            if "TOPS downloaded ==" in line:
                result["tops_downloaded"] = "==1" in line

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
            elif line.startswith("- **Time Range**:"):
                try:
                    time_part = line.split(":", 1)[1].strip()
                    result["time_range"]["raw"] = time_part
                except Exception:
                    pass

            if line.startswith("## Tickers"):
                in_tickers = True
                continue

            if in_tickers:
                if not line or line.startswith("#") or line.startswith("---") or line.startswith("*Extracted at:"):
                    in_tickers = False
                else:
                    tickers = [t.strip() for t in line.split(",") if t.strip()]
                    result["tickers"].extend(tickers)

        result["tickers"] = sorted(set(result["tickers"]))
        result["ticker_count"] = len(result["tickers"])

        return result

    def cleanup_signal(self, date: str) -> bool:
        """Remove .extract_ready from cache (not extractor's job, but provided for completeness)."""
        from config import EXT_CONFIG
        cache_dir = Path(EXT_CONFIG["cache_dir"])
        marker = cache_dir / f"{date}.extract_ready"
        try:
            if marker.exists():
                marker.unlink()
                logger.info(f"Cleaned up signal: {marker}")
            return True
        except Exception as e:
            logger.warning(f"Failed to cleanup signal: {e}")
            return False


from datetime import datetime