from PySide6.QtWidgets import *

from PySide6.QtCore import Qt, QTimer

from app.models.editable_image import pil_to_pixmap, render_editable_image
from app.services.preview import render_page_preview

from PySide6.QtWidgets import QGraphicsView
from PySide6.QtWidgets import QGraphicsScene
from PySide6.QtWidgets import QGraphicsPixmapItem

from PySide6.QtGui import QTransform

class RenameDialog(QDialog):

    def __init__(self,
                 doc,
                 start,
                 end,
                 parent=None,
                 edited_pages=None,
                 page_order=None):

        super().__init__(parent)

        self.setModal(True)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet("""
            QDialog { background: #181818; color: #f4f4f4; }
            QScrollArea {
                background: #171717;
                border: 1px solid #414141;
                border-radius: 8px;
            }
            QWidget#splitPreview { background: #202020; }
            QLabel#splitSourceNote {
                background: #243848;
                border: 1px solid #3f6b87;
                border-radius: 6px;
                color: #bde5ff;
                padding: 6px 10px;
            }
            QLabel#splitPageLabel {
                background: #292929;
                border: 1px solid #414141;
                border-radius: 5px;
                color: #ffffff;
                padding: 6px;
            }
            QLabel#splitPageImage {
                background: #ffffff;
                border: 1px solid #636363;
                border-radius: 4px;
            }
            QLineEdit {
                background: #292929;
                border: 1px solid #555555;
                border-radius: 5px;
                color: #ffffff;
                padding: 7px;
            }
            QPushButton {
                background: #303030;
                border: 1px solid #4d4d4d;
                border-radius: 5px;
                color: #ffffff;
                min-height: 30px;
            }
            QPushButton:hover {
                background: #3b3b3b;
                border-color: #5caee8;
            }
        """)

        self.zoom = 1.0
        self.rotation = 0

        self.filename = ""

        self.setWindowTitle(
            f"Tách trang {start}-{end}"
        )

        self.resize(1280, 820)
        self.setMinimumSize(980, 650)
        self.setWindowState(self.windowState() | Qt.WindowState.WindowMaximized)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)

        label = QLabel(
            f"Trang {start} → {end}"
        )

        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("font-size: 16px; font-weight: 700;")

        layout.addWidget(label)

        self.sourceNote = QLabel()
        self.sourceNote.setObjectName("splitSourceNote")
        self.sourceNote.setWordWrap(True)
        layout.addWidget(self.sourceNote)

        self.doc = doc
        self.start = start
        self.end = end
        self.current_page = start
        self.rotation = 0
        self.edited_pages = edited_pages if edited_pages is not None else {}
        self.page_order = (
            page_order if page_order is not None else list(range(doc.page_count))
        )

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

        self.previewContainer = QWidget()
        self.previewContainer.setObjectName("splitPreview")
        self.previewContainer.setAutoFillBackground(True)

        self.previewLayout = QVBoxLayout(self.previewContainer)

        self.previewLayout.setContentsMargins(12, 12, 12, 12)

        self.previewLayout.setSpacing(18)

        self.scroll = QScrollArea()

        self.scroll.setWidget(self.previewContainer)

        self.scroll.setWidgetResizable(True)

        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.scroll.viewport().setStyleSheet("background: #171717;")

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

        # Sau khi hop thoai hien ra, cap nhat lai theo chieu rong thuc te.
        QTimer.singleShot(0, self.update_preview)

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

        edited_count = sum(
            self.page_order[page_number - 1] in self.edited_pages
            for page_number in range(self.start, self.end + 1)
        )
        if edited_count:
            self.sourceNote.setText(
                f"Nguồn xem trước: {edited_count}/{self.end - self.start + 1} trang "
                "đã được chỉnh sửa trong bộ nhớ."
            )
        else:
            self.sourceNote.setText(
                "Nguồn xem trước: PDF gốc (chưa có trang chỉnh sửa tự động)."
            )

        # Lấy đúng trang hiện tại
        while self.previewLayout.count():

            item = self.previewLayout.takeAt(0)

            if item.widget() is not None:

                item.widget().deleteLater()

        preview_width = max(420, self.scroll.viewport().width() - 48)

        for page_number in range(self.start, self.end + 1):

            page_index = self.page_order[page_number - 1]

            if page_index in self.edited_pages:

                pix = pil_to_pixmap(
                    render_editable_image(self.edited_pages[page_index])
                )

            else:

                # Zoom 1 de hien thi nhieu trang ma khong ton qua nhieu bo nho.
                pix = render_page_preview(self.doc, page_index, zoom=1)

            if self.rotation != 0:

                transform = QTransform()

                transform.rotate(self.rotation)

                pix = pix.transformed(
                    transform,
                    Qt.SmoothTransformation
                )

            if self.zoom != 1:

                pix = pix.scaled(
                    int(pix.width() * self.zoom),
                    int(pix.height() * self.zoom),
                    Qt.KeepAspectRatio,
                    Qt.SmoothTransformation
                )

            if pix.width() > preview_width:

                pix = pix.scaledToWidth(preview_width, Qt.SmoothTransformation)

            page_label = QLabel(f"Trang {page_number}")

            page_label.setAlignment(Qt.AlignCenter)
            page_label.setObjectName("splitPageLabel")
            page_label.setStyleSheet("font-weight: 600;")

            image_label = QLabel()

            image_label.setAlignment(Qt.AlignCenter)

            image_label.setPixmap(pix)
            image_label.setObjectName("splitPageImage")

            self.previewLayout.addWidget(page_label)

            self.previewLayout.addWidget(image_label)

        self.previewLayout.addStretch()

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
