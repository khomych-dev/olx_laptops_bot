from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    bot_token: str
    allowed_users: list[int] = []

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


# Creating a single instance of settings for the entire project
settings = Settings()
