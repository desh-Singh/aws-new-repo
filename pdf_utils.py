import os
import tempfile
import img2pdf
from PIL import Image
from pypdf import PdfWriter, PdfReader

ALLOWED_IMAGE_EXT = {".jpg", ".jpeg", ".png"}

# --------------------------------------------------
# Convert SINGLE image → PDF
# --------------------------------------------------
def image_to_pdf(image_file, output_path):
    image = Image.open(image_file).convert("RGB")
    image.save(output_path, "PDF")


# --------------------------------------------------
# Convert MULTIPLE images → ONE PDF
# --------------------------------------------------
def images_to_single_pdf(image_files, output_path):
    image_paths = []

    for file in image_files:
        img = Image.open(file).convert("RGB")
        tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
        img.save(tmp.name, "JPEG", quality=95)
        tmp.close()
        image_paths.append(tmp.name)

    with open(output_path, "wb") as f:
        f.write(img2pdf.convert(image_paths))

    for path in image_paths:
        if os.path.exists(path):
            os.remove(path)


# --------------------------------------------------
# Merge MULTIPLE PDFs → ONE PDF
# --------------------------------------------------
def merge_pdfs(pdf_paths, output_path):
    writer = PdfWriter()

    for pdf in pdf_paths:
        reader = PdfReader(pdf)
        for page in reader.pages:
            writer.add_page(page)

    with open(output_path, "wb") as f:
        writer.write(f)


# --------------------------------------------------
# Merge MIXED FILES (images + pdfs) → ONE PDF
# --------------------------------------------------
def merge_images_and_pdfs(files, output_path):
    writer = PdfWriter()
    temp_files = []

    for file in files:
        ext = os.path.splitext(file.filename)[1].lower()

        # ---------- IMAGE ----------
        if ext in ALLOWED_IMAGE_EXT:
            img = Image.open(file).convert("RGB")

            tmp_img = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
            img.save(tmp_img.name, "JPEG", quality=95)
            tmp_img.close()

            tmp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
            tmp_pdf.close()

            with open(tmp_pdf.name, "wb") as f:
                f.write(img2pdf.convert([tmp_img.name]))

            reader = PdfReader(tmp_pdf.name)
            for page in reader.pages:
                writer.add_page(page)

            temp_files.extend([tmp_img.name, tmp_pdf.name])

        # ---------- PDF ----------
        elif ext == ".pdf":
            tmp_pdf = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
            file.save(tmp_pdf.name)
            tmp_pdf.close()

            reader = PdfReader(tmp_pdf.name)
            for page in reader.pages:
                writer.add_page(page)

            temp_files.append(tmp_pdf.name)

        else:
            raise Exception("Unsupported file type")

    with open(output_path, "wb") as f:
        writer.write(f)

    # cleanup
    for path in temp_files:
        if os.path.exists(path):
            os.remove(path)
