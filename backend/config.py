import os

class Config:
    # A strong secret key is crucial for session security.
    # In a production environment, generate a complex random string
    # and load it from environment variables or a secure configuration system.
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'cda2ebc7fabff838c58fd6441e4cd2400a8697c53032876d35e27759b41eff7e'

    # PostgreSQL database URI. Replace with your actual credentials.
    # Format: postgresql://user:password@host:port/database_name
    DATABASE_URL = os.environ.get('DATABASE_URL') or 'postgresql://postgres:Next%40123@localhost:5432/reports'

    # Session configuration (using filesystem for simplicity; a DB is better for production)
    SESSION_TYPE = 'filesystem'
    SESSION_PERMANENT = False
    SESSION_USE_SIGNER = True # Sign the session cookie to prevent tampering
    SESSION_KEY_PREFIX = 'vhr_session_'

    # Path for session files (relative to the project root, outside 'backend' for clarity)
    SESSION_FILE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'flask_session')
