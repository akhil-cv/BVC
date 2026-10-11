from downloader import TOPSDownloader
from config import DM_CONFIG

dm = TOPSDownloader()
dates = dm.fetch_hist_index()

# Test download of first available date (skip 20261009)
skip = ['20261009']
available = [d for d in dates if d['date'] not in skip]
first = available[0]
print(f"Testing download for {first['date']} ({first['size']} bytes)")

pcap_path = dm.download(first['date'], DM_CONFIG['cache_dir'])
print(f"Download result: {pcap_path}")