import sys
import os
from datetime import datetime
from typing import List, Optional

from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFileDialog, QMessageBox, QTextEdit, QProgressBar, QCheckBox
)

import backend


class CopyWorker(QThread):
    progress = pyqtSignal(int, int, str)         # current, total, message
    finished = pyqtSignal(int, int, str)         # success_count, error_count, target_dest
    line_log = pyqtSignal(str)                   # per-file line log

    def __init__(self, files: List[str], origin: str, dest: str, chunked: bool = True):
        super().__init__()
        self.files = files
        self.origin = origin
        self.dest = dest
        self.chunked = chunked

    def run(self):
        total = len(self.files)
        success = 0
        errors = 0

        for i, rel_path in enumerate(self.files, start=1):
            rel_norm = rel_path.replace("\\", "/")
            src = os.path.join(self.origin, rel_norm)
            dst = os.path.join(self.dest, rel_norm)
            try:
                backend.copy_file(src, dst, chunked=self.chunked)
                success += 1
                msg = f"OK: {rel_norm}"
            except Exception as e:
                errors += 1
                msg = f"ERROR: {rel_norm} ({e})"

            self.line_log.emit(msg)
            self.progress.emit(i, total, msg)

        self.finished.emit(success, errors, self.dest)


class BackupApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("FileXtransfer - Backup Tool (PyQt5)")
        self.resize(800, 550)

        # State
        self.origin: str = ""
        self.dest_b: str = ""          # standard destination (B)
        self.dest_c: str = ""          # alternative destination (C)
        self.use_dest_c: bool = False  # checkbox state
        self.missing_files: List[str] = []
        self.worker: Optional[CopyWorker] = None
        self.log_buffer: List[str] = []

        # UI elements
        self.origin_label = QLabel("Origine A: non selezionata")
        self.dest_b_label = QLabel("Destinazione B: non selezionata")
        self.dest_c_label = QLabel("Destinazione C: non selezionata")

        self.btn_origin = QPushButton("Seleziona origine (A)")
        self.btn_origin.clicked.connect(self.select_origin)

        self.btn_dest_b = QPushButton("Seleziona destinazione (B)")
        self.btn_dest_b.clicked.connect(self.select_dest_b)

        self.btn_dest_c = QPushButton("Seleziona destinazione alternativa (C)")
        self.btn_dest_c.clicked.connect(self.select_dest_c)

        self.checkbox_use_c = QCheckBox("Usa destinazione alternativa (C) per la copia")
        self.checkbox_use_c.stateChanged.connect(self.toggle_use_c)

        self.btn_analyze = QPushButton("Analizza (A vs B)")
        self.btn_analyze.clicked.connect(self.analyze)

        self.btn_copy = QPushButton("Copia i file mancanti")
        self.btn_copy.clicked.connect(self.start_copy)
        self.btn_copy.setEnabled(False)

        self.progress = QProgressBar()
        self.progress.setMinimum(0)
        self.progress.setValue(0)

        self.log_area = QTextEdit()
        self.log_area.setReadOnly(True)

        # Layouts
        row_a = QHBoxLayout()
        row_a.addWidget(self.origin_label)
        row_a.addWidget(self.btn_origin)

        row_b = QHBoxLayout()
        row_b.addWidget(self.dest_b_label)
        row_b.addWidget(self.btn_dest_b)

        row_c = QHBoxLayout()
        row_c.addWidget(self.dest_c_label)
        row_c.addWidget(self.btn_dest_c)

        actions = QHBoxLayout()
        actions.addWidget(self.checkbox_use_c)
        actions.addWidget(self.btn_analyze)
        actions.addWidget(self.btn_copy)

        layout = QVBoxLayout()
        layout.addLayout(row_a)
        layout.addLayout(row_b)
        layout.addLayout(row_c)
        layout.addLayout(actions)
        layout.addWidget(self.progress)
        layout.addWidget(self.log_area)

        self.setLayout(layout)

    # --------- UI actions ---------

    def select_origin(self):
        folder = QFileDialog.getExistingDirectory(self, "Seleziona origine (A)")
        if folder:
            self.origin = folder
            self.origin_label.setText(f"Origine A: {folder}")

    def select_dest_b(self):
        folder = QFileDialog.getExistingDirectory(self, "Seleziona destinazione (B)")
        if folder:
            self.dest_b = folder
            self.dest_b_label.setText(f"Destinazione B: {folder}")

    def select_dest_c(self):
        folder = QFileDialog.getExistingDirectory(self, "Seleziona destinazione alternativa (C)")
        if folder:
            self.dest_c = folder
            self.dest_c_label.setText(f"Destinazione C: {folder}")

    def toggle_use_c(self, state: int):
        self.use_dest_c = bool(state)

    def analyze(self):
        if not self.origin or not self.dest_b:
            QMessageBox.warning(self, "Errore", "Seleziona A (origine) e B (destinazione).")
            return

        self.log_area.clear()
        self.log_buffer.clear()

        missing = backend.compare(self.origin, self.dest_b)
        self.missing_files = sorted(missing)
        count = len(self.missing_files)

        if count == 0:
            self.log_area.append("Nessun file nuovo da copiare (A vs B).")
            self.btn_copy.setEnabled(False)
            self.progress.setMaximum(1)
            self.progress.setValue(0)
            return

        self.log_area.append("File mancanti (A vs B) che possono essere copiati:\n")
        for f in self.missing_files:
            self.log_area.append(f"- {f}")
        self.log_area.append(f"\nTotale: {count} file mancanti.")
        self.btn_copy.setEnabled(True)

        self.progress.setMaximum(count)
        self.progress.setValue(0)

    def start_copy(self):
        if not self.missing_files:
            QMessageBox.information(self, "Info", "Nessun file da copiare.")
            return

        target = self.dest_c if self.use_dest_c else self.dest_b
        if not target:
            QMessageBox.warning(self, "Errore", "Destinazione non selezionata.")
            return

        # Disable UI during copy
        self.toggle_ui(False)

        # Chunked copy recommended for large files
        chunked = True

        self.worker = CopyWorker(self.missing_files, self.origin, target, chunked=chunked)
        self.worker.progress.connect(self.on_progress)
        self.worker.line_log.connect(self.on_line_log)
        self.worker.finished.connect(self.on_finished)
        self.worker.start()

    def on_progress(self, current: int, total: int, message: str):
        self.progress.setMaximum(total)
        self.progress.setValue(current)

    def on_line_log(self, line: str):
        self.log_area.append(line)
        self.log_buffer.append(line)

    def on_finished(self, success_count: int, error_count: int, target_dest: str):
        self.log_area.append(f"\n>>> Copia completata verso: {target_dest}")
        self.log_area.append(f">>> OK: {success_count}, ERRORI: {error_count}")

        # Persist log to file in target destination (timestamped)
        try:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            logfile = os.path.join(target_dest, f"filextransfer_log_{ts}.txt")
            with open(logfile, "w", encoding="utf-8") as f:
                f.write("FileXtransfer log\n")
                f.write(f"Origine (A): {self.origin}\n")
                f.write(f"Destinazione analizzata (B): {self.dest_b}\n")
                f.write(f"Destinazione copia: {target_dest}\n")
                f.write(f"Totale mancanti: {len(self.missing_files)}\n")
                f.write(f"OK: {success_count}, ERRORI: {error_count}\n\n")
                for line in self.log_buffer:
                    f.write(line + "\n")
            self.log_area.append(f">>> Log salvato: {logfile}")
        except Exception as e:
            self.log_area.append(f">>> Errore salvataggio log: {e}")

        # Cleanup and re-enable UI
        self.missing_files = []
        self.log_buffer.clear()
        self.toggle_ui(True)
        self.progress.setValue(0)

    def toggle_ui(self, enabled: bool):
        self.btn_origin.setEnabled(enabled)
        self.btn_dest_b.setEnabled(enabled)
        self.btn_dest_c.setEnabled(enabled)
        self.checkbox_use_c.setEnabled(enabled)
        self.btn_analyze.setEnabled(enabled)
        self.btn_copy.setEnabled(enabled if self.missing_files else False)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = BackupApp()
    window.show()
    sys.exit(app.exec_())
