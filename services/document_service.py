from pdf_utils import image_to_pdf, merge_pdfs
from tempfile import NamedTemporaryFile
import boto3
import os

S3_BUCKET = os.getenv("S3_BUCKET")
s3 = boto3.client("s3")


def download_from_s3(files_payload):
    local_files = []

    for file in files_payload:
        tmp = NamedTemporaryFile(delete=False)
        s3.download_fileobj(S3_BUCKET, file["s3_key"], tmp)
        tmp.close()

        local_files.append({
            "field": file["field"],
            "path": tmp.name,
            "name": file["file_name"]
        })

    return local_files


def convert_and_merge(local_files):
    pdf_paths = []

    for file in local_files:
        if file["path"].lower().endswith((".jpg", ".jpeg", ".png")):
            temp_pdf = NamedTemporaryFile(delete=False, suffix=".pdf")
            image_to_pdf(file["path"], temp_pdf.name)
            pdf_paths.append(temp_pdf.name)
        else:
            pdf_paths.append(file["path"])

    if len(pdf_paths) > 1:
        merged = NamedTemporaryFile(delete=False, suffix=".pdf")
        merge_pdfs(pdf_paths, merged.name)
        return [merged.name]

    return pdf_paths