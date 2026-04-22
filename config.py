import os
import secrets
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', secrets.token_hex(32))
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL', 'sqlite:///fxshop.db')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    STRIPE_PUBLIC_KEY = os.environ.get('STRIPE_PUBLIC_KEY', 'pk_test_placeholder')
    STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY', 'sk_test_placeholder')
    STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET', 'whsec_placeholder')
    
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'True').lower() == 'true'
    MAIL_USE_SSL = os.environ.get('MAIL_USE_SSL', 'False').lower() == 'true'
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', MAIL_USERNAME)
    
    UPLOAD_FOLDER_FILES = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'secure_uploads')
    UPLOAD_FOLDER_IMAGES = os.path.join(os.path.abspath(os.path.dirname(__file__)), 'static', 'uploads', 'images')
    
    ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD')
    if ADMIN_PASSWORD is None:
        ADMIN_PASSWORD = ''.join(secrets.choice('abcdefghijklmnopqrstuvwxyz0123456789') for _ in range(16))
    
