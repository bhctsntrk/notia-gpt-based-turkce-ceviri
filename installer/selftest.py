"""Isolated lifecycle checks, also executed inside the frozen EXE."""

import csv
import io
import json
import struct
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from installer import core
from installer.core import Manager, MOD_ID, digest
from tools import build


def sample_fonts() -> dict[str, bytes]:
    with (build.ROOT / "src/translation.csv").open(encoding="utf-8", newline="") as stream:
        rows = list(csv.reader(stream))
    characters = {ord(c) for row in rows[1:] for c in row[1] if not c.isspace()} - set(map(ord, "ğĞıİşŞ"))
    root = ET.Element("FontData")
    ET.SubElement(root, "Texture").text = "data/fonts/font_pixel.png"
    ET.SubElement(root, "LineHeight").text = "7"
    ET.SubElement(root, "CharSpace").text = "0"
    ET.SubElement(root, "WordSpace").text = "3"
    for x, code in enumerate(sorted(characters)):
        ET.SubElement(root, "QuadChar", id=str(code), offset_x="0", offset_y="0", rect_h="11",
                      rect_w="1", rect_x=str(x), rect_y="0", width="1")
    bitmap = io.BytesIO()
    Image.new("RGBA", (len(characters), 11), (255, 255, 255, 255)).save(bitmap, format="PNG")
    return {f"data/fonts/{name}{suffix}": ET.tostring(root) if suffix == ".xml" else bitmap.getvalue()
            for name in core.FONT_NAMES for suffix in (".xml", ".png")}


def sample_wak(files: dict[str, bytes]) -> bytes:
    index_end = 16 + sum(12 + len(name.encode()) for name in files)
    index = bytearray(struct.pack("<4I", 0, len(files), index_end, 0))
    data = bytearray()
    for name, content in files.items():
        encoded = name.encode()
        index.extend(struct.pack("<3I", index_end + len(data), len(content), len(encoded)))
        index.extend(encoded)
        data.extend(content)
    return bytes(index + data)


