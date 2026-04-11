import json
import logging
from datetime import date
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlmodel import SQLModel
from app.db.session import get_session, engine, async_session
from app.db.init_db import init_db
from app.models.references import RefSector, RefOrganizationType, RefFundingType, RefCalculationType, RefBenefitUnit, RefBenefitType, RefTechnology, RefCountry, RefLanguage
from app.models.organization import Organization, ContactPoint
from app.models.case_study import CaseStudy, Address, Benefit, ImageObject, Methodology, Dataset, CaseStudyStatus
from app.models.user import User, UserRole
from app.core.security import get_password_hash
import os
import aiofiles

router = APIRouter()
logger = logging.getLogger(__name__)

async def run_seed(session: AsyncSession) -> dict:
    """Core seeding logic. Call from POST /seed or from CLI (python -m app.api.v1.endpoints.seed)."""
    logger.info("Seed started: dropping all tables.")
    # 0. Reset DB (Drop All Tables to ensure schema updates)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.drop_all)

    # 1. Initialize DB (Create Tables + pg_trgm extension)
    await init_db()
    logger.info("Tables recreated successfully.")

    # 1.5 Seed Users
    # IMPORTANT: get_password_hash is called here exactly ONCE per user on the
    # plain-text password string. The User model has no hashing validator, so
    # passing an already-hashed value would cause double-hashing. Never pass a
    # bcrypt hash back into get_password_hash.
    plain_password = "password123"
    users = [
        {"email": "admin@example.com",     "role": UserRole.ADMIN,      "hashed_password": get_password_hash(plain_password)},
        {"email": "custodian@example.com", "role": UserRole.CUSTODIAN,  "hashed_password": get_password_hash(plain_password)},
        {"email": "owner@example.com",     "role": UserRole.DATA_OWNER, "hashed_password": get_password_hash(plain_password)},
    ]

    data_owner_id = None

    for u in users:
        try:
            result = await session.execute(select(User).where(User.email == u["email"]))
            existing_user = result.scalars().first()
            if not existing_user:
                user = User(**u)
                session.add(user)
                await session.flush()
                logger.info("Created user: %s (role=%s)", u["email"], u["role"])
                if user.role == UserRole.DATA_OWNER:
                    data_owner_id = user.id
            else:
                logger.info("User already exists, skipping: %s", u["email"])
                if existing_user.role == UserRole.DATA_OWNER:
                    data_owner_id = existing_user.id
        except Exception as exc:
            logger.error("Failed to create user %s: %s", u["email"], exc, exc_info=True)
            raise HTTPException(status_code=500, detail=f"Failed to create user {u['email']}: {exc}") from exc

    # 3. Load Data
    data_path = "app/db/seeds/data.json"
    if not os.path.exists(data_path):
        logger.error("Seed data file not found at: %s", data_path)
        raise HTTPException(status_code=404, detail="Seed data file not found")

    async with aiofiles.open(data_path, "r", encoding="utf-8") as f:
        content = await f.read()
        data = json.loads(content)
    logger.info("Loaded seed data from %s", data_path)

    # 3. Seed References
    ref_data = data.get("reference_data", {})

    async def seed_ref(model, items):
        if not items:
            return
        inserted = 0
        for item in items:
            try:
                existing = await session.get(model, item["code"])
                if not existing:
                    session.add(model(**item))
                    inserted += 1
            except Exception as exc:
                logger.error(
                    "Failed to seed %s with code=%s: %s",
                    model.__name__, item.get("code"), exc, exc_info=True,
                )
                raise
        logger.info("Seeded %s: %d new records", model.__name__, inserted)

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

    await session.commit()
    logger.info("Reference data committed.")

    # 4. Seed Organizations
    orgs = data.get("organizations", [])
    name_to_org_map = {}

    for org_data in orgs:
        try:
            stmt = select(Organization).where(Organization.name == org_data["name"])
            result = await session.execute(stmt)
            existing_org = result.scalars().first()

            if not existing_org:
                contacts = org_data.pop("contact_points", [])
                org = Organization(**org_data)
                session.add(org)
                await session.flush()

                for c in contacts:
                    session.add(ContactPoint(**c, organization_id=org.id))

                name_to_org_map[org.name] = org
                logger.info("Created organization: %s (id=%s)", org.name, org.id)
            else:
                name_to_org_map[existing_org.name] = existing_org
                logger.info("Organization already exists, skipping: %s", existing_org.name)
        except Exception as exc:
            logger.error(
                "Failed to seed organization '%s': %s",
                org_data.get("name", "<unknown>"), exc, exc_info=True,
            )
            raise HTTPException(
                status_code=500,
                detail=f"Failed to seed organization '{org_data.get('name')}': {exc}",
            ) from exc

    await session.commit()
    logger.info("Organizations committed: %d total in map.", len(name_to_org_map))

    # 5. Seed Case Studies
    cases = data.get("case_studies", [])
    seeded_count = 0

    for case_data in cases:
        case_title = case_data.get("title", "<untitled>")
        try:
            stmt = select(CaseStudy).where(CaseStudy.title == case_title)
            result = await session.execute(stmt)
            existing_case = result.scalars().first()

            if existing_case:
                logger.info("Case study already exists, skipping: %s", case_title)
                continue

            # Extract nested data before unpacking into the model
            benefits_data = case_data.pop("benefits", [])
            addresses_data = case_data.pop("addresses", [])
            providers = case_data.pop("providers", [])
            methodology_data = case_data.pop("methodology", None)
            logo_data = case_data.pop("logo", None)
            dataset_data = case_data.pop("dataset", None)
            additional_doc_data = case_data.pop("additional_document", None)

            if case_data.get("created_date"):
                case_data["created_date"] = date.fromisoformat(case_data["created_date"])
            
            case_data.setdefault("language_code", "en")

            case_study = CaseStudy(**case_data)
            case_study.created_by = data_owner_id
            case_study.status = CaseStudyStatus.PUBLISHED

            # Initialize M2M lists to empty to avoid implicit lazy load on append
            case_study.is_provided_by = []
            case_study.is_funded_by = []
            case_study.is_used_by = []

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
                add_doc = Dataset(**additional_doc_data, language_code="en")
                session.add(add_doc)
                await session.flush()
                case_study.additional_document_id = add_doc.id

            session.add(case_study)
            await session.flush()

            for b in benefits_data:
                session.add(Benefit(**b, case_study_id=case_study.id))

            for a in addresses_data:
                session.add(Address(**a, case_study_id=case_study.id))

            for p_name in providers:
                org = name_to_org_map.get(p_name)
                if org:
                    case_study.is_provided_by.append(org)
                else:
                    logger.warning(
                        "Provider '%s' not found in org map for case study '%s'",
                        p_name, case_title,
                    )

            await session.commit()
            seeded_count += 1
            logger.info("Seeded case study: %s (id=%s)", case_title, case_study.id)

        except Exception as exc:
            await session.rollback()
            logger.error(
                "Failed to seed case study '%s': %s", case_title, exc, exc_info=True
            )
            raise HTTPException(
                status_code=500,
                detail=f"Failed to seed case study '{case_title}': {exc}",
            ) from exc

    logger.info("Seeding complete. %d case studies inserted.", seeded_count)
    return {"message": f"Database seeded successfully. {seeded_count} case studies inserted."}


@router.post("/seed")
async def seed_data(session: AsyncSession = Depends(get_session)):
    return await run_seed(session)


if __name__ == "__main__":
    import asyncio

    async def main() -> None:
        async with async_session() as session:
            try:
                result = await run_seed(session)
                print(result.get("message", result))
            except Exception as e:
                logger.exception("Seed failed: %s", e)
                raise SystemExit(1) from e

    asyncio.run(main())
