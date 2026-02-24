import requests
import json
import os

BASE_URL = "http://localhost:8000/api/v1/case-studies/"
LOGIN_URL = "http://localhost:8000/api/v1/login/access-token"

def get_auth_token():
    # Login credentials matching one of your seeded Data Owner users
    # Change these if you used different credentials in your seed.py
    login_data = {
        "username": "owner@example.com", 
        "password": "password123"             
    }
    print(f"Authenticating at {LOGIN_URL}...")
    response = requests.post(LOGIN_URL, data=login_data)
    
    if response.status_code == 200:
        print("Authentication successful.")
        return response.json().get("access_token")
    else:
        print("Login failed! Please check your test credentials.")
        print(response.text)
        return None

def test_create_case_study():
    # 1. Get the JWT Token
    token = get_auth_token()
    if not token:
        return

    # Add token to headers
    headers = {
        "Authorization": f"Bearer {token}"
    }

    # 2. Prepare metadata with ALL the new parameters
    metadata = {
        "title": "Company Case Study",
        "status": "pending_approval",
        "short_description": "Short description for Company company case study",
        "long_description": "A long description for Company company case study",
        "problem_solved": "Solved the problem by using Company in changing the environment",
        "created_date": "2026-01-15",
        "tech_code": "5g",
        "calc_type_code": "ex-ante",
        
        # Changed to 'public' to test the new URL validation rule
        "funding_type_code": "public", 
        "funding_programme_url": "https://ec.europa.eu/horizon-europe", 
        
        "benefits": [
            {
                "name": "Net Carbon Impact",
                "value": 100,
                "unit_code": "tco2",
                "type_code": "environmental",
                "is_net_carbon_impact": True,         # NEW: Mandatory flag
                "functional_unit": "per base station" # NEW: Functional unit
            },
            {
                "name": "Operational Cost Savings",
                "value": 15,
                "unit_code": "percent",
                "type_code": "economic",
                "is_net_carbon_impact": False,        # NEW: Mandatory flag
                "functional_unit": "per base station" # NEW: Functional unit
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
        "methodology_language": "en",
        "dataset_language": "en",
        "additional_document_language": "en"
    }

    print("Preparing files...")
    # 3. Files to upload (including the new additional_document)
    try:
        files = {
            "file_methodology": ("Company Brand Guidelines.pdf", open("scripts/Company Brand Guidelines.pdf", "rb"), "application/pdf"),
            "file_dataset": ("Company - overview.xlsx", open("scripts/Company - overview.xlsx", "rb"), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            "file_logo": ("Company_logo.png", open("scripts/Company_logo.png", "rb"), "image/png"),
            
            # NEW: Testing the additional document upload (reusing the PDF to save you time)
            "file_additional_document": ("Extra_Documentation.pdf", open("scripts/Company Brand Guidelines.pdf", "rb"), "application/pdf")
        }
    except FileNotFoundError as e:
        print(f"Error: Missing test file - {e}")
        return

    # Multipart data
    data = {
        "metadata": json.dumps(metadata)
    }

    print("Sending POST request to:", BASE_URL)
    try:
        # Pass the headers containing the JWT token
        response = requests.post(BASE_URL, headers=headers, data=data, files=files)
        print("Status Code:", response.status_code)
        
        if response.status_code in [200, 201]:
            print("Success! Case study created.")
            print(json.dumps(response.json(), indent=2))
        else:
            print("Error Details:")
            try:
                print(json.dumps(response.json(), indent=2))
            except:
                print(response.text)
    except Exception as e:
        print("Request failed:", e)
    finally:
        for f in files.values():
            f[1].close()

def test_create_draft():
    print("\n--- Testing Draft Submission ---")
    token = get_auth_token()
    if not token: return

    headers = {"Authorization": f"Bearer {token}"}

    # Deliberately incomplete metadata to prove drafts bypass strict validation
    metadata = {
        "title": "My Incomplete Draft",
        "status": "draft", # <--- NEW: Tells the backend to bypass strict validation
        "tech_code": "ai",
        "addresses": [],   # Empty addresses allowed for drafts
        "benefits": []     # Missing Net Carbon Impact allowed for drafts
    }

    data = {"metadata": json.dumps(metadata)}
    files = {} # Force multipart/form-data even without files

    try:
        response = requests.post(BASE_URL, headers=headers, data=data, files=files) # Properly formatted multipart request
        if response.status_code in [200, 201]:
            print("Success! Draft saved despite missing mandatory fields.")
            print(json.dumps(response.json(), indent=2))
        else:
            print("Error: Draft was rejected!")
            print(response.text)
    except Exception as e:
        print("Request failed:", e)

if __name__ == "__main__":
    test_create_case_study()
    test_create_draft()