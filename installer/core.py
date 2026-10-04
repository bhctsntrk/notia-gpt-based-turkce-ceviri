"""Transactional installation and restoration; no game saves are modified."""

import hashlib
import json
import os
import re
import shutil
import struct
import tempfile
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from pathlib import Path, PurePosixPath
from typing import Callable, Iterator

from tools import build, cheatgui, seed_changer

VERSION = "0.1.0"
MOD_ID = build.MOD_ID
FONT_NAMES = ("font_pixel", "font_pixel_big", "font_pixel_huge")
OPTIONAL_IDS = {"cheatgui": "1984977713", "seed_changer": "2284931352"}
Log = Callable[[str], None]


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def installation_id(game: Path) -> str:
    return digest(os.path.normcase(str(game.resolve())).encode("utf-8"))[:20]


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, name = tempfile.mkstemp(prefix=".noita-tr-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def safe_target(root: Path, relative: str) -> Path:
    part = PurePosixPath(relative)
    if part.is_absolute() or ".." in part.parts or not part.parts or "\\" in relative or ":" in relative:
        raise ValueError("Geçersiz dosya yolu; işlem durduruldu.")
    target = root.joinpath(*part.parts)
    if not target.resolve().is_relative_to(root.resolve()) or target.is_symlink():
        raise ValueError("Dosya yolu kurulum klasörünün dışına çıkıyor.")
    return target


def validate_game(game: Path) -> Path:
    game = game.resolve()
    if not (game / "noita.exe").is_file():
        raise ValueError("Noita klasörünü seç: içinde noita.exe bulunmalı.")
    if not (game / "mods" / MOD_ID).resolve().is_relative_to(game):
        raise ValueError("Mods klasörü oyun klasörünün dışına yönlendirilmiş.")
    return game


def discover_optional(game: Path) -> dict[str, Path]:
    result = {}
    for name, workshop_id in OPTIONAL_IDS.items():
        candidates = [game / "mods" / name,
                      game.parent.parent / "workshop/content/881100" / workshop_id]
        for candidate in candidates:
            if not (candidate / "mod.xml").is_file():
                continue
            if name == "cheatgui":
                identity = candidate / "mod_id.txt"
                valid = identity.is_file() and identity.read_text(encoding="utf-8-sig").strip() == name
            else:
                settings = candidate / "settings.lua"
                valid = settings.is_file() and re.search(
                    r'\blocal\s+mod_id\s*=\s*"seed_changer"', settings.read_text(encoding="utf-8-sig"))
            if valid:
                result[name] = candidate.resolve()
                break
    return result


def prepare_fonts(game: Path, staging: Path) -> Path:
    """Use locally owned font assets, extracting just six files if necessary."""
    expected = {f"data/fonts/{name}{suffix}" for name in FONT_NAMES for suffix in (".xml", ".png")}
    missing = set()
    for name in expected:
        source = game / name
        if source.is_file():
            target = staging / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        else:
            missing.add(name)
    if missing:
        archive = game / "data/data.wak"
        if not archive.is_file():
            raise ValueError("Oyunun font dosyaları bulunamadı. Noita dosyalarını doğrulayıp tekrar dene.")
        size = archive.stat().st_size
        found = {}
        with archive.open("rb") as stream:
            header = stream.read(16)
            if len(header) != 16:
                raise ValueError("Noita veri arşivi eksik.")
            _, count, index_end, _ = struct.unpack("<4I", header)
            if count > 200000 or not 16 <= index_end <= size:
                raise ValueError("Desteklenmeyen Noita veri arşivi.")
            for _ in range(count):
                record = stream.read(12)
                if len(record) != 12:
                    raise ValueError("Noita veri arşivi eksik.")
                offset, length, name_length = struct.unpack("<3I", record)
                if not 0 < name_length <= 4096 or stream.tell() + name_length > index_end:
                    raise ValueError("Noita veri arşivi dizini geçersiz.")
                name = stream.read(name_length).decode("utf-8")
                if name in missing:
                    if name in found or offset < index_end or offset + length > size or length > 20000000:
                        raise ValueError("Noita font kaydı geçersiz.")
                    found[name] = (offset, length)
            if missing != found.keys():
                raise ValueError("Noita arşivinde gereken fontlar bulunamadı.")
            for name, (offset, length) in found.items():
                stream.seek(offset)
                content = stream.read(length)
                if len(content) != length:
                    raise ValueError("Noita font dosyası eksik.")
                target = staging / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
    return staging


def language_value(content: bytes) -> str:
    ET.fromstring(content)
    match = re.search(rb'\blanguage\s*=\s*"([^"<>]*)"', content)
    if not match:
        raise ValueError("Dil ayarı bulunamadı; oyunu bir kez açıp kapat.")
    return match.group(1).decode("utf-8")


def replace_language(content: bytes, value: str) -> bytes:
    language_value(content)
    if not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError("Geçersiz dil ayarı.")
    return re.sub(rb'(\blanguage\s*=\s*)"[^"<>]*"',
                  lambda match: match.group(1) + b'"' + value.encode() + b'"', content, count=1)


class Manager:
    def __init__(self, game: Path, state_home: Path, config: Path | None = None,
                 game_running: Callable[[], bool] = lambda: False, log: Log = print) -> None:
        self.game = game.resolve()
        self.state = state_home / installation_id(self.game)
        self.manifest = self.state / "manifest.json"
        self.config = config
        self.game_running = game_running
        self.log = log

    def load(self) -> dict | None:
        if not self.manifest.exists():
            return None
        data = json.loads(self.manifest.read_text(encoding="utf-8"))
        if data.get("schema") != 1 or data.get("game") != str(self.game):
            raise ValueError("Kurulum kaydı oyun klasörüyle eşleşmiyor.")
        return data

    def roots(self, manifest: dict) -> dict[str, Path]:
        roots = {"main": self.game / "mods" / MOD_ID}
        for name, path in manifest.get("optional", {}).items():
            if name not in OPTIONAL_IDS:
                raise ValueError("Kurulum kaydında tanınmayan mod var.")
            allowed = [self.game / "mods" / name,
                       self.game.parent.parent / "workshop/content/881100" / OPTIONAL_IDS[name]]
            root = Path(path)
            if root not in [candidate.resolve() for candidate in allowed]:
                raise ValueError("Mod yedeği beklenmeyen bir klasöre yönlendirilmiş.")
            roots[name] = root
        return roots

    def save(self, manifest: dict) -> None:
        atomic_write(self.manifest, json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"))

    def require_closed(self) -> None:
        if self.game_running():
            raise ValueError("Noita açık. Oyunu kapatıp tekrar dene; seferine dokunmadım.")

    @contextmanager
    def locked(self) -> Iterator[None]:
        import msvcrt
        self.state.mkdir(parents=True, exist_ok=True)
        with (self.state / "operation.lock").open("a+b") as stream:
            if os.fstat(stream.fileno()).st_size == 0:
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise ValueError("Bu kurulum için başka bir işlem sürüyor.") from exc
            try:
                yield
            finally:
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)

    def install(self, selected: set[str], select_language: bool = True) -> None:
        with self.locked():
            self._install(selected, select_language)

    def _install(self, selected: set[str], select_language: bool) -> None:
        validate_game(self.game)
        self.require_closed()
        previous = self.load()
        if previous and previous["status"] != "installed":
            raise ValueError("Yarım kalan işlem var. Önce Kaldır / geri yükle düğmesini kullan.")
        optional = discover_optional(self.game)
        if not selected <= optional.keys():
            raise ValueError("Seçilen ek mod kurulu değil; önce Steam Atölyesi'nden edin.")
        if previous and set(previous.get("packages", [])) - {"main"} - selected:
            raise ValueError("Önceki ekleri çıkarmak için önce kaldır, sonra istediğin eklerle tekrar kur.")
        self.log("Paketler hazırlanıyor…")
        with tempfile.TemporaryDirectory(prefix="noita-turkce-") as temporary:
            scratch = Path(temporary)
            fonts = prepare_fonts(self.game, scratch / "game")
            pack = scratch / "pack"
            build.build(fonts, pack)
            roots = {"main": self.game / "mods" / MOD_ID}
            planned = [("main", p.relative_to(pack).as_posix(), p.read_bytes())
                       for p in pack.rglob("*") if p.is_file()]
            for name in sorted(selected):
                roots[name] = optional[name]
                stage = scratch / name
                names = ("mod.xml", "settings.lua") if name == "seed_changer" else (
                    "mod.xml", "mod_id.txt", "data/hax/cheatgui.lua", "data/hax/special_spawnables.lua")
                for relative in names:
                    target = safe_target(stage, relative)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(safe_target(optional[name], relative), target)
                if name == "seed_changer":
                    seed_changer.translate(stage, scratch / "seed-backup", False)
                else:
                    cheatgui.translate(stage, scratch / "cheat-backup", False)
                for relative in names:
                    updated = (stage / relative).read_bytes()
                    if updated != safe_target(optional[name], relative).read_bytes():
                        planned.append((name, relative, updated))
            self.require_closed()
            manifest = json.loads(json.dumps(previous)) if previous else {
                "schema": 1, "game": str(self.game), "records": [], "language": None,
            }
            manifest.update(version=VERSION, status="installing", packages=["main", *sorted(selected)],
                            optional={name: str(roots[name]) for name in selected})
            old_records = {(r["root"], r["relative"]): r for r in manifest["records"]}
            snapshots = []
            for name, relative, content in planned:
                target = safe_target(roots[name], relative)
                before = target.read_bytes() if target.exists() else None
                record = old_records.get((name, relative))
                if record and (before is None or digest(before) != record["installed_hash"]):
                    raise ValueError("Kurulumdan sonra değişmiş dosya bulundu: " + relative)
                snapshots.append((target, before, content))
                if record is None:
                    record = {"root": name, "relative": relative, "original_hash": None}
                    if before is not None:
                        backup = safe_target(self.state / "backup" / name, relative)
                        atomic_write(backup, before)
                        if digest(backup.read_bytes()) != digest(before):
                            raise ValueError("Yedek doğrulanamadı; kurulum durduruldu.")
                        record["original_hash"] = digest(before)
                    manifest["records"].append(record)
                record["installed_hash"] = digest(content)
            config_before = None
            config_after = None
            if select_language and self.config and self.config.is_file():
                config_before = self.config.read_bytes()
                before_value = language_value(config_before)
                if manifest["language"] is None:
                    manifest["language"] = {"before": before_value}
                config_after = replace_language(config_before, "tr-witty")
            self.save(manifest)
            try:
                self.log("Yedekler doğrulandı. Yama kuruluyor…")
                for target, _, content in snapshots:
                    atomic_write(target, content)
                    if target.read_bytes() != content:
                        raise ValueError("Kurulan dosya doğrulanamadı: " + target.name)
                if config_after is not None:
                    atomic_write(self.config, config_after)
                manifest["status"] = "installed"
                self.save(manifest)
            except Exception:
                for target, before, _ in reversed(snapshots):
                    if before is None:
                        target.unlink(missing_ok=True)
                    else:
                        atomic_write(target, before)
                if config_before is not None:
                    atomic_write(self.config, config_before)
                if previous:
                    self.save(previous)
                else:
                    self.manifest.unlink(missing_ok=True)
                raise
        self.log("Türkçe yama kuruldu. Ölüm evrensel, otopsi yerel.")
        if config_after is None:
            self.log("Oyunda Options > Language > Türkçe seç.")

    def uninstall(self) -> None:
        with self.locked():
            self._uninstall()

    def _uninstall(self) -> None:
        self.require_closed()
        manifest = self.load()
        if manifest is None:
            raise ValueError("Bu araçla yapılmış bir kurulum bulunamadı.")
        roots = self.roots(manifest)
        planned = []
        for record in manifest["records"]:
            root = roots[record["root"]]
            target = safe_target(root, record["relative"])
            original = None
            if record["original_hash"] is not None:
                backup = safe_target(self.state / "backup" / record["root"], record["relative"])
                original = backup.read_bytes()
                if digest(original) != record["original_hash"]:
                    raise ValueError("Yedek değişmiş veya bozulmuş; hiçbir dosya kaldırılmadı.")
            if not target.exists():
                continue
            current = target.read_bytes()
            allowed = {record["installed_hash"], record["original_hash"]}
            if digest(current) not in allowed:
                raise ValueError("Dosya sonradan değişmiş; korumak için kaldırma durduruldu: " + record["relative"])
            planned.append((target, current, original, root))
        config_before = None
        config_after = None
        if manifest["language"] and self.config and self.config.is_file():
            config_before = self.config.read_bytes()
            if language_value(config_before) == "tr-witty":
                config_after = replace_language(config_before, manifest["language"]["before"])
        self.require_closed()
        self.log("Yedekler doğrulandı. Önceki dosyalar geri yükleniyor…")
        try:
            for target, _, original, _ in planned:
                if original is None:
                    target.unlink()
                else:
                    atomic_write(target, original)
                    if target.read_bytes() != original:
                        raise ValueError("Geri yükleme doğrulanamadı.")
            if config_after is not None:
                atomic_write(self.config, config_after)
        except Exception:
            for target, current, _, _ in planned:
                atomic_write(target, current)
            if config_before is not None:
                atomic_write(self.config, config_before)
            raise
        self.manifest.unlink()
        for record in manifest["records"]:
            backup = safe_target(self.state / "backup" / record["root"], record["relative"])
            backup.unlink(missing_ok=True)
        for target, _, _, root in planned:
            directory = target.parent
            while directory.is_relative_to(root):
                try:
                    directory.rmdir()
                except OSError:
                    break
                directory = directory.parent
        self.log("Yama kaldırıldı; kurulumdan önceki dosyalar geri geldi.")
