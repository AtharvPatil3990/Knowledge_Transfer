import logging
from supabase import create_client, Client
from app.core.config import settings

# Configure explicit logging for systematic low-level debugging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

def get_supabase_client() -> Client:
    """
    Initializes and returns the Supabase client utilizing the Python SDK 
    to communicate securely over HTTPS PostGREST APIs.
    """
    try:
        # Pulling dynamically from the Pydantic settings model
        url = settings.SUPABASE_URL
        
        # Checking for either key name depending on how you resolved the previous Pydantic ValidationError
        key = getattr(settings, 'SUPABASE_KEY', None) or getattr(settings, 'SUPABASE_ANON_KEY', None)
        
        if not key:
            raise ValueError("Supabase authentication key is missing from the configuration.")

        # Initialize the Supabase PostGREST client
        client: Client = create_client(url, key)
        logger.info("Successfully initialized Supabase PostGREST client.")
        return client

    except Exception as e:
        # exc_info=True captures the full stack trace for easier isolation of the root cause
        logger.error(f"FATAL: Failed to initialize Supabase client: {str(e)}", exc_info=True)
        raise e

# Singleton instance to be imported across your FastAPI routes and services
supabase_client = get_supabase_client()