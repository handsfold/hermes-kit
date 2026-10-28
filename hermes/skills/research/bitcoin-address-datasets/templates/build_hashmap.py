#!/usr/bin/env python3
"""Construit une hashmap Python de toutes les adresses bc1 financees.

Usage: python3 build_hashmap.py [--dump dump.tsv.gz] [--output hashmap.pkl]
"""

import gzip
from pathlib import Path
import pickle
import sys
import argparse

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dump", default="blockchair_addresses_latest.tsv.gz")
    ap.add_argument("--output", default="hashmap_bc1.pkl")
    ap.add_argument("--prefix", default="bc1", help="Prefixe a filtrer")
    args = ap.parse_args()

    if not Path(args.dump).exists():
        print(f"[ERROR] Dump absent: {args.dump}")
        sys.exit(1)

    print(f"[init] chargement {args.dump}...")
    funded = set()
    total = 0
    count = 0

    with gzip.open(args.dump, "rt", encoding="utf-8", errors="replace") as f:
        f.readline()  # skip header
        for line in f:
            total += 1
            addr = line.split("\t")[0].strip()
            if addr.startswith(args.prefix):
                funded.add(addr)
                count += 1

    print(f"[done] {total:,} lignes, {count:,} {args.prefix}")
    with open(args.output, "wb") as f:
        pickle.dump(funded, f, protocol=pickle.HIGHEST_PROTOCOL)
    size_mb = Path(args.output).stat().st_size / (1024*1024)
    print(f"[save] {args.output} ({size_mb:.0f} MB)")

if __name__ == "__main__":
    main()