import sqlite3
import bcrypt
import logging

DATABASE = 'nutricook.db'

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_db():
    """Connects to the specific database."""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row # Return rows that behave like dicts
    return conn

def init_db():
    """Initializes the database schema."""
    try:
        db = get_db()
        cursor = db.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                age INTEGER,
                health_conditions TEXT
            );
        """)
        db.commit()
        logger.info("Database initialized successfully.")
    except sqlite3.Error as e:
        logger.error(f"Database initialization error: {e}")
    finally:
        if db:
            db.close()

def add_user(username, password, age, health_conditions):
    """Adds a new user to the database with a hashed password."""
    password_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed_password = bcrypt.hashpw(password_bytes, salt)

    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (username, password_hash, age, health_conditions) VALUES (?, ?, ?, ?)",
            (username, hashed_password.decode('utf-8'), age, health_conditions)
        )
        conn.commit()
        logger.info(f"User '{username}' added successfully.")
        return True
    except sqlite3.IntegrityError: # Handles UNIQUE constraint violation for username
        logger.warning(f"Username '{username}' already exists.")
        return False
    except sqlite3.Error as e:
        logger.error(f"Error adding user '{username}': {e}")
        return False
    finally:
        conn.close()

def get_user_by_username(username):
    """Retrieves a user by their username."""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        return user # Returns a Row object or None
    except sqlite3.Error as e:
        logger.error(f"Error fetching user '{username}': {e}")
        return None
    finally:
        conn.close()

def get_user_by_id(user_id):
    """Retrieves a user by their ID."""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        return user # Returns a Row object or None
    except sqlite3.Error as e:
        logger.error(f"Error fetching user with ID '{user_id}': {e}")
        return None
    finally:
        conn.close()

def check_password(stored_hash, provided_password):
    """Checks if the provided password matches the stored hash."""
    stored_hash_bytes = stored_hash.encode('utf-8')
    provided_password_bytes = provided_password.encode('utf-8')
    return bcrypt.checkpw(provided_password_bytes, stored_hash_bytes)

# Initialize the database when this module is imported or run
if __name__ == '__main__':
    print("Initializing NutriCook database...")
    init_db()
    print("Database initialization complete.")