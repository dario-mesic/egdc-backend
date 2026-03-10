
import requests
import json
import os
import uuid

BASE_URL = "http://localhost:8000/api/v1/case-studies/preview"

def test_preview_api():
    print("--- Testing Preview API ---")
    
    # Prepare metadata
    metadata = {
        "title": "Preview Case Study",
        "short_description": "This is a preview description.",
        "long_description": "This is a longer preview description for the case study.",
        "problem_solved": "The preview solves the problem of testing.",
        "created_date": "2026-03-04",
        "tech_code": "5g",
        "calc_type_code": "ex-ante",
        "funding_type_code": "public",
        "funding_programme_url": "https://example.com/funding",
        "provider_org_id": 1, # Assuming 1 exists in DB
        "benefits": [
            {
                "name": "Net Carbon Impact",
                "value": 50,
                "unit_code": "tco2",
                "type_code": "environmental",
                "is_net_carbon_impact": True,
                "functional_unit": "per year"
            },
            {
                "name": "Secondary Benefit",
                "value": 10,
                "unit_code": "percent",
                "type_code": "economic",
                "is_net_carbon_impact": False,
                "functional_unit": "per site"
            }
        ],
        "addresses": [
            {
                "admin_unit_l1": "BEL",
                "post_name": "Brussels"
            }
        ]
    }

    # Files (using existing test files if they exist, or creating dummy ones if needed)
    # Based on scripts/ directory seen earlier:
    # "Company Brand Guidelines.pdf"
    # "Company - overview.xlsx"
    # "Company_logo.png"

    path_prefix = "scripts/"
    
    try:
        files = {
            "file_methodology": ("methodology.pdf", open(os.path.join(path_prefix, "Company Brand Guidelines.pdf"), "rb"), "application/pdf"),
            "file_dataset": ("dataset.xlsx", open(os.path.join(path_prefix, "Company - overview.xlsx"), "rb"), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            "file_logo": ("logo.png", open(os.path.join(path_prefix, "Company_logo.png"), "rb"), "image/png"),
            "file_additional_document": ("extra.pdf", open(os.path.join(path_prefix, "Company Brand Guidelines.pdf"), "rb"), "application/pdf")
        }
    except FileNotFoundError:
        print("Test files not found in scripts/ directory. Please run from project root.")
        return

    data = {
        "metadata": json.dumps(metadata),
        "methodology_language": "en",
        "dataset_language": "en",
        "additional_document_language": "en"
    }

    print("Sending POST request to Preview API...")
    try:
        response = requests.post(BASE_URL, data=data, files=files)
        print("Status Code:", response.status_code)
        
        if response.status_code == 200:
            print("Preview Success!")
            result = response.json()
            # Basic validation of response
            print(f"Title in response: {result.get('title')}")
            print(f"Benefits count: {len(result.get('benefits', []))}")
            print(f"Addresses count: {len(result.get('addresses', []))}")
            # print(json.dumps(result, indent=2))
        else:
            print("Preview Failed!")
            print(response.text)
    except Exception as e:
        print("Request failed:", e)
    finally:
        for f in files.values():
            f[1].close()

if __name__ == "__main__":
    test_preview_api()
