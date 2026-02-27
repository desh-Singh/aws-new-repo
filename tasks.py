from celery_worker import celery
from services.extraction_service import extract_text_from_s3
from services.document_service import download_from_s3, convert_and_merge
from services.pipedrive_service import PipedriveService
from gpt_parser import parse_documents_with_gpt


@celery.task(bind=True, max_retries=3)
def process_documents_task(self, result, files_payload):

    service = PipedriveService()

    # STEP 1 — EXTRACT
    extracted_text = extract_text_from_s3(files_payload)

    # STEP 2 — OPENAI
    structured_data = parse_documents_with_gpt(extracted_text)

    # STEP 3 — CREATE DEAL
    ids = service.process_lead(structured_data)

    deal_id = ids["deal_id"]
    person_id = ids["person_id"]
    org_id = ids["org_id"]

    # STEP 4 — DOCUMENT PROCESSING
    local_files = download_from_s3(files_payload)
    final_pdfs = convert_and_merge(local_files)

    # STEP 5 — ATTACH
    for pdf_path in final_pdfs:
        service.attach_file_from_path(
            deal_id, person_id, org_id, pdf_path
        )

    return {"status": "completed", "deal_id": deal_id}