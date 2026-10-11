"""
IEX TOPS Extractor Agent - Main daemon.
"""
import json
import signal
import sys
import time
from pathlib import Path
from typing import Optional, Set, Dict, Any

from config import EXT_CONFIG, SHARED_CONFIG
from logger import setup_logger, get_logger
from watcher import FileWatcher
from parser import TOPSParser
from writer import ParquetWriter
from marker import MarkerFile
from progress import extraction_progress_simple

logger = get_logger(__name__)

# State file path (shared with download manager)
STATE_FILE = Path(SHARED_CONFIG.get("state_file", r"C:\IEX\state.json"))


class ExtractorAgent:
    """Main extractor daemon."""

    def __init__(self):
        self.running = True
        self.watcher = FileWatcher(
            EXT_CONFIG["cache_dir"],
            EXT_CONFIG["watch_poll_sec"]
        )
        self.marker = MarkerFile(
            EXT_CONFIG["extracted_dir"],
            EXT_CONFIG["data_root"]
        )

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        logger.info(f"Received signal {signum}, shutting down gracefully...")
        self.running = False

    def _load_state(self) -> Dict[str, Any]:
        """Load shared state.json."""
        try:
            if STATE_FILE.exists():
                with open(STATE_FILE, "r") as f:
                    return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load state: {e}")
        return {}

    def _load_symbol_filter(self) -> Optional[Set[str]]:
        """Load symbol filter from shared state.json."""
        try:
            state = self._load_state()
            filter_cfg = state.get("symbol_filter", {"enabled": False, "symbols": []})
            if filter_cfg.get("enabled") and filter_cfg.get("symbols"):
                symbols = set(filter_cfg["symbols"])
                logger.info(f"Symbol filter enabled: {len(symbols)} symbols")
                return symbols
        except Exception as e:
            logger.warning(f"Failed to load symbol filter from state: {e}")
        return None

    def _load_message_types(self) -> Dict[str, bool]:
        """Load message type filter from shared state.json."""
        try:
            state = self._load_state()
            msg_types = state.get("message_types", {"trades": True, "quotes": False})
            logger.info(f"Message types: trades={msg_types.get('trades', True)}, quotes={msg_types.get('quotes', False)}")
            return msg_types
        except Exception as e:
            logger.warning(f"Failed to load message types from state: {e}")
            return {"trades": True, "quotes": False}

    def _is_paused(self) -> bool:
        """Check if paused from state."""
        try:
            state = self._load_state()
            return state.get("paused", False)
        except Exception:
            return False

    def _get_progress_bar_setting(self) -> bool:
        """Get progress bar setting from state."""
        try:
            state = self._load_state()
            return state.get("show_progress_bars", True)
        except Exception:
            return True

    def process_date(self, date: str, signal: Dict) -> bool:
        """Process a single date: parse PCAP -> write Parquet -> write marker."""
        logger.info(f"=== Processing date: {date} ===")

        pcap_path = signal.get("pcap_path")
        # Use output_dir from signal (set by download manager based on data_root)
        output_dir = signal.get("output_dir", str(Path(EXT_CONFIG["data_root"]) / date))

        if not pcap_path:
            logger.error(f"No pcap_path in signal for {date}")
            return False

        # Load filters from state
        symbol_filter = self._load_symbol_filter()
        message_types = self._load_message_types()
        parse_trades = message_types.get("trades", True)
        parse_quotes = message_types.get("quotes", False)
        show_progress = self._get_progress_bar_setting()

        # Initialize components
        parser = TOPSParser(
            symbol_filter=symbol_filter,
            parse_trades=parse_trades,
            parse_quotes=parse_quotes
        )
        writer = ParquetWriter(
            output_dir,
            EXT_CONFIG["buffer_size"],
            EXT_CONFIG["parquet_compression"]
        )

        try:
            # Parse PCAP and write Parquet with progress bar
            trade_count = 0
            quote_count = 0

            # Use progress bar wrapper if enabled
            if EXT_CONFIG.get("show_progress_bars", True) and show_progress:
                msg_generator = extraction_progress_simple(
                    parser, pcap_path, date, show_progress
                )
            else:
                msg_generator = parser.parse_pcap(pcap_path, date)

            for msg_type, record in msg_generator:
                symbol = record["symbol"]

                if msg_type == "trade" and parse_trades:
                    writer.buffer_trade(symbol, record)
                    trade_count += 1
                elif msg_type == "quote" and parse_quotes:
                    writer.buffer_quote(symbol, record)
                    quote_count += 1

            # Flush all buffers
            writer.flush_all()

            # Get final stats
            stats = parser.get_stats()
            writer_stats = writer.get_stats()

            # Combine stats
            combined_stats = {
                "trade_count": trade_count,
                "quote_count": quote_count,
                "symbols": stats["symbols"],
                "time_range": parser.get_time_range(),
            }

            # Write completion markers
            if self.marker.write_completion(date, output_dir, combined_stats):
                logger.info(f"Completed {date}: {trade_count:,} trades, "
                           f"{quote_count:,} quotes, {len(stats['symbols'])} symbols")
                return True
            else:
                logger.error(f"Failed to write completion marker for {date}")
                return False

        except Exception as e:
            logger.exception(f"Error processing {date}: {e}")
            return False
        finally:
            # Cleanup signal from cache
            self.marker.cleanup_signal(date)

    def run(self):
        """Main daemon loop."""
        logger.info("Starting extractor daemon loop")
        poll_interval = EXT_CONFIG["watch_poll_sec"]

        while self.running:
            try:
                # Check pause state
                if self._is_paused():
                    logger.info("Extractor paused. Sleeping 30s...")
                    time.sleep(30)
                    continue

                pending = self.watcher.get_pending_dates()

                if not pending:
                    time.sleep(poll_interval)
                    continue

                for date, signal in pending:
                    if not self.running:
                        break

                    self.process_date(date, signal)
                    self.watcher.mark_processed(date)

            except KeyboardInterrupt:
                logger.info("Interrupted by user")
                break
            except Exception as e:
                logger.exception(f"Daemon error: {e}")
                time.sleep(poll_interval)

        logger.info("Extractor agent stopped")


def main():
    # Setup logging
    setup_logger(
        "extractor",
        EXT_CONFIG["log_file"],
        level="INFO",
        json_format=True,
    )

    logger.info("=" * 60)
    logger.info("IEX TOPS Extractor Agent Starting")
    logger.info("=" * 60)

    agent = ExtractorAgent()
    agent.run()

    logger.info("Extractor Agent shutdown complete")


if __name__ == "__main__":
    main()