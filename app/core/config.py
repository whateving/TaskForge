# Import BaseSettings class and SettingsConfigDict from pydantic-settings for application configuration management
from pydantic_settings import BaseSettings, SettingsConfigDict


# Define configuration model class extending Pydantic's BaseSettings to load and validate environment variables
class Settings(BaseSettings):
    # Database connection parameters (automatically mapped from POSTGRES_USER environment variable)
    postgres_user: str
    # Database connection password (automatically mapped from POSTGRES_PASSWORD environment variable)
    postgres_password: str
    # Target database name (automatically mapped from POSTGRES_DB environment variable)
    postgres_db: str

    # Full database connection string/DSN (e.g., postgresql://user:pass@host:5432/dbname)
    database_url: str
    # Redis connection string/DSN (e.g., redis://localhost:6379/0)
    redis_url: str

    # Configure Pydantic model behaviors to read configurations directly from a local environment file
    model_config = SettingsConfigDict(
        env_file=".env",              # Path to the environment variables file
        env_file_encoding="utf-8",    # Character encoding for the .env file
    )


# Instantiate settings object to load, validate, and parse environment variables upon application start
settings = Settings()