from celery_worker import celery
from gpt_parser import parse_documents_with_gpt
from geo import geocode_address
from services.pipedrive_service import PipedriveService
import json

service = PipedriveService()

@celery.task(bind=True, max_retries=3)
def process_documents_task(self, result, files_payload):
    try:
        # ================= GPT =================
        gpt_payload = {
            "email": result.get("email"),
            "phone": result.get("phone"),
            "documents": {
                "driver_license": result["documents"].get("ID.pdf"),
                "bank_document": result["documents"].get("VC.pdf"),
                "tax_document": result["documents"].get("TaxID.pdf"),
                "other_document": result["documents"].get("Statement.pdf")
            }
        }

        final_data = parse_documents_with_gpt(gpt_payload)
        final_data["files"] = files_payload

        # ================= GEO =================
        home_geo = geocode_address(final_data.get("home_address"), prefix="home")
        if home_geo:
            final_data.update(home_geo)

        business_geo = geocode_address(final_data.get("business_address"), prefix="business")
        if business_geo:
            final_data.update(business_geo)

        # ================= PIPEDRIVE =================
        pipedrive_ids = service.process_lead(final_data)

        return {"status": "completed", "deal_id": pipedrive_ids["deal_id"]}

    except Exception as e:
        return {"status": "failed", "error": str(e)}