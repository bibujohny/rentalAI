import os

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///rentalai.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # External APIs
    OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")

class DevConfig(Config):
    DEBUG = True

class ProdConfig(Config):
    DEBUG = False

config_by_name = {
    "development": DevConfig,
    "production": ProdConfig,
    "default": DevConfig,
}
