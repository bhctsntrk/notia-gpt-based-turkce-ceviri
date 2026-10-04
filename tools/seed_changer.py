"""Translate the settings menu in a user's installed Seed Changer copy."""

import argparse
import json
import re
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]


def replace_setting(text: str, setting_id: str, field: str, value: str) -> str:
    # Limit the match to this setting's block; never cross another id assignment.
    pattern = re.compile(
        r'(\bid\s*=\s*"' + re.escape(setting_id) + r'"\s*,(?:(?!\bid\s*=).)*?\b'
        + re.escape(field) + r'\s*=\s*)"(?:[^"\\]|\\.)*"', re.DOTALL)
    quoted = json.dumps(value, ensure_ascii=False)
    result, count = pattern.subn(lambda match: match.group(1) + quoted, text)
    if count != 1:
        raise ValueError(f"Expected exactly one {setting_id}.{field}; unsupported mod version.")
    return result


def translate(mod: Path, backup: Path, dry_run: bool) -> None:
    settings_path = mod / "settings.lua"
    metadata_path = mod / "mod.xml"
    settings = settings_path.read_text(encoding="utf-8-sig")
    metadata = metadata_path.read_text(encoding="utf-8-sig")
    if not re.search(r'\blocal\s+mod_id\s*=\s*"seed_changer"', settings):
        raise ValueError("Expected Seed Changer settings.lua.")
    data = json.loads((ROOT / "optional/seed_changer_strings.json").read_text(encoding="utf-8"))
    if ET.fromstring(metadata).attrib.get("name") not in ("Seed Changer", data["name"]):
        raise ValueError("Expected Seed Changer mod.xml.")
    updated_settings = settings
    for setting_id, fields in data["settings"].items():
        for field, value in fields.items():
            updated_settings = replace_setting(updated_settings, setting_id, field, value)
    updated_metadata = metadata
    for field in ("name", "description"):
        pattern = re.compile(r'(\b' + field + r'\s*=\s*)"[^"]*"')
        value = escape(data[field], {'"': '&quot;'})
        updated_metadata, count = pattern.subn(lambda m: m.group(1) + '"' + value + '"', updated_metadata)
        if count != 1:
            raise ValueError("Unsupported mod metadata.")
    ET.fromstring(updated_metadata)
    if dry_run:
        print("Seed Changer settings translation is compatible; no files changed.")
        return
    for path, old, new in ((settings_path, settings, updated_settings),
                           (metadata_path, metadata, updated_metadata)):
        if old == new:
            continue
        backup.mkdir(parents=True, exist_ok=True)
        destination = backup / path.name
        if not destination.exists():
            shutil.copyfile(path, destination)
        path.write_text(new, encoding="utf-8", newline="")
    print("Seed Changer settings translated. Reopen the menu or restart the game.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mod-dir", type=Path, required=True)
    parser.add_argument("--backup-dir", type=Path, default=ROOT / "dist/seed_changer_backup")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    translate(args.mod_dir.resolve(), args.backup_dir.resolve(), args.dry_run)
