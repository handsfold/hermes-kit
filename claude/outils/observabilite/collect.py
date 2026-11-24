#!/usr/bin/env python3
import fcntl
import os
from pathlib import Path
import usage_ledger
import hermes_snapshots
home=Path.home(); state=home/'.local/state/bilan-tokens'
state.mkdir(parents=True,exist_ok=True,mode=0o700)
with (state/'ledger.lock').open('a') as lock:
    fcntl.flock(lock,fcntl.LOCK_EX)
    usage_ledger.import_data(home,state/'ledger.sqlite')
    hermes_snapshots.collect(home,state/'ledger.sqlite')
    os.chmod(state/'ledger.sqlite',0o600)
