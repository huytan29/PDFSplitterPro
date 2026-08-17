"""Dialog for combining complete PDF files or an arbitrary page sequence."""

from __future__ import annotations

import os

import fitz
from pypdf import PdfReader
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
)

from app.services.splitter import merge_pdf_page_sequence, parse_page_selection


class PdfPagePreviewDialog(QDialog):
    """Browse a sequence of pages from one or many PDF files."""

    def __init__(self, title, page_sequence, parent=None, language="vi"):
        super().__init__(parent)
        self.language = "en" if language == "en" else "vi"
        self.page_sequence = list(page_sequence)
        self.documents = {}
        self._syncing_page = False

        self.setWindowTitle(title)
        self.resize(1120, 760)
        self.setMinimumSize(760, 520)
        self._build_ui()
        self._build_thumbnails()

    def t(self, vietnamese, english):
        return english if self.language == "en" else vietnamese

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(8)

        self.summary_label = QLabel()
        self.summary_label.setStyleSheet("font-size: 15px; font-weight: 700;")
        root.addWidget(self.summary_label)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter, 1)

        self.thumbnail_list = QListWidget()
        self.thumbnail_list.setViewMode(QListWidget.ViewMode.IconMode)
        self.thumbnail_list.setFlow(QListWidget.Flow.TopToBottom)
        self.thumbnail_list.setWrapping(False)
        self.thumbnail_list.setIconSize(QPixmap(120, 150).size())
        self.thumbnail_list.setGridSize(QPixmap(165, 190).size())
        self.thumbnail_list.setMinimumWidth(180)
        self.thumbnail_list.setMaximumWidth(240)
        self.thumbnail_list.setSpacing(5)
        self.thumbnail_list.currentRowChanged.connect(self.select_page)
        splitter.addWidget(self.thumbnail_list)

        preview_panel = QScrollArea()
        preview_panel.setWidgetResizable(False)
        preview_panel.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_panel.setStyleSheet("QScrollArea { background: #202020; border: 1px solid #4a4a4a; }")
        self.preview_label = QLabel()
        self.preview_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_panel.setWidget(self.preview_label)
        splitter.addWidget(preview_panel)
        splitter.setSizes([220, 900])

        controls = QHBoxLayout()
        self.btn_previous = QPushButton(self.t("◀ Trang trước", "◀ Previous"))
        self.btn_next = QPushButton(self.t("Trang sau ▶", "Next ▶"))
        self.page_spin = QSpinBox()
        self.page_spin.setMinimum(1)
        self.page_spin.setMaximum(max(1, len(self.page_sequence)))
        self.page_spin.valueChanged.connect(self.select_page_number)
        self.page_details = QLabel()
        self.page_details.setStyleSheet("color: #9ab6ca;")
        self.btn_previous.clicked.connect(lambda: self.page_spin.setValue(self.page_spin.value() - 1))
        self.btn_next.clicked.connect(lambda: self.page_spin.setValue(self.page_spin.value() + 1))
        controls.addWidget(self.btn_previous)
        controls.addWidget(self.page_spin)
        controls.addWidget(self.btn_next)
        controls.addWidget(self.page_details, 1)
        root.addLayout(controls)

    def pdf_document(self, path):
        document = self.documents.get(path)
        if document is None:
            document = fitz.open(path)
            self.documents[path] = document
        return document

    def render_page(self, path, page_index, scale):
        page = self.pdf_document(path).load_page(page_index)
        pixmap = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        image = QImage(
            pixmap.samples,
            pixmap.width,
            pixmap.height,
            pixmap.stride,
            QImage.Format.Format_RGB888,
        ).copy()
        return QPixmap.fromImage(image)

    def _build_thumbnails(self):
        self.thumbnail_list.blockSignals(True)
        self.thumbnail_list.clear()
        for position, (path, page_index) in enumerate(self.page_sequence, start=1):
            thumbnail = self.render_page(path, page_index, 0.20)
            item = QListWidgetItem(
                QIcon(thumbnail),
                self.t(
                    f"Trang {position}\n{os.path.basename(path)} · tr. {page_index + 1}",
                    f"Page {position}\n{os.path.basename(path)} · p. {page_index + 1}",
                ),
            )
            self.thumbnail_list.addItem(item)
        self.thumbnail_list.blockSignals(False)

        page_count = len(self.page_sequence)
        self.summary_label.setText(
            self.t(
                f"XEM TRƯỚC {page_count} TRANG", f"PREVIEWING {page_count} PAGES"
            )
        )
        if page_count:
            self.thumbnail_list.setCurrentRow(0)
            self.select_page(0)
        else:
            self.preview_label.setText(self.t("Không có trang để xem.", "No pages to preview."))
            self.btn_previous.setEnabled(False)
            self.btn_next.setEnabled(False)
            self.page_spin.setEnabled(False)

    def select_page_number(self, page_number):
        if self._syncing_page:
            return
        self.thumbnail_list.setCurrentRow(page_number - 1)

    def select_page(self, row):
        if not 0 <= row < len(self.page_sequence):
            return
        self._syncing_page = True
        self.page_spin.setValue(row + 1)
        self._syncing_page = False
        path, page_index = self.page_sequence[row]
        pixmap = self.render_page(path, page_index, 1.35)
        self.preview_label.setPixmap(pixmap)
        self.preview_label.resize(pixmap.size())
        self.page_details.setText(
            self.t(
                f"PDF nguồn: {os.path.basename(path)} | Trang gốc: {page_index + 1}",
                f"Source PDF: {os.path.basename(path)} | Original page: {page_index + 1}",
            )
        )
        self.btn_previous.setEnabled(row > 0)
        self.btn_next.setEnabled(row < len(self.page_sequence) - 1)

    def closeEvent(self, event):
        for document in self.documents.values():
            document.close()
        self.documents.clear()
        super().closeEvent(event)


