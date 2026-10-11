import json
with open(r'C:\IEX\state.json', 'r') as f:
    state = json.load(f)
print(f"Stats: {state['stats']}")
print(f"Completed: {len(state['completed'])}")
print(f"First 5 completed: {state['completed'][:5]}")
print(f"In progress: {state['in_progress']}")
print(f"Extraction pending: {state['extraction_pending']}")
if 'extracted_info' in state:
    print(f"Extracted info for 20161212: {state['extracted_info'].get('20161212', {}).get('ticker_count', 'N/A')}")