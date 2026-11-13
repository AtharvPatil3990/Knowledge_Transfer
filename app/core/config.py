from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    PROJECT_NAME: str = "Knowledge Handover API"
    SUPABASE_URL: str
    SUPABASE_ANON_KEY: str
    GITHUB_TOKEN: str | None = None
    GITHUB_CLIENT_ID: str | None = None
    GITHUB_CLIENT_SECRET: str | None = None
    EMBEDDING_MODEL: str = "BAAI/bge-small-en-v1.5"
    GROQ_API_KEY: str

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()