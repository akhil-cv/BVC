"""
Test extractor parser with a proper IEX-TP formatted PCAP.
"""
import gzip
import struct
import dpkt
import os
import shutil
from parser import TOPSParser
from writer import ParquetWriter
from marker import MarkerFile

# IEX message format constants
TRADE_FMT = "<BBQ8sIqQ"
TRADE_SIZE = 38
QUOTE_FMT = "<BBQ8sIqIq"
QUOTE_SIZE = 42


def create_iextp_payload(messages: list) -> bytes:
    """
    Create IEX-TP payload with proper header.
    Based on IEX-TP v1 spec: 40 byte header + message count (2 bytes) + messages
    """
    # IEX-TP header (40 bytes)
    # seq_num (8) + msg_count (2) + ... 
    # For simplicity, use minimal header
    iextp_header = struct.pack('<QH', 1234567890, len(messages))  # seq, count
    iextp_header += b'\x00' * (40 - len(iextp_header))  # pad to 40 bytes
    
    # Message count at offset 14 (as per notebook)
    # Actually the notebook reads from offset 14, so we need 14 bytes before count
    # Let's build it properly:
    # bytes 0-13: header prefix
    # bytes 14-15: message count (uint16)
    # bytes 16-39: rest of header
    # bytes 40+: message data
    
    header_prefix = struct.pack('<QH', 1234567890, len(messages))  # 10 bytes
    header_prefix += b'\x00' * (14 - len(header_prefix))  # pad to 14 bytes
    
    msg_count = struct.pack('<H', len(messages))  # at offset 14
    
    header_suffix = b'\x00' * (40 - 14 - 2)  # remaining to reach 40 bytes
    
    iextp_header = header_prefix + msg_count + header_suffix
    
    # Message data: each message prefixed with 2-byte length
    msg_data = b''
    for msg in messages:
        msg_data += struct.pack('<H', len(msg)) + msg
    
    return iextp_header + msg_data


def create_test_pcap(output_path: str):
    """Create a PCAP with IEX-TP formatted payload."""
    
    # Build messages
    trade1 = struct.pack(TRADE_FMT,
        ord('T'), 0, 1700000000000000000, b'AAPL\x00\x00\x00\x00', 100, 1500000, 1)
    
    trade2 = struct.pack(TRADE_FMT,
        ord('T'), 0, 1700000000000000100, b'MSFT\x00\x00\x00\x00', 50, 3000000, 2)
    
    quote1 = struct.pack(QUOTE_FMT,
        ord('Q'), 0, 1700000000000000050, b'AAPL\x00\x00\x00\x00', 
        100, 1499900, 200, 1500100)
    
    payload = create_iextp_payload([trade1, trade2, quote1])
    
    # Build packet: Ethernet -> IP -> UDP -> payload
    udp = dpkt.udp.UDP(sport=50000, dport=50001, data=payload)
    udp.ulen = len(udp)
    
    ip = dpkt.ip.IP(src=b'\xc0\xa8\x00\x01', dst=b'\xc0\xa8\x00\x02', 
                    p=dpkt.ip.IP_PROTO_UDP, data=udp)
    
    eth = dpkt.ethernet.Ethernet(src=b'\x00\x00\x00\x00\x00\x01', 
                                 dst=b'\x00\x00\x00\x00\x00\x02',
                                 type=dpkt.ethernet.ETH_TYPE_IP, data=ip)
    
    pkt_bytes = bytes(eth)
    
    # Write PCAP
    pcap_header = struct.pack('<IHHIIII', 0xa1b2c3d4, 2, 4, 0, 0, 65535, 1)
    
    with open(output_path, 'wb') as f:
        f.write(pcap_header)
        pkt_header = struct.pack('<IIII', 1700000000, 0, len(pkt_bytes), len(pkt_bytes))
        f.write(pkt_header)
        f.write(pkt_bytes)
    
    # Compress
    gz_path = output_path + '.gz'
    with open(output_path, 'rb') as f_in:
        with gzip.open(gz_path, 'wb') as f_out:
            f_out.write(f_in.read())
    
    os.unlink(output_path)
    return gz_path


def test_parser():
    """Test the parser with synthetic data."""
    print("Creating test PCAP...")
    gz_path = create_test_pcap("test.pcap")
    print(f"Created: {gz_path}")
    
    print("Parsing...")
    parser = TOPSParser()
    trades = 0
    quotes = 0
    symbols = set()
    
    for msg_type, record in parser.parse_pcap(gz_path, "20240101"):
        print(f"  {msg_type}: {record}")
        if msg_type == "trade":
            trades += 1
        elif msg_type == "quote":
            quotes += 1
        symbols.add(record["symbol"])
    
    print(f"Results: {trades} trades, {quotes} quotes, symbols: {symbols}")
    
    # Test writer
    print("Testing writer...")
    with ParquetWriter("test_output", buffer_size=10) as writer:
        parser = TOPSParser()
        for msg_type, record in parser.parse_pcap(gz_path, "20240101"):
            if msg_type == "trade":
                writer.buffer_trade(record["symbol"], record)
            elif msg_type == "quote":
                writer.buffer_quote(record["symbol"], record)
        writer.flush_all()
    
    # Test marker
    print("Testing marker...")
    marker = MarkerFile("test_extracted", "test_data")
    stats = {
        "trade_count": trades,
        "quote_count": quotes,
        "symbols": list(symbols),
        "time_range": {"start_str": "09:30:00", "end_str": "16:00:00"}
    }
    marker.write_completion("20240101", "test_output", stats)
    
    # Read back
    result = marker.read_completion("20240101")
    print(f"Marker read back: {result}")
    
    # Cleanup
    os.unlink(gz_path)
    shutil.rmtree("test_output", ignore_errors=True)
    shutil.rmtree("test_extracted", ignore_errors=True)
    shutil.rmtree("test_data", ignore_errors=True)
    
    print("All tests passed!")


if __name__ == "__main__":
    test_parser()