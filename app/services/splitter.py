import os
from io import BytesIO

import fitz

from pypdf import PdfReader
from pypdf import PdfWriter

from app.models.editable_image import render_editable_image


def parse_page_selection(selection, total_pages):
    """Chuyen chuoi chon trang thanh danh sach so trang theo thu tu nhap.

    Ho tro danh sach (``1,3,5``), khoang (``1-3``) va ket hop ca hai
    (``1-3,5,8-10``). So trang trong giao dien bat dau tu 1.
    """
    if total_pages < 1:
        raise ValueError("PDF khong co trang de ghep.")

    text = selection.replace("\n", ",").replace(";", ",").strip()
    if not text:
        raise ValueError("Chua nhap trang can ghep.")

    pages = []
    selected = set()

    for raw_item in text.split(","):
        item = raw_item.strip()
        if not item:
            raise ValueError("Danh sach trang co muc trong.")

        if "-" in item:
            if item.count("-") != 1:
                raise ValueError(f"Khoang trang khong hop le: {item}")

            start_text, end_text = (part.strip() for part in item.split("-"))
            if not start_text.isdigit() or not end_text.isdigit():
                raise ValueError(f"Khoang trang khong hop le: {item}")

            start, end = int(start_text), int(end_text)
            if start > end:
                raise ValueError(f"Khoang trang phai tang dan: {item}")

            item_pages = range(start, end + 1)
        else:
            if not item.isdigit():
                raise ValueError(f"So trang khong hop le: {item}")
            item_pages = (int(item),)

        for page_number in item_pages:
            if page_number < 1 or page_number > total_pages:
                raise ValueError(
                    f"Trang {page_number} nam ngoai PDF 1-{total_pages}."
                )
            if page_number in selected:
                raise ValueError(f"Trang {page_number} duoc chon lap lai.")

            selected.add(page_number)
            pages.append(page_number)

    return pages


def merge_selected_pages(pdf_file, output_file, page_numbers):
    """Ghep cac trang da chon cua mot PDF thanh mot file PDF moi."""
    reader = PdfReader(pdf_file)
    writer = PdfWriter()

    for page_number in page_numbers:
        writer.add_page(reader.pages[page_number - 1])

    with open(output_file, "wb") as file:
        writer.write(file)


def merge_pdf_with_edits(doc, output_file, page_numbers, edited_pages):
    """Ghep trang, dong thoi dua cac chinh sua dang nam trong bo nho vao file."""
    output_doc = fitz.open()

    try:
        for page_number in page_numbers:
            page_index = page_number - 1

            if page_index in edited_pages:
                append_edited_page(
                    output_doc,
                    doc,
                    page_index,
                    edited_pages[page_index],
                )
            else:
                output_doc.insert_pdf(
                    doc,
                    from_page=page_index,
                    to_page=page_index,
                )

        output_doc.save(output_file, garbage=4, deflate=True)
    finally:
        output_doc.close()


def create_filename(folder, name):

    filename = os.path.join(folder, name + ".pdf")

    if not os.path.exists(filename):
        return filename

    index = 1

    while True:

        filename = os.path.join(
            folder,
            f"{name} ({index}).pdf"
        )

        if not os.path.exists(filename):
            return filename

        index += 1


def split_pdf(pdf_file,
              save_folder,
              ranges,
              filenames,
              rotations):

    reader = PdfReader(pdf_file)

    for (start, end), name, rotation in zip(
            ranges,
            filenames,
            rotations):

        writer = PdfWriter()

        for page in range(start - 1, end):

            page_obj = reader.pages[page]

            if rotation != 0:
                page_obj = page_obj.rotate(rotation)

            writer.add_page(page_obj)

        output = create_filename(save_folder, name)

        try:
            with open(output, "wb") as f:
                writer.write(f)

            print("Đã lưu:", output)

        except Exception as e:
            print("Lỗi:", e)
            raise


def append_edited_page(output_doc, source_doc, page_index, model):
    """Chen mot trang da chinh sua vao PDF ket qua, giu dung ti le trang."""
    source_page = source_doc.load_page(page_index)
    image = render_editable_image(model)

    scale_x = source_page.rect.width / model.original.width
    scale_y = source_page.rect.height / model.original.height
    scale = (scale_x + scale_y) / 2

    page = output_doc.new_page(
        width=image.width * scale,
        height=image.height * scale,
    )

    buffer = BytesIO()
    # ``optimize=True`` is disproportionately slow on high-resolution scans.
    # PyMuPDF applies deflate compression when saving the finished PDF, so a
    # modest PNG compression level preserves quality while exporting faster.
    image.save(buffer, format="PNG", compress_level=3)
    page.insert_image(page.rect, stream=buffer.getvalue())
    return page


def split_pdf_with_edits(doc,
                         save_folder,
                         ranges,
                         filenames,
                         rotations,
                         edited_pages):
    """Tach PDF va ap dung cac chinh sua dang nam trong bo nho.

    Cac trang chua chinh sua duoc sao chep nguyen trang; chi trang da sua
    moi duoc render thanh anh de ho tro cat, lat guong va bo loc scan.
    """
    for (start, end), name, rotation in zip(ranges, filenames, rotations):
        output_doc = fitz.open()

        try:
            for page_index in range(start - 1, end):
                if page_index in edited_pages:
                    output_page = append_edited_page(
                        output_doc,
                        doc,
                        page_index,
                        edited_pages[page_index],
                    )
                else:
                    output_doc.insert_pdf(
                        doc,
                        from_page=page_index,
                        to_page=page_index,
                    )
                    output_page = output_doc.load_page(output_doc.page_count - 1)

                if rotation != 0:
                    output_page.set_rotation(rotation)

            output = create_filename(save_folder, name)
            output_doc.save(output, garbage=4, deflate=True)
            print("Da luu:", output)

        finally:
            output_doc.close()
