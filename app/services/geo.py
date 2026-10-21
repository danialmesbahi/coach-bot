"""Is a visitor's address Iranian? Used only to warn VPN users before the bank gateway refuses them."""
import ipaddress
from bisect import bisect_right
from functools import cache
from pathlib import Path

RANGES = Path(__file__).resolve().parent.parent / 'data' / 'ir_ipv4.txt'


@cache
def _ranges():
    spans=[]
    for line in RANGES.read_text().splitlines():
        if line and not line.startswith('#'):
            net=ipaddress.IPv4Network(line.strip())
            spans.append((int(net.network_address),int(net.broadcast_address)))
    spans.sort()
    return [s for s,_ in spans],[e for _,e in spans]


def is_iranian(address: str | None) -> bool | None:
    """True or False for a public IPv4 address; None when unknown (IPv6, private, malformed), which callers must not block."""
    try:
        ip=ipaddress.ip_address((address or '').strip())
    except ValueError:
        return None
    if ip.version!=4 or not ip.is_global:
        return None
    starts,ends=_ranges()
    i=bisect_right(starts,int(ip))-1
    return i>=0 and int(ip)<=ends[i]
