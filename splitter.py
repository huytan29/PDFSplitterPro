import os

from pypdf import PdfReader
from pypdf import PdfWriter


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