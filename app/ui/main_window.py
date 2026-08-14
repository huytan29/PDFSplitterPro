import copy
import os
import tempfile
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
from app.services.auto_naming import suggest_document_filename
from app.services.blank_pages import find_blank_page_indices
from app.services.preview import render_page_image, render_page_preview
from app.services.splitter import (
    merge_pdf_with_edits,
    merge_selected_pages,
    parse_page_selection,
    split_pdf,
    split_pdf_with_edits,
)
from app.ui.image_pdf_dialog import ImageToPdfDialog
from app.ui.merge_pdf_dialog import MergePdfDialog
from app.ui.rename_dialog import RenameDialog


class ReorderablePageList(QListWidget):
    """Horizontal page rail with mouse-driven reordering independent of Qt DnD."""

    orderChanged = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mouse_drag_item = None
        self._mouse_press_position = QPoint()
        self._mouse_dragging = False
        self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton:
            self._mouse_drag_item = self.itemAt(event.position().toPoint())
            self._mouse_press_position = event.position().toPoint()
            self._mouse_dragging = False

    def mouseMoveEvent(self, event):
        if (
            self._mouse_drag_item is None
            or not event.buttons() & Qt.MouseButton.LeftButton
        ):
            super().mouseMoveEvent(event)
            return

        position = event.position().toPoint()
        if not self._mouse_dragging:
            distance = (position - self._mouse_press_position).manhattanLength()
            if distance < QApplication.startDragDistance():
                super().mouseMoveEvent(event)
                return
            self._mouse_dragging = True
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)

        self._auto_scroll_for_drag(position.x())
        source_row = self.row(self._mouse_drag_item)
        target_item = self.itemAt(position)
        if target_item is not None:
            self.move_page_to_row(source_row, self.row(target_item))
        elif self.count():
            first_rect = self.visualItemRect(self.item(0))
            last_rect = self.visualItemRect(self.item(self.count() - 1))
            if position.x() < first_rect.left():
                self.move_page_to_row(source_row, 0)
            elif position.x() > last_rect.right():
                self.move_page_to_row(source_row, self.count() - 1)
        event.accept()

    def mouseReleaseEvent(self, event):
        was_dragging = self._mouse_dragging
        self._mouse_drag_item = None
        self._mouse_dragging = False
        self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
        if was_dragging:
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _auto_scroll_for_drag(self, x_position):
        scroll_bar = self.horizontalScrollBar()
        margin = 36
        step = max(30, scroll_bar.singleStep() * 4)
        if x_position < margin:
            scroll_bar.setValue(scroll_bar.value() - step)
        elif x_position > self.viewport().width() - margin:
            scroll_bar.setValue(scroll_bar.value() + step)

    def move_page(self, source_row, target_row):
        """Move a row to an insertion position and emit one order event."""
        if not 0 <= source_row < self.count():
            return False

        target_row = max(0, min(target_row, self.count()))
        if source_row < target_row:
            target_row -= 1
        if source_row == target_row:
            return False

        signals_were_blocked = self.blockSignals(True)
        item = self.takeItem(source_row)
        self.insertItem(target_row, item)
        self.setCurrentItem(item)
        self.blockSignals(signals_were_blocked)
        self.scrollToItem(item, QAbstractItemView.ScrollHint.EnsureVisible)
        self.orderChanged.emit()
        return True

    def move_page_to_row(self, source_row, final_row):
        """Move a page to an exact visible row."""
        if not 0 <= final_row < self.count():
            return False
        insertion_row = final_row if final_row < source_row else final_row + 1
        return self.move_page(source_row, insertion_row)


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
        # Display order contains zero-based page indexes from the source PDF.
        self.page_order = []
        self.edited_pages = {}
        self.checked_pages = set()
        self.blank_page_indices = set()
        self.removed_blank_page_indices = set()
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

        self.btnMergeFiles = QPushButton("GHÉP NHIỀU PDF")
        self.btnMergeFiles.setMinimumHeight(38)
        self.btnMergeFiles.clicked.connect(self.open_multi_file_merge)

        image_tools.addStretch()

        image_tools.addWidget(self.btnMergeFiles)
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
            "B\u1ea5m th\u1ebb \u0111\u1ec3 ch\u1ecdn; k\u00e9o th\u1ebb sang tr\u00e1i/ph\u1ea3i \u0111\u1ec3 \u0111\u1ed5i th\u1ee9 t\u1ef1 trang."
        )
        self.pageRailHint.setWordWrap(True)
        self.pageRailHint.setStyleSheet("color: #9ab6ca;")
        pageRailLayout.addWidget(self.pageRailHint)

        self.pageList = ReorderablePageList()
        self.pageList.setIconSize(QSize(120, 140))
        # A single compact row: enough for image + caption without the large
        # empty band that a fixed, oversized thumbnail area created.
        self.pageList.setGridSize(QSize(160, 180))
        self.pageList.setViewMode(QListView.ViewMode.IconMode)
        self.pageList.setFlow(QListView.Flow.LeftToRight)
        self.pageList.setWrapping(False)
        self.pageList.setResizeMode(QListView.ResizeMode.Adjust)
        # Reordering is handled directly by ReorderablePageList mouse events.
        # Native Qt drag/drop is disabled so platform DnD cannot swallow moves.
        self.pageList.setMovement(QListView.Movement.Static)
        self.pageList.setWordWrap(True)
        self.pageList.setUniformItemSizes(True)
        self.pageList.setSpacing(8)
        self.pageList.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.pageList.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.pageList.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.pageList.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.pageList.setDragEnabled(False)
        self.pageList.setAcceptDrops(False)
        self.pageList.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
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
        self.pageList.orderChanged.connect(self.on_page_order_changed)
        pageRailLayout.addWidget(self.pageList, 1)

        pageRailButtons = QHBoxLayout()
        self.btnMovePageLeft = QPushButton("◀ Sang trái")
        self.btnMovePageRight = QPushButton("Sang phải ▶")
        self.btnSelectAllPages = QPushButton("T\u00edch t\u1ea5t c\u1ea3")
        self.btnClearPageSelection = QPushButton("B\u1ecf ch\u1ecdn")
        self.btnMovePageLeft.setEnabled(False)
        self.btnMovePageRight.setEnabled(False)
        self.btnSelectAllPages.setEnabled(False)
        self.btnClearPageSelection.setEnabled(False)
        self.btnMovePageLeft.clicked.connect(lambda: self.move_current_page(-1))
        self.btnMovePageRight.clicked.connect(lambda: self.move_current_page(1))
        self.btnSelectAllPages.clicked.connect(lambda: self.set_all_pages_checked(True))
        self.btnClearPageSelection.clicked.connect(lambda: self.set_all_pages_checked(False))
        pageRailButtons.addWidget(self.btnMovePageLeft)
        pageRailButtons.addWidget(self.btnMovePageRight)
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

        self.btnAutoName = QPushButton()
        self.btnAutoName.setCheckable(True)
        self.btnAutoName.setChecked(False)
        self.btnAutoName.setFixedHeight(38)
        self.btnAutoName.setMinimumWidth(190)
        self.btnAutoName.toggled.connect(self.update_auto_name_button)

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

        self.update_auto_name_button(False)
        split_actions.addWidget(self.btnAutoName)
        split_actions.addWidget(self.btnSplit, 1)
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


    def update_auto_name_button(self, checked):
        english = self.ui_language == "en"
        if checked:
            self.btnAutoName.setText(
                "AUTO NAME: ON" if english else "TỰ ĐẶT TÊN: BẬT"
            )
            self.btnAutoName.setStyleSheet("""
                QPushButton {
                    background: #16533d;
                    border: 1px solid #38d194;
                    border-radius: 7px;
                    color: #e0fff1;
                    font-weight: 700;
                }
                QPushButton:hover { background: #1d6b4e; }
            """)
        else:
            self.btnAutoName.setText(
                "AUTO NAME: OFF" if english else "TỰ ĐẶT TÊN: TẮT"
            )
            self.btnAutoName.setStyleSheet("""
                QPushButton {
                    background: #303030;
                    border: 1px solid #606060;
                    border-radius: 7px;
                    color: #e0e0e0;
                    font-weight: 700;
                }
                QPushButton:hover { background: #3b3b3b; }
            """)
        self.btnAutoName.setToolTip(
            (
                "OCR will suggest GCN/CMND/CCCD filenames when splitting. "
                "You can review each name before saving."
            )
            if english
            else (
                "Khi bật, OCR sẽ gợi ý tên GCN/CMND/CCCD lúc tách PDF. "
                "Bạn vẫn có thể kiểm tra và sửa tên trước khi lưu."
            )
        )


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
        self.btnMergeFiles.setText(
            "MERGE PDF FILES" if english else "GHÉP NHIỀU PDF"
        )
        self.btnImageToPdf.setText("IMAGE → PDF" if english else "ẢNH → PDF")

        self.groupFile.setTitle("Source PDF" if english else "PDF nguồn")
        self.btnOpen.setText("Choose" if english else "Chọn")

        self.pageRailTitle.setText("PAGES TO EDIT" if english else "TRANG CẦN CHỈNH SỬA")
        self.pageRailHint.setText(
            "Click a page card to select it; drag cards left or right to reorder pages."
            if english
            else "Bấm thẻ để chọn; kéo thẻ sang trái/phải để đổi thứ tự trang."
        )
        self.btnSelectAllPages.setText("Select all" if english else "Tích tất cả")
        self.btnClearPageSelection.setText("Clear selection" if english else "Bỏ chọn")
        self.btnMovePageLeft.setText("◀ Move left" if english else "◀ Sang trái")
        self.btnMovePageRight.setText("Move right ▶" if english else "Sang phải ▶")
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
        self.update_auto_name_button(self.btnAutoName.isChecked())

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


    def open_multi_file_merge(self):
        """Open the independent page-by-page multi-file merge workflow."""
        MergePdfDialog(self, self.ui_language).exec()


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

        # Default the output location to the folder that contains the
        # selected source PDF.  Users can still choose another folder with
        # the "Chọn" button afterwards.
        self.save_folder = os.path.dirname(file)
        self.txtSave.setText(self.save_folder)

        try:

            self.doc=fitz.open(file)

        except Exception as error:

            self.doc = None

            QMessageBox.critical(self, "Lỗi", f"Không thể mở PDF.\n{error}")

            return

        self.edited_pages = {}
        self.blank_page_indices = self.detect_blank_pages()
        self.removed_blank_page_indices = set()
        self.checked_pages = set(self.blank_page_indices)
        self._thumbnail_cache.clear()

        self.current_page = 0
        self.page_order = list(range(self.doc.page_count))

        self.btnEditPage.setEnabled(True)

        self.btnSelectAllPages.setEnabled(True)

        self.btnClearPageSelection.setEnabled(True)

        self.btnMovePageLeft.setEnabled(True)

        self.btnMovePageRight.setEnabled(True)

        self.txtMergePages.setEnabled(True)

        self.btnMergePdf.setEnabled(True)

        self.btnAutoFix.setEnabled(True)
        self.autoOcrLanguage.setEnabled(True)

        self.build_page_list()

        self.update_preview()

        if self.blank_page_indices:
            self.ask_to_remove_blank_pages()


    def choose_folder(self):

        folder=QFileDialog.getExistingDirectory(self)

        if folder:

            self.save_folder=folder

            self.txtSave.setText(folder)


    def detect_blank_pages(self):
        """Detect likely blank pages while keeping the window responsive."""
        if self.doc is None:
            return set()

        english = self.ui_language == "en"
        progress = QProgressDialog(
            "Finding blank pages..." if english else "Đang tìm trang trắng...",
            "Cancel" if english else "Hủy",
            0,
            self.doc.page_count,
            self,
        )
        progress.setWindowTitle(
            "Blank-page detection" if english else "Nhận diện trang trắng"
        )
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setMinimumDuration(250)
        progress.setAutoClose(False)

        def update_progress(page_index, total_pages):
            progress.setValue(page_index)
            page_number = min(page_index + 1, total_pages)
            progress.setLabelText(
                f"Checking page {page_number}/{total_pages}..."
                if english
                else f"Đang kiểm tra trang {page_number}/{total_pages}..."
            )
            QApplication.processEvents()

        try:
            blank_pages = find_blank_page_indices(
                self.doc,
                should_cancel=progress.wasCanceled,
                on_progress=update_progress,
            )
        finally:
            progress.close()

        return set(blank_pages or [])


    def ask_to_remove_blank_pages(self):
        """Let the user decide whether detected blank pages leave the output."""
        english = self.ui_language == "en"
        positions = [
            str(position + 1)
            for position, page_index in enumerate(self.page_order)
            if page_index in self.blank_page_indices
        ]
        page_list = ", ".join(positions[:30])
        if len(positions) > 30:
            page_list += ", ..."

        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Icon.Question)
        dialog.setWindowTitle(
            "Blank pages detected" if english else "Trang trắng đã phát hiện"
        )
        dialog.setText(
            (
                f"Detected {len(positions)} likely blank pages (pages {page_list}) "
                "and selected them automatically."
            )
            if english
            else (
                f"Đã phát hiện {len(positions)} trang có vẻ trắng (trang {page_list}) "
                "và tự động tích chọn chúng."
            )
        )
        dialog.setInformativeText(
            (
                "Permanently remove these pages from the source PDF? "
                "This cannot be undone."
            )
            if english
            else (
                "Bạn có muốn xóa vĩnh viễn các trang này khỏi PDF nguồn không? "
                "Thao tác này không thể hoàn tác."
            )
        )
        remove_button = dialog.addButton(
            "Remove from source PDF" if english else "Xóa khỏi PDF gốc",
            QMessageBox.ButtonRole.AcceptRole,
        )
        keep_button = dialog.addButton(
            "Keep pages" if english else "Giữ lại",
            QMessageBox.ButtonRole.RejectRole,
        )
        dialog.setDefaultButton(keep_button)
        dialog.exec()

        if dialog.clickedButton() == remove_button:
            self.remove_detected_blank_pages()


    def remove_detected_blank_pages(self):
        """Permanently remove detected blank pages from the source PDF."""
        english = self.ui_language == "en"
        removable_pages = [
            page_index
            for page_index in self.page_order
            if page_index in self.blank_page_indices
        ]
        if not removable_pages:
            return

        remaining_pages = [
            page_index
            for page_index in self.page_order
            if page_index not in self.blank_page_indices
        ]
        if not remaining_pages:
            QMessageBox.warning(
                self,
                "Cannot remove pages" if english else "Không thể xóa trang",
                (
                    "Every page was detected as likely blank. "
                    "At least one page must remain in the source PDF."
                )
                if english
                else (
                    "PDF chỉ có các trang được nhận diện là trắng. "
                    "Cần giữ lại ít nhất một trang trong PDF gốc."
                ),
            )
            return

        source_path = self.pdf_path
        source_folder = os.path.dirname(source_path)
        source_name = os.path.splitext(os.path.basename(source_path))[0]
        temporary_path = None
        output_doc = None
        source_replaced = False

        try:
            descriptor, temporary_path = tempfile.mkstemp(
                prefix=f".{source_name}_without_blank_",
                suffix=".pdf",
                dir=source_folder,
            )
            os.close(descriptor)

            output_doc = fitz.open()
            for page_index in remaining_pages:
                output_doc.insert_pdf(
                    self.doc,
                    from_page=page_index,
                    to_page=page_index,
                )
            output_doc.save(temporary_path, garbage=4, deflate=True)
            output_doc.close()
            output_doc = None

            # Closing the current document releases its Windows file lock so
            # the finished temporary PDF can atomically replace the source.
            self.doc.close()
            self.doc = None
            os.replace(temporary_path, source_path)
            source_replaced = True
            temporary_path = None
            self.doc = fitz.open(source_path)
        except Exception as error:
            if self.doc is None:
                try:
                    self.doc = fitz.open(source_path)
                except Exception:
                    pass
            QMessageBox.critical(
                self,
                "Could not update source PDF" if english else "Không thể cập nhật PDF gốc",
                (
                    (
                        "The source PDF was updated, but the app could not reopen it. "
                        f"Please reopen the file.\n{error}"
                    )
                    if source_replaced and english
                    else (
                        f"PDF gốc đã được cập nhật, nhưng app không thể mở lại file. "
                        f"Hãy mở lại file.\n{error}"
                        if source_replaced
                        else (
                            f"The source PDF was not changed.\n{error}"
                            if english
                            else f"PDF gốc chưa bị thay đổi.\n{error}"
                        )
                    )
                ),
            )
            return
        finally:
            if output_doc is not None:
                output_doc.close()
            if temporary_path and os.path.exists(temporary_path):
                try:
                    os.remove(temporary_path)
                except OSError:
                    pass

        self.edited_pages = {}
        self.page_order = list(range(self.doc.page_count))
        self.checked_pages.clear()
        self.blank_page_indices.clear()
        self.removed_blank_page_indices = set(removable_pages)
        self._thumbnail_cache.clear()
        self.current_page = 0
        self.build_page_list()
        self.update_preview()

        QMessageBox.information(
            self,
            "Source PDF updated" if english else "Đã cập nhật PDF gốc",
            (
                f"Removed {len(removable_pages)} blank page(s) from the source PDF."
                if english
                else f"Đã xóa {len(removable_pages)} trang trắng khỏi PDF gốc."
            ),
        )



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
            display_page = self.page_position(page_index) + 1
            progress.setValue(position - 1)
            progress.setLabelText(
                f"Đang sửa {position}/{len(page_indices)} trang đã tích "
                f"(vị trí {display_page})..."
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
                failed_pages.append(f"Vị trí {display_page}: {error}")
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


    def suggest_split_filenames(self, ranges):
        """OCR the first pages in each range and return reviewable suggestions."""
        try:
            languages = ensure_ocr_available()
        except OcrUnavailableError as error:
            QMessageBox.critical(
                self,
                "OCR chưa sẵn sàng",
                "Không thể tự đặt tên vì bộ OCR chưa sẵn sàng.\n" + str(error),
            )
            return None

        progress = QProgressDialog(
            "Đang nhận dạng tên tài liệu...",
            "Hủy",
            0,
            len(ranges),
            self,
        )
        progress.setWindowTitle("Tự động đặt tên")
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setMinimumDuration(250)
        progress.setAutoClose(False)

        suggestions = []
        for position, (start, end) in enumerate(ranges, start=1):
            progress.setValue(position - 1)
            progress.setLabelText(
                f"Đang đọc khoảng {start}-{end} ({position}/{len(ranges)})..."
            )
            QApplication.processEvents()
            if progress.wasCanceled():
                progress.close()
                return None

            images = []
            for visible_position in range(start - 1, min(end, start + 1)):
                page_index = self.page_order[visible_position]
                model = self.page_model(page_index)
                image = (
                    render_editable_image(model)
                    if model.annotations
                    else model.image.copy()
                )
                images.append(image)

            try:
                suggestion = suggest_document_filename(
                    images,
                    languages,
                    source_path=self.pdf_path,
                    range_start=start,
                )
            except Exception:
                suggestion = None
            suggestions.append(suggestion)

        progress.setValue(len(ranges))
        progress.close()
        return suggestions


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

        try:
            for line in text.splitlines():
                line = line.strip()
                if not line:
                    continue
                if line.count("-") != 1:
                    raise ValueError(f"Khoảng trang không hợp lệ: {line}")

                a, b = (part.strip() for part in line.split("-"))
                start, end = int(a), int(b)
                if start < 1 or start > end or end > len(self.page_order):
                    raise ValueError(
                        f"Khoảng {line} phải nằm trong PDF 1-{len(self.page_order)}."
                    )
                ranges.append((start, end))
        except ValueError as error:
            QMessageBox.warning(self, "Lỗi khoảng trang", str(error))
            return

        if not ranges:
            QMessageBox.warning(self, "Lỗi", "Chưa có khoảng trang hợp lệ.")
            return

        suggestions = [None] * len(ranges)
        if self.btnAutoName.isChecked():
            suggestions = self.suggest_split_filenames(ranges)
            if suggestions is None:
                return



        filenames=[]

        rotations = []

        for range_index, (start, end) in enumerate(ranges):

            suggestion = suggestions[range_index]
            suggested_filename = suggestion.filename if suggestion else ""
            suggestion_note = ""
            if self.btnAutoName.isChecked():
                suggestion_note = (
                    suggestion.detail
                    if suggestion
                    else (
                        "Không nhận dạng chắc chắn GCN, CMND hoặc CCCD trong khoảng này. "
                        "Vui lòng nhập tên thủ công."
                    )
                )

            dlg=RenameDialog(
                self.doc,
                start,
                end,
                self,
                edited_pages=self.edited_pages,
                page_order=self.page_order,
                suggested_filename=suggested_filename,
                suggestion_note=suggestion_note,
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
                self.edited_pages,
                self.page_order,
            )

        else:

            split_pdf(
                self.pdf_path,
                self.save_folder,
                ranges,
                filenames,
                rotations,
                self.page_order,
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
                len(self.page_order),
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
                    self.page_order,
                )
            else:
                merge_selected_pages(
                    self.pdf_path,
                    output,
                    page_numbers,
                    self.page_order,
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

        if not self.page_order or any(
            page_index < 0 or page_index >= self.doc.page_count
            for page_index in self.page_order
        ):
            self.page_order = list(range(self.doc.page_count))
        self.checked_pages.intersection_update(self.page_order)
        self.blank_page_indices.intersection_update(self.page_order)

        for display_index, page_index in enumerate(self.page_order):
            item = QListWidgetItem(
                QIcon(self.page_thumbnail(page_index)),
                self.page_list_label(page_index, display_index),
            )
            item.setData(Qt.ItemDataRole.UserRole, page_index)
            self.update_page_item_tooltip(item, page_index, display_index)
            self.pageList.addItem(item)

        self.pageList.setCurrentRow(self.page_position(self.current_page))
        self.pageList.blockSignals(False)
        self.update_page_selection_status()


    def on_page_order_changed(self):
        """Persist the card order while keeping edits tied to source pages."""
        self.page_order = [
            self.pageList.item(row).data(Qt.ItemDataRole.UserRole)
            for row in range(self.pageList.count())
        ]

        current_item = self.pageList.currentItem()
        if current_item is not None:
            self.current_page = current_item.data(Qt.ItemDataRole.UserRole)

        self.refresh_all_page_list_items()
        self.update_page_selection_status()


    def move_current_page(self, direction):
        """Move the active page one position with the fallback arrow buttons."""
        if self.doc is None:
            return
        source_row = self.pageList.currentRow()
        target_row = source_row + direction
        self.pageList.move_page_to_row(source_row, target_row)


    def page_position(self, page_index):
        """Return the zero-based visible position of a source page."""
        try:
            return self.page_order.index(page_index)
        except ValueError:
            return 0


    def update_page_item_tooltip(self, item, page_index, display_index):
        if self.ui_language == "en":
            item.setToolTip(
                f"Position {display_index + 1} | Original page {page_index + 1}\n"
                "Drag left or right to change the output order."
            )
        else:
            item.setToolTip(
                f"Vị trí {display_index + 1} | Trang gốc {page_index + 1}\n"
                "Kéo sang trái hoặc phải để đổi thứ tự xuất."
            )
        if page_index in self.blank_page_indices:
            suffix = (
                "\nDetected as likely blank."
                if self.ui_language == "en"
                else "\nĐược nhận diện là trang trắng."
            )
            item.setToolTip(item.toolTip() + suffix)


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


    def page_list_label(self, page_index, display_index=None):

        if display_index is None:
            display_index = self.page_position(page_index)

        label = (
            f"Page {display_index + 1}"
            if self.ui_language == "en"
            else f"Trang {display_index + 1}"
        )
        if page_index in self.edited_pages:
            label += " (edited)" if self.ui_language == "en" else " (đã sửa)"
        if page_index in self.blank_page_indices:
            label += " (blank)" if self.ui_language == "en" else " (trắng)"
        return label


    def refresh_page_list_item(self, page_index):

        display_index = self.page_position(page_index)
        item = self.pageList.item(display_index)
        if item is None:
            return

        item.setText(self.page_list_label(page_index, display_index))
        self.update_page_item_tooltip(item, page_index, display_index)
        selected = page_index in self.checked_pages
        item.setIcon(QIcon(self.page_thumbnail(page_index, selected)))


    def refresh_all_page_list_items(self):

        for page_index in self.page_order:
            self.refresh_page_list_item(page_index)


    def invalidate_page_thumbnail(self, page_index):
        """Drop both the original and edited thumbnail variants for a page."""
        self._thumbnail_cache.pop((page_index, False), None)
        self._thumbnail_cache.pop((page_index, True), None)


    def checked_page_indices(self):

        return [
            page_index
            for page_index in self.page_order
            if page_index in self.checked_pages
        ]


    def set_all_pages_checked(self, checked):

        if checked:
            self.checked_pages = set(self.page_order)
        else:
            self.checked_pages.clear()

        for page_index in self.page_order:
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
        current_position = self.page_position(self.current_page) + 1
        order_changed = self.page_order != list(range(self.doc.page_count))
        self.btnMovePageLeft.setEnabled(current_position > 1)
        visible_page_count = len(self.page_order)
        self.btnMovePageRight.setEnabled(current_position < visible_page_count)

        if self.ui_language == "en":
            summary = (
                f"{visible_page_count} pages | "
                f"Current position: {current_position}"
            )
        else:
            summary = (
                f"{visible_page_count} trang | "
                f"Vị trí đang chọn: {current_position}"
            )

        if self.removed_blank_page_indices:
            removed_label = (
                f"Removed blank: {len(self.removed_blank_page_indices)}"
                if self.ui_language == "en"
                else f"Đã xóa trang trắng: {len(self.removed_blank_page_indices)}"
            )
            summary += f" | {removed_label}"
        elif order_changed:
            summary += " | Reordered" if self.ui_language == "en" else " | Đã đổi thứ tự"

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
                f"Applies to page at position {current_position}."
                if self.ui_language == "en"
                else f"Áp dụng cho trang ở vị trí {current_position}."
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

        position = max(0, min(page_number - 1, len(self.page_order) - 1))
        self.set_current_page(self.page_order[position])


    def set_current_page(self, page_index):

        if self.doc is None:
            return

        page_index = max(0, min(page_index, self.doc.page_count - 1))

        self.current_page = page_index

        if self.pageList.count():
            self.pageList.blockSignals(True)
            self.pageList.setCurrentRow(self.page_position(page_index))
            self.pageList.blockSignals(False)

        self.update_preview()

    def next_page(self):

        if self.doc is None:
            return

        position = self.page_position(self.current_page)
        if position < len(self.page_order) - 1:

            self.set_current_page(self.page_order[position + 1])


    def prev_page(self):

        if self.doc is None:
            return

        position = self.page_position(self.current_page)
        if position > 0:

            self.set_current_page(self.page_order[position - 1])


    def page_model(self, page_index):

        existing = self.edited_pages.get(page_index)

        if existing is not None:

            return existing

        image = render_page_image(self.doc, page_index)

        return EditableImage(
            f"Trang {self.page_position(page_index) + 1}",
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
                    f"Trang {self.page_position(page_index) + 1}",
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
