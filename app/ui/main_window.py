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
from app.services.auto_correct import (
    OcrUnavailableError,
    auto_correct_document,
    ensure_ocr_available,
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
        self._thumbnail_cache = {}
        # This is the interface language.  OCR language remains independent
        # when the user chooses the automatic OCR option.
        self.ui_language = "vi"

        self.initUI()


    def initUI(self):

        widget=QWidget()
        self.setCentralWidget(widget)

        outerLayout = QVBoxLayout(widget)
        outerLayout.setContentsMargins(0, 0, 0, 0)

        self.mainScroll = QScrollArea()
        self.mainScroll.setWidgetResizable(True)
        self.mainScroll.setFrameShape(QFrame.Shape.NoFrame)
        self.mainScroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.mainScroll.setStyleSheet("""
            QScrollArea, QScrollArea > QWidget > QWidget {
                background: #1b1b1b;
            }
        """)

        self.mainContent = QWidget()
        self.mainContent.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Minimum,
        )
        self.mainScroll.setWidget(self.mainContent)
        # The form may scroll on compact displays.  The primary split actions
        # are placed in a fixed footer below, so they never disappear below the
        # fold.
        outerLayout.addWidget(self.mainScroll, 1)

        layout=QVBoxLayout(self.mainContent)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(6)
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)

        image_tools = QHBoxLayout()

        self.btnImageToPdf = QPushButton("ẢNH → PDF")

        self.btnImageToPdf.setMinimumHeight(38)

        self.btnImageToPdf.clicked.connect(self.open_image_to_pdf)

        image_tools.addStretch()

        image_tools.addWidget(self.btnImageToPdf)

        layout.addLayout(image_tools)

        #=========================
        # FILE PDF
        #=========================

        self.groupFile=QGroupBox("PDF nguồn")
        self.groupFile.setMaximumHeight(70)
        layout.addWidget(self.groupFile)

        h1=QHBoxLayout(self.groupFile)

        self.txtPdf=QLineEdit()

        self.btnOpen=QPushButton("Chọn")

        self.btnOpen.clicked.connect(self.open_pdf)

        h1.addWidget(self.txtPdf)
        h1.addWidget(self.btnOpen)


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
        self.pageRail.setObjectName("pageRail")
        self.pageRail.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self.pageRail.setStyleSheet("""
            QWidget#pageRail {
                background: #1d1d1d;
                border: 1px solid #454545;
                border-radius: 8px;
            }
            QWidget#pageRail QLabel {
                border: none;
            }
        """)

        pageRailLayout = QVBoxLayout(self.pageRail)
        pageRailLayout.setContentsMargins(8, 8, 8, 8)

        pageRailHeader = QHBoxLayout()

        self.pageRailTitle = QLabel("TRANG C\u1ea6N CH\u1ec8NH S\u1eecA")
        self.pageRailTitle.setStyleSheet("font-size: 15px; font-weight: 700;")
        pageRailHeader.addWidget(self.pageRailTitle)
        pageRailHeader.addStretch()

        self.pageSummary = QLabel("Ch\u01b0a ch\u1ecdn PDF")
        self.pageSummary.setStyleSheet(
            "background: #2b2b2b; border-radius: 6px; padding: 5px 9px;"
        )
        pageRailHeader.addWidget(self.pageSummary)
        pageRailLayout.addLayout(pageRailHeader)

        self.pageRailHint = QLabel(
            "T\u00edch \u00f4 \u0111\u1ec3 ch\u1ec9nh s\u1eeda nhi\u1ec1u trang; b\u1ea5m th\u1ebb \u0111\u1ec3 ch\u1ecdn trang ri\u00eang."
        )
        self.pageRailHint.setText(
            "B\u1ea5m th\u1ebb trang \u0111\u1ec3 ch\u1ecdn ho\u1eb7c b\u1ecf ch\u1ecdn; d\u1ea5u \u2713 xanh hi\u1ec3n th\u1ecb ngay tr\u00ean \u1ea3nh."
        )
        self.pageRailHint.setWordWrap(True)
        self.pageRailHint.setStyleSheet("color: #9ab6ca;")
        pageRailLayout.addWidget(self.pageRailHint)

        self.pageList = QListWidget()
        self.pageList.setIconSize(QSize(120, 140))
        # A single compact row: enough for image + caption without the large
        # empty band that a fixed, oversized thumbnail area created.
        self.pageList.setGridSize(QSize(160, 180))
        self.pageList.setViewMode(QListView.ViewMode.IconMode)
        self.pageList.setFlow(QListView.Flow.LeftToRight)
        self.pageList.setWrapping(False)
        self.pageList.setResizeMode(QListView.ResizeMode.Adjust)
        self.pageList.setMovement(QListView.Movement.Static)
        self.pageList.setWordWrap(True)
        self.pageList.setUniformItemSizes(True)
        self.pageList.setSpacing(8)
        self.pageList.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.pageList.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.pageList.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.pageList.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        # One complete tile remains visible at high-DPI scaling.  Extra pages
        # use the horizontal rail rather than expanding the form vertically.
        self.pageList.setFixedHeight(206)
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

        editorLayout.addWidget(self.pageRail)

        self.pageActionsPanel = QFrame()
        self.pageActionsPanel.setObjectName("pageActionsPanel")
        self.pageActionsPanel.setStyleSheet("""
            QFrame#pageActionsPanel {
                background: #252525;
                border: 1px solid #4b4b4b;
                border-radius: 8px;
            }
        """)
        page_actions = QHBoxLayout(self.pageActionsPanel)
        page_actions.setContentsMargins(10, 8, 10, 8)
        page_actions.setSpacing(10)

        self.btnEditPage = QPushButton("CHỈNH SỬA")

        self.btnEditPage.setEnabled(False)

        self.btnEditPage.setMinimumHeight(36)
        self.btnEditPage.setMinimumWidth(126)
        self.btnEditPage.setMaximumWidth(142)

        self.btnEditPage.clicked.connect(self.edit_current_page)

        self.btnAutoFix = QPushButton("✦ TỰ SỬA")
        self.btnAutoFix.setEnabled(False)
        self.btnAutoFix.setMinimumHeight(36)
        self.btnAutoFix.setMinimumWidth(118)
        self.btnAutoFix.setMaximumWidth(128)
        self.btnAutoFix.setStyleSheet("""
            QPushButton {
                background: #153a31;
                border: 1px solid #31c98a;
                border-radius: 8px;
                color: #d9fff0;
                font-weight: 700;
                padding: 0 10px;
            }
            QPushButton:hover { background: #1c5745; }
            QPushButton:pressed { background: #0f2d25; }
            QPushButton:disabled {
                background: #252b29;
                border-color: #3c5149;
                color: #75877f;
            }
        """)
        self.btnAutoFix.setToolTip(
            "Tự nhận diện xoay 90°/180° và lật gương cho các trang đã tích."
        )
        self.btnAutoFix.clicked.connect(self.auto_correct_pages)

        self.autoOcrLanguage = QComboBox()
        self.autoOcrLanguage.addItem("Tự động", None)
        self.autoOcrLanguage.addItem("Tiếng Việt", "vie")
        self.autoOcrLanguage.addItem("English", "eng")
        self.autoOcrLanguage.setEnabled(True)
        self.autoOcrLanguage.setMinimumHeight(38)
        self.autoOcrLanguage.setMinimumWidth(106)
        self.autoOcrLanguage.setMaximumWidth(118)
        self.autoOcrLanguage.currentIndexChanged.connect(
            self.on_ocr_language_changed
        )
        self.autoOcrLanguage.setToolTip(
            "Chọn ngôn ngữ OCR cho TỰ SỬA: Tự động dùng cả tiếng Việt và English."
        )
        self.autoOcrLanguage.setStyleSheet("""
            QComboBox {
                background: #262626;
                border: 1px solid #4b4b4b;
                border-radius: 7px;
                color: #d8e7ee;
                padding: 0 8px;
            }
            QComboBox:hover { border-color: #4ca3cc; }
            QComboBox::drop-down { border: none; width: 18px; }
            QComboBox QAbstractItemView {
                background: #292929;
                border: 1px solid #4b4b4b;
                color: #ffffff;
                selection-background-color: #245069;
            }
        """)

        self.autoOcrLabel = QLabel("OCR")
        self.autoOcrLabel.setStyleSheet("color: #9ab6ca; font-weight: 600;")
        # Place the global OCR setting in the top toolbar, immediately before
        # the image-to-PDF action, rather than mixing it with page actions.
        image_tools.insertWidget(1, self.autoOcrLabel)
        image_tools.insertWidget(2, self.autoOcrLanguage)


        self.editStatus = QLabel(
            "Thay doi se duoc ap dung khi bam TACH PDF; PDF goc khong bi ghi de."
        )

        self.editStatus.setWordWrap(True)
        self.editStatus.setStyleSheet("color: #9ecff0;")

        page_actions.addWidget(self.btnEditPage)
        page_actions.addWidget(self.btnAutoFix)
        page_actions.addWidget(self.editStatus, 1)

        editorLayout.addWidget(self.pageActionsPanel)

        layout.addWidget(self.editorCard)
        # Do not reserve a large empty page-editor panel before a PDF is
        # selected.  It becomes visible as soon as a document is loaded.
        self.editorCard.setVisible(False)


        #=========================
        # SAVE
        #=========================

        self.groupSave=QGroupBox("Thư mục lưu")
        self.groupSave.setMaximumHeight(70)

        layout.addWidget(self.groupSave)

        h2=QHBoxLayout(self.groupSave)

        self.txtSave=QLineEdit()

        self.btnSave=QPushButton("Chọn")

        self.btnSave.clicked.connect(self.choose_folder)

        h2.addWidget(self.txtSave)

        h2.addWidget(self.btnSave)


        #=========================
        # RANGE
        #=========================

        self.groupRange=QGroupBox("Khoảng trang")

        self.groupRange.setMaximumHeight(82)

        v=QVBoxLayout(self.groupRange)

        self.txtRange=QPlainTextEdit()

        self.txtRange.setFixedHeight(46)

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

        self.groupMerge=QGroupBox("GH\u00c9P TRANG TH\u00c0NH 1 PDF")

        self.groupMerge.setMaximumHeight(70)

        mergeLayout=QHBoxLayout(self.groupMerge)

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

        # These compact controls share a row and expand with the available
        # width, keeping the split action visible without vertical scrolling.
        outputOptions = QHBoxLayout()
        outputOptions.setSpacing(6)
        outputOptions.addWidget(self.groupRange, 1)
        outputOptions.addWidget(self.groupMerge, 2)
        layout.addLayout(outputOptions)


        #=========================
        # Keep the main split actions visible while the form scrolls.
        splitFooter = QFrame()
        splitFooter.setObjectName("splitFooter")
        splitFooter.setStyleSheet("""
            QFrame#splitFooter {
                background: #202020;
                border-top: 1px solid #4a4a4a;
            }
        """)
        split_actions = QHBoxLayout(splitFooter)
        split_actions.setContentsMargins(8, 3, 8, 3)
        split_actions.setSpacing(8)

        self.btnSplit=QPushButton("TÁCH PDF VÀ LƯU")
        self.btnSplit.setFixedHeight(38)
        self.btnSplit.setStyleSheet("""
            QPushButton {
                background: #303030;
                border: 1px solid #565656;
                border-radius: 6px;
                color: #ffffff;
            }
            QPushButton:hover { background: #3d3d3d; }
        """)
        self.btnSplit.clicked.connect(self.do_split)

        split_actions.addWidget(self.btnSplit)
        outerLayout.addWidget(splitFooter)


    def on_ocr_language_changed(self, _index=None):
        """Synchronize the visible UI with an explicit OCR language choice.

        The Automatic option intentionally leaves the current UI language in
        place while OCR continues to check both Vietnamese and English.
        """
        selected_language = self.autoOcrLanguage.currentData()
        if selected_language == "eng":
            self.set_interface_language("en")
        elif selected_language == "vie":
            self.set_interface_language("vi")


    def set_interface_language(self, language):
        """Refresh all persistent labels in the main window."""
        self.ui_language = "en" if language == "en" else "vi"
        english = self.ui_language == "en"

        self.autoOcrLanguage.setItemText(0, "Automatic" if english else "Tự động")
        self.autoOcrLanguage.setItemText(1, "Vietnamese" if english else "Tiếng Việt")
        self.autoOcrLanguage.setItemText(2, "English")
        self.autoOcrLanguage.setToolTip(
            "Choose the OCR language for AUTO FIX. Automatic uses Vietnamese and English."
            if english
            else "Chọn ngôn ngữ OCR cho TỰ SỬA: Tự động dùng cả tiếng Việt và English."
        )
        self.autoOcrLabel.setText("OCR language" if english else "OCR")
        self.btnImageToPdf.setText("IMAGE → PDF" if english else "ẢNH → PDF")

        self.groupFile.setTitle("Source PDF" if english else "PDF nguồn")
        self.btnOpen.setText("Choose" if english else "Chọn")

        self.pageRailTitle.setText("PAGES TO EDIT" if english else "TRANG CẦN CHỈNH SỬA")
        self.pageRailHint.setText(
            "Click a page card to select or clear it; the green ✓ appears on the image."
            if english
            else "Bấm thẻ trang để chọn hoặc bỏ chọn; dấu ✓ xanh hiển thị ngay trên ảnh."
        )
        self.btnSelectAllPages.setText("Select all" if english else "Tích tất cả")
        self.btnClearPageSelection.setText("Clear selection" if english else "Bỏ chọn")
        self.btnEditPage.setText("EDIT" if english else "CHỈNH SỬA")
        self.btnAutoFix.setText("✦ AUTO FIX" if english else "✦ TỰ SỬA")
        self.btnAutoFix.setToolTip(
            "Automatically detects 90°/180° rotations and mirrored text on selected pages."
            if english
            else "Tự nhận diện xoay 90°/180° và lật gương cho các trang đã tích."
        )

        self.groupSave.setTitle("Output folder" if english else "Thư mục lưu")
        self.btnSave.setText("Choose" if english else "Chọn")
        self.groupRange.setTitle("Page ranges" if english else "Khoảng trang")
        self.txtRange.setPlaceholderText(
            "Example\n\n1-10\n11-25\n26-40"
            if english
            else "Ví dụ\n\n1-10\n11-25\n26-40"
        )
        self.groupMerge.setTitle(
            "MERGE PAGES INTO ONE PDF" if english else "GHÉP TRANG THÀNH 1 PDF"
        )
        self.txtMergePages.setPlaceholderText(
            "Example: 1,3  |  1-3  |  1,3,5  |  1-3,5,8-10"
            if english
            else "Ví dụ: 1,3  |  1-3  |  1,3,5  |  1-3,5,8-10"
        )
        self.btnMergePdf.setText(
            "SELECT AND MERGE PDF" if english else "CHỌN VÀ GHÉP PDF"
        )
        self.btnSplit.setText("SPLIT AND SAVE PDF" if english else "TÁCH PDF VÀ LƯU")

        if self.doc is None:
            self.pageSummary.setText("No PDF selected" if english else "Chưa chọn PDF")
            self.editStatus.setText(
                "Changes are applied when you select SPLIT AND SAVE PDF; the original PDF is unchanged."
                if english
                else "Thay doi se duoc ap dung khi bam TACH PDF; PDF goc khong bi ghi de."
            )
            return

        for page_index in range(self.pageList.count()):
            self.refresh_page_list_item(page_index)
        self.update_page_selection_status()


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
        self._thumbnail_cache.clear()

        self.current_page = 0

        self.btnEditPage.setEnabled(True)

        self.btnSelectAllPages.setEnabled(True)

        self.btnClearPageSelection.setEnabled(True)

        self.txtMergePages.setEnabled(True)

        self.btnMergePdf.setEnabled(True)

        self.btnAutoFix.setEnabled(True)
        self.autoOcrLanguage.setEnabled(True)

        self.build_page_list()

        self.update_preview()


    def choose_folder(self):

        folder=QFileDialog.getExistingDirectory(self)

        if folder:

            self.save_folder=folder

            self.txtSave.setText(folder)



    def auto_correct_pages(self):

        # This is a batch editing tool: never touch a page unless its green
        # checkmark is visible in the page rail.
        page_indices = self.checked_page_indices()
        if not page_indices:
            QMessageBox.warning(
                self,
                "Chưa chọn trang",
                "Hãy tích các trang cần tự sửa trước khi bấm TỰ SỬA.",
            )
            return False

        ocr_unavailable = False
        ocr_notice = ""
        try:
            languages = ensure_ocr_available()
        except OcrUnavailableError:
            # The visual certificate-layout fallback can still rotate many
            # scanned land certificates even when full OCR is unavailable.
            languages = []
            ocr_unavailable = True
            ocr_notice = "OCR chưa sẵn sàng: chưa kiểm tra lật gương."
        else:
            requested_language = self.autoOcrLanguage.currentData()
            if requested_language:
                if requested_language in languages:
                    languages = [requested_language]
                else:
                    languages = []
                    ocr_unavailable = True
                    language_name = self.autoOcrLanguage.currentText()
                    ocr_notice = (
                        f"Không có dữ liệu OCR {language_name}: "
                        "chưa kiểm tra lật gương."
                    )

        progress = QProgressDialog(
            "Đang phân tích trang bằng OCR...", "Hủy", 0, len(page_indices), self
        )
        progress.setWindowTitle("Tự động sửa PDF")
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        # Avoid showing a distracting dialog for the fast one-page path.
        progress.setMinimumDuration(350)
        progress.setAutoClose(False)

        updates = {}
        failed_pages = []
        action_log = []

        for position, page_index in enumerate(page_indices, start=1):
            progress.setValue(position - 1)
            progress.setLabelText(
                f"Đang sửa {position}/{len(page_indices)} trang đã tích "
                f"(trang PDF {page_index + 1})..."
            )
            QApplication.processEvents()
            if progress.wasCanceled():
                progress.close()
                return False

            source = self.page_model(page_index)
            image = (
                render_editable_image(source)
                if source.annotations
                else source.image.copy()
            )

            try:
                correction = auto_correct_document(image, languages)
            except Exception as error:
                failed_pages.append(f"Trang {page_index + 1}: {error}")
                continue

            if correction.actions:
                updates[page_index] = EditableImage(
                    source.path,
                    correction.image,
                    source.original.copy(),
                    [],
                )
                action_log.extend(correction.actions)

        progress.setValue(len(page_indices))
        progress.close()

        if not updates:
            detail = (
                f" {ocr_notice}"
                if ocr_unavailable
                else ""
            )
            QMessageBox.information(
                self,
                "Đã kiểm tra hướng trang",
                "Không phát hiện trang nào cần xoay hoặc lật gương. "
                "Trang được giữ nguyên theo chiều gốc." + detail,
            )
            return True

        self.edited_pages.update(updates)
        for page_index in updates:
            self.invalidate_page_thumbnail(page_index)
            self.refresh_page_list_item(page_index)
        self.update_page_selection_status()
        self.update_preview()

        rotated = sum(action.startswith("xoay") for action in action_log)
        mirrored = action_log.count("lật gương")
        summary = [f"Đã sửa hướng {len(updates)} trang"]
        if rotated:
            summary.append(f"xoay {rotated} trang")
        if mirrored:
            summary.append(f"lật gương {mirrored} trang")
        if failed_pages:
            summary.append(f"bỏ qua {len(failed_pages)} trang lỗi OCR")
        if ocr_unavailable:
            summary.append(ocr_notice)

        QMessageBox.information(
            self,
            "Đã tự động sửa",
            ". ".join(summary) + ".\n\n"
            "Các thay đổi đang ở bộ nhớ. Bấm TÁCH PDF VÀ LƯU khi bạn đã kiểm tra xong; PDF gốc không bị ghi đè.",
        )
        return True


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

        self.editorCard.setVisible(True)

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

        is_edited = page_index in self.edited_pages
        cache_key = (page_index, is_edited)
        thumbnail = self._thumbnail_cache.get(cache_key)
        if thumbnail is None:
            if is_edited:
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
            self._thumbnail_cache[cache_key] = thumbnail
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

        label = (
            f"Page {page_index + 1}"
            if self.ui_language == "en"
            else f"Trang {page_index + 1}"
        )
        if page_index in self.edited_pages:
            label += " (edited)" if self.ui_language == "en" else " (đã sửa)"
        return label


    def refresh_page_list_item(self, page_index):

        item = self.pageList.item(page_index)
        if item is None:
            return

        item.setText(self.page_list_label(page_index))
        selected = page_index in self.checked_pages
        item.setIcon(QIcon(self.page_thumbnail(page_index, selected)))


    def invalidate_page_thumbnail(self, page_index):
        """Drop both the original and edited thumbnail variants for a page."""
        self._thumbnail_cache.pop((page_index, False), None)
        self._thumbnail_cache.pop((page_index, True), None)


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

        if self.ui_language == "en":
            summary = (
                f"{self.doc.page_count} pages | "
                f"Current page: {self.current_page + 1}"
            )
        else:
            summary = (
                f"{self.doc.page_count} trang | "
                f"Trang đang chọn: {self.current_page + 1}"
            )

        if selected_count:
            selected_label = "Selected" if self.ui_language == "en" else "Đã tích"
            self.pageSummary.setText(f"{summary} | {selected_label}: {selected_count}")
            self.btnEditPage.setText("EDIT" if self.ui_language == "en" else "CHỈNH SỬA")
            self.btnAutoFix.setText("✦ AUTO FIX" if self.ui_language == "en" else "✦ TỰ SỬA")
            self.editStatus.setText(
                f"Applies to {selected_count} selected page(s)."
                if self.ui_language == "en"
                else f"Áp dụng cho {selected_count} trang đã tích."
            )
        else:
            self.pageSummary.setText(summary)
            self.btnEditPage.setText("EDIT" if self.ui_language == "en" else "CHỈNH SỬA")
            self.btnAutoFix.setText("✦ AUTO FIX" if self.ui_language == "en" else "✦ TỰ SỬA")
            self.editStatus.setText(
                f"Applies to page {self.current_page + 1}."
                if self.ui_language == "en"
                else f"Áp dụng cho trang {self.current_page + 1}."
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
                self.invalidate_page_thumbnail(page_index)
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
