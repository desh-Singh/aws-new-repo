import os
from openai import OpenAI
import json
import re
from dotenv import load_dotenv
load_dotenv()  
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def safe_json_load(content: str):
    """
    Extracts the first valid JSON object from GPT output safely
    """
    try:
        content = content.strip()

        # Remove markdown fences if present
        if content.startswith("```"):
            content = re.sub(r"```(json)?", "", content)
            content = content.strip("` \n")

        # Find JSON object
        start = content.find("{")
        end = content.rfind("}") + 1

        if start == -1 or end == -1:
            raise ValueError("No JSON object found in GPT response")

        json_str = content[start:end]
        return json.loads(json_str)

    except Exception as e:
        print("❌ GPT JSON PARSE FAILED")
        print("RAW GPT OUTPUT:\n", content)
        raise e


def parse_documents_with_gpt(payload):

    documents = payload.get("documents") or {}
    driver_license = documents.get("driver_license") or {}
    bank_document = documents.get("bank_document") or {}
    tax_document = documents.get("tax_document") or {}
    other_document = documents.get("other_document") or {}

    prompt = f"""
You are an expert KYC and business onboarding data extractor.

Your task is to analyze ALL provided OCR text together and extract a SINGLE unified JSON object.

STRICT OUTPUT RULES (MANDATORY):

Output ONLY valid JSON

Do NOT add explanations

Do NOT add markdown

Do NOT wrap in ```json

Output must start with {{ and end with }}

ALL output keys must exist (use null if missing)

If a value is unclear, conflicting, or incomplete, return null

DATA RULES:

Use semantic understanding, not keyword guessing

Do NOT hallucinate values

Clean OCR noise, watermarks, headers, footers, and duplicates

Normalize formatting (dates, numbers, spacing)

Prefer the most complete and reliable value when duplicates exist

DRIVER LICENSE NAME RULES:

Extract the PERSON’S name only

Ignore government authority text, watermarks, and slogans such as:
"NEW YORK STATE", "USA", "NOT FOR FEDERAL PURPOSES",
"DRIVER LICENSE", "SEAL", "EXCELSIOR",
names of commissioners or officials

Ignore repeated, partial, or misspelled name fragments caused by OCR errors

The valid person name usually appears near the address and date of birth

Split name strictly into first_name and last_name

Do NOT guess missing name parts

SOURCE OF TRUTH (PRIORITY ORDER):

Driver License →
first_name, last_name, date_of_birth, license_number, home_address

Tax Document →
tax_id, identification_number, business_name, business_address, business_owner

Bank Document →
bank_name, routing_number, account_number

If the same field appears in multiple documents:

Use the value from the higher-priority document

Ignore conflicting values from lower-priority documents

ADDRESS RULES:
If address appears across multiple consecutive lines,
merge them into one full address string.

If a structured address is present in ID extracted data,
use it instead of OCR text.

Return ONLY one single full address string for home_address

Combine street, city, state, and ZIP if present

Do NOT split address into parts

Do NOT infer or guess missing address elements

FILES RULE:

"files" must be an array of document types detected from the OCR text

Allowed values:
"driver_license"
"bank_document"
"tax_document"

Include only documents that clearly appear in the input

CONFIDENCE SCORE RULES:

confidence_score must be a number between 0 and 100

Score reflects overall confidence in extracted identity data

Reduce score if OCR is noisy, values required normalization, or conflicts existed

Use null only if confidence cannot be reasonably estimated

OUTPUT JSON KEYS (EXACT, DO NOT CHANGE):

first_name
last_name
email
phone
date_of_birth
license_number
home_address
bank_name
routing_number
account_number
business_name
business_address
business_owner
fns_number
sales_rep_name
identification_number
tax_id
files
confidence_score

INPUT DATA RULES:

Email: {payload.get("email")}
Phone: {payload.get("phone")}
Sales Rep Name: {payload.get("sales_rep_name")}

Driver License OCR (Raw):
<<<
{driver_license.get("raw_text", "")}
>>>

Driver License Extracted ID Data (High Confidence):
<<<
{json.dumps(driver_license.get("id_data", {}), indent=2)}
>>>

Bank Document OCR:
<<<
{bank_document.get("raw_text", "")}
>>>

Tax Document OCR:
<<<
{tax_document.get("raw_text", "")}
>>>

Other Document OCR:
<<<
{other_document.get("raw_text", "")}
>>>
"""

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You are a precise data extraction engine."},
            {"role": "user", "content": prompt}
        ],
        temperature=0
    )

    return safe_json_load(response.choices[0].message.content)