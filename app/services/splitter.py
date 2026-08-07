import os
from io import BytesIO

import fitz

from pypdf import PdfReader
from pypdf import PdfWriter

from app.models.editable_image import render_editable_image


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
    image.save(buffer, format="PNG", optimize=True)
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
