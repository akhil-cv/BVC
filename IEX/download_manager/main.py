"""
IEX TOPS Download Manager - Main daemon.
"""
import signal
import sys
import time
from typing import Optional

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DM_CONFIG
from logger import setup_logger, get_logger
from lock import CacheLock
from state import DownloadState
from downloader import TOPSDownloader
from extractor_hook import ExtractorSignal
from cleanup import delete_pcap, cleanup_stale_cache
from progress import confirm_delete, is_interactive

logger = get_logger(__name__)


class DownloadManager:
    """Main download manager daemon."""

    def __init__(self):
        self.running = True
        self.lock = CacheLock(
            DM_CONFIG["cache_dir"],
            DM_CONFIG["lock_timeout_sec"]
        )
        self.state = DownloadState(DM_CONFIG["state_file"])
        self.downloader = TOPSDownloader(
            DM_CONFIG["api_url"],
            DM_CONFIG["download_timeout_sec"]
        )
        self.extractor = ExtractorSignal(
            DM_CONFIG["cache_dir"],
            DM_CONFIG["extracted_dir"],
            DM_CONFIG["data_root"]
        )

        # Signal handlers for graceful shutdown
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.running = False

    def initialize(self):
        """Initialize state and fetch TOPS dates."""
        logger.info("Initializing Download Manager")

        # Clean up stale cache
        cleanup_stale_cache(DM_CONFIG["cache_dir"])

        # Load existing state
        self.state.load()

        # Fetch HIST index if we don't have dates
        if not self.state.state["all_tops_dates"]:
            logger.info("No dates in state, fetching from API...")
            tops_data = self.downloader.fetch_hist_index()
            dates = [d["date"] for d in tops_data]
            self.state.set_all_dates(dates)
            self.state.save()

        logger.info(f"State: {self.state.state['stats']}")
        logger.info(f"Pending queue: {len(self.state.state['pending_queue'])} dates")
        logger.info(f"Data root: {self.state.get_data_root()}")
        logger.info(f"Message types: {self.state.get_message_types()}")
        logger.info(f"Progress bars: {'enabled' if self.state.get_progress_bar_setting() else 'disabled'}")
        logger.info(f"Confirm before delete: {'enabled' if self.state.get_confirm_delete_setting() else 'disabled'}")

    def process_date(self, date: str) -> bool:
        """Process a single date: download -> signal extractor -> wait -> cleanup."""
        logger.info(f"=== Processing date: {date} ===")

        # Get settings from state
        progress_bar = self.state.get_progress_bar_setting()
        confirm_delete_setting = self.state.get_confirm_delete_setting()
        data_root = self.state.get_data_root()

        # Mark in progress (already set by pop_next_pending)
        self.state.save()
        self.lock.update_status("downloading", date)

        # Download with progress bar
        pcap_path = self.downloader.download(date, DM_CONFIG["cache_dir"], progress_bar=DM_CONFIG.get("show_progress_bars", True))
        if not pcap_path:
            self.state.mark_failed(date, "download failed after retries")
            self.state.save()
            return False

        # Signal extractor with data_root from state
        self.state.mark_extraction_pending(date)
        self.state.save()
        self.lock.update_status("extracting", date)

        if not self.extractor.signal_ready(date, pcap_path, data_root):
            self.state.mark_failed(date, "failed to signal extractor")
            self.state.save()
            return False

        # Wait for extraction
        if self.extractor.wait_for_completion(date, DM_CONFIG["extractor_wait_sec"]):
            # Read results
            marker = self.extractor.read_marker(date)
            if marker:
                tickers = marker.get("tickers", [])
                self.state.mark_extracted(date, tickers)
                logger.info(f"Extraction verified: {len(tickers)} tickers")

                # Cleanup PCAP from cache with confirmation
                self.lock.update_status("cleanup", date)
                if confirm_delete_setting and is_interactive():
                    if confirm_delete(pcap_path):
                        delete_pcap(pcap_path)
                    else:
                        logger.info(f"Skipped deletion of {pcap_path} (user declined)")
                else:
                    delete_pcap(pcap_path)
            else:
                logger.warning("Marker read failed, but extraction reported complete")
                self.state.mark_completed(date)
        else:
            self.state.mark_failed(date, "extraction timeout")
            self.state.save()
            return False

        self.state.save()
        logger.info(f"=== Completed date: {date} ===")
        return True

    def run(self):
        """Main daemon loop."""
        self.initialize()

        logger.info("Starting download manager daemon loop")
        poll_interval = DM_CONFIG["poll_interval_sec"]

        while self.running:
            try:
                # Check pause state before acquiring lock
                self.state.load()
                if self.state.is_paused():
                    logger.info("Download manager paused. Sleeping 30s...")
                    time.sleep(30)
                    continue

                # Try to acquire lock
                acquired = False
                with self.lock as lock:
                    if lock.acquire(""):
                        acquired = True

                        # Reload state in case of external updates (manage.py changes)
                        self.state.load()

                        # Check pause again after acquiring lock
                        if self.state.is_paused():
                            logger.info("Paused while waiting for lock. Releasing...")
                            continue

                        # Get next pending date from queue (pops from front)
                        date = self.state.pop_next_pending()

                        if not date:
                            logger.info("All dates completed. Sleeping 5 minutes.")
                            time.sleep(300)
                            continue

                        # Process this date
                        self.process_date(date)

                if not acquired:
                    # Couldn't acquire lock, wait and retry
                    logger.debug("Could not acquire lock, waiting...")
                    time.sleep(poll_interval)

            except KeyboardInterrupt:
                logger.info("Interrupted by user")
                break
            except Exception as e:
                logger.exception(f"Daemon error: {e}")
                time.sleep(poll_interval)

        logger.info("Download manager stopped")


def main():
    # Setup logging
    setup_logger(
        "download_manager",
        DM_CONFIG["log_file"],
        level="INFO",
        json_format=True,
    )

    logger.info("=" * 60)
    logger.info("IEX TOPS Download Manager Starting")
    logger.info("=" * 60)

    manager = DownloadManager()
    manager.run()

    logger.info("Download Manager shutdown complete")


if __name__ == "__main__":
    main()