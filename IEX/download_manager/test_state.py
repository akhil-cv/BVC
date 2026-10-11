from state import DownloadState
from config import DM_CONFIG
state = DownloadState(DM_CONFIG['state_file'])
state.load()
print(f'Queue length: {len(state.state["pending_queue"])}')
print(f'First date: {state.state["pending_queue"][0]}')
print(f'Data root: {state.get_data_root()}')
print(f'Symbol filter: {state.get_symbol_filter()}')