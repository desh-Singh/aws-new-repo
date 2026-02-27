import os
import time
import uuid
import requests
import boto3
import json 
from flask import Flask, render_template, request, redirect, url_for, flash
from dotenv import load_dotenv
#from werkzeug.utils import secure_filename

from gpt_parser import parse_documents_with_gpt
from geo import geocode_address
from pdf_utils import (image_to_pdf,images_to_single_pdf,merge_pdfs,merge_images_and_pdfs)
from tempfile import NamedTemporaryFile 
from services.pipedrive_service import PipedriveService


# --------------------------------------------------
# ENV SETUP
# --------------------------------------------------
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "dev-secret")

S3_BUCKET = os.getenv("S3_BUCKET", "desh-ocr-uploads")
REGION = os.getenv("AWS_DEFAULT_REGION", "us-east-1")
ZAPIER_URL = "https://hooks.zapier.com/hooks/catch/26068750/uqzmxwc/"

MAX_SIZE = 10 * 1024 * 1024  # 10MB
ALLOWED_EXT = {"pdf", "jpg", "jpeg", "png"}
service = PipedriveService()


# --------------------------------------------------
# AWS CLIENTS
# --------------------------------------------------
session = boto3.Session(
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=REGION
)

s3 = session.client("s3")
textract = session.client("textract")

# --------------------------------------------------
# FIELD CONFIG
# --------------------------------------------------
FILE_FIELDS = {
    "driving_license": "ID.pdf",
    "bank_doc": "VC.pdf",
    "tax_doc": "TaxID.pdf",
    "bank_statement": "Statement.pdf",
    "pictures": "Pics.pdf",
    "other_doc": "SupportingDoc.pdf"
}

MULTIPLE_FIELDS = {"pictures", "other_doc"}

FIELD_FILENAME_MAP = {
    "driving_license": "ID",
    "bank_doc": "VC",
    "tax_doc": "TaxID",
    "bank_statement": "Statement",
    "pictures": "Pics",
    "other_doc": "SupportingDoc"
}

# --------------------------------------------------
# HELPERS
# --------------------------------------------------
def is_image(file):
    return file.mimetype in ["image/jpeg", "image/png", "image/jpg"]

def is_pdf(file):
    return file.mimetype == "application/pdf"

def upload_to_s3(file_obj, field_name, filename=None):
    """
    file_obj : FileStorage OR file-like object
    filename : optional, explicit filename (recommended)
    """

    if filename:
        ext = os.path.splitext(filename)[1].lower()
    else:
        ext = os.path.splitext(getattr(file_obj, "filename", ""))[1].lower()

    if not ext:
        ext = ".pdf"

    base = FIELD_FILENAME_MAP.get(field_name, field_name)
    final_filename = f"{base}{ext}"

    s3_key = f"uploads/{uuid.uuid4()}_{final_filename}"
   # s3_key = f"uploads/{final_filename}"

    s3.upload_fileobj(
        file_obj,
        S3_BUCKET,
        s3_key,
        ExtraArgs={"ContentType": "application/pdf"}
    )

    return s3_key


# ---------------- IMAGE (SYNC) --------------------
def extract_text_image(s3_key):
    response = textract.detect_document_text(
        Document={"S3Object": {"Bucket": S3_BUCKET, "Name": s3_key}}
    )

    return "\n".join(
        block["Text"]
        for block in response["Blocks"]
        if block["BlockType"] == "LINE"
    )

def extract_id_fields_from_textract(s3_key):
    response = textract.analyze_id(
        DocumentPages=[{"S3Object": {"Bucket": S3_BUCKET, "Name": s3_key}}]
    )

    id_data = {
        "first_name": None,
        "last_name": None,
        "date_of_birth": None,
        "license_number": None,
        "home_address": None
    }

    for doc in response.get("IdentityDocuments", []):
        for field in doc.get("IdentityDocumentFields", []):
            field_type = field["Type"]["Text"].upper()
            value = field.get("ValueDetection", {}).get("Text")

            if not value:
                continue

            if field_type == "FIRST_NAME":
                id_data["first_name"] = value
            elif field_type == "LAST_NAME":
                id_data["last_name"] = value
            elif field_type in ["DATE_OF_BIRTH", "DOB"]:
                id_data["date_of_birth"] = value
            elif field_type in ["DOCUMENT_NUMBER", "ID_NUMBER"]:
                id_data["license_number"] = value
            elif field_type.startswith("ADDRESS"):
                id_data["home_address"] = value

    return id_data

