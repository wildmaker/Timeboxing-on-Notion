import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'default_secret_key')
    SQLALCHEMY_DATABASE_URI = os.getenv('DATABASE_URL', 'sqlite:///notion_automation.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    NOTION_API_BASE_URL = 'https://api.notion.com/v1/'
    NOTION_VERSION = '2022-06-28'
