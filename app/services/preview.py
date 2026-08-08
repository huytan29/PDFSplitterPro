import fitz
from PIL import Image

from PySide6.QtGui import QPixmap, QImage


def render_page_preview(doc, page_number, zoom=2):

    page = doc.load_page(page_number)

    ZOOM = zoom

    mat = fitz.Matrix(ZOOM, ZOOM)

    pix = page.get_pixmap(matrix=mat)

    fmt = QImage.Format_RGB888

    image = QImage(
        pix.samples,
        pix.width,
        pix.height,
        pix.stride,
        fmt
    )

    image = image.copy()

    return QPixmap.fromImage(image)


def render_range_preview(doc, start_page):

    return render_page_preview(doc, start_page - 1)


def render_page_image(doc, page_number, zoom=2):
    """Render mot trang PDF thanh PIL Image de chinh sua nhu anh quet."""
    page = doc.load_page(page_number)
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)

    # Avoid an expensive PNG encode -> decode round trip. PyMuPDF already
    # exposes RGB pixels in memory, and Pillow can copy them directly.
    return Image.frombytes(
        "RGB",
        (pix.width, pix.height),
        pix.samples,
    ).convert("RGBA")