# ---------------- PDF (ASYNC) ---------------------
def extract_text_pdf(s3_key):
    start = textract.start_document_text_detection(
        DocumentLocation={"S3Object": {"Bucket": S3_BUCKET, "Name": s3_key}}
    )

    job_id = start["JobId"]

    while True:
        response = textract.get_document_text_detection(JobId=job_id)
        status = response["JobStatus"]
        if status == "SUCCEEDED":
            break
        if status == "FAILED":
            raise Exception("Textract failed")
        time.sleep(2)

    text = []
    next_token = None

    while True:
        args = {"JobId": job_id}
        if next_token:
            args["NextToken"] = next_token

        response = textract.get_document_text_detection(**args)
        for block in response.get("Blocks", []):
            if block["BlockType"] == "LINE":
                text.append(block["Text"])

        next_token = response.get("NextToken")
        if not next_token:
            break

    return "\n".join(text)

# ---------------- UNIFIED -------------------------
def extract_text(file, s3_key):
    if is_image(file):
        return extract_text_image(s3_key)
    if is_pdf(file):
        return extract_text_pdf(s3_key)
    raise Exception("Unsupported file type")

# --------------------------------------------------
# ROUTES
# --------------------------------------------------
@app.route("/")
def index():
    return render_template("new.html")

