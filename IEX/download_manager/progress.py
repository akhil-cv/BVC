"""
Progress bar utilities using tqdm.
"""
import sys
from pathlib import Path
from typing import Generator, Tuple, Any, Optional

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

import requests
import gzip
import dpkt
import struct


def is_interactive() -> bool:
    """Check if running in interactive terminal."""
    return sys.stdout.isatty()


def download_progress(
    url: str, 
    dest_path: str, 
    total_size: int, 
    desc: str = "Downloading",
    show_progress: bool = True,
    timeout: int = 3600
) -> bool:
    """
    Download with tqdm progress bar.
    Returns True on success.
    """
    show = show_progress and TQDM_AVAILABLE and is_interactive()
    
    try:
        with requests.get(url, stream=True, timeout=timeout) as resp:
            resp.raise_for_status()
            
            # Handle resume - get existing file size
            existing_size = Path(dest_path).stat().st_size if Path(dest_path).exists() else 0
            mode = "ab" if existing_size > 0 else "wb"
            
            if show:
                pbar = tqdm(
                    total=total_size,
                    initial=existing_size,
                    unit="B",
                    unit_scale=True,
                    unit_divisor=1024,
                    desc=desc,
                    leave=True,
                    dynamic_ncols=True
                )
            else:
                pbar = None
            
            try:
                with open(dest_path, mode) as f:
                    for chunk in resp.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            if pbar:
                                pbar.update(len(chunk))
                if pbar:
                    pbar.close()
                return True
            except Exception as e:
                if pbar:
                    pbar.close()
                raise
                
    except Exception as e:
        if Path(dest_path).exists():
            Path(dest_path).unlink()
        raise


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
    show = show_progress and TQDM_AVAILABLE and is_interactive()
    
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


def confirm_delete(path: str) -> bool:
    """
    Prompt user for confirmation before deleting file.
    Returns True if user confirms.
    """
    if not is_interactive():
        return True  # Auto-confirm in non-interactive mode
    
    path = Path(path)
    size_mb = path.stat().st_size / (1024 * 1024) if path.exists() else 0
    
    response = input(f"\nDelete {path.name} ({size_mb:.1f} MB)? [y/N]: ").strip().lower()
    return response in ('y', 'yes')