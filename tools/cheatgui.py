"""Apply Turkish UI text to a locally installed Cheatgui 1.5.0 copy."""

import argparse
import json
import re
import shutil
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path
from xml.sax.saxutils import escape

from luaparser import ast
from luaparser.astnodes import Call, Name, String

ROOT = Path(__file__).resolve().parents[1]
MARKER = "-- Turkish UI patch v1"
FONT_MARKER = "-- Turkish GUI font binding v1"
PANEL_NAMES = {"wand builder", "teleport", "health", "gold", "gui grid ref.",
               "always cast", "spells", "perks", "flasks", "items", "wands",
               "widgets", "shift material", "fungal", "console"}


def literal_translations(text: str, mapping: dict[str, str]) -> tuple[str, set[str], int]:
    tree = ast.parse(text)
    lines = text.splitlines()
    replacements = []
    found = set()
    for node in ast.walk(tree):
        if not isinstance(node, String):
            continue
        value = node.s.decode("utf-8")
        if value not in mapping:
            continue
        # Lowercase panel titles also occur as internal widget keys. Only change titles.
        if value in PANEL_NAMES and "Panel{" not in lines[node.first_token.line - 1]:
            continue
        found.add(value)
        translated = mapping[value]
        if Counter(re.findall(r"%0?\d*[sdf]|\d+", value)) != Counter(re.findall(r"%0?\d*[sdf]|\d+", translated)):
            raise ValueError(f"Number or format token mismatch: {value}")
        replacements.append((node.first_token.start, node.last_token.stop + 1,
                             json.dumps(translated, ensure_ascii=False)))
    for start, end, translated in sorted(replacements, reverse=True):
        text = text[:start] + translated + text[end:]
    ast.parse(text)
    return text, found, len(replacements)


def replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise ValueError("Unexpected Cheatgui structure; refusing a partial patch.")
    return text.replace(old, new, 1)


def bind_turkish_font(text: str) -> str:
    if FONT_MARKER in text:
        return text
    calls = Counter()
    for node in ast.walk(ast.parse(text)):
        if isinstance(node, Call) and isinstance(node.func, Name):
            name = node.func.id
            if name in ("GuiText", "GuiButton"):
                expected = 4 if name == "GuiText" else 5
                if len(node.args) != expected:
                    raise ValueError("Unexpected Cheatgui text call; refusing a partial font patch.")
                calls[name] += 1
    if not calls["GuiText"] or not calls["GuiButton"]:
        raise ValueError("Expected Cheatgui text and button calls.")
    helper = (ROOT / "tools/cheatgui_font.lua").read_text(encoding="utf-8")
    return helper + "\n" + text


def improve_localized_display(text: str, categories: dict[str, str]) -> str:
    text, count = re.subn(r'(create_radio\("Türkçe adlar:",\s*\{.*?\},\s*)2(\s*,\s*16\))',
                         lambda m: m.group(1) + "1" + m.group(2), text, flags=re.DOTALL)
    if count != 1:
        raise ValueError("Expected one localized-name option.")
    text = replace_once(text, "ui_name = item.name,",
                        "ui_name = resolve_localized_name(item.name, item.xml),")
    text = replace_once(text, "local localize_alchemy = false", "local localize_alchemy = true")
    text = replace_once(text, 'tostring((shift_from or "?"))',
                        'tostring(resolve_localized_name(shift_from or "?"))')
    text = replace_once(text, 'tostring((shift_to or "?"))',
                        'tostring(resolve_localized_name(shift_to or "?"))')
    text = replace_once(text, '"KAYNAK: " .. fungal_conv.from',
                        '"KAYNAK: " .. localize_material(fungal_conv.from)')
    text = replace_once(text, '"HEDEF: " .. fungal_conv.to',
                        '"HEDEF: " .. localize_material(fungal_conv.to)')
    text = replace_once(text, '(always_casts[idx] or "Yok")',
                        '(always_casts[idx] and cheatgui_tr_spell(always_casts[idx]) or "Yok")')
    text = replace_once(text, 'potion_options[idx] = {text = material,',
                        'potion_options[idx] = {text = cheatgui_tr_category(material),')
    text = replace_once(text, 'GamePrint("Gezgin modu: " .. tostring(tourist_mode_on))',
                        'GamePrint("Gezgin modu: " .. (tourist_mode_on and "açık" or "kapalı"))')
    text = replace_once(text, 'return "[" .. ((tourist_mode_on and "disable") or "enable") .. " tourist mode]"',
                        'return "[Gezgin modu: " .. ((tourist_mode_on and "kapat") or "aç") .. "]"')
    category_rows = [f"  [{json.dumps(key)}] = {json.dumps(value, ensure_ascii=False)},"
                     for key, value in categories.items()]
    helper = MARKER + "\nlocal cheatgui_tr_categories = {\n" + "\n".join(category_rows) + "\n}\n"
    helper += """
local function cheatgui_tr_category(text)
  return cheatgui_tr_categories[text] or text
end
local function cheatgui_tr_spell(id)
  for _, action in ipairs(actions or {}) do
    if action.id:lower() == tostring(id):lower() then
      return resolve_localized_name(action.name, id)
    end
  end
  return id
end
"""
    return helper + text


