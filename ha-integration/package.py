"""Build an inspectable integration ZIP without caches or machine credentials."""
import hashlib
import json
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

ROOT = Path(__file__).parent
output = ROOT / "dist"
output.mkdir(exist_ok=True)
source = ROOT / "custom_components/kindle_panel"
files = sorted(path for path in source.rglob("*") if path.is_file() and "__pycache__" not in path.parts)
archive = output / "kindle-panel-0.2.0.zip"
manifest = []
with ZipFile(archive, "w", ZIP_DEFLATED) as package:
    for path in files:
        relative = path.relative_to(ROOT)
        value = path.read_bytes()
        info = ZipInfo(relative.as_posix(), date_time=(1980, 1, 1, 0, 0, 0))
        info.create_system = 3
        info.external_attr = 0o100644 << 16
        info.compress_type = ZIP_DEFLATED
        package.writestr(info, value)
        manifest.append({"file": relative.as_posix(), "bytes": len(value), "sha256": hashlib.sha256(value).hexdigest()})
(output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8", newline="\n")
print(f"Packaged {len(files)} files in {archive}")
print("SHA256 " + hashlib.sha256(archive.read_bytes()).hexdigest())
