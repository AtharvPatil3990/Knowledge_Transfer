from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Knowledge Handover API"
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()