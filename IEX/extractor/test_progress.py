from config import EXT_CONFIG
from parser import TOPSParser
from writer import ParquetWriter
from marker import MarkerFile
from progress import extraction_progress_simple, is_interactive
from pathlib import Path

date = '20161212'
pcap_path = r'C:\IEX\cache\20161212_IEXTP1_TOPS1.5.pcap.gz'
output_dir = r'C:\IEX\data\test_extract'

print(f'Testing extraction for {date} with progress bar...')
print(f'is_interactive: {is_interactive()}')

parser = TOPSParser(symbol_filter={'AAPL', 'MSFT'}, parse_trades=True, parse_quotes=True)
writer = ParquetWriter(output_dir, buffer_size=100000, compression='snappy')

trade_count = 0
quote_count = 0

for msg_type, record in extraction_progress_simple(parser, pcap_path, date, show_progress=True):
    symbol = record['symbol']
    if msg_type == 'trade':
        writer.buffer_trade(symbol, record)
        trade_count += 1
    elif msg_type == 'quote':
        writer.buffer_quote(symbol, record)
        quote_count += 1

writer.flush_all()
stats = parser.get_stats()
print(f'Done: {trade_count} trades, {quote_count} quotes, {len(stats["symbols"])} symbols')