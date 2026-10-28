#!/usr/bin/env python3
"""bech32_funded.txt.gz → hash160s.bin (sorted, 20 bytes each, no header)

Usage:
    python3 convert_bech32_to_hash160.py [input.gz] [output.bin]
    Defaults: bech32_funded.txt.gz → hash160s.bin

Requires: pip install bech32
Runtime: ~7 min for 20M addresses on typical SSD
"""
import bech32
import gzip
import time
import sys

input_path = sys.argv[1] if len(sys.argv) > 1 else 'bech32_funded.txt.gz'
output_path = sys.argv[2] if len(sys.argv) > 2 else 'hash160s.bin'

t0 = time.time()
hash160s = []

with gzip.open(input_path, 'rt') as f:
    for i, line in enumerate(f):
        addr = line.strip()
        if not addr:
            continue
        try:
            hrp, data = bech32.bech32_decode(addr)
            if hrp != 'bc' or not data or data[0] != 0:
                continue
            decoded = bech32.convertbits(data[1:], 5, 8, False)
            if decoded and len(decoded) == 20:
                hash160s.append(bytes(decoded))
        except Exception:
            pass
        if i % 1_000_000 == 0:
            print(f"{i/1e6:.0f}M... {len(hash160s)} valid ({time.time()-t0:.0f}s)", flush=True)

print(f"\nTotal: {len(hash160s)} hash160s ({time.time()-t0:.0f}s)")

hash160s.sort()
unique = [h for i, h in enumerate(hash160s) if i == 0 or h != hash160s[i-1]]

print(f"Unique: {len(unique)}")

with open(output_path, 'wb') as f:
    for h in unique:
        f.write(h)

size_mb = len(unique) * 20 / 1e6
print(f"Written {output_path} ({size_mb:.0f} MB in {time.time()-t0:.0f}s)")