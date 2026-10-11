"""
TOPS file downloader with resume capability and progress bar.
"""
import os
import time
import requests
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DM_CONFIG
from logger import get_logger
from progress import download_progress, is_interactive

logger = get_logger(__name__)


class TOPSDownloader:
    """Downloads TOPS PCAP files from IEX with resume and verification."""

    def __init__(self, api_url: str = None, timeout: int = 3600):
        self.api_url = api_url or DM_CONFIG["api_url"]
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": DM_CONFIG["user_agent"]})
        self._hist_index: Dict = {}

    def fetch_hist_index(self) -> List[Dict]:
        """Fetch and parse the HIST index from IEX API."""
        logger.info(f"Fetching HIST index from {self.api_url}")
        try:
            resp = self.session.get(self.api_url, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            # Parse: {date: [{feed, link, size, version, protocol}]}
            tops_dates = []
            for date_str, feeds in data.items():
                for feed in feeds:
                    if feed.get("feed") == "TOPS":
                        tops_dates.append({
                            "date": date_str,
                            "link": feed["link"],
                            "size": feed["size"],
                            "version": feed["version"],
                            "protocol": feed["protocol"],
                        })
                        break  # One TOPS per date

            # Sort by date
            tops_dates.sort(key=lambda x: x["date"])

            # Cache for lookups
            self._hist_index = {d["date"]: d for d in tops_dates}

            logger.info(f"Found {len(tops_dates)} TOPS dates from {tops_dates[0]['date']} to {tops_dates[-1]['date']}")
            return tops_dates

        except Exception as e:
            logger.error(f"Failed to fetch HIST index: {e}")
            raise

    def get_file_info(self, date: str) -> Optional[Dict]:
        """Get file info for a specific date."""
        return self._hist_index.get(date)

    def download(self, date: str, dest_dir: str, progress_bar: bool = None) -> Optional[str]:
        """Download TOPS file for a date with resume support and optional progress bar."""
        info = self.get_file_info(date)
        if not info:
            logger.error(f"No TOPS file info for date {date}")
            return None

        url = info["link"]
        expected_size = int(info["size"])
        version = info["version"]
        protocol = info["protocol"]

        # Construct filename
        filename = f"{date}_{protocol}_TOPS{version}.pcap.gz"
        dest_path = Path(dest_dir) / filename

        dest_dir = Path(dest_dir)
        dest_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"Downloading {date} ({expected_size:,} bytes) -> {dest_path}")

        # Use progress bar setting from config if not explicitly provided
        if progress_bar is None:
            progress_bar = DM_CONFIG.get("show_progress_bars", True) and is_interactive()

        for attempt in range(DM_CONFIG["max_retries"]):
            try:
                if progress_bar:
                    result = download_progress(url, str(dest_path), expected_size, f"DL {date}")
                else:
                    result = self._download_with_resume(url, dest_path, expected_size)
                
                if result:
                    logger.info(f"Download complete: {dest_path}")
                    return str(dest_path)
            except Exception as e:
                logger.warning(f"Download attempt {attempt + 1} failed: {e}")
                if attempt < DM_CONFIG["max_retries"] - 1:
                    time.sleep(DM_CONFIG["retry_delay_sec"] * (attempt + 1))
                else:
                    logger.error(f"All download attempts failed for {date}")
                    # Clean up partial file
                    if dest_path.exists():
                        dest_path.unlink()

        return None

    def _download_with_resume(self, url: str, dest_path: Path, expected_size: int) -> bool:
        """Download with HTTP Range header resume (no progress bar)."""
        # Check existing file
        existing_size = dest_path.stat().st_size if dest_path.exists() else 0

        if existing_size >= expected_size:
            # Verify size matches
            if existing_size == expected_size:
                logger.info(f"File already complete: {dest_path}")
                return True
            else:
                logger.warning(f"File larger than expected, re-downloading: {existing_size} > {expected_size}")
                dest_path.unlink()
                existing_size = 0

        headers = {}
        if existing_size > 0:
            headers["Range"] = f"bytes={existing_size}-"
            logger.info(f"Resuming download from byte {existing_size:,}")

        # Stream download
        with self.session.get(url, headers=headers, stream=True, timeout=self.timeout) as resp:
            if existing_size > 0 and resp.status_code == 416:
                # Range not satisfiable, file might be complete
                logger.warning("Range not satisfiable, checking file")
                return self.verify_size(dest_path, expected_size)

            resp.raise_for_status()

            mode = "ab" if existing_size > 0 else "wb"
            downloaded = existing_size

            with open(dest_path, mode) as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)

                        # Progress log every 100MB
                        if downloaded % (100 * 1024 * 1024) < 8192:
                            pct = (downloaded / expected_size) * 100 if expected_size > 0 else 0
                            logger.info(f"Progress: {downloaded:,}/{expected_size:,} ({pct:.1f}%)")

        return self.verify_size(dest_path, expected_size)

    def verify_size(self, file_path: Path, expected_size: int) -> bool:
        """Verify downloaded file size matches expected."""
        try:
            actual_size = file_path.stat().st_size
            if actual_size == expected_size:
                logger.info(f"Size verified: {actual_size:,} bytes")
                return True
            else:
                logger.error(f"Size mismatch: expected {expected_size:,}, got {actual_size:,}")
                return False
        except Exception as e:
            logger.error(f"Size verification failed: {e}")
            return False

    def get_all_dates(self) -> List[str]:
        """Get sorted list of all TOPS dates."""
        if not self._hist_index:
            self.fetch_hist_index()
        return sorted(self._hist_index.keys())