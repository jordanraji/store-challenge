from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://store:store@localhost:5432/store"

    session_secret: str = ""
    secure_cookies: bool = False
