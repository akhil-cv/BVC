#!/usr/bin/env python3
"""
IEX TOPS Management CLI - Control download queue, symbol filter, data root, and new features.
"""
import json
import sys
from pathlib import Path
from typing import List, Optional

# Add download_manager to path for imports
sys.path.insert(0, str(Path(__file__).parent / "download_manager"))

from config import SHARED_CONFIG, DM_CONFIG
from state import DownloadState


STATE_FILE = Path(SHARED_CONFIG.get("state_file", r"C:\IEX\state.json"))


def load_state() -> DownloadState:
    """Load state from file."""
    state = DownloadState(str(STATE_FILE))
    state.load()
    return state


def save_state(state: DownloadState) -> bool:
    """Save state to file."""
    return state.save()


def cmd_queue_show(state: DownloadState, all_dates: bool = False, limit: int = 20):
    """Show pending queue."""
    queue = state.state["pending_queue"]
    if not queue:
        print("Queue is empty.")
        return

    print(f"Pending queue ({len(queue)} dates):")
    print("-" * 40)
    dates_to_show = queue if all_dates else queue[:limit]
    for i, date in enumerate(dates_to_show):
        display = f"{date[:4]}-{date[4:6]}-{date[6:8]}"
        marker = ">>> " if i == 0 else "    "
        print(f"{marker}{i+1:3d}. {date} ({display})")
    if not all_dates and len(queue) > limit:
        print(f"    ... and {len(queue) - limit} more")


def cmd_queue_move_top(state: DownloadState, date: str):
    """Move date to front of queue."""
    if date not in state.state["pending_queue"]:
        print(f"Date {date} not in pending queue.")
        return False
    state.move_date_in_queue(date, 0)
    save_state(state)
    print(f"Moved {date} to front of queue.")
    return True


def cmd_queue_move_bottom(state: DownloadState, date: str):
    """Move date to end of queue."""
    if date not in state.state["pending_queue"]:
        print(f"Date {date} not in pending queue.")
        return False
    state.move_date_in_queue(date, len(state.state["pending_queue"]))
    save_state(state)
    print(f"Moved {date} to end of queue.")
    return True


def cmd_queue_remove(state: DownloadState, date: str):
    """Remove date from queue (mark as skipped)."""
    if date not in state.state["pending_queue"]:
        print(f"Date {date} not in pending queue.")
        return False
    state.remove_from_queue(date)
    save_state(state)
    print(f"Removed {date} from queue.")
    return True


def cmd_queue_reset(state: DownloadState):
    """Rebuild queue from all_tops_dates (latest-first)."""
    confirm = input("This will rebuild the entire queue. Continue? (y/N): ")
    if confirm.lower() != 'y':
        print("Cancelled.")
        return
    state._initialize_queue()
    save_state(state)
    print(f"Queue rebuilt with {len(state.state['pending_queue'])} dates (latest-first).")


def cmd_symbols_show(state: DownloadState):
    """Show current symbol filter."""
    filter_cfg = state.get_symbol_filter()
    enabled = filter_cfg.get("enabled", False)
    symbols = filter_cfg.get("symbols", [])
    print(f"Symbol filter: {'ENABLED' if enabled else 'DISABLED'}")
    if symbols:
        print(f"Symbols ({len(symbols)}):")
        for i, sym in enumerate(sorted(symbols)):
            print(f"  {sym}")
    else:
        print("No symbols configured (will extract all).")


def cmd_symbols_enable(state: DownloadState, symbols: List[str]):
    """Enable symbol filter with given symbols."""
    state.set_symbol_filter(True, symbols)
    save_state(state)
    print(f"Symbol filter ENABLED with {len(symbols)} symbols: {', '.join(sorted(symbols))}")


def cmd_symbols_disable(state: DownloadState):
    """Disable symbol filter (extract all)."""
    state.set_symbol_filter(False, [])
    save_state(state)
    print("Symbol filter DISABLED (will extract all symbols).")


def cmd_symbols_add(state: DownloadState, symbols: List[str]):
    """Add symbols to existing filter."""
    filter_cfg = state.get_symbol_filter()
    current = set(filter_cfg.get("symbols", []))
    current.update(symbols)
    state.set_symbol_filter(filter_cfg.get("enabled", True), list(current))
    save_state(state)
    print(f"Added {len(symbols)} symbols. Total: {len(current)}")


