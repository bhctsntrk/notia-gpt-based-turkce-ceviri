"""Single-window installation utility; all packages work offline."""

import argparse
import ctypes
import queue
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from installer import windows
from installer.core import Log, Manager, VERSION, discover_optional


class App:
    def __init__(self, root: tk.Tk, game: str | None, uninstall: bool) -> None:
        self.root = root
        self.events = queue.Queue()
        self.busy = False
        self.game = tk.StringVar(value=game or "")
        self.language = tk.BooleanVar(value=True)
        self.extras = {name: tk.BooleanVar(value=False) for name in ("cheatgui", "seed_changer")}
        self.status = tk.StringVar(value="Noita klasörünü seç; kalanını birlikte hallederiz.")
        root.title("Noita Türkçe — Kur / Kaldır")
        root.geometry("740x620")
        root.minsize(700, 580)
        root.configure(background="#181b20")
        root.protocol("WM_DELETE_WINDOW", self.close)
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TFrame", background="#181b20")
        style.configure("TLabel", background="#181b20", foreground="#f2eee8", font=("Segoe UI", 10))
        style.configure("Title.TLabel", font=("Segoe UI", 24, "bold"), foreground="#f8c16b")
        style.configure("Muted.TLabel", foreground="#bcc1c8")
        style.configure("TCheckbutton", background="#181b20", foreground="#f2eee8", font=("Segoe UI", 10))
        style.map("TCheckbutton", background=[("active", "#252a31")],
                  foreground=[("disabled", "#777e88")])
        style.configure("TButton", font=("Segoe UI", 10), padding=(12, 8))
        style.configure("Install.TButton", background="#e4ab55", foreground="#16191e")
        frame = ttk.Frame(root, padding=24)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Noita Türkçe", style="Title.TLabel").pack(anchor="w")
        ttk.Label(frame, text="GPT 6.1 Sol ile çevrildi.  •  Ölüm evrensel, otopsi yerel.",
                  style="Muted.TLabel").pack(anchor="w", pady=(4, 20))
        ttk.Label(frame, text="Oyun klasörü", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        row = ttk.Frame(frame)
        row.pack(fill="x", pady=(6, 16))
        self.location = ttk.Combobox(row, textvariable=self.game)
        self.location.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.browse_button = ttk.Button(row, text="Klasör seç…", command=self.browse)
        self.browse_button.pack(side="right")
        games = windows.discover_games()
        self.location["values"] = [str(path) for path in games]
        if not game and games:
            self.game.set(str(games[0]))
        ttk.Label(frame, text="Paketler", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        ttk.Label(frame, text="✓  Ana oyun — 3.610 Türkçe metin", foreground="#f8c16b").pack(anchor="w", pady=(8, 4))
        self.checks = {}
        for name, title in (("cheatgui", "Cheatgui — Hile Tezgâhı"),
                            ("seed_changer", "Seed Changer — Kader Ayarı")):
            check = ttk.Checkbutton(frame, text=title, variable=self.extras[name])
            check.pack(anchor="w", pady=3)
            self.checks[name] = check
        self.extras_status = ttk.Label(frame, text="", style="Muted.TLabel")
        self.extras_status.pack(anchor="w", pady=(4, 10))
        self.language_check = ttk.Checkbutton(frame, text="Oyun dilini Türkçe yap", variable=self.language)
        self.language_check.pack(anchor="w", pady=(0, 12))
        ttk.Label(frame, text="Kurulum öncesi yedek alınır. Kaldırma, önceki dosyalarını geri getirir.",
                  style="Muted.TLabel").pack(anchor="w")
        ttk.Label(frame, text="Kayıt oyunlarına dokunulmaz. Kurarken ve kaldırırken Noita kapalı olmalı.",
                  style="Muted.TLabel").pack(anchor="w", pady=(4, 14))
        actions = ttk.Frame(frame)
        actions.pack(fill="x")
        self.install_button = ttk.Button(actions, text="Türkçe yamayı kur", style="Install.TButton",
                                         command=lambda: self.start(False))
        self.install_button.pack(side="left")
        self.remove_button = ttk.Button(actions, text="Kaldır / geri yükle", command=lambda: self.start(True))
        self.remove_button.pack(side="left", padx=8)
        ttk.Button(actions, text="Proje sayfası", command=lambda: webbrowser.open(
            "https://github.com/bhctsntrk/notia-gpt-based-turkce-ceviri")).pack(side="right")
        self.progress = ttk.Progressbar(frame, mode="indeterminate")
        self.progress.pack(fill="x", pady=(14, 8))
        ttk.Label(frame, textvariable=self.status, wraplength=680).pack(anchor="w")
        self.log = tk.Text(frame, height=5, background="#111419", foreground="#cbd1da",
                           relief="flat", font=("Segoe UI", 9), state="disabled", wrap="word")
        self.log.pack(fill="both", expand=True, pady=(8, 0))
        self.location.bind("<<ComboboxSelected>>", lambda _: self.refresh())
        self.location.bind("<FocusOut>", lambda _: self.refresh())
        self.refresh()
        if uninstall:
            self.status.set("Kurulumu kaldırmak için Kaldır / geri yükle düğmesine bas.")
        root.after(100, self.poll)

    def manager(self, log: Log = print) -> Manager:
        return Manager(Path(self.game.get()), windows.state_home(), windows.config_path(), windows.game_running, log)

    def browse(self) -> None:
        value = filedialog.askdirectory(title="noita.exe dosyasının bulunduğu klasörü seç")
        if value:
            self.game.set(value)
            self.refresh()

    def refresh(self) -> None:
        if self.busy:
            return
        game = Path(self.game.get())
        valid = bool(self.game.get()) and (game / "noita.exe").is_file()
        try:
            extras = discover_optional(game) if valid else {}
            installed = self.manager().load() if self.game.get() else None
            error = None
        except (OSError, ValueError) as exc:
            extras, installed, error = {}, None, str(exc)
        for name, check in self.checks.items():
            check.configure(state="normal" if name in extras else "disabled")
            self.extras[name].set(name in extras)
        self.extras_status.configure(text="Kurulu ekler seçildi." if extras else "Ek mod bulunamadı; ana yama kurulabilir.")
        self.install_button.configure(state="normal" if valid and not error else "disabled")
        self.remove_button.configure(state="normal" if installed else "disabled")
        self.status.set(error or ("Bu araçla kurulmuş yama bulundu." if installed else
                                 "Kurulum hazır." if valid else "noita.exe dosyasının bulunduğu klasörü seç."))

    def start(self, remove: bool) -> None:
        if self.busy:
            return
        manager = self.manager(lambda line: self.events.put(("log", line)))
        selected = {name for name, value in self.extras.items() if value.get()}
        language = self.language.get()
        self.busy = True
        for widget in [self.location, self.browse_button, self.install_button, self.remove_button,
                       self.language_check, *self.checks.values()]:
            widget.configure(state="disabled")
        self.status.set("Geri yükleniyor…" if remove else "Kuruluyor…")
        self.progress.start(12)

        def work() -> None:
            try:
                if remove:
                    manager.uninstall()
                    windows.unregister_uninstaller(manager.game)
                else:
                    manager.install(selected, language)
                    try:
                        windows.register_uninstaller(manager.game)
                    except OSError:
                        self.events.put(("log", "Windows kaldırma kaydı eklenemedi. Bu EXE içindeki Kaldır düğmesini kullanabilirsin."))
                self.events.put(("done", "Yama kaldırıldı." if remove else "Kuruldu. Noita'yı açabilirsin."))
            except Exception as exc:
                detail = str(exc)
                if isinstance(exc, PermissionError):
                    detail = "Bu oyun klasörüne yazma iznin yok. Yazılabilir bir Noita kurulum klasörü seç."
                self.events.put(("error", detail))

        threading.Thread(target=work, daemon=True).start()

    def poll(self) -> None:
        while True:
            try:
                kind, text = self.events.get_nowait()
            except queue.Empty:
                break
            self.log.configure(state="normal")
            self.log.insert("end", text + "\n")
            self.log.see("end")
            self.log.configure(state="disabled")
            if kind in ("done", "error"):
                self.busy = False
                self.progress.stop()
                self.location.configure(state="normal")
                self.browse_button.configure(state="normal")
                self.language_check.configure(state="normal")
                self.refresh()
                self.status.set(text)
                if kind == "error":
                    messagebox.showerror("İşlem tamamlanamadı", text)
        self.root.after(100, self.poll)

    def close(self) -> None:
        if self.busy:
            self.status.set("Dosya işlemi sürüyor; bitince pencereyi kapatabilirsin.")
        else:
            self.root.destroy()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--game-dir")
    parser.add_argument("--uninstall", action="store_true")
    parser.add_argument("--self-test", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--smoke-report", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.self_test:
        from installer.selftest import run
        run(args.self_test)
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except (OSError, AttributeError):
        pass
    root = tk.Tk()
    app = App(root, args.game_dir, args.uninstall)
    if args.smoke_report:
        def report() -> None:
            import json
            root.update_idletasks()
            args.smoke_report.write_text(json.dumps({"version": VERSION, "title": root.title(),
                "width": root.winfo_width(), "height": root.winfo_height(), "tk": root.tk.call("info", "patchlevel"),
                "ready": True}), encoding="utf-8")
            root.destroy()
        root.after(800, report)
    root.mainloop()


if __name__ == "__main__":
    main()
