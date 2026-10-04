"""Windows discovery, process checks and per-user uninstall registration."""

import ctypes
import os
import re
import shutil
import sys
import winreg
from ctypes import wintypes
from pathlib import Path

from installer.core import VERSION, installation_id

UNINSTALL_ROOT = r"Software\Microsoft\Windows\CurrentVersion\Uninstall"


def state_home() -> Path:
    return Path(os.environ["LOCALAPPDATA"]) / "NoitaTurkce/Installations"


def config_path() -> Path:
    return Path(os.environ["USERPROFILE"]) / "AppData/LocalLow/Nolla_Games_Noita/save_shared/config.xml"


def registry_value(hive: int, path: str, name: str) -> str | None:
    try:
        with winreg.OpenKey(hive, path) as key:
            return str(winreg.QueryValueEx(key, name)[0])
    except OSError:
        return None


def steam_libraries() -> list[Path]:
    roots = []
    for hive, key, name in (
        (winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
        (winreg.HKEY_LOCAL_MACHINE, r"Software\WOW6432Node\Valve\Steam", "InstallPath"),
    ):
        value = registry_value(hive, key, name)
        if value:
            roots.append(Path(value))
    fallback = Path(os.environ.get("ProgramFiles(x86)", "C:/Program Files (x86)")) / "Steam"
    if fallback.is_dir():
        roots.append(fallback)
    libraries = list(roots)
    for root in roots:
        listing = root / "steamapps/libraryfolders.vdf"
        if listing.is_file():
            text = listing.read_text(encoding="utf-8-sig")
            for value in re.findall(r'"path"\s*"((?:\\.|[^"\\])*)"', text):
                libraries.append(Path(value.replace("\\\\", "\\").replace('\\"', '"')))
    return list(dict.fromkeys(p.resolve() for p in libraries))


def discover_games() -> list[Path]:
    games = []
    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        location = registry_value(hive, UNINSTALL_ROOT + r"\Steam App 881100", "InstallLocation")
        if location:
            games.append(Path(location))
    games.extend(library / "steamapps/common/Noita" for library in steam_libraries())
    if state_home().is_dir():
        import json
        for manifest in state_home().glob("*/manifest.json"):
            try:
                games.append(Path(json.loads(manifest.read_text(encoding="utf-8"))["game"]))
            except (OSError, ValueError, KeyError):
                continue
    return list(dict.fromkeys(game.resolve() for game in games if (game / "noita.exe").is_file()))


def game_running() -> bool:
    class ProcessEntry(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                    ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG),
                    ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260)]

    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    kernel.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
    kernel.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.CreateToolhelp32Snapshot(2, 0)
    if handle == ctypes.c_void_p(-1).value:
        raise OSError("Açık oyun kontrol edilemedi; işlem durduruldu.")
    try:
        entry = ProcessEntry()
        entry.dwSize = ctypes.sizeof(entry)
        found = kernel.Process32FirstW(handle, ctypes.byref(entry))
        while found:
            if entry.szExeFile.casefold() in ("noita.exe", "noita_dev.exe"):
                return True
            found = kernel.Process32NextW(handle, ctypes.byref(entry))
        return False
    finally:
        kernel.CloseHandle(handle)


def register_uninstaller(game: Path) -> None:
    if not getattr(sys, "frozen", False):
        return
    utility = state_home().parent / "NoitaTurkceSetup.exe"
    utility.parent.mkdir(parents=True, exist_ok=True)
    source = Path(sys.executable)
    if source.resolve() != utility.resolve():
        shutil.copyfile(source, utility)
    key_path = UNINSTALL_ROOT + "\\NoitaTurkce_" + installation_id(game)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path) as key:
        values = {
            "DisplayName": "Noita Türkçe Çeviri", "DisplayVersion": VERSION,
            "Publisher": "Noita Türkçe Çeviri", "InstallLocation": str(game),
            "DisplayIcon": str(utility),
            "UninstallString": f'"{utility}" --uninstall --game-dir "{game}"',
            "URLInfoAbout": "https://github.com/bhctsntrk/notia-gpt-based-turkce-ceviri",
        }
        for name, value in values.items():
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)
        for name in ("NoModify", "NoRepair"):
            winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, 1)


def unregister_uninstaller(game: Path) -> None:
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER,
                         UNINSTALL_ROOT + "\\NoitaTurkce_" + installation_id(game))
    except FileNotFoundError:
        pass
