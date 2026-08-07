import fitz

from PySide6.QtGui import QPixmap, QImage


def render_page_preview(doc, page_number):

    page = doc.load_page(page_number)

    ZOOM = 2
    
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