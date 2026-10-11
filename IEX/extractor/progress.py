"""
Progress bar utilities for Extractor using tqdm.
"""
import sys
from pathlib import Path
from typing import Generator, Tuple, Any

try:
    from tqdm import tqdm
    TQDM_AVAILABLE = True
except ImportError:
    TQDM_AVAILABLE = False
    def tqdm(*args, **kwargs):
        class DummyTqdm:
            def __init__(self, *args, **kwargs): pass
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def update(self, n): pass
            def set_description(self, desc): pass
            def refresh(self): pass
        return DummyTqdm()

import gzip
import dpkt
import struct


def is_interactive() -> bool:
    """Check if running in interactive terminal."""
    return sys.stdout.isatty()


def estimate_pcap_messages(pcap_path: str, sample_packets: int = 100) -> int:
    """
    Quick estimate of total messages in PCAP for progress bar.
    Samples first N packets to estimate avg messages/packet.
    """
    try:
        with gzip.open(pcap_path, "rb") as f:
            try:
                pcap = dpkt.pcapng.Reader(f)
            except Exception:
                f.seek(0)
                pcap = dpkt.pcap.Reader(f)
            
            sampled = 0
            total_msgs = 0
            
            for _, (_, raw) in enumerate(pcap):
                if sampled >= sample_packets:
                    break
                try:
                    eth = dpkt.ethernet.Ethernet(raw)
                    ip = eth.data
                    if not isinstance(ip, dpkt.ip.IP):
                        continue
                    udp = ip.data
                    if not isinstance(udp, dpkt.udp.UDP):
                        continue
                    payload = udp.data
                    if len(payload) < 16:
                        continue
                    msg_count = struct.unpack_from("<H", payload, 14)[0]
                    total_msgs += msg_count
                    sampled += 1
                except Exception:
                    continue
            
            if sampled == 0:
                return 1_000_000  # fallback
            
            avg_per_packet = total_msgs / sampled
            # Rough estimate of total packets in file
            return int(avg_per_packet * 500_000)
            
    except Exception:
        return 1_000_000


def extraction_progress(
    parser,
    pcap_path: str,
    date: str,
    parse_trades: bool,
    parse_quotes: bool,
    desc: str = "Extracting",
    show_progress: bool = True
) -> Generator[Tuple[str, dict], None, None]:
    """
    Wrap parser generator with tqdm progress bar.
    """
    show = show_progress and False  # We'll check TQDM_AVAILABLE and is_interactive
    
    try:
        from tqdm import tqdm
        TQDM_AVAILABLE = True
    except ImportError:
        TQDM_AVAILABLE = False
    
    show = show_progress and TQDM_AVAILABLE and (sys.stdout.isatty() if 'sys' in globals() else False)
    
    if show:
        total_estimate = estimate_pcap_messages(pcap_path)
        pbar = tqdm(
            total=total_estimate,
            unit="msgs",
            desc=f"{desc} {date}",
            leave=True,
            dynamic_ncols=True,
            smoothing=0.1
        )
    else:
        pbar = None
    
    try:
        for msg_type, record in parser.parse_pcap(pcap_path, date):
            yield msg_type, record
            if pbar:
                pbar.update(1)
        
        # If we processed more than estimate, update total
        if pbar and pbar.n > pbar.total:
            pbar.total = pbar.n
            pbar.refresh()
    finally:
        if pbar:
            pbar.close()


def extraction_progress_simple(
    parser,
    pcap_path: str,
    date: str,
    desc: str = "Extracting",
    show_progress: bool = True
) -> Generator[Tuple[str, dict], None, None]:
    """
    Simple wrapper that works with any parser that has parse_pcap method.
    """
    import sys
    
    try:
        from tqdm import tqdm
        TQDM_AVAILABLE = True
    except ImportError:
        TQDM_AVAILABLE = False
    
    show = show_progress and TQDM_AVAILABLE and sys.stdout.isatty()
    
    if show:
        total_estimate = estimate_pcap_messages(pcap_path)
        pbar = tqdm(
            total=total_estimate,
            unit="msgs",
            desc=f"{desc} {date}",
            leave=True,
            dynamic_ncols=True,
            smoothing=0.1
        )
    else:
        pbar = None
    
    try:
        for msg_type, record in parser.parse_pcap(pcap_path, date):
            yield msg_type, record
            if pbar:
                pbar.update(1)
        
        if pbar and pbar.n > pbar.total:
            pbar.total = pbar.n
            pbar.refresh()
    finally:
        if pbar:
            pbar.close()