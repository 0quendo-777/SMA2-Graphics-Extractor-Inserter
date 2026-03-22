"""
    SMA2 Graphics Extractor / Inserter (MVP)

    This is a simple GUI for extracting and inserting graphics files into a SMA2 ROM.
    It uses the binptrs.txt file to determine the offsets and lengths of the graphics files.
    By Oquendo 20/03/2026 :D
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional

from PySide6 import QtCore, QtGui, QtWidgets

import struct
from pathlib import Path
from typing import List
from PySide6 import QtCore


def resource_path(relative_path: str) -> str:
    """
    Resolve paths both when running from source and when bundled by PyInstaller.
    """
    # PyInstaller (onefile/onedir) usa sys._MEIPASS para apuntar al directorio temporal
    # o interno donde mete recursos empaquetados.
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        p = Path(meipass) / relative_path
        if p.exists():
            return str(p)

    # Fallback: cuando es onedir, normalmente hay una carpeta "_internal" junto al .exe.
    exe_dir = Path(sys.executable).resolve().parent
    candidates = [
        exe_dir / relative_path,
        exe_dir / "_internal" / relative_path,
        exe_dir.parent / relative_path,
        exe_dir.parent / "_internal" / relative_path,
    ]
    for c in candidates:
        if c.exists():
            return str(c)

    # Dev mode (source tree)
    return str(Path(__file__).resolve().parent / relative_path)


def apply_dark_theme(app: QtWidgets.QApplication) -> None:
    # Lightweight dark theme (no extra dependency).
    app.setStyleSheet(
        """
        QWidget { background-color: #1e1e1e; color: #d4d4d4; }
        QPlainTextEdit, QTextEdit, QLineEdit, QTextBrowser { background-color: #252526; color: #d4d4d4; border: 1px solid #3c3c3c; }
        QPushButton { background-color: #333333; color: #d4d4d4; border: 1px solid #3c3c3c; padding: 6px 10px; border-radius: 6px; }
        QPushButton:hover { background-color: #3a3a3a; }
        QPushButton:disabled { color: #888888; border-color: #444444; background-color: #2a2a2a; }
        QComboBox, QTreeWidget, QListWidget, QTableWidget, QSpinBox, QDoubleSpinBox, QSlider {
            background-color: #252526; color: #d4d4d4; border: 1px solid #3c3c3c;
        }
        QTreeWidget::item { height: 24px; }
        QTreeWidget::item:selected { background: #0e639c; color: #ffffff; }
        QHeaderView::section { background-color: #2d2d2d; color: #d4d4d4; border: 1px solid #3c3c3c; padding: 4px; }
        QProgressBar { border: 1px solid #3c3c3c; background-color: #252526; border-radius: 6px; text-align: center; }
        QProgressBar::chunk { background-color: #0e639c; }
        QCheckBox { spacing: 6px; }
        QCheckBox::indicator { width: 16px; height: 16px; }
        """
    )

    pal = QtGui.QPalette()
    pal.setColor(QtGui.QPalette.Window, QtGui.QColor("#1e1e1e"))
    pal.setColor(QtGui.QPalette.Base, QtGui.QColor("#252526"))
    pal.setColor(QtGui.QPalette.Text, QtGui.QColor("#d4d4d4"))
    pal.setColor(QtGui.QPalette.Button, QtGui.QColor("#333333"))
    pal.setColor(QtGui.QPalette.ButtonText, QtGui.QColor("#d4d4d4"))
    pal.setColor(QtGui.QPalette.Highlight, QtGui.QColor("#0e639c"))
    pal.setColor(QtGui.QPalette.HighlightedText, QtGui.QColor("#ffffff"))
    app.setPalette(pal)


@dataclass(frozen=True)
class BinPtrEntry:
    startptr: int
    length: int  # resolved length; if source was "None" we resolve with default
    out_path: str  # relative path like Graphics/....bin

    @property
    def file_offset(self) -> int:
        # Matches extraer.py logic: startptr is an in-ROM address and maps to file offset.
        return self.startptr & 0x01FFFFFF


class BinPtrMap:
    def __init__(self, binptrs_path: Path):
        self.binptrs_path = binptrs_path

    def parse(self, *, default_len_if_unknown: int = 0x2000) -> List[BinPtrEntry]:
        if not self.binptrs_path.exists():
            raise FileNotFoundError(f"Missing {self.binptrs_path}")

        ptrmap: List[BinPtrEntry] = []
        # We keep a mutable placeholder list for entries created with unknown length.
        pending_lengths: List[Optional[int]] = []

        fillnext = False
        with self.binptrs_path.open("r", encoding="utf-8") as f:
            for line in f:
                rawdata = line.strip().split()
                if not rawdata:
                    continue
                try:
                    startptr = int(rawdata[0], 16)
                except ValueError:
                    continue

                if fillnext and ptrmap:
                    # Next "startptr" line ends the previous unknown-length entry.
                    endptr = startptr
                    prev_start = ptrmap[-1].startptr
                    length = endptr - prev_start
                    if length > 0:
                        pending_lengths[-1] = length
                    fillnext = False

                if len(rawdata) >= 3:
                    endptr = int(rawdata[1], 16)
                    length = endptr - startptr
                    out_path = rawdata[2]
                    ptrmap.append(BinPtrEntry(startptr=startptr, length=length, out_path=out_path))
                    pending_lengths.append(length)
                elif len(rawdata) == 2:
                    out_path = rawdata[1]
                    ptrmap.append(BinPtrEntry(startptr=startptr, length=default_len_if_unknown, out_path=out_path))
                    pending_lengths.append(None)
                    fillnext = True

        # Resolve any unknown-length entries that never got filled.
        resolved: List[BinPtrEntry] = []
        for i, e in enumerate(ptrmap):
            length = pending_lengths[i]
            if length is None:
                resolved.append(e)  # already defaulted
            else:
                resolved.append(BinPtrEntry(startptr=e.startptr, length=length, out_path=e.out_path))

        return resolved


def filter_entries(entries: Iterable[BinPtrEntry], mode: str) -> List[BinPtrEntry]:
    if mode == "graphics":
        return [e for e in entries if e.out_path.startswith("Graphics/")]
    if mode == "graphics_tilemaps":
        return [e for e in entries if e.out_path.startswith("Graphics/") or e.out_path.startswith("Tilemaps/")]
    if mode == "all":
        return list(entries)
    raise ValueError(f"Unknown filter mode: {mode}")


class ExtractWorker(QtCore.QThread):
    log = QtCore.Signal(str)
    failed = QtCore.Signal(str)
    done = QtCore.Signal()

    def __init__(self, *, rom_path: Path, entries: List[BinPtrEntry], output_root: Path, parent=None):
        super().__init__(parent)
        self.rom_path = rom_path
        self.entries = entries
        self.output_root = output_root
        self._abort = False

    def abort(self) -> None:
        self._abort = True

    def run(self) -> None:
        try:
            if not self.rom_path.exists():
                raise FileNotFoundError(f"ROM not found: {self.rom_path}")

            rom_size = self.rom_path.stat().st_size
            self.output_root.mkdir(parents=True, exist_ok=True)

            with self.rom_path.open("rb") as f:
                for idx, entry in enumerate(self.entries, start=1):
                    if self._abort:
                        return
                    off = entry.file_offset
                    end = off + entry.length
                    if off < 0 or end > rom_size:
                        raise ValueError(
                            f"Entry out of ROM bounds: {entry.out_path} off=0x{off:X} len=0x{entry.length:X}"
                        )

                    f.seek(off)
                    data = f.read(entry.length)
                    if len(data) != entry.length:
                        raise IOError(
                            f"Read short for {entry.out_path}: expected {entry.length}, got {len(data)}"
                        )

                    out_path = self.output_root / entry.out_path
                    out_path.parent.mkdir(parents=True, exist_ok=True)
                    out_path.write_bytes(data)
                    self.log.emit(
                        f"[{idx}/{len(self.entries)}] Extracted: {entry.out_path} ({entry.length} bytes)"
                    )

        except Exception as e:
            self.failed.emit(str(e))
            return
        self.done.emit()


class InsertWorker(QtCore.QThread):
    log = QtCore.Signal(str)
    failed = QtCore.Signal(str)
    done = QtCore.Signal()

    def __init__(
        self,
        *,
        rom_path: Path,
        entries: List['BinPtrEntry'], # Keeping your original entry type
        output_root: Path,
        new_rom_path: Path,
        parent=None,
    ):
        super().__init__(parent)
        self.rom_path = rom_path
        self.entries = entries
        self.output_root = output_root
        self.new_rom_path = new_rom_path

    def run(self) -> None:
        try:
            if not self.rom_path.exists():
                raise FileNotFoundError(f"ROM not found: {self.rom_path}")

            if self.new_rom_path.resolve() == self.rom_path.resolve():
                raise ValueError("New ROM path cannot be the same as the input ROM.")

            rom_data = bytearray(self.rom_path.read_bytes())
            
            # 1. Sort entries by their original offset.
            # This is crucial so we shift data left-to-right correctly 
            # based on your binptrs.txt order.
            sorted_entries = sorted(self.entries, key=lambda e: e.file_offset)
            
            shift_delta = 0

            for idx, entry in enumerate(sorted_entries, start=1):
                src_path = self.output_root / entry.out_path
                if not src_path.exists():
                    raise FileNotFoundError(f"Missing extracted file for insertion: {src_path}")

                data = src_path.read_bytes()
                new_length = len(data)
                
                # Apply the current shift to find where the data actually goes now
                current_off = entry.file_offset + shift_delta
                current_end = current_off + entry.length
                
                if current_off < 0 or current_off > len(rom_data):
                    raise ValueError(
                        f"Entry out of ROM bounds: {entry.out_path} off=0x{current_off:X} len=0x{entry.length:X}"
                    )

                # 2. Insert the data. Python bytearray automatically resizes 
                # if the slice bounds don't match the new data size.
                rom_data[current_off:current_end] = data
                
                # 3. Handle Pointers if the data shifted
                if shift_delta != 0:
                    # GBA ROMs map to memory at 0x08000000
                    # We pack the old and new addresses as 4-byte little-endian integers
                    old_gba_ptr = struct.pack('<I', 0x08000000 + entry.file_offset)
                    new_gba_ptr = struct.pack('<I', 0x08000000 + current_off)
                    
                    # Search and replace the pointers in the ROM
                    occurrences = rom_data.count(old_gba_ptr)
                    if occurrences > 0:
                        # bytearray replace creates a new bytearray, so we reassign it
                        rom_data = bytearray(rom_data.replace(old_gba_ptr, new_gba_ptr))
                        self.log.emit(f"    -> Updated {occurrences} pointers from 0x{0x08000000 + entry.file_offset:08X} to 0x{0x08000000 + current_off:08X}")

                # 4. Update the shift delta for the next file
                size_difference = new_length - entry.length
                shift_delta += size_difference

                # Log the status
                if size_difference != 0:
                    self.log.emit(f"[{idx}/{len(self.entries)}] Inserted (Resized {size_difference:+} bytes): {entry.out_path}")
                else:
                    self.log.emit(f"[{idx}/{len(self.entries)}] Inserted: {entry.out_path}")

            # 5. Save the final ROM
            self.new_rom_path.parent.mkdir(parents=True, exist_ok=True)
            self.new_rom_path.write_bytes(rom_data)
            self.log.emit(f"[OK] Saved modified ROM to: {self.new_rom_path}")

        except Exception as e:
            self.failed.emit(str(e))
            return
            
        self.done.emit()


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SMA2 Graphics Extractor / Inserter (MVP)")
        # Taskbar + window icon (no external file dependency).
        self.setWindowIcon(self.style().standardIcon(QtWidgets.QStyle.SP_ComputerIcon))
        self.resize(1050, 720)

        self.entries_all: List[BinPtrEntry] = []
        self.entries_filtered: List[BinPtrEntry] = []
        self._worker: Optional[QtCore.QThread] = None

        # UI
        root = QtWidgets.QWidget()
        self.setCentralWidget(root)
        lay = QtWidgets.QVBoxLayout(root)

        form = QtWidgets.QGridLayout()
        lay.addLayout(form)

        self.rom_line = QtWidgets.QLineEdit()
        self.rom_line.setPlaceholderText("sma2.gba path")
        self.rom_browse = QtWidgets.QPushButton("Select ROM")
        self.rom_browse.clicked.connect(self.on_browse_rom)

        self.out_line = QtWidgets.QLineEdit()
        self.out_line.setPlaceholderText("Output folder (e.g. data)")
        self.out_browse = QtWidgets.QPushButton("Choose folder")
        self.out_browse.clicked.connect(self.on_browse_output)

        self.filter_combo = QtWidgets.QComboBox()
        self.filter_combo.addItems(
            [
                "Graphics only",
                "Graphics + Tilemaps",
                "All binptrs entries",
            ]
        )
        self.filter_combo.setCurrentIndex(0)
        self.filter_combo.currentIndexChanged.connect(self.reload_entries)

        form.addWidget(QtWidgets.QLabel("ROM:"), 0, 0)
        form.addWidget(self.rom_line, 0, 1)
        form.addWidget(self.rom_browse, 0, 2)

        form.addWidget(QtWidgets.QLabel("Output:"), 1, 0)
        form.addWidget(self.out_line, 1, 1)
        form.addWidget(self.out_browse, 1, 2)

        form.addWidget(QtWidgets.QLabel("Filter:"), 2, 0)
        form.addWidget(self.filter_combo, 2, 1, 1, 2)

        self.tree = QtWidgets.QTreeWidget()
        self.tree.setColumnCount(6)
        self.tree.setHeaderLabels(["Use", "Path", "Start", "Len", "Status", "Current size"])
        self.tree.setRootIsDecorated(False)
        self.tree.itemChanged.connect(self.on_tree_item_changed)
        lay.addWidget(self.tree, 1)

        btns = QtWidgets.QHBoxLayout()
        lay.addLayout(btns)

        self.extract_selected_btn = QtWidgets.QPushButton("Extract selected")
        self.extract_all_btn = QtWidgets.QPushButton("Extract all")
        self.insert_selected_btn = QtWidgets.QPushButton("Insert selected (new ROM)")
        self.refresh_status_btn = QtWidgets.QPushButton("Refresh status")

        self.extract_selected_btn.clicked.connect(self.on_extract_selected)
        self.extract_all_btn.clicked.connect(self.on_extract_all)
        self.insert_selected_btn.clicked.connect(self.on_insert_selected)
        self.refresh_status_btn.clicked.connect(self.reload_entries)

        btns.addWidget(self.extract_selected_btn)
        btns.addWidget(self.extract_all_btn)
        btns.addWidget(self.insert_selected_btn)
        btns.addStretch(1)
        btns.addWidget(self.refresh_status_btn)

        self.log = QtWidgets.QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(2000)
        lay.addWidget(self.log, 0)

        # Keep routes empty so the user explicitly selects them.
        self.rom_line.setText("")
        self.out_line.setText("")

        # Load entries from binptrs.txt immediately.
        self.reload_entries()

    def _filter_mode(self) -> str:
        idx = self.filter_combo.currentIndex()
        if idx == 0:
            return "graphics"
        if idx == 1:
            return "graphics_tilemaps"
        if idx == 2:
            return "all"
        return "graphics"

    def log_line(self, msg: str) -> None:
        self.log.appendPlainText(msg)

    def set_busy(self, busy: bool) -> None:
        for b in (
            self.extract_selected_btn,
            self.extract_all_btn,
            self.insert_selected_btn,
            self.refresh_status_btn,
        ):
            b.setEnabled(not busy)
        self.rom_browse.setEnabled(not busy)
        self.out_browse.setEnabled(not busy)
        self.filter_combo.setEnabled(not busy)
        self.tree.setEnabled(not busy)
        QtWidgets.QApplication.processEvents()

    def on_browse_rom(self) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Select sma2.gba", "", "GBA ROM (*.gba);;All files (*)"
        )
        if path:
            self.rom_line.setText(path)
            self.reload_entries()

    def on_browse_output(self) -> None:
        path = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Select output folder", self.out_line.text()
        )
        if path:
            self.out_line.setText(path)
            self.reload_entries()

    def reload_entries(self) -> None:
        self.tree.blockSignals(True)
        self.tree.clear()

        binptrs_path = Path(resource_path("binptrs.txt"))
        try:
            self.entries_all = BinPtrMap(binptrs_path).parse()
        except Exception as e:
            self.entries_all = []
            self.log_line(f"[ERROR] Could not read binptrs.txt: {e}")
            self.tree.blockSignals(False)
            return

        mode = self._filter_mode()
        self.entries_filtered = filter_entries(self.entries_all, mode=mode)
        mode_human = {
            "graphics": "Graphics only",
            "graphics_tilemaps": "Graphics + Tilemaps",
            "all": "All binptrs entries",
        }.get(mode, mode)

        out_text = self.out_line.text().strip()
        out_root: Optional[Path] = None
        if out_text:
            out_root = Path(out_text).resolve()

        rom_size = None
        if self.rom_line.text().strip():
            rom_path = Path(self.rom_line.text().strip())
            if rom_path.exists():
                try:
                    rom_size = rom_path.stat().st_size
                except OSError:
                    rom_size = None

        # Populate tree; default checkbox is checked if the file exists and matches size.
        for i, entry in enumerate(self.entries_filtered):
            if out_root is None:
                status = "No output selected"
                cur_size = -1
                checked = False
            else:
                out_path = out_root / entry.out_path
                if out_path.exists():
                    cur_size = out_path.stat().st_size
                    if cur_size == entry.length:
                        status = "OK"
                        checked = True
                    else:
                        status = "Size mismatch"
                        checked = False
                else:
                    status = "Missing"
                    cur_size = -1
                    checked = False

            if rom_size is not None:
                # Extra info for "out of bounds" entries.
                end = entry.file_offset + entry.length
                if entry.file_offset < 0 or end > rom_size:
                    status = f"ROM bounds!"
                    checked = False

            item = QtWidgets.QTreeWidgetItem(self.tree)
            item.setFlags(item.flags() | QtCore.Qt.ItemIsUserCheckable | QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)
            item.setCheckState(0, QtCore.Qt.Checked if checked else QtCore.Qt.Unchecked)
            item.setText(1, entry.out_path)
            item.setText(2, f"0x{entry.startptr:08X}")
            item.setText(3, f"0x{entry.length:X}")
            item.setText(4, status)
            item.setText(5, "-" if cur_size < 0 else str(cur_size))
            item.setData(0, QtCore.Qt.UserRole, i)

        self.tree.blockSignals(False)
        self.log_line(f"[OK] Loaded {len(self.entries_filtered)} entries ({mode_human}).")

    def on_tree_item_changed(self, item: QtWidgets.QTreeWidgetItem, column: int) -> None:
        # No-op for now; we keep it for potential future logic.
        _ = item
        _ = column

    def get_checked_entries(self) -> List[BinPtrEntry]:
        checked: List[BinPtrEntry] = []
        for i in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(i)
            if item.checkState(0) == QtCore.Qt.Checked:
                idx = int(item.data(0, QtCore.Qt.UserRole))
                checked.append(self.entries_filtered[idx])
        return checked

    def selected_count(self) -> int:
        return sum(1 for i in range(self.tree.topLevelItemCount()) if self.tree.topLevelItem(i).checkState(0) == QtCore.Qt.Checked)

    def on_extract_selected(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return

        rom_path_str = self.rom_line.text().strip()
        if not rom_path_str:
            QtWidgets.QMessageBox.warning(self, "Missing ROM", "Please select a ROM file first.")
            return
        rom_path = Path(rom_path_str)
        if not rom_path.exists():
            QtWidgets.QMessageBox.warning(self, "ROM does not exist", f"Does not exist: {rom_path}")
            return

        entries = self.get_checked_entries()
        if not entries:
            QtWidgets.QMessageBox.information(
                self, "Nothing selected", "Select at least one entry in the list."
            )
            return

        out_text = self.out_line.text().strip()
        if not out_text:
            QtWidgets.QMessageBox.warning(self, "Missing output", "Please select an output folder first.")
            return
        out_root = Path(out_text)

        self.log_line(f"[RUN] Extracting ({len(entries)} entries)...")
        self.set_busy(True)
        self._worker = ExtractWorker(rom_path=rom_path, entries=entries, output_root=out_root, parent=self)
        self._worker.log.connect(self.log_line)
        self._worker.failed.connect(self.on_worker_failed)
        self._worker.done.connect(self.on_extract_done)
        self._worker.start()

    def on_extract_all(self) -> None:
        # Check all entries.
        for i in range(self.tree.topLevelItemCount()):
            self.tree.topLevelItem(i).setCheckState(0, QtCore.Qt.Checked)
        self.on_extract_selected()

    def on_extract_done(self) -> None:
        self.set_busy(False)
        self.log_line("[DONE] Extraction finished.")
        self.reload_entries()

    def on_insert_selected(self) -> None:
        if self._worker is not None and self._worker.isRunning():
            return

        rom_path_str = self.rom_line.text().strip()
        if not rom_path_str:
            QtWidgets.QMessageBox.warning(self, "Missing ROM", "Please select a ROM file first.")
            return
        rom_path = Path(rom_path_str)
        if not rom_path.exists():
            QtWidgets.QMessageBox.warning(self, "ROM does not exist", f"Does not exist: {rom_path}")
            return

        entries = self.get_checked_entries()
        if not entries:
            QtWidgets.QMessageBox.information(
                self, "Nothing selected", "Select at least one entry in the list."
            )
            return

        out_text = self.out_line.text().strip()
        if not out_text:
            QtWidgets.QMessageBox.warning(self, "Missing output", "Please select an output folder first.")
            return
        out_root = Path(out_text)
        default_new = rom_path.with_name(rom_path.stem + "_gfx_edit.gba")
        new_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Save modified ROM",
            str(default_new),
            "GBA ROM (*.gba);;All files (*)",
        )
        if not new_path:
            return

        self.log_line(f"[RUN] Inserting ({len(entries)} entries) -> {new_path}")
        self.set_busy(True)
        self._worker = InsertWorker(
            rom_path=rom_path,
            entries=entries,
            output_root=out_root,
            new_rom_path=Path(new_path),
            parent=self,
        )
        self._worker.log.connect(self.log_line)
        self._worker.failed.connect(self.on_worker_failed)
        self._worker.done.connect(self.on_insert_done)
        self._worker.start()

    def on_insert_done(self) -> None:
        self.set_busy(False)
        self.log_line("[DONE] Insertion finished.")

    def on_worker_failed(self, message: str) -> None:
        self.set_busy(False)
        self.log_line(f"[ERROR] {message}")
        QtWidgets.QMessageBox.critical(self, "Error", message)


def main() -> int:
    app = QtWidgets.QApplication(sys.argv)
    apply_dark_theme(app)

    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

