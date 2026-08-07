import copy
import fitz

from PySide6.QtWidgets import *

from PySide6.QtGui import *

from PySide6.QtCore import *

from preview import render_page_image, render_page_preview
from splitter import split_pdf, split_pdf_with_edits
from rename_dialog import RenameDialog
from image_pdf_dialog import (
    EditableImage,
    ImageToPdfDialog,
    pil_to_pixmap,
    render_editable_image,
)


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()

        self.setWindowTitle("PDF Splitter Pro")
        self.resize(1000,750)

        self.pdf_path=""
        self.save_folder=""
        self.doc=None
        self.current_page = 0
        self.edited_pages = {}

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
        # Preview
        #=========================

#        self.preview=QLabel()

#        self.preview.setFixedHeight(420)

#        self.preview.setAlignment(Qt.AlignCenter)

#        self.preview.setStyleSheet("""
#        border:1px solid gray;
#        background:white;
#        """)

        self.scroll = QScrollArea()

        self.scroll.setWidgetResizable(True)

        self.scroll.setAlignment(Qt.AlignCenter)

        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        self.preview = QLabel()

        self.preview.setAlignment(Qt.AlignCenter)

        self.preview.setStyleSheet("""
        background:white;
        """)

        self.scroll.setWidget(self.preview)

        layout.addWidget(self.scroll, 1)

        self.lblPages=QLabel("Số trang: 0")

        layout.addWidget(self.lblPages)

        nav = QHBoxLayout()

        self.btnPrev = QPushButton("◀ Trang trước")

        self.btnNext = QPushButton("Trang sau ▶")

        self.lblCurrent = QLabel("Trang 1")

        self.pageSlider = QSlider(Qt.Horizontal)

        self.pageSlider.setRange(1, 1)

        self.pageSlider.setEnabled(False)

        self.pageSpin = QSpinBox()

        self.pageSpin.setRange(1, 1)

        self.pageSpin.setEnabled(False)

        nav.addWidget(self.btnPrev)
        nav.addWidget(self.lblCurrent)
        nav.addWidget(QLabel("Lướt trang:"))
        nav.addWidget(self.pageSlider, 1)
        nav.addWidget(self.pageSpin)
        nav.addWidget(self.btnNext)

        layout.addLayout(nav)

        self.btnPrev.clicked.connect(self.prev_page)
        self.btnNext.clicked.connect(self.next_page)
        self.pageSlider.valueChanged.connect(self.select_page_from_control)
        self.pageSpin.valueChanged.connect(self.select_page_from_control)

        page_actions = QHBoxLayout()

        self.btnEditPage = QPushButton("CHỈNH SỬA TRANG HIỆN TẠI")

        self.btnEditPage.setEnabled(False)

        self.btnEditPage.clicked.connect(self.edit_current_page)


        self.editStatus = QLabel(
            "Thay doi se duoc ap dung khi bam TACH PDF; PDF goc khong bi ghi de."
        )

        self.editStatus.setStyleSheet("color: #336699;")

        page_actions.addWidget(self.btnEditPage)
        page_actions.addWidget(self.editStatus, 1)

        layout.addLayout(page_actions)


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

        layout.addWidget(groupRange)

        v=QVBoxLayout(groupRange)

        self.txtRange=QPlainTextEdit()

        self.txtRange.setPlaceholderText(
"""Ví dụ

1-10
11-25
26-40"""
)

        v.addWidget(self.txtRange)


        #=========================
        btnSplit=QPushButton("TÁCH PDF")

        btnSplit.setMinimumHeight(50)

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

        self.lblPages.setText(f"Số trang: {self.doc.page_count}")

#        pix=render_page_preview(self.doc,0)

#        self.preview.setPixmap(
#            pix.scaled(
#                350,
#                500,
#                Qt.KeepAspectRatio,
#                Qt.SmoothTransformation
#            )
#        )


        self.current_page = 0

        self.pageSlider.blockSignals(True)

        self.pageSpin.blockSignals(True)

        self.pageSlider.setRange(1, self.doc.page_count)

        self.pageSpin.setRange(1, self.doc.page_count)

        self.pageSlider.setValue(1)

        self.pageSpin.setValue(1)

        self.pageSlider.setEnabled(self.doc.page_count > 1)

        self.pageSpin.setEnabled(True)

        self.pageSlider.blockSignals(False)

        self.pageSpin.blockSignals(False)

        self.btnEditPage.setEnabled(True)


        self.lblCurrent.setText(
            f"Trang 1/{self.doc.page_count}"
        )

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
    def update_preview(self):

        if self.doc is None:
            return

        if self.current_page in self.edited_pages:

            pix = pil_to_pixmap(
                render_editable_image(self.edited_pages[self.current_page])
            )

        else:

            pix = render_page_preview(
                self.doc,
                self.current_page
            )

        width = max(1, self.scroll.viewport().width() - 20)

        pix = pix.scaledToWidth(
            width,
            Qt.SmoothTransformation
        )

        self.preview.setPixmap(pix)

        self.preview.adjustSize()

        self.update_page_status()


    def update_page_status(self):

        if self.doc is None:
            return

        edited = " • đã chỉnh sửa" if self.current_page in self.edited_pages else ""

        self.lblCurrent.setText(
            f"Trang {self.current_page+1}/{self.doc.page_count}{edited}"
        )


    def select_page_from_control(self, page_number):

        if self.doc is None:
            return

        self.set_current_page(page_number - 1)


    def set_current_page(self, page_index):

        if self.doc is None:
            return

        page_index = max(0, min(page_index, self.doc.page_count - 1))

        self.current_page = page_index

        self.pageSlider.blockSignals(True)

        self.pageSpin.blockSignals(True)

        self.pageSlider.setValue(page_index + 1)

        self.pageSpin.setValue(page_index + 1)

        self.pageSlider.blockSignals(False)

        self.pageSpin.blockSignals(False)

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


    def current_page_model(self):

        existing = self.edited_pages.get(self.current_page)

        if existing is not None:

            return existing

        image = render_page_image(self.doc, self.current_page)

        return EditableImage(
            f"Trang {self.current_page+1}",
            image.copy(),
            image.copy()
        )


    def edit_current_page(self):

        if self.doc is None:
            return

        source = self.current_page_model()

        # Mo ban sao lam viec: dong hop thoai Huy se khong anh huong trang goc.
        working = EditableImage(
            source.path,
            source.image.copy(),
            source.original.copy(),
            copy.deepcopy(source.annotations)
        )

        dialog = ImageToPdfDialog(
            self,
            [working],
            page_edit_mode=True
        )

        if dialog.exec():

            updated = dialog.images[0]

            if self.page_model_is_original(updated):

                self.edited_pages.pop(self.current_page, None)

            else:

                self.edited_pages[self.current_page] = updated


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
