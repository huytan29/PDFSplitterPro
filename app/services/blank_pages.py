"""Nhan dien cac trang PDF gan nhu khong co noi dung."""

import fitz


def page_looks_blank(doc, page_index):
    """Return ``True`` only for conservatively detected white/blank pages.

    The page is sampled at a low resolution and without its outer border,
    where scanner shadows and punch holes commonly appear.  The thresholds are
    intentionally conservative: a page with normal text or a small amount of
    visible content is kept for the user to review instead of being removed.
    """
    page = doc.load_page(page_index)
    pix = page.get_pixmap(
        matrix=fitz.Matrix(0.5, 0.5),
        colorspace=fitz.csGRAY,
        alpha=False,
    )

    margin_x = max(1, round(pix.width * 0.03))
    margin_y = max(1, round(pix.height * 0.03))
    start_x, end_x = margin_x, pix.width - margin_x
    start_y, end_y = margin_y, pix.height - margin_y

    if start_x >= end_x or start_y >= end_y:
        return False

    samples = pix.samples
    sample_count = 0
    brightness_total = 0
    ink_pixels = 0
    dark_pixels = 0

    # Sampling every other pixel keeps detection fast on large documents while
    # still retaining enough detail to reject pages containing real text.
    for y in range(start_y, end_y, 2):
        row_offset = y * pix.stride
        for x in range(start_x, end_x, 2):
            brightness = samples[row_offset + x]
            sample_count += 1
            brightness_total += brightness
            if brightness < 220:
                ink_pixels += 1
            if brightness < 180:
                dark_pixels += 1

    if not sample_count:
        return False

    average_brightness = brightness_total / sample_count
    return (
        average_brightness >= 225
        and ink_pixels / sample_count <= 0.0015
        and dark_pixels / sample_count <= 0.0002
    )


def find_blank_page_indices(doc, should_cancel=None, on_progress=None):
    """Find blank page indexes, or return ``None`` when detection is canceled."""
    blank_pages = []
    total_pages = doc.page_count

    for page_index in range(total_pages):
        if on_progress is not None:
            on_progress(page_index, total_pages)
        if should_cancel is not None and should_cancel():
            return None

        try:
            if page_looks_blank(doc, page_index):
                blank_pages.append(page_index)
        # A damaged page should not prevent the user from opening the rest of
        # the document.  It is simply left unselected for manual review.
        except Exception:
            continue

    if on_progress is not None:
        on_progress(total_pages, total_pages)
    return blank_pages
