"""Stage the one-time startup installer after native pairing/control validation."""
import argparse
import json
from pathlib import Path
import shutil
from datetime import datetime

ROOT = Path(__file__).parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--device", type=Path, default=Path("H:/"), help="Mounted, already paired Kindle (default: H:/)")
DEVICE = parser.parse_args().device.expanduser().resolve()
snapshot = json.loads((DEVICE / "nativeha/snapshot-cache.json").read_text(encoding="utf-8"))
assert snapshot.get("device", {}).get("id"), "Pairing must be verified before staging startup"
assert "5.6.1.1" in (DEVICE / "system/version.txt").read_text(encoding="utf-8"), "Unexpected Kindle firmware"
backup = ROOT.parent / "backups" / ("before-startup-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
backup.mkdir(parents=True)
for relative in ("RUNME.sh", "nativeha/config.json"):
    path = DEVICE / relative
    if path.is_file():
        archived = backup / relative
        archived.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, archived)
        assert path.read_bytes() == archived.read_bytes()
files = {}
for source in (ROOT / "startup").iterdir():
    if source.is_file():
        files[source] = DEVICE / "nativeha/startup" / source.name
for source, target in files.items():
    target.parent.mkdir(parents=True, exist_ok=True)
    value = source.read_bytes().replace(b"\r\n", b"\n")
    target.write_bytes(value)
    assert target.read_bytes() == value
wrapper = b"#!/bin/sh\n/bin/sh /mnt/us/nativeha/startup/install.sh\n"
(DEVICE / "RUNME.sh").write_bytes(wrapper)
assert (DEVICE / "RUNME.sh").read_bytes() == wrapper
# Keep the server URL written during pairing; example configuration is not device state.
print(f"Startup installer staged and verified; prior launcher/config backed up at {backup}")
print("No startup job has been installed yet. Run ;log runme on the Kindle, then restart normally.")
