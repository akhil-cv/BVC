"""
TOPS PCAP Parser - extracts trades and quotes from IEX TOPS feed.
Based on logic from C:/GIT/BVC/IEX_download.ipynb
"""
import gzip
import struct
import dpkt
from pathlib import Path
from typing import Generator, Tuple, Dict, Any, Optional, Set
from datetime import datetime

from config import TRADE_FMT, TRADE_SIZE, QUOTE_FMT, QUOTE_SIZE, MSG_TRADE, MSG_QUOTE
from logger import get_logger

logger = get_logger(__name__)


class TOPSParser:
    """Parses IEX TOPS PCAP files and yields trade/quote messages."""

    def __init__(self, symbol_filter: Set[str] = None, parse_trades: bool = True, parse_quotes: bool = False):
        """
        Initialize parser.
        
        Args:
            symbol_filter: Set of symbols to extract. None = all symbols.
            parse_trades: Whether to parse trade messages (type T).
            parse_quotes: Whether to parse quote messages (type Q).
        """
        self.symbol_filter = symbol_filter
        self.parse_trades = parse_trades
        self.parse_quotes = parse_quotes
        self.trade_count = 0
        self.quote_count = 0
        self.symbols: Set[str] = set()
        self.first_timestamp: Optional[int] = None
        self.last_timestamp: Optional[int] = None
        self.packet_count = 0

    def _should_process_symbol(self, symbol: str) -> bool:
        """Check if symbol should be processed based on filter."""
        if self.symbol_filter is None:
            return True
        return symbol in self.symbol_filter

    def parse_pcap(self, pcap_path: str, date: str) -> Generator[Tuple[str, Dict[str, Any]], None, None]:
        """
        Parse PCAP file and yield (msg_type, parsed_dict) for each TOPS message.
        
        Yields:
            ("trade", {...}) or ("quote", {...})
        """
        self._reset_stats()

        path = Path(pcap_path)
        if not path.exists():
            logger.error(f"PCAP file not found: {pcap_path}")
            return

        logger.info(f"Parsing PCAP: {pcap_path} (filter: {self.symbol_filter or 'all'})")

        try:
            with gzip.open(pcap_path, "rb") as f:
                # Try pcapng first, then pcap
                try:
                    pcap = dpkt.pcapng.Reader(f)
                except Exception:
                    f.seek(0)
                    pcap = dpkt.pcap.Reader(f)

                for packet_no, (pcap_ts, raw_packet) in enumerate(pcap):
                    self.packet_count = packet_no

                    # Parse Ethernet -> IP -> UDP
                    try:
                        eth = dpkt.ethernet.Ethernet(raw_packet)
                        ip = eth.data
                        if not isinstance(ip, dpkt.ip.IP):
                            continue
                        udp = ip.data
                        if not isinstance(udp, dpkt.udp.UDP):
                            continue
                        payload = udp.data
                    except Exception:
                        continue

                    # Parse IEX-TP header + messages
                    # IEX-TP: 14 bytes header, then message count (2 bytes), then messages
                    if len(payload) < 16:
                        continue

                    # Message count at offset 14 (per notebook)
                    msg_count = struct.unpack_from("<H", payload, 14)[0]
                    data = payload[40:]  # Skip IEX-TP header (40 bytes per notebook)
                    pos = 0

                    for _ in range(msg_count):
                        if pos + 2 > len(data):
                            break

                        msg_len = struct.unpack_from("<H", data, pos)[0]
                        msg_start = pos + 2
                        msg_end = msg_start + msg_len

                        if msg_end > len(data):
                            break

                        msg = data[msg_start:msg_end]

                        # Parse message based on type
                        if len(msg) >= TRADE_SIZE and msg[0] == MSG_TRADE:
                            parsed = self._parse_trade(msg, packet_no)
                            if parsed:
                                yield "trade", parsed
                        elif len(msg) >= QUOTE_SIZE and msg[0] == MSG_QUOTE:
                            parsed = self._parse_quote(msg, packet_no)
                            if parsed:
                                yield "quote", parsed

                        pos = msg_end

                    # Progress log
                    if packet_no % 10_000_000 == 0 and packet_no > 0:
                        logger.info(f"Processed {packet_no:,} packets, "
                                  f"{self.trade_count:,} trades, {self.quote_count:,} quotes")

        except Exception as e:
            logger.error(f"PCAP parse error: {e}")

        logger.info(f"Parse complete: {self.packet_count:,} packets, "
                   f"{self.trade_count:,} trades, {self.quote_count:,} quotes, "
                   f"{len(self.symbols)} symbols")

    def _parse_trade(self, msg: bytes, packet_no: int) -> Optional[Dict[str, Any]]:
        """Parse trade message (type T)."""
        try:
            # Format: type(1) + flags(1) + timestamp(8) + symbol(8) + size(4) + price(8) + trade_id(8)
            fields = struct.unpack(TRADE_FMT, msg[:TRADE_SIZE])

            msg_type, flags, timestamp, symbol_bytes, size, price_raw, trade_id = fields

            # Decode symbol (8 bytes, null-padded ASCII)
            symbol = symbol_bytes.decode("ascii", errors="ignore").rstrip("\x00").strip()
            if not symbol:
                return None

            # Apply symbol filter early to avoid unnecessary processing
            if not self._should_process_symbol(symbol):
                return None

            # Price is fixed-point 4 decimals
            price = price_raw / 10000.0

            # Track stats
            self.trade_count += 1
            self.symbols.add(symbol)
            self._update_time_range(timestamp)

            return {
                "timestamp": timestamp,
                "symbol": symbol,
                "price": price,
                "size": size,
                "trade_id": trade_id,
                "flags": flags,
                "packet_no": packet_no,
            }

        except Exception as e:
            logger.debug(f"Trade parse error: {e}")
            return None

    def _parse_quote(self, msg: bytes, packet_no: int) -> Optional[Dict[str, Any]]:
        """Parse quote message (type Q)."""
        try:
            # Format: type(1) + flags(1) + timestamp(8) + symbol(8) + bid_size(4) + bid_price(8) + ask_size(4) + ask_price(8)
            fields = struct.unpack(QUOTE_FMT, msg[:QUOTE_SIZE])

            msg_type, flags, timestamp, symbol_bytes, bid_size, bid_price_raw, ask_size, ask_price_raw = fields

            symbol = symbol_bytes.decode("ascii", errors="ignore").rstrip("\x00").strip()
            if not symbol:
                return None

            # Apply symbol filter early to avoid unnecessary processing
            if not self._should_process_symbol(symbol):
                return None

            bid_price = bid_price_raw / 10000.0
            ask_price = ask_price_raw / 10000.0

            self.quote_count += 1
            self.symbols.add(symbol)
            self._update_time_range(timestamp)

            return {
                "timestamp": timestamp,
                "symbol": symbol,
                "bid_price": bid_price,
                "bid_size": bid_size,
                "ask_price": ask_price,
                "ask_size": ask_size,
                "flags": flags,
                "packet_no": packet_no,
            }

        except Exception as e:
            logger.debug(f"Quote parse error: {e}")
            return None

    def _update_time_range(self, timestamp: int):
        if self.first_timestamp is None or timestamp < self.first_timestamp:
            self.first_timestamp = timestamp
        if self.last_timestamp is None or timestamp > self.last_timestamp:
            self.last_timestamp = timestamp

    def _reset_stats(self):
        self.trade_count = 0
        self.quote_count = 0
        self.symbols = set()
        self.first_timestamp = None
        self.last_timestamp = None
        self.packet_count = 0

    def get_stats(self) -> Dict[str, Any]:
        return {
            "trade_count": self.trade_count,
            "quote_count": self.quote_count,
            "symbols": sorted(self.symbols),
            "symbol_count": len(self.symbols),
            "first_timestamp": self.first_timestamp,
            "last_timestamp": self.last_timestamp,
            "packet_count": self.packet_count,
        }

    def get_time_range(self) -> Dict[str, Any]:
        """Get human-readable time range."""
        if self.first_timestamp is None:
            return {}

        def ns_to_str(ns: int) -> str:
            dt = datetime.utcfromtimestamp(ns / 1e9)
            return dt.strftime("%H:%M:%S.%f")

        return {
            "start_ns": self.first_timestamp,
            "end_ns": self.last_timestamp,
            "start_str": ns_to_str(self.first_timestamp),
            "end_str": ns_to_str(self.last_timestamp),
        }