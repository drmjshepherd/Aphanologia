import psycopg2
from psycopg2.extras import RealDictCursor

# Database Connection Parameters
DB_CONFIG = {
    "dbname": "Aphanologia",
    "user": "postgres",
    "password": "actual_password_here",  # <--- UPDATE THIS to your local PostgreSQL password
    "host": "localhost",
    "port": "5432"
}

def get_db_connection():
    """Establishes and returns a connection to the local Aphanologia PostGIS database."""
    try:
        conn = psycopg2.connect(**DB_CONFIG, cursor_factory=RealDictCursor)
        return conn
    except Exception as e:
        print(f"❌ Error connecting to Aphanologia database: {e}")
        raise e