class MergePdfDialog(QDialog):
    """Build a PDF from pages from one or more source files."""

    def __init__(self, parent=None, language="vi"):
        super().__init__(parent)
        self.language = "en" if language == "en" else "vi"
        self.sources = []
        self.last_export_path = ""

        self.setWindowTitle(self.t("Ghép nhiều file PDF", "Merge PDF files"))
        self.resize(1120, 650)
        self.setMinimumSize(860, 540)
        self._build_ui()

    def t(self, vietnamese, english):
        return english if self.language == "en" else vietnamese

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        title = QLabel(self.t("GHÉP NHIỀU FILE PDF", "MERGE MULTIPLE PDF FILES"))
        title.setStyleSheet("font-size: 17px; font-weight: 700;")
        root.addWidget(title)

        hint = QLabel(
            self.t(
                "Thêm các PDF, chọn trang cần lấy rồi sắp xếp danh sách đầu ra. "
                "Thứ tự trong danh sách là thứ tự của PDF kết quả.",
                "Add PDFs, choose pages, then arrange the output list. "
                "The list order is the order in the merged PDF.",
            )
        )
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #9ab6ca;")
        root.addWidget(hint)

        content = QHBoxLayout()
        content.setSpacing(10)
        root.addLayout(content, 1)

        source_group = QGroupBox(self.t("1. File PDF nguồn", "1. Source PDF files"))
        source_layout = QVBoxLayout(source_group)
        self.source_list = QListWidget()
        self.source_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.source_list.currentRowChanged.connect(self._update_source_state)
        self.source_list.itemDoubleClicked.connect(self.open_source_preview)
        source_layout.addWidget(self.source_list, 1)

        source_buttons = QHBoxLayout()
        self.btn_add_files = QPushButton(self.t("Thêm PDF", "Add PDF"))
        self.btn_remove_file = QPushButton(self.t("Bỏ file", "Remove file"))
        self.btn_source_up = QPushButton("▲")
        self.btn_source_down = QPushButton("▼")
        self.btn_add_files.clicked.connect(self.add_files)
        self.btn_remove_file.clicked.connect(self.remove_source)
        self.btn_source_up.clicked.connect(lambda: self.move_source(-1))
        self.btn_source_down.clicked.connect(lambda: self.move_source(1))
        for button in (
            self.btn_add_files,
            self.btn_remove_file,
            self.btn_source_up,
            self.btn_source_down,
        ):
            source_buttons.addWidget(button)
        source_layout.addLayout(source_buttons)
        self.btn_preview_source = QPushButton(
            self.t("XEM FILE NGUỒN", "VIEW SOURCE PDF")
        )
        self.btn_preview_source.clicked.connect(self.open_source_preview)
        source_layout.addWidget(self.btn_preview_source)
        content.addWidget(source_group, 1)

        page_group = QGroupBox(self.t("2. Chọn trang từ file đang chọn", "2. Choose pages from selected file"))
        page_layout = QVBoxLayout(page_group)
        self.source_info = QLabel(self.t("Chưa chọn file PDF.", "No PDF file selected."))
        self.source_info.setWordWrap(True)
        self.source_info.setStyleSheet("color: #9ab6ca;")
        page_layout.addWidget(self.source_info)

        self.page_input = QLineEdit()
        self.page_input.setPlaceholderText(
            self.t(
                "Trang cần thêm, ví dụ: 1,3,5 hoặc 1-3 (để trống = tất cả)",
                "Pages to add, e.g. 1,3,5 or 1-3 (blank = all pages)",
            )
        )
        page_layout.addWidget(self.page_input)

        self.btn_add_pages = QPushButton(self.t("Thêm trang đã chọn", "Add selected pages"))
        self.btn_add_all_pages = QPushButton(self.t("Thêm toàn bộ trang", "Add all pages"))
        self.btn_add_all_files = QPushButton(
            self.t("Thêm tất cả file theo thứ tự", "Add all files in order")
        )
        self.btn_add_pages.clicked.connect(self.add_selected_pages)
        self.btn_add_all_pages.clicked.connect(self.add_all_pages_for_source)
        self.btn_add_all_files.clicked.connect(self.add_all_sources)
        page_layout.addWidget(self.btn_add_pages)
        page_layout.addWidget(self.btn_add_all_pages)
        page_layout.addStretch()
        page_layout.addWidget(self.btn_add_all_files)
        content.addWidget(page_group, 1)

        output_group = QGroupBox(self.t("3. Thứ tự trang PDF kết quả", "3. Output PDF page order"))
        output_layout = QVBoxLayout(output_group)
        output_hint = QLabel(
            self.t(
                "Kéo thả hoặc dùng nút lên/xuống để đổi thứ tự từng trang.",
                "Drag pages or use the up/down buttons to change their order.",
            )
        )
        output_hint.setWordWrap(True)
        output_hint.setStyleSheet("color: #9ab6ca;")
        output_layout.addWidget(output_hint)

        self.output_list = QListWidget()
        self.output_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.output_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.output_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.output_list.model().rowsMoved.connect(self.refresh_output_labels)
        self.output_list.itemDoubleClicked.connect(self.open_output_preview)
        output_layout.addWidget(self.output_list, 1)

        output_buttons = QHBoxLayout()
        self.btn_output_up = QPushButton(self.t("▲ Lên", "▲ Up"))
        self.btn_output_down = QPushButton(self.t("Xuống ▼", "Down ▼"))
        self.btn_output_remove = QPushButton(self.t("Bỏ trang", "Remove page"))
        self.btn_output_clear = QPushButton(self.t("Xóa danh sách", "Clear list"))
        self.btn_output_up.clicked.connect(lambda: self.move_output(-1))
        self.btn_output_down.clicked.connect(lambda: self.move_output(1))
        self.btn_output_remove.clicked.connect(self.remove_output_pages)
        self.btn_output_clear.clicked.connect(self.output_list.clear)
        for button in (
            self.btn_output_up,
            self.btn_output_down,
            self.btn_output_remove,
            self.btn_output_clear,
        ):
            output_buttons.addWidget(button)
        output_layout.addLayout(output_buttons)
        preview_buttons = QHBoxLayout()
        self.btn_preview_output = QPushButton(
            self.t("XEM TRƯỚC KẾT QUẢ", "PREVIEW RESULT")
        )
        self.btn_preview_exported = QPushButton(
            self.t("XEM PDF ĐÃ GHÉP", "VIEW MERGED PDF")
        )
        self.btn_preview_output.clicked.connect(self.open_output_preview)
        self.btn_preview_exported.clicked.connect(self.open_exported_preview)
        preview_buttons.addWidget(self.btn_preview_output)
        preview_buttons.addWidget(self.btn_preview_exported)
        output_layout.addLayout(preview_buttons)
        content.addWidget(output_group, 2)

        footer = QHBoxLayout()
        self.output_status = QLabel(self.t("Chưa có trang để ghép.", "No pages selected for merging."))
        self.output_status.setStyleSheet("color: #9ab6ca;")
        self.btn_cancel = QPushButton(self.t("Hủy", "Cancel"))
        self.btn_export = QPushButton(self.t("GHÉP VÀ LƯU PDF", "MERGE AND SAVE PDF"))
        self.btn_export.setMinimumHeight(38)
        self.btn_export.setStyleSheet(
            "QPushButton { background: #153a31; border: 1px solid #31c98a; "
            "border-radius: 8px; color: #d9fff0; font-weight: 700; padding: 0 16px; } "
            "QPushButton:hover { background: #1c5745; }"
        )
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_export.clicked.connect(self.export_pdf)
        footer.addWidget(self.output_status, 1)
        footer.addWidget(self.btn_cancel)
        footer.addWidget(self.btn_export)
        root.addLayout(footer)

        self.output_list.model().rowsInserted.connect(self.update_output_status)
        self.output_list.model().rowsRemoved.connect(self.update_output_status)
        self._update_source_state()

    def add_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            self.t("Chọn các file PDF", "Choose PDF files"),
            "",
            "PDF (*.pdf)",
        )
        if not paths:
            return

        existing = {source["path"] for source in self.sources}
        errors = []
        for path in paths:
            if path in existing:
                continue
            try:
                reader = PdfReader(path)
                if reader.is_encrypted and reader.decrypt("") == 0:
                    raise ValueError(self.t("PDF có mật khẩu", "Password-protected PDF"))
                page_count = len(reader.pages)
                if not page_count:
                    raise ValueError(self.t("PDF không có trang", "PDF has no pages"))
            except Exception as error:
                errors.append(f"{os.path.basename(path)}: {error}")
                continue
            self.sources.append({"path": path, "page_count": page_count})
            existing.add(path)

        self.refresh_sources(select_last=True)
        if errors:
            QMessageBox.warning(
                self,
                self.t("Không thể thêm một số PDF", "Some PDFs could not be added"),
                "\n".join(errors),
            )

    def refresh_sources(self, select_last=False, selected_row=None):
        if selected_row is None:
            selected_row = self.source_list.currentRow()
        self.source_list.blockSignals(True)
        self.source_list.clear()
        for position, source in enumerate(self.sources, start=1):
            item = QListWidgetItem(
                self.t(
                    f"{position}. {os.path.basename(source['path'])}\n{source['page_count']} trang",
                    f"{position}. {os.path.basename(source['path'])}\n{source['page_count']} pages",
                )
            )
            item.setData(Qt.ItemDataRole.UserRole, source["path"])
            self.source_list.addItem(item)
        if self.sources:
            row = len(self.sources) - 1 if select_last else max(0, min(selected_row, len(self.sources) - 1))
            self.source_list.setCurrentRow(row)
        self.source_list.blockSignals(False)
        self._update_source_state()

    def current_source(self):
        row = self.source_list.currentRow()
        return self.sources[row] if 0 <= row < len(self.sources) else None

    def _update_source_state(self, *_):
        source = self.current_source()
        available = source is not None
        self.btn_remove_file.setEnabled(available)
        self.btn_source_up.setEnabled(available and self.source_list.currentRow() > 0)
        self.btn_source_down.setEnabled(
            available and self.source_list.currentRow() < len(self.sources) - 1
        )
        self.btn_add_pages.setEnabled(available)
        self.btn_add_all_pages.setEnabled(available)
        self.btn_preview_source.setEnabled(available)
        self.btn_add_all_files.setEnabled(bool(self.sources))
        if source:
            self.source_info.setText(
                self.t(
                    f"{os.path.basename(source['path'])}: {source['page_count']} trang.",
                    f"{os.path.basename(source['path'])}: {source['page_count']} pages.",
                )
            )
        else:
            self.source_info.setText(self.t("Chưa chọn file PDF.", "No PDF file selected."))

    def remove_source(self):
        row = self.source_list.currentRow()
        if not 0 <= row < len(self.sources):
            return
        path = self.sources.pop(row)["path"]
        for index in range(self.output_list.count() - 1, -1, -1):
            if self.output_list.item(index).data(Qt.ItemDataRole.UserRole)[0] == path:
                self.output_list.takeItem(index)
        self.refresh_sources(selected_row=row)
        self.update_output_status()

    def move_source(self, direction):
        row = self.source_list.currentRow()
        new_row = row + direction
        if not 0 <= row < len(self.sources) or not 0 <= new_row < len(self.sources):
            return
        self.sources[row], self.sources[new_row] = self.sources[new_row], self.sources[row]
        self.refresh_sources(selected_row=new_row)

    def selected_page_numbers(self, source):
        text = self.page_input.text().strip()
        if not text:
            return list(range(1, source["page_count"] + 1))
        return parse_page_selection(text, source["page_count"])

    def add_selected_pages(self):
        source = self.current_source()
        if source is None:
            return
        try:
            page_numbers = self.selected_page_numbers(source)
        except ValueError as error:
            QMessageBox.warning(
                self,
                self.t("Lỗi chọn trang", "Invalid page selection"),
                str(error),
            )
            return
        self.add_pages(source, page_numbers)

    def add_all_pages_for_source(self):
        source = self.current_source()
        if source is not None:
            self.add_pages(source, range(1, source["page_count"] + 1))

    def add_all_sources(self):
        for source in self.sources:
            self.add_pages(source, range(1, source["page_count"] + 1), refresh=False)
        self.refresh_output_labels()
        self.update_output_status()

    def add_pages(self, source, page_numbers, refresh=True):
        for page_number in page_numbers:
            item = QListWidgetItem()
            item.setData(
                Qt.ItemDataRole.UserRole,
                (source["path"], page_number - 1),
            )
            self.output_list.addItem(item)
        if refresh:
            self.refresh_output_labels()
            self.update_output_status()

    def refresh_output_labels(self, *_):
        for row in range(self.output_list.count()):
            item = self.output_list.item(row)
            path, page_index = item.data(Qt.ItemDataRole.UserRole)
            item.setText(
                self.t(
                    f"{row + 1}. {os.path.basename(path)}  —  Trang {page_index + 1}",
                    f"{row + 1}. {os.path.basename(path)}  —  Page {page_index + 1}",
                )
            )
        self.update_output_status()

    def update_output_status(self, *_):
        count = self.output_list.count()
        self.btn_preview_output.setEnabled(bool(count))
        self.btn_preview_exported.setEnabled(bool(self.last_export_path))
        self.output_status.setText(
            self.t(
                "Chưa có trang để ghép." if not count else f"Sẽ xuất {count} trang.",
                "No pages selected for merging." if not count else f"{count} pages will be exported.",
            )
        )

    def open_source_preview(self, _item=None):
        source = self.current_source()
        if source is None:
            return
        pages = [
            (source["path"], page_index)
            for page_index in range(source["page_count"])
        ]
        PdfPagePreviewDialog(
            self.t(
                f"Xem PDF nguồn - {os.path.basename(source['path'])}",
                f"Source PDF - {os.path.basename(source['path'])}",
            ),
            pages,
            self,
            self.language,
        ).exec()

    def open_output_preview(self, _item=None):
        pages = self.page_sequence()
        if not pages:
            QMessageBox.warning(
                self,
                self.t("Chưa có trang", "No pages selected"),
                self.t(
                    "Hãy thêm trang vào danh sách ghép trước khi xem trước.",
                    "Add pages to the output list before previewing.",
                ),
            )
            return
        PdfPagePreviewDialog(
            self.t("Xem trước PDF kết quả", "Merged PDF preview"),
            pages,
            self,
            self.language,
        ).exec()

    def open_exported_preview(self):
        if not self.last_export_path or not os.path.isfile(self.last_export_path):
            return
        try:
            with fitz.open(self.last_export_path) as document:
                pages = [
                    (self.last_export_path, page_index)
                    for page_index in range(document.page_count)
                ]
        except Exception as error:
            QMessageBox.critical(
                self,
                self.t("Không thể mở PDF đã ghép", "Could not open merged PDF"),
                str(error),
            )
            return
        PdfPagePreviewDialog(
            self.t("PDF đã ghép", "Merged PDF"),
            pages,
            self,
            self.language,
        ).exec()

    def move_output(self, direction):
        row = self.output_list.currentRow()
        new_row = row + direction
        if not 0 <= row < self.output_list.count() or not 0 <= new_row < self.output_list.count():
            return
        item = self.output_list.takeItem(row)
        self.output_list.insertItem(new_row, item)
        self.output_list.setCurrentItem(item)
        self.refresh_output_labels()

    def remove_output_pages(self):
        rows = sorted(
            {self.output_list.row(item) for item in self.output_list.selectedItems()},
            reverse=True,
        )
        for row in rows:
            self.output_list.takeItem(row)
        self.refresh_output_labels()

    def page_sequence(self):
        return [
            self.output_list.item(row).data(Qt.ItemDataRole.UserRole)
            for row in range(self.output_list.count())
        ]

    def export_pdf(self):
        sequence = self.page_sequence()
        if not sequence:
            QMessageBox.warning(
                self,
                self.t("Chưa có trang", "No pages selected"),
                self.t("Hãy thêm ít nhất một trang vào danh sách ghép.", "Add at least one page to the output list."),
            )
            return

        first_source = self.sources[0]["path"] if self.sources else "merged.pdf"
        directory = os.path.dirname(first_source)
        name = os.path.splitext(os.path.basename(first_source))[0]
        suggested = os.path.join(directory, f"{name}_ghep.pdf")
        output, _ = QFileDialog.getSaveFileName(
            self,
            self.t("Lưu PDF đã ghép", "Save merged PDF"),
            suggested,
            "PDF (*.pdf)",
        )
        if not output:
            return
        if not output.lower().endswith(".pdf"):
            output += ".pdf"

        source_paths = {os.path.normcase(os.path.abspath(path)) for path, _ in sequence}
        if os.path.normcase(os.path.abspath(output)) in source_paths:
            QMessageBox.warning(
                self,
                self.t("Tên file không hợp lệ", "Invalid output file"),
                self.t(
                    "Không thể ghi đè lên một PDF nguồn. Hãy đặt tên file khác.",
                    "The output must not overwrite a source PDF. Choose a different filename.",
                ),
            )
            return

        try:
            merge_pdf_page_sequence(sequence, output)
        except Exception as error:
            QMessageBox.critical(
                self,
                self.t("Không thể ghép PDF", "Could not merge PDFs"),
                str(error),
            )
            return

        self.last_export_path = output
        self.update_output_status()
        QMessageBox.information(
            self,
            self.t("Hoàn thành", "Completed"),
            self.t(
                f"Đã ghép thành công {len(sequence)} trang.\n{output}",
                f"Successfully merged {len(sequence)} pages.\n{output}",
            ),
        )
