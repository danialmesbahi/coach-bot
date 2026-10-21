"""Refresh app/data/ir_ipv4.txt from the aggregated RIR allocation list for Iran."""
import datetime
import ipaddress
import urllib.request
from pathlib import Path

SOURCE = 'https://raw.githubusercontent.com/ipverse/rir-ip/master/country/ir/ipv4-aggregated.txt'
TARGET = Path(__file__).resolve().parent.parent / 'app' / 'data' / 'ir_ipv4.txt'

with urllib.request.urlopen(SOURCE, timeout=30) as response:
    lines = [l.strip() for l in response.read().decode().splitlines() if l.strip() and not l.startswith('#')]
for line in lines:
    ipaddress.IPv4Network(line)  # Refuse to write anything that is not a CIDR list.
if len(lines) < 500:
    raise SystemExit(f'Only {len(lines)} ranges; refusing to replace the list.')
header = (f'# Iranian IPv4 ranges (RIR allocations, aggregated). Source: github.com/ipverse/rir-ip country/ir. '
          f'Updated {datetime.date.today()}.\n# Refresh with: python scripts/update_ir_ranges.py\n')
TARGET.write_text(header + '\n'.join(lines) + '\n')
print(f'{len(lines)} ranges written to {TARGET}')
