import copy
import os
import fitz

from PySide6.QtWidgets import *

from PySide6.QtGui import *

from PySide6.QtCore import *

from app.models.editable_image import (
    EditableImage,
    pil_to_pixmap,
    render_editable_image,
)
from app.services.preview import render_page_image, render_page_preview
from app.services.splitter import (
    merge_pdf_with_edits,
    merge_selected_pages,
    parse_page_selection,
    split_pdf,
    split_pdf_with_edits,
)
from app.ui.image_pdf_dialog import ImageToPdfDialog
from app.ui.rename_dialog import RenameDialog


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()

        self.setWindowTitle("PDF Splitter Pro")
        self.resize(1200,900)
        self.setMinimumSize(960,700)

        self.pdf_path=""
        self.save_folder=""
        self.doc=None
        self.current_page = 0
        self.edited_pages = {}
        self.checked_pages = set()

        self.initUI()


    def initUI(self):

        widget=QWidget()
        self.setCentralWidget(widget)

        layout=QVBoxLayout(widget)

        image_tools = QHBoxLayout()

        btnImageToPdf = QPushButton("ẢNH → PDF")

        btnImageToPdf.setMinimumHeight(38)

        btnImageToPdf.clicked.connect(self.open_image_to_pdf)

        image_tools.addStretch()

        image_tools.addWidget(btnImageToPdf)

        layout.addLayout(image_tools)

        #=========================
        # FILE PDF
        #=========================

        groupFile=QGroupBox("PDF nguồn")
        layout.addWidget(groupFile)

        h1=QHBoxLayout(groupFile)

        self.txtPdf=QLineEdit()

        btnOpen=QPushButton("Chọn")

        btnOpen.clicked.connect(self.open_pdf)

        h1.addWidget(self.txtPdf)
        h1.addWidget(btnOpen)


        #=========================
        # PAGE EDITOR
        #=========================

        self.editorCard = QFrame()
        self.editorCard.setObjectName("editorCard")
        self.editorCard.setStyleSheet("""
            QFrame#editorCard {
                background: #1c1c1c;
                border: 1px solid #505050;
                border-radius: 10px;
            }
        """)
        editorLayout = QVBoxLayout(self.editorCard)
        editorLayout.setContentsMargins(10, 10, 10, 10)
        editorLayout.setSpacing(8)

        self.pageRail = QWidget()
        self.pageRail.setMinimumHeight(460)
        self.pageRail.setStyleSheet("""
            QWidget {
                background: #1d1d1d;
                border: 1px solid #454545;
                border-radius: 8px;
            }
            QLabel {
                border: none;
            }
        """)

        pageRailLayout = QVBoxLayout(self.pageRail)
        pageRailLayout.setContentsMargins(8, 8, 8, 8)

        pageRailHeader = QHBoxLayout()

        pageRailTitle = QLabel("TRANG C\u1ea6N CH\u1ec8NH S\u1eecA")
        pageRailTitle.setStyleSheet("font-size: 15px; font-weight: 700;")
        pageRailHeader.addWidget(pageRailTitle)
        pageRailHeader.addStretch()

        self.pageSummary = QLabel("Ch\u01b0a ch\u1ecdn PDF")
        self.pageSummary.setStyleSheet(
            "background: #2b2b2b; border-radius: 6px; padding: 5px 9px;"
        )
        pageRailHeader.addWidget(self.pageSummary)
        pageRailLayout.addLayout(pageRailHeader)

        pageRailHint = QLabel(
            "T\u00edch \u00f4 \u0111\u1ec3 ch\u1ec9nh s\u1eeda nhi\u1ec1u trang; b\u1ea5m th\u1ebb \u0111\u1ec3 ch\u1ecdn trang ri\u00eang."
        )
        pageRailHint.setText(
            "B\u1ea5m th\u1ebb trang \u0111\u1ec3 ch\u1ecdn ho\u1eb7c b\u1ecf ch\u1ecdn; d\u1ea5u \u2713 xanh hi\u1ec3n th\u1ecb ngay tr\u00ean \u1ea3nh."
        )
        pageRailHint.setWordWrap(True)
        pageRailHint.setStyleSheet("color: #9ab6ca;")
        pageRailLayout.addWidget(pageRailHint)

        self.pageList = QListWidget()
        self.pageList.setIconSize(QSize(145, 180))
        self.pageList.setGridSize(QSize(185, 235))
        self.pageList.setViewMode(QListView.ViewMode.IconMode)
        self.pageList.setFlow(QListView.Flow.LeftToRight)
        self.pageList.setWrapping(True)
        self.pageList.setResizeMode(QListView.ResizeMode.Adjust)
        self.pageList.setMovement(QListView.Movement.Static)
        self.pageList.setWordWrap(True)
        self.pageList.setSpacing(8)
        self.pageList.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.pageList.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.pageList.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.pageList.setStyleSheet("""
            QListWidget {
                background: #202020;
                border: 1px solid #4a4a4a;
                border-radius: 8px;
                padding: 4px;
            }
            QListWidget::item {
                background: #2a2a2a;
                border: 1px solid #3b3b3b;
                border-radius: 6px;
                margin: 4px;
                padding: 7px;
            }
            QListWidget::item:selected {
                background: #243d50;
                border: 2px solid #3daee9;
            }
        """)
        self.pageList.itemSelectionChanged.connect(self.select_page_from_list)
        self.pageList.itemClicked.connect(self.toggle_page_checked)
        pageRailLayout.addWidget(self.pageList, 1)

        pageRailButtons = QHBoxLayout()
        self.btnSelectAllPages = QPushButton("T\u00edch t\u1ea5t c\u1ea3")
        self.btnClearPageSelection = QPushButton("B\u1ecf ch\u1ecdn")
        self.btnSelectAllPages.setEnabled(False)
        self.btnClearPageSelection.setEnabled(False)
        self.btnSelectAllPages.clicked.connect(lambda: self.set_all_pages_checked(True))
        self.btnClearPageSelection.clicked.connect(lambda: self.set_all_pages_checked(False))
        pageRailButtons.addWidget(self.btnSelectAllPages)
        pageRailButtons.addWidget(self.btnClearPageSelection)
        pageRailLayout.addLayout(pageRailButtons)

        editorLayout.addWidget(self.pageRail, 1)

        page_actions = QHBoxLayout()

        self.btnEditPage = QPushButton("CHỈNH SỬA TRANG HIỆN TẠI")

        self.btnEditPage.setEnabled(False)

        self.btnEditPage.setMinimumHeight(36)

        self.btnEditPage.clicked.connect(self.edit_current_page)


        self.editStatus = QLabel(
            "Thay doi se duoc ap dung khi bam TACH PDF; PDF goc khong bi ghi de."
        )

        self.editStatus.setStyleSheet("color: #336699;")

        page_actions.addWidget(self.btnEditPage)
        page_actions.addWidget(self.editStatus, 1)

        editorLayout.addLayout(page_actions)

        layout.addWidget(self.editorCard, 1)


        #=========================
        # SAVE
        #=========================

        groupSave=QGroupBox("Thư mục lưu")

        layout.addWidget(groupSave)

        h2=QHBoxLayout(groupSave)

        self.txtSave=QLineEdit()

        btnSave=QPushButton("Chọn")

        btnSave.clicked.connect(self.choose_folder)

        h2.addWidget(self.txtSave)

        h2.addWidget(btnSave)


        #=========================
        # RANGE
        #=========================

        groupRange=QGroupBox("Khoảng trang")

        groupRange.setMaximumHeight(125)

        layout.addWidget(groupRange)

        v=QVBoxLayout(groupRange)

        self.txtRange=QPlainTextEdit()

        self.txtRange.setFixedHeight(78)

        self.txtRange.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

        self.txtRange.setPlaceholderText(
"""Ví dụ

1-10
11-25
26-40"""
)

        v.addWidget(self.txtRange)


        #=========================
        # MERGE SELECTED PAGES
        #=========================

        groupMerge=QGroupBox("GH\u00c9P TRANG TH\u00c0NH 1 PDF")

        groupMerge.setMaximumHeight(88)

        layout.addWidget(groupMerge)

        mergeLayout=QHBoxLayout(groupMerge)

        self.txtMergePages=QLineEdit()

        self.txtMergePages.setPlaceholderText(
            "V\u00ed d\u1ee5: 1,3  |  1-3  |  1,3,5  |  1-3,5,8-10"
        )

        self.txtMergePages.setEnabled(False)

        self.btnMergePdf=QPushButton("CH\u1eccN V\u00c0 GH\u00c9P PDF")

        self.btnMergePdf.setFixedHeight(34)
        self.btnMergePdf.setMinimumWidth(210)

        self.btnMergePdf.setEnabled(False)

        self.btnMergePdf.clicked.connect(self.do_merge)

        mergeLayout.addWidget(self.txtMergePages, 1)
        mergeLayout.addWidget(self.btnMergePdf)


        #=========================
        btnSplit=QPushButton("TÁCH PDF")

        btnSplit.setFixedHeight(42)

        btnSplit.clicked.connect(self.do_split)

        layout.addWidget(btnSplit)


    def open_image_to_pdf(self):

        dialog = ImageToPdfDialog(self)

        dialog.exec()


    def open_pdf(self):

        file,_=QFileDialog.getOpenFileName(
            self,
            "Open PDF",
            "",
            "PDF (*.pdf)"
        )

        if not file:
            return

        if self.doc is not None:

            self.doc.close()

        self.pdf_path=file

        self.txtPdf.setText(file)

        try:

            self.doc=fitz.open(file)

        except Exception as error:

            self.doc = None

            QMessageBox.critical(self, "Lỗi", f"Không thể mở PDF.\n{error}")

            return

        self.edited_pages = {}

        self.current_page = 0

        self.btnEditPage.setEnabled(True)

        self.btnSelectAllPages.setEnabled(True)

        self.btnClearPageSelection.setEnabled(True)

        self.txtMergePages.setEnabled(True)

        self.btnMergePdf.setEnabled(True)

        self.build_page_list()

        self.update_preview()


    def choose_folder(self):

        folder=QFileDialog.getExistingDirectory(self)

        if folder:

            self.save_folder=folder

            self.txtSave.setText(folder)



    def do_split(self):

        if self.doc is None:

            QMessageBox.warning(self,"Lỗi","Chưa chọn PDF")

            return

        if self.save_folder=="":

            QMessageBox.warning(self,"Lỗi","Chưa chọn thư mục lưu")

            return

        text=self.txtRange.toPlainText().strip()

        if text=="":

            QMessageBox.warning(self,"Lỗi","Chưa nhập khoảng trang")

            return

        ranges=[]

        for line in text.splitlines():

            if "-" not in line:

                continue

            a,b=line.split("-")

            ranges.append((int(a),int(b)))



        filenames=[]

        rotations = []

        for start,end in ranges:

            dlg=RenameDialog(
                self.doc,
                start,
                end,
                self,
                edited_pages=self.edited_pages
            )

            if dlg.exec():

                filenames.append(dlg.filename)
                rotations.append(dlg.rotation)



        if len(filenames)!=len(ranges):

            return


        if self.edited_pages:

            split_pdf_with_edits(
                self.doc,
                self.save_folder,
                ranges,
                filenames,
                rotations,
                self.edited_pages
            )

        else:

            split_pdf(
                self.pdf_path,
                self.save_folder,
                ranges,
                filenames,
                rotations
            )

        QMessageBox.information(
            self,
            "Hoàn thành",
            "Đã tách PDF thành công."
        )


    def do_merge(self):

        if self.doc is None:

            QMessageBox.warning(self, "L\u1ed7i", "Ch\u01b0a ch\u1ecdn PDF")

            return

        try:
            page_numbers = parse_page_selection(
                self.txtMergePages.text(),
                self.doc.page_count,
            )
        except ValueError as error:
            QMessageBox.warning(self, "L\u1ed7i ch\u1ecdn trang", str(error))
            return

        source_name = os.path.splitext(os.path.basename(self.pdf_path))[0]
        initial_folder = self.save_folder or os.path.dirname(self.pdf_path)
        suggested_file = os.path.join(initial_folder, f"{source_name}_ghep.pdf")

        output, _ = QFileDialog.getSaveFileName(
            self,
            "L\u01b0u PDF \u0111\u00e3 gh\u00e9p",
            suggested_file,
            "PDF (*.pdf)",
        )

        if not output:
            return

        if not output.lower().endswith(".pdf"):
            output += ".pdf"

        if os.path.normcase(os.path.abspath(output)) == os.path.normcase(
            os.path.abspath(self.pdf_path)
        ):
            QMessageBox.warning(
                self,
                "L\u1ed7i",
                "Kh\u00f4ng th\u1ec3 ghi \u0111\u00e8 PDF ngu\u1ed3n. H\u00e3y ch\u1ecdn t\u00ean file kh\u00e1c.",
            )
            return

        try:
            if self.edited_pages:
                merge_pdf_with_edits(
                    self.doc,
                    output,
                    page_numbers,
                    self.edited_pages,
                )
            else:
                merge_selected_pages(
                    self.pdf_path,
                    output,
                    page_numbers,
                )
        except Exception as error:
            QMessageBox.critical(
                self,
                "L\u1ed7i gh\u00e9p PDF",
                f"Kh\u00f4ng th\u1ec3 gh\u00e9p PDF.\n{error}",
            )
            return

        QMessageBox.information(
            self,
            "Ho\u00e0n th\u00e0nh",
            f"\u0110\u00e3 gh\u00e9p {len(page_numbers)} trang th\u00e0nh c\u00f4ng.\n{output}",
        )


    def build_page_list(self):

        if self.doc is None:
            return

        self.pageList.blockSignals(True)
        self.pageList.clear()
        self.checked_pages.clear()

        for page_index in range(self.doc.page_count):
            item = QListWidgetItem(
                QIcon(self.page_thumbnail(page_index)),
                self.page_list_label(page_index),
            )
            item.setData(Qt.ItemDataRole.UserRole, page_index)
            self.pageList.addItem(item)

        self.pageList.setCurrentRow(self.current_page)
        self.pageList.blockSignals(False)
        self.update_page_selection_status()


    def page_thumbnail(self, page_index, selected=False):

        if page_index in self.edited_pages:
            pix = pil_to_pixmap(
                render_editable_image(self.edited_pages[page_index])
            )
        else:
            pix = render_page_preview(self.doc, page_index, zoom=0.30)

        thumbnail = pix.scaled(
            self.pageList.iconSize(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        return self.add_selected_badge(thumbnail) if selected else thumbnail


    def add_selected_badge(self, pixmap):

        """Draw a prominent green selection badge on a page thumbnail."""
        result = QPixmap(pixmap)
        painter = QPainter(result)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        badge_size = max(24, min(36, min(result.width(), result.height()) // 4))
        badge_rect = QRect(
            result.width() - badge_size - 5,
            5,
            badge_size,
            badge_size,
        )
        painter.setPen(QPen(QColor("#93ffd0"), 2))
        painter.setBrush(QColor("#20c77a"))
        painter.drawEllipse(badge_rect)

        font = QFont()
        font.setBold(True)
        font.setPixelSize(round(badge_size * 0.72))
        painter.setFont(font)
        painter.setPen(QColor("#ffffff"))
        painter.drawText(badge_rect, Qt.AlignCenter, "✓")
        painter.end()
        return result


    def page_list_label(self, page_index):

        label = f"Trang {page_index + 1}"
        if page_index in self.edited_pages:
            label += " (\u0111\u00e3 s\u1eeda)"
        return label


    def refresh_page_list_item(self, page_index):

        item = self.pageList.item(page_index)
        if item is None:
            return

        item.setText(self.page_list_label(page_index))
        selected = page_index in self.checked_pages
        item.setIcon(QIcon(self.page_thumbnail(page_index, selected)))


    def checked_page_indices(self):

        return sorted(self.checked_pages)


    def set_all_pages_checked(self, checked):

        if checked:
            self.checked_pages = set(range(self.pageList.count()))
        else:
            self.checked_pages.clear()

        for page_index in range(self.pageList.count()):
            self.refresh_page_list_item(page_index)
        self.update_page_selection_status()


    def toggle_page_checked(self, item):

        page_index = item.data(Qt.ItemDataRole.UserRole)
        if page_index is None:
            return

        if page_index in self.checked_pages:
            self.checked_pages.remove(page_index)
        else:
            self.checked_pages.add(page_index)

        self.refresh_page_list_item(page_index)
        self.update_page_selection_status()


    def update_page_selection_status(self):

        if self.doc is None:
            return

        selected_count = len(self.checked_page_indices())
        self.btnEditPage.setEnabled(True)

        summary = (
            f"{self.doc.page_count} trang | "
            f"Trang \u0111ang ch\u1ecdn: {self.current_page + 1}"
        )

        if selected_count:
            self.pageSummary.setText(f"{summary} | \u0110\u00e3 t\u00edch: {selected_count}")
            self.btnEditPage.setText(
                f"CH\u1ec8NH S\u1eecA {selected_count} TRANG \u0110\u00c3 T\u00cdCH"
            )
            self.editStatus.setText(
                "Thao t\u00e1c h\u00e0ng lo\u1ea1t \u00e1p d\u1ee5ng cho c\u00e1c trang \u0111\u00e3 t\u00edch; m\u1ed7i trang v\u1eabn l\u01b0u ri\u00eang."
            )
        else:
            self.pageSummary.setText(summary)
            self.btnEditPage.setText("CH\u1ec8NH S\u1eecA TRANG \u0110ANG CH\u1eccN")
            self.editStatus.setText(
                "B\u1ea5m th\u1ebb trang \u0111\u1ec3 ch\u1ecdn nhi\u1ec1u trang c\u00f9ng l\u00fac."
            )


    def select_page_from_list(self):

        item = self.pageList.currentItem()
        if item is None:
            return

        page_index = item.data(Qt.ItemDataRole.UserRole)
        if page_index is not None and page_index != self.current_page:
            self.set_current_page(page_index)


    def update_preview(self):

        if self.doc is None:
            return

        self.update_page_status()


    def update_page_status(self):

        if self.doc is None:
            return

        self.update_page_selection_status()


    def select_page_from_control(self, page_number):

        if self.doc is None:
            return

        self.set_current_page(page_number - 1)


    def set_current_page(self, page_index):

        if self.doc is None:
            return

        page_index = max(0, min(page_index, self.doc.page_count - 1))

        self.current_page = page_index

        if self.pageList.count():
            self.pageList.blockSignals(True)
            self.pageList.setCurrentRow(page_index)
            self.pageList.blockSignals(False)

        self.update_preview()

    def next_page(self):

        if self.doc is None:
            return

        if self.current_page < self.doc.page_count - 1:

            self.set_current_page(self.current_page + 1)


    def prev_page(self):

        if self.doc is None:
            return

        if self.current_page > 0:

            self.set_current_page(self.current_page - 1)


    def page_model(self, page_index):

        existing = self.edited_pages.get(page_index)

        if existing is not None:

            return existing

        image = render_page_image(self.doc, page_index)

        return EditableImage(
            f"Trang {page_index + 1}",
            image.copy(),
            image.copy()
        )


    def current_page_model(self):

        return self.page_model(self.current_page)


    def edit_current_page(self):

        if self.doc is None:
            return

        page_indices = self.checked_page_indices() or [self.current_page]
        working_pages = []

        for page_index in page_indices:
            source = self.page_model(page_index)
            # Mo ban sao lam viec: dong hop thoai Huy se khong anh huong trang goc.
            working_pages.append(
                EditableImage(
                    source.path,
                    source.image.copy(),
                    source.original.copy(),
                    copy.deepcopy(source.annotations)
                )
            )

        dialog = ImageToPdfDialog(
            self,
            working_pages,
            page_edit_mode=True
        )

        if dialog.exec():

            for page_index, updated in zip(page_indices, dialog.images):
                if self.page_model_is_original(updated):
                    self.edited_pages.pop(page_index, None)
                else:
                    self.edited_pages[page_index] = updated
                self.refresh_page_list_item(page_index)

            self.update_page_selection_status()
            self.update_preview()


    def page_model_is_original(self, model):

        return (
            not model.annotations
            and model.image.mode == model.original.mode
            and model.image.size == model.original.size
            and model.image.tobytes() == model.original.tobytes()
        )


    def resizeEvent(self, event):

        super().resizeEvent(event)

        if self.doc:

            self.update_preview()
