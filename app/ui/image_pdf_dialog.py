"""Giao dien chuyen anh thanh PDF va chinh sua anh truoc khi xuat."""

from __future__ import annotations

import copy
import os

from PIL import Image, ImageEnhance, ImageOps

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QAbstractItemView,
    QColorDialog,
    QDialog,
    QFileDialog,
    QFormLayout,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from app.models.editable_image import (
    EditableImage,
    TextAnnotation,
    pil_to_pixmap,
    render_annotations,
    render_editable_image,
)


IMAGE_FILTER = (
    "Anh (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp);;"
    "Tat ca tep (*.*)"
)


class CropGraphicsView(QGraphicsView):
    """Vung xem anh co the keo mot khung cat hoac chon vi tri chen chu."""

    crop_selected = Signal(QRectF)
    text_position_selected = Signal(QPointF)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setBackgroundBrush(QColor("#e8e8e8"))

        self.crop_mode = False
        self.text_mode = False
        self._start_point: QPointF | None = None
        self._crop_item: QGraphicsRectItem | None = None

    def begin_crop(self) -> None:
        self.crop_mode = True
        self.text_mode = False
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.viewport().setCursor(Qt.CursorShape.CrossCursor)

    def begin_text(self) -> None:
        self.text_mode = True
        self.crop_mode = False
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.viewport().setCursor(Qt.CursorShape.IBeamCursor)

    def cancel_action(self) -> None:
        self.crop_mode = False
        self.text_mode = False
        self._start_point = None
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.viewport().setCursor(Qt.CursorShape.ArrowCursor)

    def clear_crop_rectangle(self) -> None:
        if self._crop_item is not None and self.scene() is not None:
            self.scene().removeItem(self._crop_item)
        self._crop_item = None

    def fit_image(self) -> None:
        if self.scene() is None or self.scene().itemsBoundingRect().isNull():
            return
        self.fitInView(self.scene().itemsBoundingRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def mousePressEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.text_mode:
            self.text_position_selected.emit(self.mapToScene(event.position().toPoint()))
            self.cancel_action()
            return

        if event.button() == Qt.MouseButton.LeftButton and self.crop_mode:
            self._start_point = self.mapToScene(event.position().toPoint())
            self.clear_crop_rectangle()
            pen = QPen(QColor("#d35400"), 3, Qt.PenStyle.DashLine)
            self._crop_item = QGraphicsRectItem(QRectF(self._start_point, self._start_point))
            self._crop_item.setPen(pen)
            self.scene().addItem(self._crop_item)
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self.crop_mode and self._start_point is not None and self._crop_item is not None:
            end_point = self.mapToScene(event.position().toPoint())
            self._crop_item.setRect(QRectF(self._start_point, end_point).normalized())
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.crop_mode:
            if self._crop_item is not None:
                rect = self._crop_item.rect()
                if rect.width() >= 5 and rect.height() >= 5:
                    self.crop_selected.emit(rect)
            self.crop_mode = False
            self._start_point = None
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
            return
        super().mouseReleaseEvent(event)


class AddTextDialog(QDialog):
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Them chu vao anh")
        self.color = QColor(Qt.GlobalColor.black)

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.text_edit = QLineEdit()
        self.text_edit.setPlaceholderText("Nhap noi dung can chen")
        form.addRow("Noi dung:", self.text_edit)

        self.size_spin = QSpinBox()
        self.size_spin.setRange(10, 160)
        self.size_spin.setValue(32)
        self.size_spin.setSuffix(" px")
        form.addRow("Co chu:", self.size_spin)

        self.color_button = QPushButton("Chon mau")
        self.color_button.clicked.connect(self.choose_color)
        form.addRow("Mau chu:", self.color_button)
        layout.addLayout(form)

        hint = QLabel("Bam OK, sau do bam vao vi tri muon dat chu tren anh.")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        buttons = QHBoxLayout()
        cancel = QPushButton("Huy")
        accept = QPushButton("OK")
        cancel.clicked.connect(self.reject)
        accept.clicked.connect(self.accept)
        buttons.addStretch()
        buttons.addWidget(cancel)
        buttons.addWidget(accept)
        layout.addLayout(buttons)
        self._update_color_button()

    def choose_color(self) -> None:
        color = QColorDialog.getColor(self.color, self, "Chon mau chu")
        if color.isValid():
            self.color = color
            self._update_color_button()

    def _update_color_button(self) -> None:
        self.color_button.setStyleSheet(
            f"background: {self.color.name()}; color: "
            f"{'white' if self.color.lightness() < 128 else 'black'};"
        )


class ImageToPdfDialog(QDialog):
    """Chon nhieu anh, chinh tung anh va xuat mot PDF nhieu trang."""

    def __init__(
        self,
        parent: QWidget | None = None,
        initial_images: list[EditableImage] | None = None,
        page_edit_mode: bool = False,
    ):
        super().__init__(parent)
        self.page_edit_mode = page_edit_mode
        self.setWindowTitle("Chinh sua trang PDF" if page_edit_mode else "Chuyen anh thanh PDF")
        self.resize(1250, 800)

        self.images: list[EditableImage] = initial_images if initial_images is not None else []
        self.current_index = -1
        self.pending_crop: QRectF | None = None
        self.pending_text: tuple[str, int, tuple[int, int, int]] | None = None

        self._build_ui()
        self._populate_initial_images()

    def _populate_initial_images(self) -> None:
        for model in self.images:
            self.image_list.addItem(QListWidgetItem(os.path.basename(model.path)))
        if self.images:
            self.image_list.setCurrentRow(0)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        title = QLabel(
            "Chinh sua tung trang PDF" if self.page_edit_mode
            else "Anh → PDF  |  Chinh sua anh truoc khi xuat"
        )
        title.setStyleSheet("font-size: 17px; font-weight: 600;")
        root.addWidget(title)

        content = QHBoxLayout()
        root.addLayout(content, 1)

        left = QVBoxLayout()
        content.addLayout(left, 0)
        left.addWidget(QLabel("Thu tu trang PDF"))

        self.image_list = QListWidget()
        self.image_list.setMinimumWidth(250)
        self.image_list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.image_list.currentRowChanged.connect(self.select_image)
        left.addWidget(self.image_list, 1)

        list_buttons = QHBoxLayout()
        add = QPushButton("Them anh")
        remove = QPushButton("Xoa")
        up = QPushButton("Len")
        down = QPushButton("Xuong")
        add.clicked.connect(self.add_images)
        remove.clicked.connect(self.remove_current_image)
        up.clicked.connect(lambda: self.move_current_image(-1))
        down.clicked.connect(lambda: self.move_current_image(1))
        for button in (add, remove, up, down):
            list_buttons.addWidget(button)
            button.setVisible(not self.page_edit_mode)
        left.addLayout(list_buttons)

        right = QVBoxLayout()
        content.addLayout(right, 1)

        self.status_label = QLabel("Chon anh de bat dau chinh sua.")
        right.addWidget(self.status_label)

        self.scene = QGraphicsScene(self)
        self.preview = CropGraphicsView()
        self.preview.setScene(self.scene)
        self.preview.crop_selected.connect(self.set_crop_selection)
        self.preview.text_position_selected.connect(self.place_text)
        right.addWidget(self.preview, 1)

        edit_group = QGroupBox("Chinh sua anh")
        edit_layout = QVBoxLayout(edit_group)
        right.addWidget(edit_group)

        transform_row = QHBoxLayout()
        rotate_left = QPushButton("Xoay trai 90°")
        rotate_right = QPushButton("Xoay phai 90°")
        flip_horizontal = QPushButton("Lat ngang")
        flip_vertical = QPushButton("Lat doc")
        undo = QPushButton("Hoan tac")
        reset = QPushButton("Khoi phuc anh goc")
        rotate_left.clicked.connect(lambda: self.rotate_current(90))
        rotate_right.clicked.connect(lambda: self.rotate_current(-90))
        flip_horizontal.clicked.connect(lambda: self.flip_current(Image.Transpose.FLIP_LEFT_RIGHT))
        flip_vertical.clicked.connect(lambda: self.flip_current(Image.Transpose.FLIP_TOP_BOTTOM))
        undo.clicked.connect(self.undo_current)
        reset.clicked.connect(self.reset_current)
        for button in (rotate_left, rotate_right, flip_horizontal, flip_vertical, undo, reset):
            transform_row.addWidget(button)
        edit_layout.addLayout(transform_row)

        crop_row = QHBoxLayout()
        start_crop = QPushButton("Chon vung cat")
        apply_crop = QPushButton("Ap dung cat")
        cancel_crop = QPushButton("Huy cat")
        start_crop.clicked.connect(self.start_crop)
        apply_crop.clicked.connect(self.apply_crop)
        cancel_crop.clicked.connect(self.cancel_crop)
        crop_row.addWidget(start_crop)
        crop_row.addWidget(apply_crop)
        crop_row.addWidget(cancel_crop)
        crop_row.addStretch()
        edit_layout.addLayout(crop_row)

        scan_row = QHBoxLayout()
        enhance = QPushButton("Lam ro tai lieu")
        black_white = QPushButton("Den trang")
        add_text = QPushButton("Them chu")
        remove_text = QPushButton("Xoa chu cuoi")
        enhance.clicked.connect(self.enhance_document)
        black_white.clicked.connect(self.make_black_white)
        add_text.clicked.connect(self.start_add_text)
        remove_text.clicked.connect(self.remove_last_text)
        for button in (enhance, black_white, add_text, remove_text):
            scan_row.addWidget(button)
        scan_row.addStretch()
        edit_layout.addLayout(scan_row)

        export_row = QHBoxLayout()
        export_row.addWidget(QLabel("Do phan giai PDF:"))
        self.dpi_spin = QSpinBox()
        self.dpi_spin.setRange(72, 300)
        self.dpi_spin.setValue(150)
        self.dpi_spin.setSuffix(" DPI")
        export_row.addWidget(self.dpi_spin)
        export_row.addStretch()
        export = QPushButton("AP DUNG THAY DOI" if self.page_edit_mode else "XUAT PDF")
        export.setMinimumHeight(38)
        export.clicked.connect(self.apply_page_changes if self.page_edit_mode else self.export_pdf)
        export_row.addWidget(export)
        root.addLayout(export_row)

    def current_image(self) -> EditableImage | None:
        if 0 <= self.current_index < len(self.images):
            return self.images[self.current_index]
        return None

    def add_images(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(self, "Chon anh", "", IMAGE_FILTER)
        if not paths:
            return

        errors: list[str] = []
        for path in paths:
            try:
                with Image.open(path) as source:
                    image = ImageOps.exif_transpose(source).convert("RGBA")
                    image.load()
                model = EditableImage(path, image.copy(), image.copy())
                self.images.append(model)
                self.image_list.addItem(QListWidgetItem(os.path.basename(path)))
            except Exception as error:
                errors.append(f"{os.path.basename(path)}: {error}")

        if self.current_index == -1 and self.images:
            self.image_list.setCurrentRow(0)
        if errors:
            QMessageBox.warning(self, "Khong mo duoc mot so anh", "\n".join(errors))

    def select_image(self, row: int) -> None:
        self.pending_crop = None
        self.pending_text = None
        self.preview.cancel_action()
        self.current_index = row
        self.update_preview()

    def remove_current_image(self) -> None:
        model = self.current_image()
        if model is None:
            return
        row = self.current_index
        del self.images[row]
        self.image_list.takeItem(row)
        if self.images:
            self.image_list.setCurrentRow(min(row, len(self.images) - 1))
        else:
            self.current_index = -1
            self.update_preview()

    def move_current_image(self, direction: int) -> None:
        row = self.current_index
        new_row = row + direction
        if row < 0 or not 0 <= new_row < len(self.images):
            return
        self.images[row], self.images[new_row] = self.images[new_row], self.images[row]
        item = self.image_list.takeItem(row)
        self.image_list.insertItem(new_row, item)
        self.image_list.setCurrentRow(new_row)

    def save_history(self, model: EditableImage) -> None:
        model.history.append((model.image.copy(), copy.deepcopy(model.annotations)))
        if len(model.history) > 12:
            model.history.pop(0)

    def undo_current(self) -> None:
        model = self.current_image()
        if model is None or not model.history:
            return
        model.image, model.annotations = model.history.pop()
        self.pending_crop = None
        self.update_preview()

    def reset_current(self) -> None:
        model = self.current_image()
        if model is None:
            return
        self.save_history(model)
        model.image = model.original.copy()
        model.annotations.clear()
        self.pending_crop = None
        self.update_preview()

    def flatten_annotations(self, model: EditableImage) -> None:
        if not model.annotations:
            return
        model.image = render_annotations(model.image, model.annotations)
        model.annotations.clear()

    def rotate_current(self, angle: int) -> None:
        model = self.current_image()
        if model is None:
            return
        self.save_history(model)
        self.flatten_annotations(model)
        model.image = model.image.rotate(angle, expand=True)
        self.update_preview()

    def flip_current(self, operation: Image.Transpose) -> None:
        model = self.current_image()
        if model is None:
            return
        self.save_history(model)
        self.flatten_annotations(model)
        model.image = model.image.transpose(operation)
        self.update_preview()

    def start_crop(self) -> None:
        if self.current_image() is None:
            return
        self.pending_crop = None
        self.preview.clear_crop_rectangle()
        self.preview.begin_crop()
        self.status_label.setText("Keo chuot tren anh de chon vung can cat, sau do bam 'Ap dung cat'.")

    def set_crop_selection(self, rect: QRectF) -> None:
        model = self.current_image()
        if model is None:
            return
        image_rect = QRectF(0, 0, model.image.width, model.image.height)
        self.pending_crop = rect.intersected(image_rect)
        self.status_label.setText("Da chon vung cat. Bam 'Ap dung cat' de xac nhan.")

    def apply_crop(self) -> None:
        model = self.current_image()
        if model is None or self.pending_crop is None:
            QMessageBox.information(self, "Cat anh", "Hay keo chuot chon vung can cat truoc.")
            return
        rect = self.pending_crop
        left = max(0, int(rect.left()))
        top = max(0, int(rect.top()))
        right = min(model.image.width, int(rect.right()) + 1)
        bottom = min(model.image.height, int(rect.bottom()) + 1)
        if right - left < 10 or bottom - top < 10:
            QMessageBox.warning(self, "Cat anh", "Vung cat qua nho.")
            return
        self.save_history(model)
        self.flatten_annotations(model)
        model.image = model.image.crop((left, top, right, bottom))
        self.pending_crop = None
        self.preview.clear_crop_rectangle()
        self.update_preview()

    def cancel_crop(self) -> None:
        self.pending_crop = None
        self.preview.clear_crop_rectangle()
        self.preview.cancel_action()
        self.status_label.setText("Da huy thao tac cat anh.")

    def enhance_document(self) -> None:
        model = self.current_image()
        if model is None:
            return
        self.save_history(model)
        # Tang tuong phan, tu dong can bang sang va lam net nhu che do scan tai lieu.
        rgb = model.image.convert("RGB")
        rgb = ImageOps.autocontrast(rgb, cutoff=1)
        rgb = ImageEnhance.Contrast(rgb).enhance(1.3)
        rgb = ImageEnhance.Sharpness(rgb).enhance(1.6)
        model.image = rgb.convert("RGBA")
        self.update_preview()

    def make_black_white(self) -> None:
        model = self.current_image()
        if model is None:
            return
        self.save_history(model)
        grayscale = ImageOps.autocontrast(model.image.convert("L"), cutoff=1)
        threshold = 165
        model.image = grayscale.point(lambda pixel: 255 if pixel >= threshold else 0).convert("RGBA")
        self.update_preview()

    def start_add_text(self) -> None:
        model = self.current_image()
        if model is None:
            return
        dialog = AddTextDialog(self)
        if not dialog.exec():
            return
        content = dialog.text_edit.text().strip()
        if not content:
            QMessageBox.warning(self, "Them chu", "Noi dung chu khong duoc de trong.")
            return
        color = dialog.color
        self.pending_text = (
            content,
            dialog.size_spin.value(),
            (color.red(), color.green(), color.blue()),
        )
        self.preview.begin_text()
        self.status_label.setText("Bam vao anh de dat vi tri chen chu.")

    def place_text(self, point: QPointF) -> None:
        model = self.current_image()
        if model is None or self.pending_text is None:
            return
        image_rect = QRectF(0, 0, model.image.width, model.image.height)
        if not image_rect.contains(point):
            self.pending_text = None
            self.status_label.setText("Vi tri chen chu phai nam trong anh. Hay bam Them chu de thu lai.")
            return
        content, size, color = self.pending_text
        self.save_history(model)
        model.annotations.append(
            TextAnnotation(
                content,
                max(0.0, min(1.0, point.x() / model.image.width)),
                max(0.0, min(1.0, point.y() / model.image.height)),
                size,
                color,
            )
        )
        self.pending_text = None
        self.status_label.setText("Da chen chu. Ban co the them chu khac hoac tiep tuc chinh sua.")
        self.update_preview()

    def remove_last_text(self) -> None:
        model = self.current_image()
        if model is None or not model.annotations:
            return
        self.save_history(model)
        model.annotations.pop()
        self.update_preview()

    def update_preview(self) -> None:
        self.preview.clear_crop_rectangle()
        self.scene.clear()
        model = self.current_image()
        if model is None:
            self.status_label.setText("Chon anh de bat dau chinh sua.")
            return

        pixmap = pil_to_pixmap(model.image)
        self.scene.addItem(QGraphicsPixmapItem(pixmap))
        for annotation in model.annotations:
            item = QGraphicsTextItem(annotation.text)
            font = QFont()
            font.setPixelSize(max(10, round(min(model.image.size) * annotation.size / 1000)))
            font.setBold(True)
            item.setFont(font)
            item.setDefaultTextColor(QColor(*annotation.color))
            item.setPos(annotation.x * model.image.width, annotation.y * model.image.height)
            self.scene.addItem(item)

        self.scene.setSceneRect(0, 0, model.image.width, model.image.height)
        self.preview.fit_image()
        self.status_label.setText(
            f"{os.path.basename(model.path)}  |  {model.image.width} x {model.image.height} px"
        )

    def build_export_image(self, model: EditableImage) -> Image.Image:
        # Xuat tren ban sao; nut Xuat PDF khong lam thay doi anh dang chinh sua.
        return render_editable_image(model)

    def apply_page_changes(self) -> None:
        if not self.images:
            QMessageBox.warning(self, "Chinh sua trang", "Khong co trang nao de chinh sua.")
            return
        self.accept()

    def export_pdf(self) -> None:
        if not self.images:
            QMessageBox.warning(self, "Xuat PDF", "Hay them it nhat mot anh.")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Luu PDF", "", "PDF (*.pdf)")
        if not path:
            return
        if not path.lower().endswith(".pdf"):
            path += ".pdf"

        try:
            pages = [self.build_export_image(model) for model in self.images]
            pages[0].save(
                path,
                "PDF",
                save_all=True,
                append_images=pages[1:],
                resolution=float(self.dpi_spin.value()),
                quality=90,
            )
        except Exception as error:
            QMessageBox.critical(self, "Khong the xuat PDF", str(error))
            return

        QMessageBox.information(
            self,
            "Hoan thanh",
            f"Da tao PDF {len(pages)} trang.\n{path}",
        )
