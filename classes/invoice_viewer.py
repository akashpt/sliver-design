"""
invoice_viewer.py – place in classes/
Renders belt-invoice.pdf page-by-page using PyMuPDF (fitz).
Supports Zoom In / Zoom Out / Reset with buttons and Ctrl+scroll.
"""

import os
import shutil
from pathlib import Path

import fitz  # PyMuPDF
from PyQt5.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QPushButton,
    QLabel,
    QFileDialog,
    QScrollArea,
    QWidget,
    QSizePolicy,
    QProgressDialog, 
)
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QPixmap, QImage, QWheelEvent

from path import INVOICE_PDF

ZOOM_STEP = 0.25
ZOOM_MIN = 0.5
ZOOM_MAX = 4.0
ZOOM_DEFAULT = 0.8  # base zoom (renders crisply at ~110 DPI)


class InvoiceViewer(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Invoice Preview")
        self.setMinimumSize(860, 720)
        self.resize(960, 860)
        self.setModal(True)

        self._pdf_path = Path(INVOICE_PDF).resolve()
        self._zoom = ZOOM_DEFAULT
        self._pages = []  # list of fitz.Page (kept open)
        self._doc = None

        # ── Root Layout ─────────────────────────────
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Toolbar ─────────────────────────────────
        toolbar = QHBoxLayout()
        toolbar.setContentsMargins(14, 8, 14, 8)
        toolbar.setSpacing(8)

        title = QLabel("Invoice Preview")
        title.setStyleSheet("font-weight:600; font-size:14px; color:#722f37;")

        self.status_lbl = QLabel("")
        self.status_lbl.setStyleSheet("font-size:12px; color:#555;")

        # ── Zoom Controls ───────────────────────────
        btn_style = """
            QPushButton {
                background:#f0f0f0; color:#333;
                border:1px solid #ccc; border-radius:5px;
                padding:0 12px; font-size:16px; font-weight:700;
            }
            QPushButton:hover   { background:#ddd; }
            QPushButton:pressed { background:#bbb; }
            QPushButton:disabled { color:#aaa; }
        """

        self.btn_zoom_out = QPushButton("−")
        self.btn_zoom_out.setCursor(Qt.PointingHandCursor)
        self.btn_zoom_out.setFixedHeight(34)
        self.btn_zoom_out.setFixedWidth(38)
        self.btn_zoom_out.setStyleSheet(btn_style)
        self.btn_zoom_out.setToolTip("Zoom Out  (Ctrl + scroll down)")
        self.btn_zoom_out.clicked.connect(self.zoom_out)

        self.zoom_lbl = QLabel(f"{int(ZOOM_DEFAULT * 100)}%")
        self.zoom_lbl.setAlignment(Qt.AlignCenter)
        self.zoom_lbl.setFixedWidth(52)
        self.zoom_lbl.setStyleSheet("font-size:13px; color:#444;")

        self.btn_zoom_in = QPushButton("+")
        self.btn_zoom_in.setCursor(Qt.PointingHandCursor)
        self.btn_zoom_in.setFixedHeight(34)
        self.btn_zoom_in.setFixedWidth(38)
        self.btn_zoom_in.setStyleSheet(btn_style)
        self.btn_zoom_in.setToolTip("Zoom In  (Ctrl + scroll up)")
        self.btn_zoom_in.clicked.connect(self.zoom_in)

        self.btn_reset = QPushButton("⟳ Reset")
        self.btn_reset.setCursor(Qt.PointingHandCursor)
        self.btn_reset.setFixedHeight(34)
        self.btn_reset.setStyleSheet(btn_style)
        self.btn_reset.setToolTip("Reset Zoom")
        self.btn_reset.clicked.connect(self.zoom_reset)

        # ── Download / Close ────────────────────────
        self.download_btn = QPushButton("⬇  Download PDF")
        self.download_btn.setCursor(Qt.PointingHandCursor)
        self.download_btn.setFixedHeight(34)
        self.download_btn.setEnabled(False)
        self.download_btn.setStyleSheet(
            """
            QPushButton {
                background:#722f37; color:white;
                border:none; border-radius:6px;
                padding:0 18px; font-size:13px; font-weight:600;
            }
            QPushButton:hover   { background:#8b3a44; }
            QPushButton:pressed { background:#5c2430; }
        """
        )
        self.download_btn.clicked.connect(self.download_pdf)

        close_btn = QPushButton("✕  Close")
        close_btn.setCursor(Qt.PointingHandCursor)
        close_btn.setFixedHeight(34)
        close_btn.setStyleSheet(
            """
            QPushButton {
                background:#eeeeee; color:#333;
                border:none; border-radius:6px; padding:0 14px;
            }
            QPushButton:hover { background:#dddddd; }
        """
        )
        close_btn.clicked.connect(self.close)

        toolbar.addWidget(title)
        toolbar.addStretch()
        toolbar.addWidget(self.status_lbl)
        toolbar.addSpacing(10)
        toolbar.addWidget(self.btn_zoom_out)
        toolbar.addWidget(self.zoom_lbl)
        toolbar.addWidget(self.btn_zoom_in)
        toolbar.addWidget(self.btn_reset)
        toolbar.addSpacing(10)
        toolbar.addWidget(self.download_btn)
        toolbar.addWidget(close_btn)

        # ── Divider ────────────────────────────────
        divider = QLabel()
        divider.setFixedHeight(2)
        divider.setStyleSheet("background:#722f37;")

        # ── Scroll Area ────────────────────────────
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("background:#606060; border:none;")

        # Override wheelEvent on viewport for Ctrl+scroll zoom
        self.scroll.viewport().wheelEvent = self._wheel_event

        self.pages_widget = QWidget()
        self.pages_widget.setStyleSheet("background:#606060;")
        self.pages_layout = QVBoxLayout(self.pages_widget)
        self.pages_layout.setAlignment(Qt.AlignHCenter)
        self.pages_layout.setSpacing(12)
        self.pages_layout.setContentsMargins(20, 20, 20, 20)
        self.scroll.setWidget(self.pages_widget)

        # ── Assemble ───────────────────────────────
        root.addLayout(toolbar)
        root.addWidget(divider)
        root.addWidget(self.scroll)

        self._load_pdf()
        self._render_pages()

    # ------------------------------------------------
    # Load PDF document (keep open for re-renders)
    # ------------------------------------------------
    def _load_pdf(self):
        if not self._pdf_path.exists():
            self.status_lbl.setText("❌ File not found")
            return
        try:
            self._doc = fitz.open(str(self._pdf_path))
        except Exception as e:
            self.status_lbl.setText(f"❌ Open error: {e}")

    # ------------------------------------------------
    # Render / Re-render all pages at current zoom
    # ------------------------------------------------
    def _render_pages(self):
        if self._doc is None:
            err = QLabel(f"❌ PDF not found:\n{self._pdf_path}")
            err.setStyleSheet("color:red; font-size:14px; padding:40px;")
            err.setAlignment(Qt.AlignCenter)
            self.pages_layout.addWidget(err)
            return

        # Clear previous page labels
        while self.pages_layout.count():
            item = self.pages_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        try:
            mat = fitz.Matrix(self._zoom * 2, self._zoom * 2)
            total = len(self._doc)

            for page in self._doc:
                pix = page.get_pixmap(matrix=mat, alpha=False)
                img = QImage(
                    pix.samples,
                    pix.width,
                    pix.height,
                    pix.stride,
                    QImage.Format_RGB888,
                )
                qpix = QPixmap.fromImage(img)

                lbl = QLabel()
                lbl.setPixmap(qpix)
                lbl.setAlignment(Qt.AlignCenter)
                lbl.setStyleSheet("background:white; border:1px solid #ccc;")
                lbl.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
                lbl.setFixedSize(qpix.size())
                self.pages_layout.addWidget(lbl, alignment=Qt.AlignHCenter)

            self.status_lbl.setText(f"Ready  ({total} page{'s' if total > 1 else ''})")
            self.download_btn.setEnabled(True)
            self._update_zoom_ui()

        except Exception as e:
            err = QLabel(f"❌ Render error:\n{e}")
            err.setStyleSheet("color:red; font-size:13px; padding:40px;")
            err.setAlignment(Qt.AlignCenter)
            self.pages_layout.addWidget(err)
            self.status_lbl.setText("❌ Render error")

    # ------------------------------------------------
    # Zoom helpers
    # ------------------------------------------------
    def _update_zoom_ui(self):
        self.zoom_lbl.setText(f"{int(self._zoom * 100)}%")
        self.btn_zoom_in.setEnabled(self._zoom < ZOOM_MAX)
        self.btn_zoom_out.setEnabled(self._zoom > ZOOM_MIN)

    def zoom_in(self):
        if self._zoom < ZOOM_MAX:
            self._zoom = min(ZOOM_MAX, round(self._zoom + ZOOM_STEP, 2))
            self._render_pages()

    def zoom_out(self):
        if self._zoom > ZOOM_MIN:
            self._zoom = max(ZOOM_MIN, round(self._zoom - ZOOM_STEP, 2))
            self._render_pages()

    def zoom_reset(self):
        self._zoom = ZOOM_DEFAULT
        self._render_pages()

    # ------------------------------------------------
    # Ctrl + Mouse Wheel → zoom
    # ------------------------------------------------
    def _wheel_event(self, event: QWheelEvent):
        if event.modifiers() & Qt.ControlModifier:
            if event.angleDelta().y() > 0:
                self.zoom_in()
            else:
                self.zoom_out()
        else:
            # Normal scroll — pass to scroll area
            QScrollArea.wheelEvent(self.scroll, event)

    # ------------------------------------------------
    # Download PDF
    # ------------------------------------------------
    def download_pdf(self):

        save_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Invoice as PDF",
            "TEXA_Invoice.pdf",
            "PDF Files (*.pdf)",
        )

        if not save_path:
            self.status_lbl.setText("❌ Download cancelled")
            return

        try:
            src = self._pdf_path
            dst = Path(save_path)

            # ---- Auto rename if exists ----
            if dst.exists():
                base = dst.stem
                suffix = dst.suffix
                parent = dst.parent

                i = 1
                while True:
                    new_name = parent / f"{base}({i}){suffix}"
                    if not new_name.exists():
                        dst = new_name
                        break
                    i += 1

            file_size = src.stat().st_size

            progress = QProgressDialog(
                "Downloading Invoice...",
                "Cancel",
                0,
                100,
                self,
            )
            progress.setWindowTitle("Downloading")
            progress.setWindowModality(Qt.WindowModal)
            progress.setMinimumDuration(0)
            progress.setValue(0)

            copied = 0
            chunk_size = 1024 * 1024

            with open(src, "rb") as fsrc, open(dst, "wb") as fdst:
                while True:

                    if progress.wasCanceled():
                        fdst.close()
                        dst.unlink(missing_ok=True)
                        self.status_lbl.setText("❌ Download cancelled")
                        return

                    chunk = fsrc.read(chunk_size)
                    if not chunk:
                        break

                    fdst.write(chunk)
                    copied += len(chunk)

                    percent = int((copied / file_size) * 100)
                    progress.setValue(percent)

            progress.setValue(100)
            self.status_lbl.setText(f"✅ Saved: {dst.name}")

        except Exception as e:
            self.status_lbl.setText(f"❌ Save failed: {e}")
    # ------------------------------------------------
    # Close — release PDF document
    # ------------------------------------------------
    def closeEvent(self, event):
        if self._doc:
            self._doc.close()
            self._doc = None
        super().closeEvent(event)
