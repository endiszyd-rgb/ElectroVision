"""Cloud sync panel — GitHub, Google Drive, ElectroVision Server + AI assistant."""
import subprocess
import sys
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QTabWidget, QTextEdit, QListWidget, QListWidgetItem,
    QGroupBox, QMessageBox, QFileDialog, QProgressBar, QSplitter,
    QFormLayout
)
from PySide6.QtCore import Qt, Slot, QThread, Signal
from PySide6.QtGui import QFont

from src.core.project import Project
from src.ai.bridge import AIBridge


def _find_project_root() -> Path:
    """Locate project root by searching for requirements.txt / main.py upward."""
    current = Path(__file__).resolve()
    for parent in current.parents:
        if (parent / "main.py").exists() or (parent / "requirements.txt").exists():
            return parent
    return current.parents[3]


class _WorkerThread(QThread):
    result = Signal(str)
    error  = Signal(str)

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self._fn = fn
        self._args = args
        self._kwargs = kwargs

    def run(self) -> None:
        try:
            out = self._fn(*self._args, **self._kwargs)
            self.result.emit(str(out))
        except Exception as e:
            self.error.emit(str(e))


class CloudPanel(QWidget):
    def __init__(self, project: Project, parent=None) -> None:
        super().__init__(parent)
        self._project   = project
        self._ai        = AIBridge.instance()
        self._gh_client = None
        self._gd_client = None
        self._sv_client = None
        self._project_root = _find_project_root()
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        main_splitter = QSplitter(Qt.Horizontal)

        # ── Left: cloud tabs ──────────────────────────────────────────────────
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)

        tabs = QTabWidget()
        tabs.addTab(self._build_github_tab(),  "🐙  GitHub")
        tabs.addTab(self._build_gdrive_tab(),  "📁  Drive")
        tabs.addTab(self._build_server_tab(),  "🌐  Serwer")
        left_layout.addWidget(tabs)

        log_box = QGroupBox("Log")
        log_layout = QVBoxLayout(log_box)
        self._log = QTextEdit()
        self._log.setReadOnly(True)
        self._log.setFont(QFont("Consolas", 9))
        self._log.setMaximumHeight(110)
        log_layout.addWidget(self._log)
        left_layout.addWidget(log_box)

        main_splitter.addWidget(left)

        # ── Right: AI project assistant ───────────────────────────────────────
        right = QWidget()
        right.setMaximumWidth(420)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)

        ai_box = QGroupBox("🤖 AI — Asystent publikacji projektu")
        ai_layout = QVBoxLayout(ai_box)

        # Project metadata fields (filled by AI or manually)
        meta_form = QFormLayout()

        self._meta_title = QLineEdit()
        self._meta_title.setPlaceholderText("Tytuł projektu (GitHub/Drive)")
        meta_form.addRow("Tytuł:", self._meta_title)

        self._meta_desc = QTextEdit()
        self._meta_desc.setPlaceholderText("Opis projektu (po angielsku dla GitHub)…")
        self._meta_desc.setMaximumHeight(70)
        meta_form.addRow("Opis:", self._meta_desc)

        self._meta_tags = QLineEdit()
        self._meta_tags.setPlaceholderText("tagi, oddzielone, przecinkiem")
        meta_form.addRow("Tagi:", self._meta_tags)
        ai_layout.addLayout(meta_form)

        # AI buttons
        ai_btns_row1 = QHBoxLayout()
        btn_gen_meta = QPushButton("Generuj opis projektu")
        btn_gen_meta.setToolTip(
            "AI wygeneruje tytuł, opis i tagi na podstawie płytki PCB — "
            "gotowe do wklejenia na GitHub lub Google Drive"
        )
        btn_gen_meta.clicked.connect(self._ai_generate_meta)
        ai_btns_row1.addWidget(btn_gen_meta)

        btn_tags = QPushButton("Sugeruj tagi")
        btn_tags.setToolTip("AI zaproponuje optymalne tagi dla widoczności projektu")
        btn_tags.clicked.connect(self._ai_suggest_tags)
        ai_btns_row1.addWidget(btn_tags)
        ai_layout.addLayout(ai_btns_row1)

        ai_btns_row2 = QHBoxLayout()
        btn_readme = QPushButton("Generuj README")
        btn_readme.setToolTip("AI napisze pełny README.md dla Twojego projektu PCB")
        btn_readme.clicked.connect(self._ai_generate_readme)
        ai_btns_row2.addWidget(btn_readme)

        btn_release = QPushButton("Notatki do release")
        btn_release.setToolTip("AI przygotuje changelog i release notes dla GitHub Release")
        btn_release.clicked.connect(self._ai_release_notes)
        ai_btns_row2.addWidget(btn_release)

        btn_clear = QPushButton("✕")
        btn_clear.setMaximumWidth(28)
        btn_clear.clicked.connect(lambda: self._ai_output.clear())
        ai_btns_row2.addWidget(btn_clear)
        ai_layout.addLayout(ai_btns_row2)

        self._ai_progress = QProgressBar()
        self._ai_progress.setRange(0, 0)
        self._ai_progress.setVisible(False)
        self._ai_progress.setMaximumHeight(6)
        ai_layout.addWidget(self._ai_progress)

        self._ai_output = QTextEdit()
        self._ai_output.setReadOnly(True)
        self._ai_output.setFont(QFont("Consolas", 9))
        self._ai_output.setPlaceholderText(
            "AI pomoże Ci w:\n"
            "• Opisie projektu (tytuł, opis, tagi) — gotowe do GitHub\n"
            "• Generowaniu README.md z opisem sprzętowym\n"
            "• Sugestiach tagów dla widoczności w wyszukiwarkach\n"
            "• Przygotowaniu notatek do wydania (release notes)\n\n"
            "Kliknij 'Generuj opis projektu' aby zacząć."
        )
        ai_layout.addWidget(self._ai_output, 1)

        right_layout.addWidget(ai_box)
        main_splitter.addWidget(right)
        main_splitter.setSizes([560, 420])
        layout.addWidget(main_splitter)

    # ── GitHub tab ────────────────────────────────────────────────────────────

    def _build_github_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)

        auth_box = QGroupBox("Autoryzacja GitHub")
        a_lay = QHBoxLayout(auth_box)
        a_lay.addWidget(QLabel("Token (ghp_…):"))
        self._gh_token = QLineEdit()
        self._gh_token.setEchoMode(QLineEdit.Password)
        self._gh_token.setPlaceholderText("ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx")
        a_lay.addWidget(self._gh_token)
        btn_login = QPushButton("Zaloguj")
        btn_login.clicked.connect(self._gh_login)
        a_lay.addWidget(btn_login)
        lay.addWidget(auth_box)

        actions = QHBoxLayout()
        btn_push = QPushButton("⬆ Push projektu")
        btn_push.clicked.connect(self._gh_push)
        actions.addWidget(btn_push)
        btn_release = QPushButton("🏷 Utwórz Release")
        btn_release.clicked.connect(self._gh_create_release)
        actions.addWidget(btn_release)
        btn_search = QPushButton("🔍 Szukaj PCB")
        btn_search.clicked.connect(self._gh_search)
        actions.addWidget(btn_search)
        lay.addLayout(actions)

        self._gh_search_input = QLineEdit()
        self._gh_search_input.setPlaceholderText("np. esp32 temperature sensor kicad pcb")
        self._gh_search_input.returnPressed.connect(self._gh_search)
        lay.addWidget(self._gh_search_input)

        self._gh_results = QListWidget()
        self._gh_results.itemDoubleClicked.connect(self._gh_open_url)
        lay.addWidget(self._gh_results)

        hint = QLabel(
            "Token: GitHub → Settings → Developer settings → Personal access tokens\n"
            "Wymagane scope: repo (read + write)"
        )
        hint.setStyleSheet("color: #888; font-size: 9px;")
        hint.setWordWrap(True)
        lay.addWidget(hint)
        return w

    # ── Google Drive tab ──────────────────────────────────────────────────────

    def _build_gdrive_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)

        info = QLabel(
            "Wymagany plik credentials.json z Google Cloud Console.\n"
            "Umieść go w: %USERPROFILE%\\.electrovision\\gdrive_credentials.json\n\n"
            "1. Wejdź na console.cloud.google.com\n"
            "2. Utwórz projekt → API & Services → Enable Google Drive API\n"
            "3. Credentials → OAuth 2.0 → Download JSON"
        )
        info.setWordWrap(True)
        info.setStyleSheet("color: #aaa; font-size: 10px;")
        lay.addWidget(info)

        btn_auth = QPushButton("🔐 Autoryzuj Google Drive (przeglądarka)")
        btn_auth.clicked.connect(self._gd_auth)
        lay.addWidget(btn_auth)

        actions = QHBoxLayout()
        btn_upload = QPushButton("⬆ Prześlij projekt")
        btn_upload.clicked.connect(self._gd_upload)
        actions.addWidget(btn_upload)
        btn_list = QPushButton("📋 Lista projektów")
        btn_list.clicked.connect(self._gd_list)
        actions.addWidget(btn_list)
        btn_download = QPushButton("⬇ Pobierz wybrany")
        btn_download.clicked.connect(self._gd_download)
        actions.addWidget(btn_download)
        lay.addLayout(actions)

        self._gd_list_widget = QListWidget()
        lay.addWidget(self._gd_list_widget)
        return w

    # ── Server tab ────────────────────────────────────────────────────────────

    def _build_server_tab(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)

        conn_box = QGroupBox("Połączenie z serwerem")
        c_lay = QHBoxLayout(conn_box)
        c_lay.addWidget(QLabel("URL:"))
        self._sv_url = QLineEdit("http://localhost:8765")
        c_lay.addWidget(self._sv_url)
        btn_ping = QPushButton("Ping")
        btn_ping.clicked.connect(self._sv_ping)
        c_lay.addWidget(btn_ping)
        btn_start = QPushButton("▶ Start lokalny")
        btn_start.clicked.connect(self._sv_start_local)
        c_lay.addWidget(btn_start)
        lay.addWidget(conn_box)

        auth_box = QGroupBox("Konto")
        a_lay = QHBoxLayout(auth_box)
        self._sv_user = QLineEdit()
        self._sv_user.setPlaceholderText("Nazwa użytkownika")
        self._sv_pass = QLineEdit()
        self._sv_pass.setPlaceholderText("Hasło")
        self._sv_pass.setEchoMode(QLineEdit.Password)
        a_lay.addWidget(self._sv_user)
        a_lay.addWidget(self._sv_pass)
        btn_reg = QPushButton("Rejestruj")
        btn_reg.clicked.connect(self._sv_register)
        btn_login = QPushButton("Zaloguj")
        btn_login.clicked.connect(self._sv_login)
        a_lay.addWidget(btn_reg)
        a_lay.addWidget(btn_login)
        lay.addWidget(auth_box)

        actions = QHBoxLayout()
        btn_upload = QPushButton("⬆ Prześlij")
        btn_upload.clicked.connect(self._sv_upload)
        actions.addWidget(btn_upload)
        btn_list = QPushButton("📋 Przeglądaj")
        btn_list.clicked.connect(self._sv_list)
        actions.addWidget(btn_list)
        btn_dl = QPushButton("⬇ Pobierz")
        btn_dl.clicked.connect(self._sv_download)
        actions.addWidget(btn_dl)
        lay.addLayout(actions)

        self._sv_list_widget = QListWidget()
        lay.addWidget(self._sv_list_widget)
        return w

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _log_msg(self, msg: str) -> None:
        self._log.append(msg)

    @Slot(object)
    def on_project_changed(self, project: Project) -> None:
        self._project = project
        self._ai.set_project_context(project_name=project.name, board=project.board)
        if project.name:
            self._meta_title.setText(project.name)

    # ── GitHub ────────────────────────────────────────────────────────────────

    def _gh_login(self) -> None:
        from src.cloud.github.client import GitHubClient
        self._gh_client = GitHubClient(self._gh_token.text().strip())
        try:
            user = self._gh_client.authenticate(self._gh_token.text().strip())
            self._log_msg(f"GitHub: zalogowano jako {user.get('login')}")
        except Exception as e:
            self._log_msg(f"GitHub błąd: {e}")

    def _gh_push(self) -> None:
        if not self._project.path:
            QMessageBox.warning(self, "GitHub", "Brak zapisanego projektu.")
            return
        if not self._gh_client:
            self._log_msg("GitHub: najpierw się zaloguj.")
            return
        desc = self._meta_desc.toPlainText().strip() or self._project.name
        files = {self._project.path.name: self._project.path.read_text(encoding="utf-8", errors="replace")}
        try:
            msg = self._gh_client.push_project(self._project.name, files, desc)
            self._log_msg(f"GitHub: {msg}")
        except Exception as e:
            self._log_msg(f"GitHub błąd: {e}")

    def _gh_create_release(self) -> None:
        if not self._gh_client:
            self._log_msg("GitHub: najpierw się zaloguj.")
            return
        try:
            tag = f"v1.0.0-{self._project.name.replace(' ','_')}"
            notes = self._ai_output.toPlainText()[:500] or "Pierwsza wersja projektu PCB."
            msg = self._gh_client.create_release(self._project.name, tag, notes)
            self._log_msg(f"GitHub Release: {msg}")
        except Exception as e:
            self._log_msg(f"GitHub Release błąd: {e}")

    def _gh_search(self) -> None:
        query = self._gh_search_input.text().strip() or "kicad pcb design"
        if not self._gh_client:
            from src.cloud.github.client import GitHubClient
            self._gh_client = GitHubClient()
        try:
            results = self._gh_client.search_pcb_designs(query)
            self._gh_results.clear()
            for r in results:
                item = QListWidgetItem(
                    f"⭐{r['stars']}  {r['name']} — {r.get('description','')[:60]}"
                )
                item.setData(Qt.UserRole, r["url"])
                self._gh_results.addItem(item)
        except Exception as e:
            self._log_msg(f"GitHub search błąd: {e}")

    def _gh_open_url(self, item: QListWidgetItem) -> None:
        url = item.data(Qt.UserRole)
        if url:
            import webbrowser
            webbrowser.open(url)

    # ── Google Drive ──────────────────────────────────────────────────────────

    def _gd_auth(self) -> None:
        from src.cloud.gdrive.client import GoogleDriveClient
        self._gd_client = GoogleDriveClient()
        try:
            user = self._gd_client.authenticate()
            self._log_msg(f"Google Drive: {user.get('displayName','OK')}")
        except Exception as e:
            self._log_msg(f"Google Drive błąd: {e}")

    def _gd_upload(self) -> None:
        if not self._gd_client:
            self._log_msg("Google Drive: najpierw autoryzuj.")
            return
        files = [str(self._project.path)] if self._project.path else []
        try:
            msg = self._gd_client.upload_project(self._project.name, files)
            self._log_msg(f"Drive: {msg}")
        except Exception as e:
            self._log_msg(f"Drive błąd: {e}")

    def _gd_list(self) -> None:
        if not self._gd_client:
            self._log_msg("Google Drive: najpierw autoryzuj.")
            return
        try:
            projects = self._gd_client.list_projects()
            self._gd_list_widget.clear()
            for p in projects:
                self._gd_list_widget.addItem(
                    f"📁 {p.get('name','?')} ({p.get('modifiedTime','')[:10]})"
                )
        except Exception as e:
            self._log_msg(f"Drive błąd: {e}")

    def _gd_download(self) -> None:
        items = self._gd_list_widget.selectedItems()
        if not items:
            return
        dest = QFileDialog.getExistingDirectory(self, "Wybierz folder docelowy")
        if not dest and not self._gd_client:
            return
        self._log_msg("Drive: pobieranie… (nie zaimplementowano pobierania po ID z listy)")

    # ── Server ────────────────────────────────────────────────────────────────

    def _get_sv_client(self):
        from src.cloud.server.client import ServerClient
        if not self._sv_client:
            self._sv_client = ServerClient(self._sv_url.text().strip())
        return self._sv_client

    def _sv_ping(self) -> None:
        ok = self._get_sv_client().health_check()
        self._log_msg(f"Serwer: {'✓ online' if ok else '✗ offline — uruchom server/app.py'}")

    def _sv_register(self) -> None:
        try:
            token = self._get_sv_client().register(self._sv_user.text(), self._sv_pass.text())
            self._log_msg(f"Serwer: zarejestrowano, token: {token[:8]}…")
        except Exception as e:
            self._log_msg(f"Serwer błąd: {e}")

    def _sv_login(self) -> None:
        try:
            token = self._get_sv_client().login(self._sv_user.text(), self._sv_pass.text())
            self._log_msg(f"Serwer: zalogowano, token: {token[:8]}…")
        except Exception as e:
            self._log_msg(f"Serwer błąd: {e}")

    def _sv_upload(self) -> None:
        if not self._project.path:
            QMessageBox.warning(self, "Serwer", "Brak projektu do przesłania.")
            return
        try:
            tags_raw = self._meta_tags.text()
            tags = [t.strip() for t in tags_raw.split(",") if t.strip()] or ["kicad", "pcb"]
            result = self._get_sv_client().upload_project(
                self._project.name,
                [str(self._project.path)],
                tags=tags,
            )
            self._log_msg(f"Serwer: przesłano — ID {result.get('id','')}")
        except Exception as e:
            self._log_msg(f"Serwer błąd: {e}")

    def _sv_list(self) -> None:
        try:
            projects = self._get_sv_client().list_projects()
            self._sv_list_widget.clear()
            for p in projects:
                item = QListWidgetItem(
                    f"📦 {p.get('name','?')} — {p.get('owner','?')} [{p.get('id','')[:8]}]"
                )
                item.setData(Qt.UserRole, p.get("id"))
                self._sv_list_widget.addItem(item)
        except Exception as e:
            self._log_msg(f"Serwer błąd: {e}")

    def _sv_download(self) -> None:
        items = self._sv_list_widget.selectedItems()
        if not items:
            return
        project_id = items[0].data(Qt.UserRole)
        dest = QFileDialog.getExistingDirectory(self, "Wybierz folder docelowy")
        if not dest:
            return
        try:
            path = self._get_sv_client().download_project(project_id, dest)
            self._log_msg(f"Serwer: pobrano do {path}")
        except Exception as e:
            self._log_msg(f"Serwer błąd: {e}")

    def _sv_start_local(self) -> None:
        try:
            subprocess.Popen(
                [sys.executable, "-m", "server.app"],
                cwd=str(self._project_root)
            )
            self._log_msg("Serwer lokalny uruchomiony na http://localhost:8765")
        except Exception as e:
            self._log_msg(f"Błąd uruchamiania serwera: {e}")

    # ── AI ────────────────────────────────────────────────────────────────────

    def _ai_done(self, _="") -> None:
        self._ai_progress.setVisible(False)

    def _ai_error(self, msg: str) -> None:
        self._ai_progress.setVisible(False)
        self._ai_output.append(f"\n⚠ {msg}")

    def _ai_generate_meta(self) -> None:
        self._ai_output.clear()
        self._ai_progress.setVisible(True)

        def _on_done(data: dict) -> None:
            self._ai_progress.setVisible(False)
            if isinstance(data, dict):
                if data.get("title"):
                    self._meta_title.setText(data["title"])
                if data.get("description"):
                    self._meta_desc.setPlainText(data["description"])
                if data.get("tags"):
                    self._meta_tags.setText(", ".join(data["tags"]))
                self._ai_output.setPlainText(
                    f"Tytuł: {data.get('title','')}\n"
                    f"Opis: {data.get('description','')}\n"
                    f"Tagi: {', '.join(data.get('tags',[]))}\n"
                    f"Kategoria: {data.get('category','')}\n"
                    f"Poziom: {data.get('difficulty','')}"
                )
            else:
                self._ai_output.setPlainText(str(data))

        self._ai.generate_project_meta(
            project_name=self._project.name or "ElectroVision Project",
            board=self._project.board if self._project else None,
            on_done=_on_done,
            on_error=self._ai_error,
        )

    def _ai_suggest_tags(self) -> None:
        self._ai_output.clear()
        self._ai_progress.setVisible(True)
        board_info = ""
        if self._project.board:
            b = self._project.board
            types = {}
            for c in b.components:
                types[c.component_type] = types.get(c.component_type, 0) + 1
            board_info = f"Komponenty: {types}. Wymiary: {b.width_mm:.0f}x{b.height_mm:.0f}mm"
        self._ai.ask_async(
            f"Zaproponuj 10-15 optymalnych tagów dla projektu PCB na GitHub i repozytoria open-source.\n"
            f"Nazwa projektu: '{self._project.name or 'ElectroVision Project'}'\n"
            f"{board_info}\n\n"
            "Format: tagi oddzielone przecinkami, po angielsku (dla GitHub), "
            "mieszaj: ogólne (pcb, kicad, electronics) + specyficzne (esp32, iot, sensor).",
            system_key="pcb_system",
            on_chunk=self._ai_output.insertPlainText,
            on_done=self._ai_done,
            on_error=self._ai_error,
        )

    def _ai_generate_readme(self) -> None:
        self._ai_output.clear()
        self._ai_progress.setVisible(True)
        board_info = "Brak danych PCB"
        if self._project.board:
            b = self._project.board
            types: dict = {}
            for c in b.components:
                types[c.component_type] = types.get(c.component_type, 0) + 1
            board_info = (
                f"PCB {b.width_mm:.0f}×{b.height_mm:.0f} mm, "
                f"{len(b.components)} komponentów ({types}), "
                f"{len(b.traces)} ścieżek, {len(b.vias)} przelotki"
            )
        self._ai.ask_async(
            f"Napisz profesjonalny README.md po angielsku dla projektu PCB:\n"
            f"Nazwa: {self._project.name or 'PCB Project'}\n"
            f"Dane płytki: {board_info}\n\n"
            "README musi zawierać:\n"
            "1. Krótki opis projektu (1 akapit)\n"
            "2. Features (lista funkcji)\n"
            "3. Hardware Requirements (lista komponentów z wartościami)\n"
            "4. Schematic / PCB Preview (placeholder)\n"
            "5. Getting Started (jak uruchomić, co wgrać na MCU)\n"
            "6. Wiring Diagram (opis połączeń)\n"
            "7. Software Dependencies (biblioteki)\n"
            "8. License: MIT\n\n"
            "Format: pełny markdown gotowy do skopiowania do README.md",
            system_key="pcb_system",
            on_chunk=self._ai_output.insertPlainText,
            on_done=self._ai_done,
            on_error=self._ai_error,
        )

    def _ai_release_notes(self) -> None:
        self._ai_output.clear()
        self._ai_progress.setVisible(True)
        self._ai.ask_async(
            f"Przygotuj profesjonalne Release Notes dla projektu PCB '{self._project.name or 'PCB Project'}' v1.0.0.\n\n"
            "Format markdown:\n"
            "## What's New\n"
            "## Hardware Changes\n"
            "## Known Issues\n"
            "## How to Update (jeśli dotyczy)\n"
            "## Checksum / BOM Summary\n\n"
            "Napisz po angielsku. Bądź konkretny i techniczny.",
            system_key="pcb_system",
            on_chunk=self._ai_output.insertPlainText,
            on_done=self._ai_done,
            on_error=self._ai_error,
        )
