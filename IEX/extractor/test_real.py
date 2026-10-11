"""Test extractor on real downloaded file."""
from parser import TOPSParser
from writer import ParquetWriter
from marker import MarkerFile
from config import EXT_CONFIG

date = "20161212"
pcap_path = r"C:\IEX\cache\20161212_IEXTP1_TOPS1.5.pcap.gz"
output_dir = r"C:\IEX\data\20161212"

print(f"Processing {date}...")
print(f"PCAP: {pcap_path}")

parser = TOPSParser()
writer = ParquetWriter(output_dir, buffer_size=100_000, compression="snappy")

trade_count = 0
quote_count = 0

for msg_type, record in parser.parse_pcap(pcap_path, date):
    if msg_type == "trade":
        writer.buffer_trade(record["symbol"], record)
        trade_count += 1
    elif msg_type == "quote":
        writer.buffer_quote(record["symbol"], record)
        quote_count += 1

    if (trade_count + quote_count) % 1_000_000 == 0:
        print(f"  Progress: {trade_count:,} trades, {quote_count:,} quotes")

writer.flush_all()

stats = parser.get_stats()
combined = {
    "trade_count": trade_count,
    "quote_count": quote_count,
    "symbols": stats["symbols"],
    "time_range": parser.get_time_range(),
}

marker = MarkerFile(EXT_CONFIG["extracted_dir"], EXT_CONFIG["data_dir"])
marker.write_completion(date, output_dir, combined)

print(f"Done! {trade_count:,} trades, {quote_count:,} quotes, {len(stats['symbols'])} symbols")

# Cleanup signal
marker.cleanup_signal(date)