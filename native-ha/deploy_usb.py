"""Update the already installed native panel, retaining a verified PC backup."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
from datetime import datetime

ROOT = Path(__file__).parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--device", type=Path, default=Path("H:/"), help="Mounted Kindle user-storage directory (default: H:/)")
DEVICE = parser.parse_args().device.expanduser().resolve()
if not (DEVICE / "system/version.txt").is_file() or not (DEVICE / "koreader/koreader.sh").is_file():
    raise SystemExit(f"Expected a mounted Kindle with KOReader at {DEVICE}")
stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
backup = ROOT.parent / "backups" / ("native-before-cards-" + stamp)
files = {}
for source in (ROOT / "nativeha.koplugin").glob("*.lua"):
    files[source] = DEVICE / "koreader/plugins/nativeha.koplugin" / source.name
for source in (ROOT / "icons").glob("*.svg"):
    files[source] = DEVICE / "nativeha/icons" / source.name
files[ROOT / "default-snapshot.json"] = DEVICE / "nativeha/default-snapshot.json"
if not (DEVICE / "nativeha/config.json").exists():
    files[ROOT / "config.example.json"] = DEVICE / "nativeha/config.json"
for name in ("launch.sh", "menu.json", "config.xml"):
    files[ROOT / "extensions/nativeha" / name] = DEVICE / "extensions/nativeha" / name
manifest = []
for source, target in files.items():
    relative = target.relative_to(DEVICE)
    if target.exists():
        archived = backup / relative
        archived.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(target, archived)
        assert archived.read_bytes() == target.read_bytes()
    target.parent.mkdir(parents=True, exist_ok=True)
    value = source.read_bytes()
    if source.suffix == ".sh":
        value = value.replace(b"\r\n", b"\n")
    target.write_bytes(value)
    assert target.read_bytes() == value
    manifest.append({"file": str(relative), "bytes": len(value), "sha256": hashlib.sha256(value).hexdigest()})
backup.mkdir(parents=True, exist_ok=True)
(backup / "deployment-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
print(f"Verified {len(manifest)} files; previous versions backed up at {backup}")