@app.route("/upload", methods=["POST"])
def upload():
    try:
        result = {
            "email": request.form.get("email"),
            "phone": request.form.get("phone"),
            "documents": {}
        }

        # ==================================================
        # LOOP OVER ALL DOCUMENT FIELDS
        # ==================================================
        for field, final_name in FILE_FIELDS.items():
            print("\n==============================")
            print("Processing field:", field)
            print("==============================")
            # ==================================================
            # CASE 1: PICTURES → MULTIPLE IMAGES → ONE PDF
            # ==================================================
            if field == "pictures":

                print("→ Pictures field detected")
                print("→ Merging images to single PDF")
                print("→ OCR SKIPPED")
                images = request.files.getlist("pictures[]")
                images = [f for f in images if f and f.filename]

                if not images:
                    continue

                # validate images
                for img in images:
                    ext = os.path.splitext(img.filename)[1].lower()
                    if ext not in [".jpg", ".jpeg", ".png"]:
                        raise Exception("Pictures must be JPG or PNG only")

                # create temp pdf
                temp_pdf = NamedTemporaryFile(delete=False, suffix=".pdf")
                temp_pdf.close()

                # 👉 UTIL FUNCTION
                images_to_single_pdf(images, temp_pdf.name)

                # upload combined pdf
                with open(temp_pdf.name, "rb") as f:
                    s3_key = upload_to_s3(
                        f,
                        "pictures",
                        filename="Pics.pdf"   # 👈 EXPLICIT
                    )
                os.remove(temp_pdf.name)

                result["documents"][final_name] = {
                    "s3_keys": [s3_key],
                    "raw_text": None,     # ❌ NO OCR
                    "id_data": None
                }

                continue  # 🔥 skip OCR logic

            # ==================================================
            # CASE 2: OTHER DOC → MIXED FILES → ONE PDF
            # ==================================================
            if field == "other_doc":

                print("→ Other Doc field detected")
                print("→ Merging files to single PDF")
                print("→ OCR SKIPPED")
                files = request.files.getlist("other_doc[]")
                files = [f for f in files if f and f.filename]

                if not files:
                    continue

                temp_pdf = NamedTemporaryFile(delete=False, suffix=".pdf")
                temp_pdf.close()

                # 👉 UTIL FUNCTION
                merge_images_and_pdfs(files, temp_pdf.name)

                with open(temp_pdf.name, "rb") as f:
                    s3_key = upload_to_s3(
                        f,
                        "other_doc",
                        filename="SupportingDoc.pdf"
                    )

                os.remove(temp_pdf.name)

                result["documents"][final_name] = {
                    "s3_keys": [s3_key],
                    "raw_text": None,     # ❌ NO OCR
                    "id_data": None
                }

                continue

            # ==================================================
            # CASE 3: NORMAL SINGLE FILES → OCR ENABLED
            # ==================================================
 

            file = request.files.get(field)
            if not file or not file.filename:
                continue
            print("Uploading file:", file.filename)
            ext = os.path.splitext(file.filename)[1].lower()
            if ext.replace(".", "") not in ALLOWED_EXT:
                raise Exception(f"Invalid file type: {file.filename}")
            
            raw_text = None
            id_data = None
            final_s3_keys = []


            if is_image(file):
                print("Image detected → OCR on image")

                # 1️⃣ Save image to temp file
                tmp_img = NamedTemporaryFile(delete=False)
                file.save(tmp_img.name)
                tmp_img.close()

                # 2️⃣ Upload IMAGE for OCR
                with open(tmp_img.name, "rb") as f:
                    s3_image_key = upload_to_s3(f, field)

                # 3️⃣ OCR on IMAGE
                raw_text = extract_text_image(s3_image_key)
                print("OCR END for", field, "| Text length:", len(raw_text))

                if field == "driving_license":
                    id_data = extract_id_fields_from_textract(s3_image_key)

                # 4️⃣ IMAGE → PDF
                temp_pdf = NamedTemporaryFile(delete=False, suffix=".pdf")
                temp_pdf.close()

                image_to_pdf(tmp_img.name, temp_pdf.name)

                # 5️⃣ Upload FINAL PDF
                with open(temp_pdf.name, "rb") as f:
                    s3_pdf_key = upload_to_s3(
                        f,
                        field,
                        filename=final_name
                    )

                # cleanup
                os.remove(tmp_img.name)
                os.remove(temp_pdf.name)

                final_s3_keys = [s3_pdf_key]


            # ===================== PDF UPLOAD =====================
            elif is_pdf(file):
                print("PDF detected → OCR on PDF")

    # upload pdf
                s3_pdf_key = upload_to_s3(
                    file,
                    field,
                    filename=final_name
                )

                # 🔥 PDF OCR (ASYNC TEXTRACT)
                raw_text = extract_text_pdf(s3_pdf_key)

                print("OCR END for", field, "| Text length:", len(raw_text))

                final_s3_keys = [s3_pdf_key]


            # ===================== UNSUPPORTED =====================
            else:
                raise Exception("Unsupported file type")


            # ===================== SAVE RESULT =====================
            result["documents"][final_name] = {
                "s3_keys": final_s3_keys,
                "raw_text": raw_text,
                "id_data": id_data
            }

            # s3_key = upload_to_s3(file, field)

            # # OCR
            # raw_text = extract_text(file, s3_key)

            # print("OCR END for", field, "| Text length:", len(raw_text))

            # id_data = None
            # if field == "driving_license" and is_image(file):
            #     id_data = extract_id_fields_from_textract(s3_key)

            # # 2️⃣ IMAGE → PDF (AFTER OCR)
            #     temp_pdf = NamedTemporaryFile(delete=False, suffix=".pdf")
            #     temp_pdf.close()

            #     image_to_pdf(file, temp_pdf.name)

            #     with open(temp_pdf.name, "rb") as f:
            #         s3_pdf_key = upload_to_s3(
            #             f,
            #             field,
            #             filename=final_name   # ID.pdf / VC.pdf etc
            #         )

            #     os.remove(temp_pdf.name)

            #     result["documents"][final_name] = {
            #         "s3_keys": [s3_pdf_key],   # ✅ PDF link only
            #         "raw_text": raw_text,
            #         "id_data": id_data
            #     }

            #

        # ================= FILE LINKS =================
        files_payload = []
        for doc in result["documents"].values():
            for key in doc["s3_keys"]:
                files_payload.append({
                    "file_name": os.path.basename(key),
                    "s3_key": key,
                    "s3_url": f"https://{S3_BUCKET}.s3.amazonaws.com/{key}"
                })

        # ================= GPT PARSING =================

        gpt_payload = {
            "email": result.get("email"),
            "phone": result.get("phone"),
            "sales_rep_name": result.get("sales_rep_name"),
            "documents": {
                "driver_license": result["documents"].get("ID.pdf"),
                "bank_document": result["documents"].get("VC.pdf"),
                "tax_document": result["documents"].get("TaxID.pdf"),
                "other_document": result["documents"].get("Statement.pdf")
            }
        }


   
        final_data = parse_documents_with_gpt(gpt_payload)
        final_data["files"] = files_payload
        print("FILES PAYLOAD:", json.dumps(files_payload, indent=2))
        # ================= GEO =================
        home_geo = geocode_address(final_data.get("home_address"), prefix="home")
        if home_geo:
            final_data.update(home_geo)

        business_geo = geocode_address(final_data.get("business_address"), prefix="business")
        if business_geo:
            final_data.update(business_geo)

        # ================= ZAPIER =================
        
        pipedrive_ids =  service.process_lead(final_data)
       # pipedrive_ids = pipedrive.process_lead(final_data)

        #requests.post(ZAPIER_URL, json=final_data, timeout=10)
        

        flash(f"✅ Deal created! <a href='?id={pipedrive_ids['deal_id']}' target='_blank'>Open Deal</a>", "success")
        return redirect(url_for("index"))

    except Exception as e:
        print("UPLOAD ERROR:", e)
        flash(str(e), "error")
        return redirect(url_for("index"))

# --------------------------------------------------
if __name__ == "__main__":
    app.run(debug=True)
