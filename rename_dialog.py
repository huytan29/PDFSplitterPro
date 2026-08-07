from PySide6.QtWidgets import *

from PySide6.QtCore import Qt

from preview import render_range_preview

from PySide6.QtWidgets import QGraphicsView
from PySide6.QtWidgets import QGraphicsScene
from PySide6.QtWidgets import QGraphicsPixmapItem

from PySide6.QtGui import QTransform

class RenameDialog(QDialog):

    def __init__(self,
                 doc,
                 start,
                 end,
                 parent=None):

        super().__init__(parent)

        self.zoom = 1.0
        self.rotation = 0
        
        self.filename = ""

        self.setWindowTitle(
            f"Tách trang {start}-{end}"
        )

        self.resize(1000,700)

        layout = QVBoxLayout(self)

        label = QLabel(
            f"Trang {start} → {end}"
        )

        label.setAlignment(Qt.AlignCenter)

        layout.addWidget(label)

        self.doc = doc
        self.start = start
        self.end = end
        self.current_page = start
        self.rotation = 0

        #self.preview = QLabel()

        #self.preview.setAlignment(Qt.AlignCenter)

        #pix = render_range_preview(doc, start)

        #self.preview.setPixmap(
        #    pix.scaled(
        #        450,
        #        550,
        #        Qt.KeepAspectRatio,
        #       Qt.SmoothTransformation
        #   )
        #)

        #layout.addWidget(self.preview)

        pix = render_range_preview(doc, start)

        self.preview = QLabel()

        self.preview.setPixmap(pix)

        self.preview.setAlignment(Qt.AlignCenter)

        self.scroll = QScrollArea()

        self.scroll.setWidget(self.preview)

        self.scroll.setWidgetResizable(True)

        layout.addWidget(self.scroll)

        rotateLayout = QHBoxLayout()

        self.btnLeft = QPushButton("↶ 90°")

        self.btnRight = QPushButton("↷ 90°")

        self.btn180 = QPushButton("180°")

        rotateLayout.addWidget(self.btnLeft)

        rotateLayout.addWidget(self.btn180)

        rotateLayout.addWidget(self.btnRight)

        layout.addLayout(rotateLayout)

        layout.addWidget(QLabel("Tên file"))

        self.edit = QLineEdit()

        layout.addWidget(self.edit)

        buttons = QHBoxLayout()

        btnCancel = QPushButton("Huỷ")

        btnOK = QPushButton("Tiếp")

        btnCancel.clicked.connect(self.reject)

        btnOK.clicked.connect(self.ok_clicked)

        buttons.addWidget(btnCancel)

        buttons.addWidget(btnOK)

        layout.addLayout(buttons)

        btnZoomIn = QPushButton("＋")

        btnZoomOut = QPushButton("－")

        btnZoomIn.clicked.connect(self.zoom_in)

        btnZoomOut.clicked.connect(self.zoom_out)

        self.btnLeft.clicked.connect(self.rotate_left)

        self.btnRight.clicked.connect(self.rotate_right)

        self.btn180.clicked.connect(self.rotate_180)

        self.update_preview()

    def ok_clicked(self):

        text = self.edit.text().strip()

        if text == "":

            QMessageBox.warning(
                self,
                "Lỗi",
                "Chưa nhập tên file."
            )
            return

        self.filename = text

        self.accept()

    def update_preview(self):

        # Lấy đúng trang hiện tại
        pix = render_range_preview(
            self.doc,
            self.current_page
        )

        # Xoay preview
        if self.rotation != 0:

            transform = QTransform()

            transform.rotate(self.rotation)

            pix = pix.transformed(
                transform,
                Qt.SmoothTransformation
            )

        # Zoom
        if self.zoom != 1:

            w = int(pix.width() * self.zoom)

            h = int(pix.height() * self.zoom)

            pix = pix.scaled(
                w,
                h,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation
            )

        self.preview.setPixmap(pix)

        self.preview.adjustSize()

    def zoom_in(self):

        self.zoom += 0.25

        self.update_preview()


    def zoom_out(self):

        if self.zoom > 0.5:

            self.zoom -= 0.25

            self.update_preview()
    def rotate_left(self):

        self.rotation = (self.rotation - 90) % 360

        self.update_preview()


    def rotate_right(self):

        self.rotation = (self.rotation + 90) % 360

        self.update_preview()


    def rotate_180(self):

        self.rotation = (self.rotation + 180) % 360

        self.update_preview()

class PreviewLabel(QLabel):

    def wheelEvent(self,event):

        if event.angleDelta().y()>0:

            self.parent().zoom_in()

        else:

            self.parent().zoom_out()