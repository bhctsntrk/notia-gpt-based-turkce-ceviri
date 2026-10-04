"""Build the native language pack from locally owned Noita font assets."""

import argparse
import csv
import json
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
MOD_ID = "translation_tr_witty"
COLORS = {".": (0, 0, 0, 0), "W": (255, 255, 255, 255), "B": (0, 0, 0, 255)}


def build_fonts(game: Path, output: Path, characters: set[str]) -> None:
    definitions = json.loads((ROOT / "src/fonts/turkish_glyphs.json").read_text(encoding="utf-8"))
    font_output = output / "fonts"
    font_output.mkdir()
    for name, glyphs in definitions.items():
        tree = ET.parse(game / "data/fonts" / (name + ".xml"))
        root = tree.getroot()
        with Image.open(game / "data/fonts" / (name + ".png")) as image:
            atlas = image.convert("RGBA")
        missing = [glyph for glyph in glyphs
                   if root.find(f'QuadChar[@id="{glyph["metrics"]["id"]}"]') is None]
        width = atlas.width + sum(int(g["metrics"]["rect_w"]) + 1 for g in missing)
        height = max([atlas.height] + [int(g["metrics"]["rect_h"]) for g in missing])
        combined = Image.new("RGBA", (width, height), COLORS["."])
        combined.paste(atlas, (0, 0))
        cursor = atlas.width
        for glyph in missing:
            attrs = dict(glyph["metrics"], rect_x=str(cursor), rect_y="0")
            w, h = int(attrs["rect_w"]), int(attrs["rect_h"])
            assert len(glyph["pixels"]) == h and all(len(row) == w for row in glyph["pixels"])
            patch = Image.new("RGBA", (w, h), COLORS["."])
            for y, row in enumerate(glyph["pixels"]):
                for x, code in enumerate(row):
                    patch.putpixel((x, y), COLORS[code])
            combined.paste(patch, (cursor, 0))
            ET.SubElement(root, "QuadChar", attrs)
            cursor += w + 1
        # Preserve all original atlas pixels, including their transparency values.
        assert combined.crop((0, 0, atlas.width, atlas.height)).tobytes() == atlas.tobytes()
        root.find("Texture").text = f"\n    mods/{MOD_ID}/fonts/{name}.png\n  "
        ids = {int(node.attrib["id"]) for node in root.findall("QuadChar")}
        unsupported = {c for c in characters if not c.isspace() and ord(c) not in ids}
        if unsupported:
            raise ValueError(f"Unsupported characters in {name}: {unsupported}")
        for node in root.findall("QuadChar"):
            a = node.attrib
            assert int(a["rect_x"]) + int(a["rect_w"]) <= width
            assert int(a["rect_y"]) + int(a["rect_h"]) <= height
        ET.indent(tree, space="  ")
        tree.write(font_output / (name + ".xml"), encoding="utf-8")
        combined.save(font_output / (name + ".png"))


def build(game: Path, output: Path) -> None:
    with (ROOT / "src/translation.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.reader(stream))
    assert rows[0] == ["", "tr"]
    assert all(len(row) == 2 and row[0] and row[1].strip() for row in rows[1:])
    assert len({row[0] for row in rows[1:]}) == len(rows) - 1 == 3610
    for name in ("font_pixel", "font_pixel_big", "font_pixel_huge"):
        for suffix in (".xml", ".png"):
            if not (game / "data/fonts" / (name + suffix)).is_file():
                raise FileNotFoundError("Extract Noita data/fonts using the game's modding instructions first.")
    if output.exists():
        raise FileExistsError("Output already exists. Choose a new --output directory.")
    output.mkdir(parents=True)
    for name in ("mod.xml", "translation.xml", "translation.csv"):
        shutil.copyfile(ROOT / "src" / name, output / name)
    characters = {c for row in rows[1:] for c in row[1]}
    build_fonts(game, output, characters)
    assert ET.parse(output / "mod.xml").getroot().attrib["is_translation"] == "1"
    assert ET.parse(output / "translation.xml").getroot().attrib["key"] == "tr-witty"
    print("Built and validated 3610 translations and all Turkish glyphs.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "dist" / MOD_ID)
    args = parser.parse_args()
    build(args.game_dir.resolve(), args.output.resolve())