def cmd_symbols_remove(state: DownloadState, symbols: List[str]):
    """Remove symbols from filter."""
    filter_cfg = state.get_symbol_filter()
    current = set(filter_cfg.get("symbols", []))
    for sym in symbols:
        current.discard(sym)
    state.set_symbol_filter(filter_cfg.get("enabled", True), list(current))
    save_state(state)
    print(f"Removed {len(symbols)} symbols. Total: {len(current)}")


def cmd_data_root_show(state: DownloadState):
    """Show current data root."""
    root = state.get_data_root()
    print(f"Data root: {root}")


def cmd_data_root_set(state: DownloadState, path: str):
    """Set data root path."""
    state.set_data_root(path)
    save_state(state)
    print(f"Data root set to: {path}")


# NEW: Pause/Resume commands
def cmd_pause(state: DownloadState):
    """Pause both agents."""
    state.set_paused(True)
    save_state(state)
    print("Agents PAUSED. They will finish current work and wait.")


def cmd_resume(state: DownloadState):
    """Resume both agents."""
    state.set_paused(False)
    save_state(state)
    print("Agents RESUMED. They will continue processing.")


def cmd_pause_status(state: DownloadState):
    """Show pause status."""
    paused = state.is_paused()
    print(f"Paused: {paused}")
    if paused:
        print("Agents will finish current work and wait. Use 'resume' to continue.")


# NEW: Message type commands
def cmd_message_types_show(state: DownloadState):
    """Show current message type filter."""
    msg_types = state.get_message_types()
    trades = msg_types.get("trades", True)
    quotes = msg_types.get("quotes", False)
    print(f"Message types:")
    print(f"  Trades:  {'ENABLED' if trades else 'DISABLED'}")
    print(f"  Quotes:  {'ENABLED' if quotes else 'DISABLED'}")


def cmd_message_types_set(state: DownloadState, trades: bool, quotes: bool):
    """Set message type filter."""
    state.set_message_types(trades, quotes)
    save_state(state)
    print(f"Message types updated: trades={'ENABLED' if trades else 'DISABLED'}, quotes={'ENABLED' if quotes else 'DISABLED'}")


def cmd_message_types_enable(state: DownloadState, types: List[str]):
    """Enable specific message types."""
    # Accept both short (t, q) and long (trades, quotes) forms
    types_lower = [t.lower() for t in types]
    trades = any(t in ('t', 'trades') for t in types_lower)
    quotes = any(t in ('q', 'quotes') for t in types_lower)
    state.set_message_types(trades, quotes)
    save_state(state)
    cmd_message_types_show(state)


def cmd_message_types_disable(state: DownloadState, types: List[str]):
    """Disable specific message types."""
    state.set_message_types("trades" not in types, "quotes" not in types)
    save_state(state)
    cmd_message_types_show(state)


# NEW: Progress bar commands
def cmd_progress_show(state: DownloadState):
    """Show progress bar setting."""
    enabled = state.get_progress_bar_setting()
    print(f"Progress bars: {'ENABLED' if enabled else 'DISABLED'}")


def cmd_progress_enable(state: DownloadState):
    """Enable progress bars."""
    state.set_progress_bar_setting(True)
    save_state(state)
    print("Progress bars ENABLED")


def cmd_progress_disable(state: DownloadState):
    """Disable progress bars."""
    state.set_progress_bar_setting(False)
    save_state(state)
    print("Progress bars DISABLED")


# NEW: Confirm before delete commands
def cmd_confirm_delete_show(state: DownloadState):
    """Show confirm before delete setting."""
    enabled = state.get_confirm_delete_setting()
    print(f"Confirm before delete: {'ENABLED' if enabled else 'DISABLED'}")


def cmd_confirm_delete_enable(state: DownloadState):
    """Enable confirm before delete."""
    state.set_confirm_delete_setting(True)
    save_state(state)
    print("Confirm before delete ENABLED")


def cmd_confirm_delete_disable(state: DownloadState):
    """Disable confirm before delete."""
    state.set_confirm_delete_setting(False)
    save_state(state)
    print("Confirm before delete DISABLED")


def cmd_symbols_show(state: DownloadState):
    """Show current symbol filter."""
    filter_cfg = state.get_symbol_filter()
    enabled = filter_cfg.get("enabled", False)
    symbols = filter_cfg.get("symbols", [])
    print(f"Symbol filter: {'ENABLED' if enabled else 'DISABLED'}")
    if symbols:
        print(f"Symbols ({len(symbols)}):")
        for i, sym in enumerate(sorted(symbols)):
            print(f"  {sym}")
    else:
        print("No symbols configured (will extract all).")


