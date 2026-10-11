from downloader import TOPSDownloader
from config import DM_CONFIG

dm = TOPSDownloader()
dates = dm.fetch_hist_index()
first = [d for d in dates if d['date'] == '20161212'][0]
print(f"Expected size: {first['size']}")
print(f"Current file: {424599552}")
print(f"Remaining: {int(first['size']) - 424599552} bytes")