def metadata_translation(text: str, data: dict) -> str:
    if ET.fromstring(text).attrib.get("name") not in ("Cheatgui", data["name"]):
        raise ValueError("Expected Cheatgui mod.xml.")
    for field in ("name", "description"):
        value = escape(data[field], {'"': '&quot;'})
        pattern = re.compile(r'(\b' + field + r'\s*=\s*)"[^"]*"')
        text, count = pattern.subn(lambda m: m.group(1) + '"' + value + '"', text)
        if count != 1:
            raise ValueError("Unexpected mod metadata.")
    ET.fromstring(text)
    return text


def translate(mod: Path, backup: Path, dry_run: bool) -> None:
    if (mod / "mod_id.txt").read_text(encoding="utf-8-sig").strip() != "cheatgui":
        raise ValueError("Expected Cheatgui mod directory.")
    data = json.loads((ROOT / "optional/cheatgui_strings.json").read_text(encoding="utf-8"))
    main_path = mod / "data/hax/cheatgui.lua"
    special_path = mod / "data/hax/special_spawnables.lua"
    main = main_path.read_text(encoding="utf-8-sig")
    special = special_path.read_text(encoding="utf-8-sig")
    if not re.search(r'local\s+CHEATGUI_VERSION\s*=\s*"1\.5\.0"', main):
        raise ValueError("This patch supports Cheatgui 1.5.0; unsupported version.")
    metadata_path = mod / "mod.xml"
    metadata = metadata_path.read_text(encoding="utf-8-sig")
    if MARKER in main or main.startswith("-- Turkish UI patch:"):
        updated = main
        if main.startswith("-- Turkish UI patch:"):
            updated = MARKER + "\n" + main.partition("\n")[2]
        updated = bind_turkish_font(updated)
        ast.parse(updated)
        if dry_run:
            print("Validated Turkish UI and font bindings; no files changed.")
            return
        if updated != main:
            destination = backup / "before_font_fix" / main_path.relative_to(mod)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not destination.exists():
                shutil.copyfile(main_path, destination)
            main_path.write_text(updated, encoding="utf-8", newline="")
            assert main_path.read_text(encoding="utf-8") == updated
            print("Updated Turkish UI font bindings; restart Noita.")
            return
        print("Cheatgui Turkish UI is already installed; no files changed.")
        return
    translated_main, main_found, main_count = literal_translations(main, data["strings"])
    translated_special, special_found, special_count = literal_translations(special, data["strings"])
    missing = data["strings"].keys() - (main_found | special_found)
    if missing:
        raise ValueError(f"UI strings missing in this mod version: {sorted(missing)}")
    translated_main = improve_localized_display(translated_main, data["material_categories"])
    translated_main = bind_turkish_font(translated_main)
    ast.parse(translated_main)
    translated_metadata = metadata_translation(metadata, data)
    if dry_run:
        print(f"Validated {main_count + special_count} UI literals, localized names and Lua syntax; no files changed.")
        return
    planned = [(main_path, main, translated_main), (special_path, special, translated_special),
               (metadata_path, metadata, translated_metadata)]
    # Validate every file before writing, and preserve original backups on repeated installs.
    for path, _, _ in planned:
        destination = backup / path.relative_to(mod)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists():
            shutil.copyfile(path, destination)
    for path, _, translated in planned:
        path.write_text(translated, encoding="utf-8", newline="")
    assert main_path.read_text(encoding="utf-8") == translated_main
    print(f"Installed {main_count + special_count} translated UI literals and localized display. Restart Noita.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mod-dir", type=Path, required=True)
    parser.add_argument("--backup-dir", type=Path, default=ROOT / "dist/cheatgui_backup")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    translate(args.mod_dir.resolve(), args.backup_dir.resolve(), args.dry_run)
