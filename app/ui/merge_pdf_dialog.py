"""Dialog for combining complete PDF files or an arbitrary page sequence."""

from __future__ import annotations

import os

from pypdf import PdfReader
from PySide6.QtCore import Qt
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
    QVBoxLayout,
)

from app.services.splitter import merge_pdf_page_sequence, parse_page_selection


class MergePdfDialog(QDialog):
    """Build a PDF from pages from one or more source files."""

    def __init__(self, parent=None, language="vi"):
        super().__init__(parent)
        self.language = "en" if language == "en" else "vi"
        self.sources = []

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
        self.output_status.setText(
            self.t(
                "Chưa có trang để ghép." if not count else f"Sẽ xuất {count} trang.",
                "No pages selected for merging." if not count else f"{count} pages will be exported.",
            )
        )

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

        QMessageBox.information(
            self,
            self.t("Hoàn thành", "Completed"),
            self.t(
                f"Đã ghép thành công {len(sequence)} trang.\n{output}",
                f"Successfully merged {len(sequence)} pages.\n{output}",
            ),
        )
        self.accept()
