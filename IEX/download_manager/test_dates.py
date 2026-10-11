from downloader import TOPSDownloader

dm = TOPSDownloader()
dates = dm.fetch_hist_index()
print(f"Total dates: {len(dates)}")
print(f"First date: {dates[0]['date']}")
print(f"Last date: {dates[-1]['date']}")

# Check skip date
skip = ['20261009']
available = [d for d in dates if d['date'] not in skip]
print(f"After skip: {len(available)} dates")
print(f"First available: {available[0]['date']}")