def cmd_symbols_enable(state: DownloadState, symbols: List[str]):
    """Enable symbol filter with given symbols."""
    state.set_symbol_filter(True, symbols)
    save_state(state)
    print(f"Symbol filter ENABLED with {len(symbols)} symbols: {', '.join(sorted(symbols))}")


def cmd_symbols_disable(state: DownloadState):
    """Disable symbol filter (extract all)."""
    state.set_symbol_filter(False, [])
    save_state(state)
    print("Symbol filter DISABLED (will extract all symbols).")


def cmd_symbols_add(state: DownloadState, symbols: List[str]):
    """Add symbols to existing filter."""
    filter_cfg = state.get_symbol_filter()
    current = set(filter_cfg.get("symbols", []))
    current.update(symbols)
    state.set_symbol_filter(filter_cfg.get("enabled", True), list(current))
    save_state(state)
    print(f"Added {len(symbols)} symbols. Total: {len(current)}")


def cmd_symbols_remove(state: DownloadState, symbols: List[str]):
    """Remove symbols from filter."""
    filter_cfg = state.get_symbol_filter()
    current = set(filter_cfg.get("symbols", []))
    for sym in symbols:
        current.discard(sym)
    state.set_symbol_filter(filter_cfg.get("enabled", True), list(current))
    save_state(state)
    print(f"Removed {len(symbols)} symbols. Total: {len(current)}")


def cmd_data_root_show(state: DownloadState):
    """Show current data root."""
    root = state.get_data_root()
    print(f"Data root: {root}")


def cmd_data_root_set(state: DownloadState, path: str):
    """Set data root path."""
    state.set_data_root(path)
    save_state(state)
    print(f"Data root set to: {path}")


def cmd_status(state: DownloadState):
    """Show overall status."""
    stats = state.state["stats"]
    print("=" * 50)
    print("IEX TOPS Status")
    print("=" * 50)
    print(f"Total dates (API):     {stats['total']:,}")
    print(f"Completed:             {stats['done']:,}")
    print(f"Pending (queue):       {stats['pending']:,}")
    print(f"Failed:                {stats['failed']:,}")
    print(f"In progress:           {state.state['in_progress'] or 'None'}")
    print(f"Extraction pending:    {state.state['extraction_pending'] or 'None'}")
    print(f"Data root:             {state.get_data_root()}")
    print(f"Paused:                {state.is_paused()}")
    
    filter_cfg = state.get_symbol_filter()
    print(f"Symbol filter:         {'ENABLED' if filter_cfg['enabled'] else 'DISABLED'} "
          f"({len(filter_cfg['symbols'])} symbols)")
    
    msg_types = state.get_message_types()
    print(f"Message types:         trades={'ENABLED' if msg_types.get('trades', True) else 'DISABLED'}, "
          f"quotes={'ENABLED' if msg_types.get('quotes', False) else 'DISABLED'}")
    
    print(f"Progress bars:         {'ENABLED' if state.get_progress_bar_setting() else 'DISABLED'}")
    print(f"Confirm before delete: {'ENABLED' if state.get_confirm_delete_setting() else 'DISABLED'}")
    
    print(f"\nNext 5 dates in queue:")
    for i, date in enumerate(state.state["pending_queue"][:5]):
        display = f"{date[:4]}-{date[4:6]}-{date[6:8]}"
        print(f"  {i+1}. {date} ({display})")


def print_usage():
    print("""
IEX TOPS Management CLI

Usage: python manage.py <command> [args]

Commands:
  queue --show [--all]           Show pending queue (first 20, or all with --all)
  queue --move-top <date>        Move date to front of queue
  queue --move-bottom <date>     Move date to end of queue
  queue --remove <date>          Remove date from queue (skip it)
  queue --reset                  Rebuild queue from all dates (latest-first)

  symbols --show                 Show current symbol filter
  symbols --enable <sym1> [sym2] Enable filter with symbols
  symbols --disable              Disable filter (extract all)
  symbols --add <sym1> [sym2]    Add symbols to filter
  symbols --remove <sym1> [sym2] Remove symbols from filter

  data-root --show               Show current data root
  data-root <path>               Set data root path

  pause                          Pause both agents (finish current, then wait)
  resume                         Resume both agents
  pause-status                   Show pause status

  message-types --show           Show current message type filter
  message-types --enable <t|q>   Enable types: t=trades, q=quotes (e.g. --enable t q)
  message-types --disable <t|q>  Disable types

  progress --show                Show progress bar setting
  progress --enable              Enable progress bars
  progress --disable             Disable progress bars

  confirm-delete --show          Show confirm before delete setting
  confirm-delete --enable        Enable confirm before delete
  confirm-delete --disable       Disable confirm before delete

  status                         Show overall status

Examples:
  python manage.py queue --show
  python manage.py queue --move-top 20241025
  python manage.py symbols --enable AAPL MSFT NVDA
  python manage.py symbols --add GOOGL
  python manage.py data-root D:\\MarketData\\IEX
  python manage.py pause
  python manage.py resume
  python manage.py message-types --enable t q
  python manage.py progress --disable
  python manage.py confirm-delete --disable
  python manage.py status
""")


