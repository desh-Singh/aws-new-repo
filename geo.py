import requests
import os
from dotenv import load_dotenv
load_dotenv() 
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")

def geocode_address(address, prefix="home"):
    if not address:
        return None

    url = "https://maps.googleapis.com/maps/api/geocode/json"
    params = {
        "address": address,
        "key": GOOGLE_MAPS_API_KEY
    }

    res = requests.get(url, params=params, timeout=10).json()

    if res.get("status") != "OK":
        return None

    result = res["results"][0]
    location = result["geometry"]["location"]

    components = {
        f"{prefix}_address_full": result["formatted_address"],
        f"{prefix}_house_number": None,
        f"{prefix}_street_name": None,
        f"{prefix}_apartment": None,
        f"{prefix}_city": None,
        f"{prefix}_state": None,
        f"{prefix}_zip": None,
        f"{prefix}_latitude": location["lat"],
        f"{prefix}_longitude": location["lng"]
    }

    # components = {
    #     "home_house_number": None,
    #     "home_street_name": None,
    #     "home_apartment": None,
    #     "home_city": None,
    #     "home_state": None,
    #     "home_zip": None,
    #     "home_latitude": location["lat"],
    #     "home_longitude": location["lng"]
    # }

    for comp in result["address_components"]:
        t = comp["types"]

        if "street_number" in t:
            components[f"{prefix}_house_number"] = comp["long_name"]

        elif "route" in t:
            components[f"{prefix}_street_name"] = comp["short_name"]

        elif "subpremise" in t:
            components[f"{prefix}_apartment"] = comp["long_name"]

        elif "locality" in t or "sublocality" in t:
            components[f"{prefix}_city"] = comp["long_name"]

        elif "administrative_area_level_1" in t:
            components[f"{prefix}_state"] = comp["short_name"]

        elif "postal_code" in t:
            components[f"{prefix}_zip"] = comp["long_name"]

    return components

