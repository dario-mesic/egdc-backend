import json
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlmodel import SQLModel
from app.db.session import get_session, engine
from app.db.init_db import init_db
from app.models.references import RefSector, RefOrganizationType, RefFundingType, RefCalculationType, RefBenefitUnit, RefBenefitType, RefTechnology, RefCountry, RefLanguage
from app.models.organization import Organization, ContactPoint
from app.models.case_study import CaseStudy, Address, Benefit, ImageObject, Methodology, Dataset, CaseStudyStatus
from app.models.user import User, UserRole
from app.core.security import get_password_hash
import os
import aiofiles

router = APIRouter()

@router.post("/seed")
async def seed_data(session: AsyncSession = Depends(get_session)):
    # 0. Reset DB (Drop All Tables to ensure schema updates)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)

    # 1. Initialize DB (Create Tables)
    await init_db()

    # 1.5 Seed Users
    users = [
        {"email": "admin@example.com", "role": UserRole.ADMIN, "hashed_password": get_password_hash("password123")},
        {"email": "custodian@example.com", "role": UserRole.CUSTODIAN, "hashed_password": get_password_hash("password123")},
        {"email": "owner@example.com", "role": UserRole.DATA_OWNER, "hashed_password": get_password_hash("password123")},
    ]
    
    data_owner_id = None
    
    for u in users:
        result = await session.execute(select(User).where(User.email == u["email"]))
        existing_user = result.scalars().first()
        if not existing_user:
            user = User(**u)
            session.add(user)
            await session.flush()
            if user.role == UserRole.DATA_OWNER:
                data_owner_id = user.id
        else:
            # Update password if needed, but for now just get ID
            if existing_user.role == UserRole.DATA_OWNER:
                data_owner_id = existing_user.id

    # 3. Load Data
    data_path = "app/db/seeds/data.json"
    if not os.path.exists(data_path):
        raise HTTPException(status_code=404, detail="Seed data file not found")
    
    async with aiofiles.open(data_path, "r", encoding="utf-8") as f:
        content = await f.read()
        data = json.loads(content)

    # 3. Seed References
    ref_data = data.get("reference_data", {})
    
    # Helper to seed simple ref tables
    async def seed_ref(model, items):
        if not items: return
        for item in items:
            existing = await session.get(model, item["code"])
            if not existing:
                session.add(model(**item))
    
    await seed_ref(RefSector, ref_data.get("sectors"))
    await seed_ref(RefOrganizationType, ref_data.get("org_types"))
    await seed_ref(RefFundingType, ref_data.get("funding_types"))
    await seed_ref(RefCalculationType, ref_data.get("calculation_types"))
    await seed_ref(RefBenefitUnit, ref_data.get("benefit_units"))
    await seed_ref(RefBenefitType, ref_data.get("benefit_types"))
    await seed_ref(RefTechnology, ref_data.get("technologies"))
    await seed_ref(RefCountry, ref_data.get("countries"))

    # Seed Languages (Hardcoded per requirement)
    eu_languages = [
        {"code": "bg", "label": "Bulgarian"},
        {"code": "hr", "label": "Croatian"},
        {"code": "cs", "label": "Czech"},
        {"code": "da", "label": "Danish"},
        {"code": "nl", "label": "Dutch"},
        {"code": "en", "label": "English"},
        {"code": "et", "label": "Estonian"},
        {"code": "fi", "label": "Finnish"},
        {"code": "fr", "label": "French"},
        {"code": "de", "label": "German"},
        {"code": "el", "label": "Greek"},
        {"code": "hu", "label": "Hungarian"},
        {"code": "ga", "label": "Irish"},
        {"code": "it", "label": "Italian"},
        {"code": "lv", "label": "Latvian"},
        {"code": "lt", "label": "Lithuanian"},
        {"code": "mt", "label": "Maltese"},
        {"code": "pl", "label": "Polish"},
        {"code": "pt", "label": "Portuguese"},
        {"code": "ro", "label": "Romanian"},
        {"code": "sk", "label": "Slovak"},
        {"code": "sl", "label": "Slovenian"},
        {"code": "es", "label": "Spanish"},
        {"code": "sv", "label": "Swedish"}
    ]
    await seed_ref(RefLanguage, eu_languages)
    
    await session.commit() # Commit refs first

    # 4. Seed Organizations
    orgs = data.get("organizations", [])
    name_to_org_map = {}
    
    for org_data in orgs:
        # Check by name
        stmt = select(Organization).where(Organization.name == org_data["name"])
        result = await session.execute(stmt)
        existing_org = result.scalars().first()
        
        if not existing_org:
            contacts = org_data.pop("contact_points", [])
            org = Organization(**org_data)
            session.add(org)
            await session.flush() # Get ID
            
            for c in contacts:
                session.add(ContactPoint(**c, organization_id=org.id))
            
            name_to_org_map[org.name] = org
        else:
            name_to_org_map[existing_org.name] = existing_org
    
    await session.commit()

    # 5. Seed Case Studies
    cases = data.get("case_studies", [])
    for case_data in cases:
        stmt = select(CaseStudy).where(CaseStudy.title == case_data["title"])
        result = await session.execute(stmt)
        existing_case = result.scalars().first()
        
        if not existing_case:
            # Extract nested
            benefits_data = case_data.pop("benefits", [])
            addresses_data = case_data.pop("addresses", [])
            providers = case_data.pop("providers", [])
            methodology_data = case_data.pop("methodology", None)
            logo_data = case_data.pop("logo", None)
            dataset_data = case_data.pop("dataset", None)
            additional_doc_data = case_data.pop("additional_document", None)
            
            # Convert string date to date object if present
            if case_data.get("created_date"):
                case_data["created_date"] = date.fromisoformat(case_data["created_date"])
            
            # Create Main Entity
            case_study = CaseStudy(**case_data)
            case_study.created_by = data_owner_id
            case_study.status = CaseStudyStatus.PUBLISHED
            
            # Initialize M2M lists to empty to avoid implicit lazy load on append
            case_study.is_provided_by = []
            case_study.is_funded_by = []
            case_study.is_used_by = []
            
            # Handle One-to-One
            if methodology_data:
                meth = Methodology(**methodology_data, language_code="en")
                session.add(meth)
                await session.flush()
                case_study.methodology_id = meth.id
                
            if logo_data:
                logo = ImageObject(**logo_data)
                session.add(logo)
                await session.flush()
                case_study.logo_id = logo.id
            
            if dataset_data:
                dataset = Dataset(**dataset_data, language_code="en")
                session.add(dataset)
                await session.flush()
                case_study.dataset_id = dataset.id
            
            if additional_doc_data:
                add_doc = Document(**additional_doc_data, language_code="en")
                session.add(add_doc)
                await session.flush()
                case_study.additional_document_id = add_doc.id
            
            session.add(case_study)
            await session.flush()
            
            # Nested Lists
            for b in benefits_data:
                benefit = Benefit(**b, case_study_id=case_study.id)
                session.add(benefit)
            
            for a in addresses_data:
                session.add(Address(**a, case_study_id=case_study.id))
                
            # Links
            for p_name in providers:
                org = name_to_org_map.get(p_name)
                if org:
                    # Append works now because we initialized the list
                    case_study.is_provided_by.append(org)
                    
            await session.commit()
            
    return {"message": "Database seeded successfully"}
