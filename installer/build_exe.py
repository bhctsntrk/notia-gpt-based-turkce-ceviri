"""Build a single Windows EXE containing the language and optional mod patches."""

import argparse
import importlib.metadata
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "dist/installer")
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="noita-tr-build-") as temporary:
        scratch = Path(temporary)
        licenses = scratch / "THIRD_PARTY.txt"
        parts = ["Noita Turkish installer — third-party dependency notices\n"]
        for name in ("pyinstaller", "pillow", "luaparser", "antlr4-python3-runtime", "multimethod"):
            distribution = importlib.metadata.distribution(name)
            parts.append(f"\n{name} {distribution.version}\n")
            for entry in distribution.files or []:
                if "dist-info" in str(entry) and any(word in entry.name.lower() for word in ("license", "copying")):
                    parts.append(distribution.locate_file(entry).read_text(encoding="utf-8", errors="replace"))
        python_license = Path(sys.base_prefix) / "LICENSE.txt"
        if not python_license.is_file():
            raise FileNotFoundError("Python license file is required for distribution.")
        parts.append("\nPython\n" + python_license.read_text(encoding="utf-8"))
        for terms in (Path(sys.base_prefix) / "tcl").glob("*/license.terms"):
            parts.append("\nTcl/Tk\n" + terms.read_text(encoding="utf-8"))
        licenses.write_text("\n".join(parts), encoding="utf-8")
        command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--onefile", "--windowed",
                   "--name", "NoitaTurkceSetup-0.1.0", "--paths", str(ROOT),
                   "--distpath", str(output), "--workpath", str(scratch / "build"),
                   "--specpath", str(scratch), "--collect-submodules", "luaparser",
                   "--version-file", str(ROOT / "installer/version_info.txt")]
        for source, destination in ((ROOT / "src", "src"), (ROOT / "optional", "optional"),
                                    (ROOT / "tools/cheatgui_font.lua", "tools"),
                                    (ROOT / "RIGHTS.md", "."), (ROOT / "legal", "legal"), (licenses, ".")):
            command.extend(["--add-data", str(source) + ":" + destination])
        command.append(str(ROOT / "installer/app.py"))
        subprocess.run(command, check=True, cwd=ROOT)
    print("Built " + str(output / "NoitaTurkceSetup-0.1.0.exe"))


if __name__ == "__main__":
    main()
