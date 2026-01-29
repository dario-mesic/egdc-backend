import requests
import json
import os

BASE_URL = "http://localhost:8000/api/v1/case-studies/"

def test_create_case_study():
    # Prepare metadata
    metadata = {
        "title": "Company Case Study",
        "short_description": "Short description for Company company case study",
        "long_description": "A long description for Company company case study",
        "problem_solved": "Solved the problem by using Company in changing the environment",
        "created_date": "2026-01-15",
        "tech_code": "5g",
        "calc_type_code": "ex-ante",
        "funding_type_code": "private",
        "benefits": [
            {
                "name": "Environmental Impact",
                "value": 100,
                "unit_code": "tco2",
                "type_code": "environmental"
            }
        ],
        "addresses": [
            {
                "admin_unit_l1": "CRO",
                "post_name": "Zagreb"
            }
        ],
        "provider_org_id": 9,
        "funder_org_id": 1,
        "methodology_language_code": "en",
        "dataset_language_code": "en"
    }

    # Files to upload
    files = {
        "file_methodology": ("Company Brand Guidelines.pdf", open("scripts/Company Brand Guidelines.pdf", "rb"), "application/pdf"),
        "file_dataset": ("Company - overview.xlsx", open("scripts/Company - overview.xlsx", "rb"), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        "file_logo": ("Company_logo.png", open("scripts/Company_logo.png", "rb"), "image/png")
    }

    # Multipart data
    data = {
        "metadata": json.dumps(metadata)
    }

    print("Sending POST request to:", BASE_URL)
    try:
        response = requests.post(BASE_URL, data=data, files=files)
        print("Status Code:", response.status_code)
        if response.status_code == 200:
            print("Success!")
            print(json.dumps(response.json(), indent=2))
        else:
            print("Error Details:")
            print(response.text)
    except Exception as e:
        print("Request failed:", e)
    finally:
        for f in files.values():
            f[1].close()

if __name__ == "__main__":
    test_create_case_study()
