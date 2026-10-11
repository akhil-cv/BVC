"""
Cleanup utilities for download manager.
"""
import os
from pathlib import Path
from typing import List

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DM_CONFIG
from logger import get_logger

logger = get_logger(__name__)


def delete_pcap(pcap_path: str) -> bool:
    """Delete downloaded PCAP file after extraction."""
    path = Path(pcap_path)
    try:
        if path.exists():
            size = path.stat().st_size
            path.unlink()
            logger.info(f"Deleted PCAP: {path} ({size:,} bytes)")
        return True
    except Exception as e:
        logger.error(f"Failed to delete PCAP {pcap_path}: {e}")
        return False


def cleanup_stale_cache(cache_dir: str = None) -> int:
    """Remove orphaned files from cache on startup."""
    cache_dir = Path(cache_dir or DM_CONFIG["cache_dir"])
    if not cache_dir.exists():
        return 0

    removed = 0
    # Keep: .lock, *.extract_ready, *.pcap.gz (active)
    # Remove: any other files
    for item in cache_dir.iterdir():
        if item.name == ".lock":
            continue
        if item.suffix == ".pcap.gz":
            # Could be stale from previous run
            # Check if there's a corresponding .extract_ready
            date = item.name.split("_")[0]
            marker = cache_dir / f"{date}.extract_ready"
            if not marker.exists():
                # No active extraction, might be stale
                logger.warning(f"Found orphaned PCAP: {item}")
        elif item.suffix == ".extract_ready":
            # Check if extraction completed
            date = item.stem
            # We'll let the extractor handle this
            pass
        else:
            # Unknown file
            logger.warning(f"Unknown cache file: {item}")

    return removed


def cleanup_completed_pcaps(cache_dir: str = None, completed_dates: List[str] = None) -> int:
    """Delete PCAP files for dates that are fully completed."""
    cache_dir = Path(cache_dir or DM_CONFIG["cache_dir"])
    if not cache_dir.exists() or not completed_dates:
        return 0

    removed = 0
    for date in completed_dates:
        # Find PCAP for this date
        for pcap in cache_dir.glob(f"{date}_*.pcap.gz"):
            try:
                size = pcap.stat().st_size
                pcap.unlink()
                logger.info(f"Cleaned up completed PCAP: {pcap} ({size:,} bytes)")
                removed += 1
            except Exception as e:
                logger.warning(f"Failed to cleanup PCAP {pcap}: {e}")

    return removed


def get_cache_usage(cache_dir: str = None) -> dict:
    """Get cache directory disk usage."""
    cache_dir = Path(cache_dir or DM_CONFIG["cache_dir"])
    if not cache_dir.exists():
        return {"total_bytes": 0, "file_count": 0, "files": []}

    files = []
    total = 0
    for item in cache_dir.iterdir():
        if item.is_file():
            size = item.stat().st_size
            files.append({"name": item.name, "size": size})
            total += size

    return {
        "total_bytes": total,
        "file_count": len(files),
        "files": files,
    }