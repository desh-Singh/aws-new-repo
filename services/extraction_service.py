import boto3
import os
import time

S3_BUCKET = os.getenv("S3_BUCKET")

session = boto3.Session(
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    region_name=os.getenv("AWS_DEFAULT_REGION")
)

textract = session.client("textract")


def extract_text_from_s3(files_payload):
    full_text = ""

    for file in files_payload:
        key = file["s3_key"]

        if key.lower().endswith((".jpg", ".jpeg", ".png")):
            res = textract.detect_document_text(
                Document={"S3Object": {"Bucket": S3_BUCKET, "Name": key}}
            )

            for block in res["Blocks"]:
                if block["BlockType"] == "LINE":
                    full_text += block["Text"] + "\n"

        elif key.lower().endswith(".pdf"):
            start = textract.start_document_text_detection(
                DocumentLocation={"S3Object": {"Bucket": S3_BUCKET, "Name": key}}
            )

            job_id = start["JobId"]

            while True:
                res = textract.get_document_text_detection(JobId=job_id)
                if res["JobStatus"] == "SUCCEEDED":
                    break
                time.sleep(2)

            for block in res["Blocks"]:
                if block["BlockType"] == "LINE":
                    full_text += block["Text"] + "\n"

    return full_text