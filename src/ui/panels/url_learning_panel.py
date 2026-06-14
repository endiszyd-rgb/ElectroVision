"""URL Learning Panel — fetches web articles/docs and adds them to local AI knowledge base."""
from __future__ import annotations
import re
import time
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QLineEdit, QTextEdit, QComboBox, QProgressBar, QGroupBox,
    QListWidget, QListWidgetItem, QSplitter, QFormLayout, QMessageBox
)
from PySide6.QtCore import Qt, QThread, Signal, Slot
from PySide6.QtGui import QFont, QColor


class _FetchWorker(QThread):
    """Background thread: fetch URL, extract text, save to training_data/."""
    progress   = Signal(str)
    finished   = Signal(str, str)  # (saved_path, extracted_text)
    error      = Signal(str)

    def __init__(self, url: str, domain: str, title: str, out_dir: Path):
        super().__init__()
        self._url     = url
        self._domain  = domain
        self._title   = title
        self._out_dir = out_dir

    def run(self) -> None:
        try:
            self.progress.emit(f"Pobieranie: {self._url}")

            try:
                import urllib.request
                import urllib.parse

                headers = {
                    "User-Agent": "Mozilla/5.0 (compatible; ElectroVision/1.0; +https://github.com/electrovision)",
                    "Accept": "text/html,application/xhtml+xml",
                    "Accept-Language": "en-US,en;q=0.9,pl;q=0.8",
                }
                req = urllib.request.Request(self._url, headers=headers)
                with urllib.request.urlopen(req, timeout=30) as resp:
                    raw = resp.read()
                    encoding = resp.headers.get_content_charset("utf-8")
                    html = raw.decode(encoding, errors="replace")
            except Exception as e:
                self.error.emit(f"Błąd pobierania: {e}\nURL: {self._url}")
                return

            self.progress.emit("Ekstrakcja tekstu…")
            text = self._extract_text(html)

            if len(text.strip()) < 200:
                self.error.emit(
                    "Strona zwróciła za mało tekstu (może wymaga JavaScript lub logowania).\n"
                    "Spróbuj skopiować tekst ręcznie i użyć 'Wklej tekst bezpośrednio'."
                )
                return

            self.progress.emit("Zapis do bazy wiedzy…")
            saved = self._save(text)
            self.finished.emit(saved, text[:500])

        except Exception as e:
            self.error.emit(f"Nieoczekiwany błąd: {e}")

    def _extract_text(self, html: str) -> str:
        """Convert HTML to clean markdown-friendly text."""
        # Remove scripts, styles, nav
        html = re.sub(r'<script[^>]*>.*?</script>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<style[^>]*>.*?</style>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<nav[^>]*>.*?</nav>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<header[^>]*>.*?</header>', '', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<footer[^>]*>.*?</footer>', '', html, flags=re.DOTALL | re.IGNORECASE)

        # Convert headers
        html = re.sub(r'<h1[^>]*>(.*?)</h1>', r'\n# \1\n', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<h2[^>]*>(.*?)</h2>', r'\n## \1\n', html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<h3[^>]*>(.*?)</h3>', r'\n### \1\n', html, flags=re.DOTALL | re.IGNORECASE)

        # Code blocks
        html = re.sub(r'<pre[^>]*><code[^>]*>(.*?)</code></pre>', r'\n```\n\1\n```\n',
                      html, flags=re.DOTALL | re.IGNORECASE)
        html = re.sub(r'<code[^>]*>(.*?)</code>', r'`\1`', html, flags=re.DOTALL | re.IGNORECASE)

        # Lists
        html = re.sub(r'<li[^>]*>(.*?)</li>', r'\n- \1', html, flags=re.DOTALL | re.IGNORECASE)

        # Line breaks
        html = re.sub(r'<br\s*/?>', '\n', html, flags=re.IGNORECASE)
        html = re.sub(r'<p[^>]*>', '\n\n', html, flags=re.IGNORECASE)

        # Remove remaining tags
        html = re.sub(r'<[^>]+>', '', html)

        # Decode HTML entities
        html = html.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>')\
                   .replace('&nbsp;', ' ').replace('&quot;', '"').replace('&#39;', "'")
        html = re.sub(r'&#\d+;', '', html)

        # Clean whitespace
        html = re.sub(r'\n{4,}', '\n\n\n', html)
        html = re.sub(r'[ \t]+', ' ', html)
        lines = [l.strip() for l in html.split('\n')]
        lines = [l for l in lines if l]
        return '\n'.join(lines)

    def _save(self, text: str) -> str:
        """Save extracted text to training_data/<domain>/ folder."""
        self._out_dir.mkdir(parents=True, exist_ok=True)

        # Sanitize title for filename
        safe_title = re.sub(r'[^\w\-_]', '_', self._title)[:60].strip('_') or "article"
        ts = int(time.time())
        filename = f"{safe_title}_{ts}.md"
        path = self._out_dir / filename

        header = (
            f"# {self._title}\n"
            f"Source: {self._url}\n"
            f"Domain: {self._domain}\n"
            f"Added: {time.strftime('%Y-%m-%d %H:%M')}\n\n"
        )
        path.write_text(header + text, encoding="utf-8")
        return str(path)


class URLLearningPanel(QWidget):
    """
    Panel for adding web articles and documentation to the local AI knowledge base (RAG).

    User provides URL → app fetches and extracts text → saves to training_data/ → rebuilds RAG index.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._worker: _FetchWorker | None = None
        self._project_root = self._find_project_root()
        self._training_dir = self._project_root / "training_data"
        self._build_ui()
        self._load_existing()

    def _find_project_root(self) -> Path:
        p = Path(__file__).resolve()
        for _ in range(8):
            if (p / "main.py").exists() or (p / "requirements.txt").exists():
                return p
            p = p.parent
        return Path.cwd()

    # ── UI ──────────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        layout.addWidget(QLabel(
            "<b>Nauka AI z linków</b> — dodaj dokumentację, artykuły i posty do lokalnej bazy wiedzy"
        ))

        splitter = QSplitter(Qt.Horizontal)

        # ── LEFT: Add URL ────────────────────────────────────────────────────────
        left = QWidget()
        left.setMaximumWidth(440)
        left_lay = QVBoxLayout(left)
        left_lay.setContentsMargins(0, 0, 0, 0)

        # URL input group
        url_box = QGroupBox("Dodaj link do dokumentacji / artykułu")
        url_form = QFormLayout(url_box)

        self._url_edit = QLineEdit()
        self._url_edit.setPlaceholderText(
            "https://docs.espressif.com/... lub https://arduino.cc/..."
        )
        self._url_edit.returnPressed.connect(self._fetch_url)
        url_form.addRow("URL:", self._url_edit)

        self._title_edit = QLineEdit()
        self._title_edit.setPlaceholderText("Tytuł artykułu (opcjonalne, auto-wykryje)")
        url_form.addRow("Tytuł:", self._title_edit)

        self._domain_combo = QComboBox()
        self._domain_combo.addItems([
            "pcb",
            "stl",
            "code",
            "electronics",
            "components",
            "kicad",
            "cadquery",
            "micropython",
            "freertos",
            "general",
        ])
        url_form.addRow("Domena wiedzy:", self._domain_combo)

        btn_fetch = QPushButton("⬇  Pobierz i dodaj do bazy wiedzy")
        btn_fetch.setStyleSheet("font-weight: bold; padding: 6px;")
        btn_fetch.clicked.connect(self._fetch_url)
        url_form.addRow(btn_fetch)

        left_lay.addWidget(url_box)

        # Quick links
        quick_box = QGroupBox("Szybkie linki — popularne źródła")
        quick_lay = QVBoxLayout(quick_box)
        quick_lay.setSpacing(3)

        quick_links = [
            ("ESP-IDF GPIO", "https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/peripherals/gpio.html", "code"),
            ("ESP-IDF I2C", "https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/peripherals/i2c.html", "code"),
            ("MicroPython ESP32", "https://docs.micropython.org/en/latest/esp32/quickref.html", "code"),
            ("Arduino Language Ref", "https://www.arduino.cc/reference/en/", "code"),
            ("CadQuery API", "https://cadquery.readthedocs.io/en/latest/apireference.html", "stl"),
            ("KiCad PCB Calculator", "https://docs.kicad.org/8.0/en/pcb_calculator/pcb_calculator.html", "pcb"),
            ("IPC-2221 Trace Width", "https://www.7pcb.com/trace-width-calculator.php", "pcb"),
            ("JLCPCB Design Rules", "https://jlcpcb.com/capabilities/pcb-capabilities", "pcb"),
            ("Adafruit BME280", "https://learn.adafruit.com/adafruit-bme280-humidity-barometric-pressure-temperature-sensor-breakout", "components"),
            ("RP2040 Datasheet", "https://datasheets.raspberrypi.com/rp2040/rp2040-product-brief.pdf", "code"),
        ]

        for label_text, url, domain in quick_links:
            row = QHBoxLayout()
            btn = QPushButton(label_text)
            btn.setStyleSheet("text-align:left; padding: 2px 6px; font-size:10px;")
            btn.setFlat(True)
            btn.clicked.connect(lambda checked, u=url, d=domain, t=label_text:
                                self._quick_fetch(u, d, t))
            row.addWidget(btn)
            quick_lay.addLayout(row)

        left_lay.addWidget(quick_box)

        # Paste text directly
        paste_box = QGroupBox("Wklej tekst bezpośrednio")
        paste_lay = QVBoxLayout(paste_box)
        self._paste_text = QTextEdit()
        self._paste_text.setPlaceholderText(
            "Wklej tutaj fragment dokumentacji, datasheet, post lub artykuł...\n"
            "AI nauczy się tej wiedzy dla wybranej domeny."
        )
        self._paste_text.setMaximumHeight(120)
        paste_lay.addWidget(self._paste_text)
        paste_btn = QPushButton("Dodaj wklejony tekst do bazy")
        paste_btn.clicked.connect(self._add_pasted_text)
        paste_lay.addWidget(paste_btn)
        left_lay.addWidget(paste_box)
        left_lay.addStretch()

        splitter.addWidget(left)

        # ── RIGHT: Status + Knowledge base list ───────────────────────────────────
        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)

        # Status
        status_box = QGroupBox("Status")
        status_lay = QVBoxLayout(status_box)

        self._progress = QProgressBar()
        self._progress.setRange(0, 0)
        self._progress.setVisible(False)
        self._progress.setMaximumHeight(6)
        status_lay.addWidget(self._progress)

        self._status_log = QTextEdit()
        self._status_log.setReadOnly(True)
        self._status_log.setMaximumHeight(120)
        self._status_log.setFont(QFont("Consolas", 9))
        self._status_log.setPlaceholderText("Status pobierania i indeksowania...")
        status_lay.addWidget(self._status_log)

        rag_row = QHBoxLayout()
        btn_rebuild = QPushButton("🔄 Odbuduj indeks RAG")
        btn_rebuild.setToolTip(
            "Po dodaniu nowych materiałów odbuduj indeks wektorowy\n"
            "aby AI mogło korzystać z nowej wiedzy."
        )
        btn_rebuild.clicked.connect(self._rebuild_rag)
        rag_row.addWidget(btn_rebuild)

        btn_stats = QPushButton("📊 Statystyki bazy")
        btn_stats.clicked.connect(self._show_stats)
        rag_row.addWidget(btn_stats)
        status_lay.addLayout(rag_row)
        right_lay.addWidget(status_box)

        # Knowledge base files
        kb_box = QGroupBox("Pliki wiedzy w bazie")
        kb_lay = QVBoxLayout(kb_box)

        self._file_list = QListWidget()
        self._file_list.setFont(QFont("Consolas", 9))
        kb_lay.addWidget(self._file_list)

        kb_btns = QHBoxLayout()
        btn_refresh = QPushButton("Odśwież listę")
        btn_refresh.clicked.connect(self._load_existing)
        kb_btns.addWidget(btn_refresh)

        btn_open = QPushButton("📂 Otwórz folder")
        btn_open.clicked.connect(self._open_training_folder)
        kb_btns.addWidget(btn_open)

        btn_remove = QPushButton("🗑 Usuń zaznaczony")
        btn_remove.clicked.connect(self._remove_selected)
        kb_btns.addWidget(btn_remove)
        kb_lay.addLayout(kb_btns)
        right_lay.addWidget(kb_box, 1)

        splitter.addWidget(right)
        splitter.setSizes([440, 560])
        layout.addWidget(splitter, 1)

    # ── Actions ─────────────────────────────────────────────────────────────────

    def _fetch_url(self) -> None:
        url = self._url_edit.text().strip()
        if not url:
            return
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
            self._url_edit.setText(url)

        title  = self._title_edit.text().strip() or url.split("/")[-1][:60]
        domain = self._domain_combo.currentText()
        out_dir = self._training_dir / domain

        self._log(f"⬇ Pobieranie: {url}")
        self._start_fetch(url, domain, title, out_dir)

    def _quick_fetch(self, url: str, domain: str, title: str) -> None:
        self._url_edit.setText(url)
        self._title_edit.setText(title)
        self._domain_combo.setCurrentText(domain)
        out_dir = self._training_dir / domain
        self._log(f"⬇ Szybkie pobieranie [{domain}]: {title}")
        self._start_fetch(url, domain, title, out_dir)

    def _start_fetch(self, url: str, domain: str, title: str, out_dir: Path) -> None:
        if self._worker and self._worker.isRunning():
            self._log("⚠ Poprzednie pobieranie nadal trwa. Poczekaj.")
            return

        self._progress.setVisible(True)
        self._worker = _FetchWorker(url, domain, title, out_dir)
        self._worker.progress.connect(self._log)
        self._worker.finished.connect(self._on_fetch_done)
        self._worker.error.connect(self._on_fetch_error)
        self._worker.start()

    @Slot(str, str)
    def _on_fetch_done(self, saved_path: str, preview: str) -> None:
        self._progress.setVisible(False)
        self._log(f"✓ Zapisano: {Path(saved_path).name}")
        self._log(f"  Podgląd: {preview[:120].strip()}…")
        self._load_existing()
        self._url_edit.clear()
        self._title_edit.clear()

    @Slot(str)
    def _on_fetch_error(self, error: str) -> None:
        self._progress.setVisible(False)
        self._log(f"✗ Błąd: {error}")

    def _add_pasted_text(self) -> None:
        text = self._paste_text.toPlainText().strip()
        if len(text) < 50:
            self._log("⚠ Za mało tekstu (min 50 znaków)")
            return

        title  = self._title_edit.text().strip() or "pasted_article"
        domain = self._domain_combo.currentText()
        out_dir = self._training_dir / domain
        out_dir.mkdir(parents=True, exist_ok=True)

        safe_title = re.sub(r'[^\w\-]', '_', title)[:50]
        path = out_dir / f"{safe_title}_{int(time.time())}.md"
        path.write_text(
            f"# {title}\nDomain: {domain}\nAdded: {time.strftime('%Y-%m-%d %H:%M')}\n\n{text}",
            encoding="utf-8"
        )
        self._log(f"✓ Zapisano wklejony tekst: {path.name}")
        self._paste_text.clear()
        self._load_existing()

    def _rebuild_rag(self) -> None:
        self._log("🔄 Odbudowywanie indeksu RAG…")
        self._progress.setVisible(True)

        def _worker():
            try:
                from src.ai.rag.knowledge_base import LocalKnowledgeBase
                kb = LocalKnowledgeBase.instance()
                result = kb.build(force=True)
                return result
            except Exception as e:
                return f"Błąd: {e}"

        import threading
        def _run():
            result = _worker()
            self._progress.setVisible(False)
            self._log(f"✓ {result}")

        threading.Thread(target=_run, daemon=True).start()

    def _show_stats(self) -> None:
        try:
            from src.ai.rag.knowledge_base import LocalKnowledgeBase
            kb = LocalKnowledgeBase.instance()
            if kb.is_ready:
                self._log(f"📊 Indeks RAG: {kb.chunk_count} chunków gotowych")
            else:
                self._log("📊 Indeks RAG nie jest jeszcze zbudowany. Kliknij 'Odbuduj'.")
        except Exception as e:
            self._log(f"📊 Błąd: {e}")

    def _load_existing(self) -> None:
        self._file_list.clear()
        if not self._training_dir.exists():
            return

        total_size = 0
        for md_file in sorted(self._training_dir.rglob("*.md")):
            size = md_file.stat().st_size
            total_size += size
            rel = md_file.relative_to(self._training_dir)
            domain = rel.parts[0] if len(rel.parts) > 1 else "root"
            item = QListWidgetItem(f"[{domain}] {md_file.stem}")
            item.setToolTip(str(md_file))
            item.setForeground(QColor("#aaa"))
            self._file_list.addItem(item)

        for jsonl_file in sorted(self._training_dir.rglob("*.jsonl")):
            size = jsonl_file.stat().st_size
            total_size += size
            rel = jsonl_file.relative_to(self._training_dir)
            item = QListWidgetItem(f"[qa] {jsonl_file.stem}")
            item.setToolTip(str(jsonl_file))
            item.setForeground(QColor("#8a8"))
            self._file_list.addItem(item)

        count = self._file_list.count()
        self._log(f"📚 Baza wiedzy: {count} plików, {total_size//1024} KB łącznie")

    def _remove_selected(self) -> None:
        item = self._file_list.currentItem()
        if not item:
            return
        path = item.toolTip()
        reply = QMessageBox.question(
            self, "Usuń plik",
            f"Usunąć plik z bazy wiedzy?\n{Path(path).name}",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            try:
                Path(path).unlink()
                self._load_existing()
                self._log(f"🗑 Usunięto: {Path(path).name}")
            except Exception as e:
                self._log(f"✗ Błąd usuwania: {e}")

    def _open_training_folder(self) -> None:
        import subprocess
        try:
            subprocess.Popen(f'explorer "{self._training_dir}"')
        except Exception:
            pass

    def _log(self, msg: str) -> None:
        self._status_log.append(f"[{time.strftime('%H:%M:%S')}] {msg}")
        sb = self._status_log.verticalScrollBar()
        sb.setValue(sb.maximum())
