"""Editable image model and rendering helpers shared across the application."""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from PIL import Image, ImageDraw, ImageFont
from PySide6.QtGui import QImage, QPixmap


@dataclass
class TextAnnotation:
    text: str
    x: float
    y: float
    size: int
    color: tuple[int, int, int]


@dataclass
class EditableImage:
    path: str
    image: Image.Image
    original: Image.Image
    annotations: list[TextAnnotation] = field(default_factory=list)
    history: list[tuple[Image.Image, list[TextAnnotation]]] = field(default_factory=list)


def pil_to_pixmap(image: Image.Image) -> QPixmap:
    """Convert a PIL image to an independent QPixmap."""
    rgba = image.convert("RGBA")
    data = rgba.tobytes("raw", "RGBA")
    qimage = QImage(
        data,
        rgba.width,
        rgba.height,
        rgba.width * 4,
        QImage.Format.Format_RGBA8888,
    ).copy()
    return QPixmap.fromImage(qimage)


def get_font(size: int) -> ImageFont.ImageFont:
    """Use an installed Windows font, with a safe fallback for PDF export."""
    fonts_dir = os.path.join(os.environ.get("WINDIR", r"C:\\Windows"), "Fonts")
    for name in ("arial.ttf", "calibri.ttf", "segoeui.ttf"):
        font_path = os.path.join(fonts_dir, name)
        if os.path.exists(font_path):
            return ImageFont.truetype(font_path, size)
    return ImageFont.load_default()


def render_annotations(
    image: Image.Image,
    annotations: list[TextAnnotation],
) -> Image.Image:
    """Draw text annotations on an RGBA copy of the image."""
    canvas = image.convert("RGBA")
    draw = ImageDraw.Draw(canvas)
    for annotation in annotations:
        size = max(10, round(min(canvas.size) * annotation.size / 1000))
        draw.text(
            (round(annotation.x * canvas.width), round(annotation.y * canvas.height)),
            annotation.text,
            font=get_font(size),
            fill=annotation.color + (255,),
            stroke_width=max(0, size // 28),
            stroke_fill=(255, 255, 255, 180),
        )
    return canvas


def render_editable_image(model: EditableImage) -> Image.Image:
    """Return a flattened RGB image for previewing or inserting into a PDF."""
    image = render_annotations(model.image, model.annotations)
    background = Image.new("RGB", image.size, "white")
    background.paste(image, mask=image.getchannel("A"))
    return background
