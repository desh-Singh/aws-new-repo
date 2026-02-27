import requests
import os

PIPEDRIVE_TOKEN = os.getenv("PIPEDRIVE_API_KEY")
BASE_URL = os.getenv("PIPEDRIVE_BASE_URL", "https://api.pipedrive.com/v1")
 

class PipedriveService:

    def __init__(self):
        self.base_url = BASE_URL
        self.token = PIPEDRIVE_TOKEN
        self.session = requests.Session()

    # ---------------- PERSON ----------------
    def create_person(self, data):
        payload = {
            "name": f"{data.get('first_name','')} {data.get('last_name','')}".strip() or data.get("email"),
            "email": data.get("email"),
            "phone": data.get("phone"),
            "owner_id": 23640243,
            "visible_to": 3,

            # DOB
            "c1370eac8a04feabd3a533ed981bf9a1a498b4a6": data.get("date_of_birth"),

            # ADDRESS FULL
            "1367ab6ef1d586538eea139bc7e4971e204068c4": data.get("home_address_full"),
            "1367ab6ef1d586538eea139bc7e4971e204068c4_street_number": data.get("home_house_number"),
            "1367ab6ef1d586538eea139bc7e4971e204068c4_route": data.get("home_street_name"),
            "1367ab6ef1d586538eea139bc7e4971e204068c4_subpremise": data.get("home_apartment"),
            "1367ab6ef1d586538eea139bc7e4971e204068c4_locality": data.get("home_city"),
            "1367ab6ef1d586538eea139bc7e4971e204068c4_admin_area_level_1": data.get("home_state"),
            "1367ab6ef1d586538eea139bc7e4971e204068c4_postal_code": data.get("home_zip"),
            "1367ab6ef1d586538eea139bc7e4971e204068c4_lat": data.get("home_latitude"),
            "1367ab6ef1d586538eea139bc7e4971e204068c4_long": data.get("home_longitude"),
        }

        res = self.session.post(
            f"{self.base_url}/persons",
            params={"api_token": self.token},
            json=payload,
            timeout=20
        )
        if not res.ok:
            print("PERSON ERROR:", res.text)
        res.raise_for_status()
        return res.json()["data"]["id"]

    # ---------------- ORGANIZATION ----------------
    def create_organization(self, data):
        payload = {
            "name": data.get("business_name"),
            "address": data.get("business_address"),
            "owner_id": 23640243,
            "visible_to": 3,

            "a5caf4d8d131d8b6d965dc17a52d08de2d433bd9": data.get("identification_number"),
            "87e4f8286776a95af868610d3c73af929b7da72f": data.get("bank_name"),
            "d48c4347fce9119821fe599ca67daec5b2be614f": data.get("routing_number"),
            "7a749d6ff1cf7de4ecaa2ad3ffc8b35e1f1442a7": data.get("account_number"),
            "06c1fb36badf0a225002dbaa81402218947ca0d9": data.get("identification_number"),
        }

        res = self.session.post(
            f"{self.base_url}/organizations",
            params={"api_token": self.token},
            json=payload,
            timeout=20
        )
        res.raise_for_status()
        return res.json()["data"]["id"]

    # ---------------- DEAL ----------------
    def create_deal(self, data, person_id, org_id):
        payload = {
        "title": (data.get("business_name") or data.get("email") or "New Lead") + " - Onboarding",
        "status": "open",
        "stage_id": 36,
        "pipeline_id": 2,

        # 🔥 FIX HERE
        "user_id": 23640243,

        "org_id": org_id,
        "person_id": person_id,
        "visible_to": 3,
        "currency": "USD"
    }

        res = self.session.post(
            f"{self.base_url}/deals",
            params={"api_token": self.token},
            json=payload,
            timeout=20
        )
        if not res.ok:
            print("DEAL ERROR:", res.text)
        res.raise_for_status()
        return res.json()["data"]["id"]

    # ---------------- FILE ATTACH ----------------
    def attach_file(self, deal_id, person_id, org_id, file):

        # download file from S3 first
        file_res =self.session.get(file["s3_url"])
        file_res.raise_for_status()

        files = {
            "file": (file["file_name"], file_res.content, "application/pdf")
        }

        data = {
            "deal_id": deal_id,
            "person_id": person_id,
            "org_id": org_id
        }

        res = self.session.post(
            f"{self.base_url}/files",
            params={"api_token": self.token},
            files=files,
            data=data,
            timeout=300
        )

        if not res.ok:
            print("FILE ERROR:", res.text)

        res.raise_for_status()

    # ---------------- FULL PIPELINE ----------------
    def process_lead(self, data):

        person_id = self.create_person(data)
        org_id = self.create_organization(data)
        print("PERSON ID:", person_id)
        print("ORG ID:", org_id)
        deal_id = self.create_deal(data, person_id, org_id)

        for file in data.get("files", []):
            self.attach_file(deal_id, person_id, org_id, file)

        # 🔹 VERIFY DEAL EXISTS
        deal_data = self.get_deal(deal_id)

        if not deal_data:
            raise Exception("Deal created but not returned from Pipedrive")

        return {
            "person_id": person_id,
            "org_id": org_id,
            "deal_id": deal_id,
            "deal_title": deal_data.get("title"),
            "deal_status": deal_data.get("status"),
            "person_linked": deal_data.get("person_id"),
            "org_linked": deal_data.get("org_id")
        }
    
    def get_deal(self, deal_id):
        res =self.session.get(
            f"{self.base_url}/deals/{deal_id}",
            params={"api_token": self.token},
            timeout=20
        )
        res.raise_for_status()
        return res.json()["data"]
    
    