def main():
    if len(sys.argv) < 2:
        print_usage()
        return

    state = load_state()
    cmd = sys.argv[1]

    try:
        if cmd == "queue":
            subcmd = sys.argv[2] if len(sys.argv) > 2 else "--show"
            if subcmd == "--show":
                all_dates = "--all" in sys.argv
                cmd_queue_show(state, all_dates=all_dates)
            elif subcmd == "--move-top" and len(sys.argv) > 3:
                cmd_queue_move_top(state, sys.argv[3])
            elif subcmd == "--move-bottom" and len(sys.argv) > 3:
                cmd_queue_move_bottom(state, sys.argv[3])
            elif subcmd == "--remove" and len(sys.argv) > 3:
                cmd_queue_remove(state, sys.argv[3])
            elif subcmd == "--reset":
                cmd_queue_reset(state)
            else:
                print("Unknown queue command. Use --show, --move-top, --move-bottom, --remove, --reset")

        elif cmd == "symbols":
            subcmd = sys.argv[2] if len(sys.argv) > 2 else "--show"
            if subcmd == "--show":
                cmd_symbols_show(state)
            elif subcmd == "--enable" and len(sys.argv) > 3:
                symbols = sys.argv[3:]
                cmd_symbols_enable(state, symbols)
            elif subcmd == "--disable":
                cmd_symbols_disable(state)
            elif subcmd == "--add" and len(sys.argv) > 3:
                symbols = sys.argv[3:]
                cmd_symbols_add(state, symbols)
            elif subcmd == "--remove" and len(sys.argv) > 3:
                symbols = sys.argv[3:]
                cmd_symbols_remove(state, symbols)
            else:
                print("Unknown symbols command. Use --show, --enable, --disable, --add, --remove")

        elif cmd == "data-root":
            if len(sys.argv) == 2 or sys.argv[2] == "--show":
                cmd_data_root_show(state)
            elif len(sys.argv) > 2:
                path = " ".join(sys.argv[2:])
                cmd_data_root_set(state, path)
            else:
                print("Usage: python manage.py data-root [--show] [<path>]")

        elif cmd == "pause":
            cmd_pause(state)

        elif cmd == "resume":
            cmd_resume(state)

        elif cmd == "pause-status":
            cmd_pause_status(state)

        elif cmd == "message-types":
            subcmd = sys.argv[2] if len(sys.argv) > 2 else "--show"
            if subcmd == "--show":
                cmd_message_types_show(state)
            elif subcmd == "--enable" and len(sys.argv) > 3:
                types = sys.argv[3:]
                cmd_message_types_enable(state, types)
            elif subcmd == "--disable" and len(sys.argv) > 3:
                types = sys.argv[3:]
                cmd_message_types_disable(state, types)
            else:
                print("Unknown message-types command. Use --show, --enable, --disable")

        elif cmd == "progress":
            subcmd = sys.argv[2] if len(sys.argv) > 2 else "--show"
            if subcmd == "--show":
                cmd_progress_show(state)
            elif subcmd == "--enable":
                cmd_progress_enable(state)
            elif subcmd == "--disable":
                cmd_progress_disable(state)
            else:
                print("Unknown progress command. Use --show, --enable, --disable")

        elif cmd == "confirm-delete":
            subcmd = sys.argv[2] if len(sys.argv) > 2 else "--show"
            if subcmd == "--show":
                cmd_confirm_delete_show(state)
            elif subcmd == "--enable":
                cmd_confirm_delete_enable(state)
            elif subcmd == "--disable":
                cmd_confirm_delete_disable(state)
            else:
                print("Unknown confirm-delete command. Use --show, --enable, --disable")

        elif cmd == "status":
            cmd_status(state)

        else:
            print(f"Unknown command: {cmd}")
            print_usage()

    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()