"""Test full download manager flow for one date."""
import os
import sys
sys.path.insert(0, r"C:\IEX\download_manager")

from config import DM_CONFIG
from logger import setup_logger
from downloader import TOPSDownloader
from state import DownloadState
from lock import CacheLock
from extractor_hook import ExtractorSignal
from cleanup import delete_pcap

# Setup logging
logger = setup_logger("test_flow", DM_CONFIG["log_file"], level="INFO")

# Initialize
lock = CacheLock(DM_CONFIG["cache_dir"], DM_CONFIG["lock_timeout_sec"])
state = DownloadState(DM_CONFIG["state_file"])
state.load()

downloader = TOPSDownloader(DM_CONFIG["api_url"], DM_CONFIG["download_timeout_sec"])
extractor = ExtractorSignal(DM_CONFIG["cache_dir"], DM_CONFIG["extracted_dir"], DM_CONFIG["data_dir"])

# Test with first available date
dates = downloader.fetch_hist_index()
skip = DM_CONFIG.get("skip_dates", [])
available = [d for d in dates if d['date'] not in skip]
first = available[0]
date = first['date']

print(f"Testing full flow for date: {date}")

# Acquire lock
if lock.acquire(date):
    try:
        # Mark in progress
        state.mark_in_progress(date)
        state.save()
        lock.update_status("downloading", date)

        # Download
        pcap_path = downloader.download(date, DM_CONFIG["cache_dir"])
        if not pcap_path:
            state.mark_failed(date, "download failed")
            state.save()
            print("Download failed")
            sys.exit(1)

        print(f"Downloaded: {pcap_path}")

        # Signal extractor
        state.mark_extraction_pending(date)
        state.save()
        lock.update_status("extracting", date)

        if not extractor.signal_ready(date, pcap_path):
            state.mark_failed(date, "failed to signal extractor")
            state.save()
            print("Signal failed")
            sys.exit(1)

        print("Signaled extractor, waiting for completion...")

        # Wait for extraction (with shorter timeout for test)
        if extractor.wait_for_completion(date, timeout=300, poll_interval=5):
            marker = extractor.read_marker(date)
            if marker:
                tickers = marker.get("tickers", [])
                state.mark_extracted(date, tickers)
                print(f"Extraction verified: {len(tickers)} tickers")

                # Cleanup PCAP from cache
                lock.update_status("cleanup", date)
                delete_pcap(pcap_path)
                print("PCAP cleaned up")
            else:
                print("Marker read failed")
                state.mark_failed(date, "marker read failed")
        else:
            print("Extraction timeout")
            state.mark_failed(date, "extraction timeout")

        state.save()
        print("Full flow completed successfully!")

    finally:
        lock.release()
else:
    print("Could not acquire lock")