class Lifecycle(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="noita-tr-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / "Türkçe klasör"
        self.game = self.root / "library/steamapps/common/Noita"
        self.game.mkdir(parents=True)
        (self.game / "noita.exe").write_bytes(b"fixture-only")
        for name, content in sample_fonts().items():
            path = self.game / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)
        self.config = self.root / "config.xml"
        self.config.write_bytes(b'\xef\xbb\xbf<Config language="en" volume="0.5" />\r\n')
        self.save = self.root / "save00/world.bin"
        self.save.parent.mkdir()
        self.save.write_bytes(b"save-canary")
        self.manager = Manager(self.game, self.root / "state", self.config, log=lambda _: None)

    def optional(self) -> dict[str, bytes]:
        originals = {}
        seed = self.game / "mods/seed_changer"
        seed.mkdir(parents=True)
        (seed / "settings.lua").write_text('''local mod_id = "seed_changer"
return {{id="fixed_seed", ui_name="Fixed", ui_description="Fixed description"},
        {id="seed", ui_name="Seed", ui_description="Seed description"}}
''', encoding="utf-8")
        (seed / "mod.xml").write_text('<Mod name="Seed Changer" description="Original" />', encoding="utf-8")
        cheat = self.game / "mods/cheatgui"
        (cheat / "data/hax").mkdir(parents=True)
        (cheat / "mod_id.txt").write_text("cheatgui", encoding="utf-8")
        (cheat / "mod.xml").write_text('<Mod name="Hile Tezgâhı" description="Test" />', encoding="utf-8")
        (cheat / "data/hax/cheatgui.lua").write_text('''-- Turkish UI patch v1
local CHEATGUI_VERSION = "1.5.0"
GuiText(gui, 0, 0, "Türkçe")
GuiButton(gui, 0, 0, "Düğme", 123)
''', encoding="utf-8")
        (cheat / "data/hax/special_spawnables.lua").write_text("return {}", encoding="utf-8")
        for root in (seed, cheat):
            for path in root.rglob("*"):
                if path.is_file():
                    originals[str(path)] = path.read_bytes()
        return originals

    def test_install_uninstall_preserves_later_settings_and_save(self) -> None:
        self.manager.install(set())
        self.assertEqual(core.language_value(self.config.read_bytes()), "tr-witty")
        self.assertEqual(len(self.manager.load()["records"]), 9)
        self.config.write_bytes(self.config.read_bytes().replace(b'volume="0.5"', b'volume="0.8"'))
        self.manager.uninstall()
        self.assertEqual(core.language_value(self.config.read_bytes()), "en")
        self.assertIn(b'volume="0.8"', self.config.read_bytes())
        self.assertFalse((self.game / "mods" / MOD_ID).exists())
        self.assertIsNone(self.manager.load())
        self.assertEqual(self.save.read_bytes(), b"save-canary")

    def test_optional_mods_restore_exact_original_bytes(self) -> None:
        originals = self.optional()
        self.manager.install({"seed_changer", "cheatgui"})
        self.assertIn("Turkish GUI font binding", (self.game / "mods/cheatgui/data/hax/cheatgui.lua").read_text())
        self.assertIn("Dünya tohumu", (self.game / "mods/seed_changer/settings.lua").read_text(encoding="utf-8"))
        self.manager.uninstall()
        for name, content in originals.items():
            self.assertEqual(Path(name).read_bytes(), content)

    def test_reinstall_keeps_original_baseline(self) -> None:
        previous = self.game / "mods" / MOD_ID / "mod.xml"
        previous.parent.mkdir(parents=True)
        previous.write_bytes(b"pre-existing-mod")
        self.manager.install(set())
        self.manager.install(set())
        self.manager.uninstall()
        self.assertEqual(previous.read_bytes(), b"pre-existing-mod")

    def test_changed_file_stops_uninstall_before_any_write(self) -> None:
        self.manager.install(set())
        target = self.game / "mods" / MOD_ID / "translation.csv"
        target.write_bytes(b"user-edit")
        before = {str(p): p.read_bytes() for p in target.parent.rglob("*") if p.is_file()}
        with self.assertRaisesRegex(ValueError, "sonradan değişmiş"):
            self.manager.uninstall()
        self.assertEqual(before, {str(p): p.read_bytes() for p in target.parent.rglob("*") if p.is_file()})
        self.assertIsNotNone(self.manager.load())

    def test_backup_corruption_stops_uninstall(self) -> None:
        self.optional()
        self.manager.install({"seed_changer"})
        backup = self.manager.state / "backup/seed_changer/settings.lua"
        backup.write_bytes(b"corrupt")
        with self.assertRaisesRegex(ValueError, "Yedek değişmiş"):
            self.manager.uninstall()
        self.assertEqual(core.language_value(self.config.read_bytes()), "tr-witty")

    def test_write_failure_rolls_back(self) -> None:
        previous = self.game / "mods" / MOD_ID / "mod.xml"
        previous.parent.mkdir(parents=True)
        previous.write_bytes(b"pre-existing-mod")
        original_write = core.atomic_write
        failed = False

        def failing_write(path: Path, data: bytes) -> None:
            nonlocal failed
            if path.name == "translation.xml" and not failed:
                failed = True
                raise OSError("injected-write-failure")
            original_write(path, data)

        with patch.object(core, "atomic_write", failing_write):
            with self.assertRaisesRegex(OSError, "injected"):
                self.manager.install(set())
        self.assertEqual(previous.read_bytes(), b"pre-existing-mod")
        self.assertFalse((previous.parent / "translation.csv").exists())
        self.assertIsNone(self.manager.load())
        self.assertEqual(core.language_value(self.config.read_bytes()), "en")

    def test_running_game_blocks_changes(self) -> None:
        self.manager.game_running = lambda: True
        with self.assertRaisesRegex(ValueError, "Noita açık"):
            self.manager.install(set())
        self.assertFalse((self.game / "mods" / MOD_ID).exists())
        self.assertEqual(core.language_value(self.config.read_bytes()), "en")

    def test_unsupported_optional_mod_does_not_install_main(self) -> None:
        self.optional()
        (self.game / "mods/cheatgui/data/hax/cheatgui.lua").write_text("bad-version", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.manager.install({"cheatgui"})
        self.assertFalse((self.game / "mods" / MOD_ID).exists())

    def test_wak_font_extraction(self) -> None:
        fonts = sample_fonts()
        for name in fonts:
            (self.game / name).unlink()
        (self.game / "data/data.wak").write_bytes(sample_wak(fonts))
        self.manager.install(set())
        self.assertTrue((self.game / "mods" / MOD_ID / "fonts/font_pixel.png").is_file())
        self.manager.uninstall()

    def test_language_changed_by_user_is_preserved(self) -> None:
        self.manager.install(set())
        self.config.write_bytes(core.replace_language(self.config.read_bytes(), "fi"))
        self.manager.uninstall()
        self.assertEqual(core.language_value(self.config.read_bytes()), "fi")

    def test_traversal_record_is_rejected(self) -> None:
        self.manager.install(set())
        data = self.manager.load()
        data["records"][0]["relative"] = "../../outside"
        self.manager.save(data)
        with self.assertRaises(ValueError):
            self.manager.uninstall()

    def test_parallel_operation_is_rejected(self) -> None:
        second = Manager(self.game, self.root / "state", self.config, log=lambda _: None)
        with self.manager.locked():
            with self.assertRaisesRegex(ValueError, "başka bir işlem"):
                second.install(set())
        self.assertIsNone(self.manager.load())

    def test_windows_uninstall_registration(self) -> None:
        import sys
        import winreg
        from installer import windows
        fake_home = self.root / "windows/Installations"
        key_path = windows.UNINSTALL_ROOT + "\\NoitaTurkce_" + core.installation_id(self.game)
        with patch.object(windows, "state_home", return_value=fake_home), patch.object(sys, "frozen", True, create=True):
            try:
                windows.register_uninstaller(self.game)
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                    name = winreg.QueryValueEx(key, "DisplayName")[0]
                    command = winreg.QueryValueEx(key, "UninstallString")[0]
                self.assertEqual(name, "Noita Türkçe Çeviri")
                self.assertIn('--uninstall --game-dir "' + str(self.game) + '"', command)
                self.assertTrue((fake_home.parent / "NoitaTurkceSetup.exe").is_file())
            finally:
                windows.unregister_uninstaller(self.game)
        with self.assertRaises(FileNotFoundError):
            winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path)

    def test_malformed_wak_stops_before_install(self) -> None:
        (self.game / "data/fonts/font_pixel.xml").unlink()
        (self.game / "data/data.wak").write_bytes(struct.pack("<4I", 0, 500000, 0, 0))
        with self.assertRaises(ValueError):
            self.manager.install(set())
        self.assertFalse((self.game / "mods" / MOD_ID).exists())

    def test_remove_button_works_after_game_exe_is_removed(self) -> None:
        import tkinter as tk
        from installer import windows
        from installer.app import App
        self.manager.install(set())
        (self.game / "noita.exe").unlink()
        with patch.object(windows, "state_home", return_value=self.root / "state"), \
                patch.object(windows, "discover_games", return_value=[]):
            root = tk.Tk()
            root.withdraw()
            try:
                app = App(root, str(self.game), True)
                self.assertEqual(str(app.remove_button["state"]), "normal")
                self.assertEqual(str(app.install_button["state"]), "disabled")
            finally:
                root.destroy()
        self.manager.uninstall()
        self.assertIsNone(self.manager.load())


def run(report: Path) -> None:
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(
        unittest.defaultTestLoader.loadTestsFromTestCase(Lifecycle))
    report.write_text(json.dumps({"success": result.wasSuccessful(), "tests": result.testsRun,
        "failures": len(result.failures), "errors": len(result.errors), "details": stream.getvalue()},
        ensure_ascii=False, indent=2), encoding="utf-8")
    if not result.wasSuccessful():
        raise SystemExit(1)


if __name__ == "__main__":
    import sys
    run(Path(sys.argv[1]))
