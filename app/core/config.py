from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "EGDC Repository"
    API_V1_STR: str = "/api/v1"
    DATABASE_URL: str = "postgresql://user:pass@localhost:5432/db"
    BACKEND_CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:8000"]

    class Config:
        case_sensitive = True
        env_file = ".env"

settings = Settings()
