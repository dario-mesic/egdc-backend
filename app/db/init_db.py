from sqlmodel import SQLModel
from app.db.session import engine
# Import all models to ensure they are registered
from app.models.references import *
from app.models.organization import *
from app.models.case_study import *

async def init_db():
    async with engine.begin() as conn:
        # await conn.run_sync(SQLModel.metadata.drop_all) # Optional: Reset DB
        await conn.run_sync(SQLModel.metadata.create_all)
