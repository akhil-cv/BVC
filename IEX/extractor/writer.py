"""
Buffered Parquet writer for Extractor agent.
Writes each buffer as a separate file to avoid corruption and file handle limits.
"""
import pyarrow as pa
import pyarrow.parquet as pq
from pathlib import Path
from typing import Dict, List, Any

from config import EXT_CONFIG
from logger import get_logger

logger = get_logger(__name__)


# Parquet schemas
TRADE_SCHEMA = pa.schema([
    ("timestamp", pa.int64()),
    ("symbol", pa.string()),
    ("price", pa.float64()),
    ("size", pa.int64()),
    ("trade_id", pa.int64()),
    ("flags", pa.int64()),
    ("packet_no", pa.int64()),
])

QUOTE_SCHEMA = pa.schema([
    ("timestamp", pa.int64()),
    ("symbol", pa.string()),
    ("bid_price", pa.float64()),
    ("bid_size", pa.int64()),
    ("ask_price", pa.float64()),
    ("ask_size", pa.int64()),
    ("flags", pa.int64()),
    ("packet_no", pa.int64()),
])


class ParquetWriter:
    """Buffered Parquet writer - writes each buffer as separate file."""

    def __init__(self, output_dir: str, buffer_size: int = 100_000, compression: str = "snappy"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.buffer_size = buffer_size
        self.compression = compression

        # Buffers per symbol
        self.trade_buffers: Dict[str, List[Dict]] = {}
        self.quote_buffers: Dict[str, List[Dict]] = {}

        # Sequence numbers for file naming
        self.trade_seq: Dict[str, int] = {}
        self.quote_seq: Dict[str, int] = {}

        self.trade_counts: Dict[str, int] = {}
        self.quote_counts: Dict[str, int] = {}

    def _sanitize_symbol(self, symbol: str) -> str:
        """Sanitize symbol for use as filename."""
        # Replace invalid Windows filename characters
        invalid = '<>:"/\\|?*'
        result = ''.join(c if c not in invalid else '_' for c in symbol)
        return result

    def _write_buffer(self, symbol: str, buffer: List[Dict], schema: pa.Schema, suffix: str, seq: int):
        """Write buffer to a new Parquet file."""
        if not buffer:
            return

        safe_symbol = self._sanitize_symbol(symbol)
        path = self.output_dir / f"{safe_symbol}_{suffix}_{seq:04d}.parquet"

        try:
            table = pa.Table.from_pylist(buffer, schema=schema)
            pq.write_table(table, path, compression=self.compression)
        except Exception as e:
            logger.error(f"Failed to write {suffix} buffer for {symbol}: {e}")
            raise

    def buffer_trade(self, symbol: str, record: Dict[str, Any]):
        """Add trade record to buffer, flush if full."""
        buf = self.trade_buffers.setdefault(symbol, [])
        buf.append(record)

        if len(buf) >= self.buffer_size:
            seq = self.trade_seq.get(symbol, 0) + 1
            self._write_buffer(symbol, buf, TRADE_SCHEMA, "trades", seq)
            self.trade_seq[symbol] = seq
            self.trade_counts[symbol] = self.trade_counts.get(symbol, 0) + len(buf)
            buf.clear()

    def buffer_quote(self, symbol: str, record: Dict[str, Any]):
        """Add quote record to buffer, flush if full."""
        buf = self.quote_buffers.setdefault(symbol, [])
        buf.append(record)

        if len(buf) >= self.buffer_size:
            seq = self.quote_seq.get(symbol, 0) + 1
            self._write_buffer(symbol, buf, QUOTE_SCHEMA, "quotes", seq)
            self.quote_seq[symbol] = seq
            self.quote_counts[symbol] = self.quote_counts.get(symbol, 0) + len(buf)
            buf.clear()

    def flush_all(self):
        """Flush all buffers."""
        # Flush remaining trade buffers
        for symbol, buf in list(self.trade_buffers.items()):
            if buf:
                seq = self.trade_seq.get(symbol, 0) + 1
                self._write_buffer(symbol, buf, TRADE_SCHEMA, "trades", seq)
                self.trade_seq[symbol] = seq
                self.trade_counts[symbol] = self.trade_counts.get(symbol, 0) + len(buf)
                buf.clear()

        # Flush remaining quote buffers
        for symbol, buf in list(self.quote_buffers.items()):
            if buf:
                seq = self.quote_seq.get(symbol, 0) + 1
                self._write_buffer(symbol, buf, QUOTE_SCHEMA, "quotes", seq)
                self.quote_seq[symbol] = seq
                self.quote_counts[symbol] = self.quote_counts.get(symbol, 0) + len(buf)
                buf.clear()

        logger.info(f"All buffers flushed. Trade counts: {sum(self.trade_counts.values()):,}, Quote counts: {sum(self.quote_counts.values()):,}")

    def get_stats(self) -> Dict[str, Any]:
        """Get per-symbol statistics."""
        return {
            "symbols": list(set(list(self.trade_counts.keys()) + list(self.quote_counts.keys()))),
            "trade_counts": self.trade_counts,
            "quote_counts": self.quote_counts,
            "total_trades": sum(self.trade_counts.values()),
            "total_quotes": sum(self.quote_counts.values()),
        }

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.flush_all()
        return False