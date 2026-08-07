import fitz

from PySide6.QtWidgets import *

from PySide6.QtGui import *

from PySide6.QtCore import *

from preview import render_page_preview
from splitter import split_pdf
from rename_dialog import RenameDialog


class MainWindow(QMainWindow):

    def __init__(self):
        super().__init__()

        self.setWindowTitle("PDF Splitter Pro")
        self.resize(1000,750)

        self.pdf_path=""
        self.save_folder=""
        self.doc=None
        self.current_page = 0

        self.initUI()


    def initUI(self):

        widget=QWidget()
        self.setCentralWidget(widget)

        layout=QVBoxLayout(widget)

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

        nav.addWidget(self.btnPrev)
        nav.addWidget(self.lblCurrent)
        nav.addWidget(self.btnNext)

        layout.addLayout(nav)

        self.btnPrev.clicked.connect(self.prev_page)
        self.btnNext.clicked.connect(self.next_page)


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


    def open_pdf(self):

        file,_=QFileDialog.getOpenFileName(
            self,
            "Open PDF",
            "",
            "PDF (*.pdf)"
        )

        if not file:
            return

        self.pdf_path=file

        self.txtPdf.setText(file)

        self.doc=fitz.open(file)

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

            dlg=RenameDialog(self.doc,start,end,self)

            if dlg.exec():

                filenames.append(dlg.filename)
                rotations.append(dlg.rotation)



        if len(filenames)!=len(ranges):

            return


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

        pix = render_page_preview(
            self.doc,
            self.current_page
        )

        width = self.scroll.viewport().width() - 20

        pix = pix.scaledToWidth(
            width,
            Qt.SmoothTransformation
        )

        self.preview.setPixmap(pix)

        self.preview.adjustSize()

    def next_page(self):

        if self.doc is None:
            return

        if self.current_page < self.doc.page_count - 1:

            self.current_page += 1

            self.lblCurrent.setText(
                f"Trang {self.current_page+1}/{self.doc.page_count}"
            )

            self.update_preview()


    def prev_page(self):

        if self.doc is None:
            return

        if self.current_page > 0:

            self.current_page -= 1

            self.lblCurrent.setText(
                f"Trang {self.current_page+1}/{self.doc.page_count}"
            )

            self.update_preview()
    def resizeEvent(self, event):

        super().resizeEvent(event)

        if self.doc:

            self.update_preview()
    