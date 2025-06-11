import psycopg2
from flask import current_app
from werkzeug.security import generate_password_hash, check_password_hash

# --- Database Connection ---
def get_db_connection():
    """Establishes a connection to the PostgreSQL database."""
    try:
        # Use current_app.config to get the DATABASE_URL
        conn = psycopg2.connect(current_app.config['DATABASE_URL'])
        return conn
    except psycopg2.Error as e:
        print(f"Database connection error: {e}")
        # In a real application, you'd want more robust error handling
        # and logging.
        return None

# --- Password Hashing Utilities ---
def hash_password(password):
    """
    Hashes a password using Werkzeug's secure hashing.
    """
    return generate_password_hash(password)

def check_password(hashed_password, password):
    """
    Checks if a given password matches a hashed password using Werkzeug.
    """
    return check_password_hash(hashed_password, password)

# --- Other Database Interaction Functions (to be added later) ---
# You can add functions here for common database operations,
# e.g., get_user_by_username, create_patient, add_medical_record, etc.
# This keeps database logic centralized.
