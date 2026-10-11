from config import EXT_CONFIG, SHARED_CONFIG
from parser import TOPSParser
from writer import ParquetWriter
from marker import MarkerFile
from watcher import FileWatcher

print('Extractor config loaded')
print(f'data_root: {EXT_CONFIG["data_root"]}')
print(f'date_order: {EXT_CONFIG["date_order"]}')
print(f'symbol_filter: {EXT_CONFIG["symbol_filter"]}')
print('All imports OK')