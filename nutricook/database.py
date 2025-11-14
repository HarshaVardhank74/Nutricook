import sqlite3
import bcrypt
import logging
import datetime # Needed for timestamps

DATABASE = 'nutricook.db'

# Setup basic logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initializes the database schema, adding new table and column if they don't exist."""
    try:
        db = get_db()
        cursor = db.cursor()
        # Create users table (ensure total_health_score column exists)
        try:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT UNIQUE NOT NULL,
                    password_hash TEXT NOT NULL,
                    age INTEGER,
                    health_conditions TEXT,
                    total_health_score INTEGER DEFAULT 0
                );
            """)
            # Add total_health_score column if it doesn't exist (for migrations)
            cursor.execute("ALTER TABLE users ADD COLUMN total_health_score INTEGER DEFAULT 0;")
            logger.info("Added 'total_health_score' column to users table.")
        except sqlite3.OperationalError as e:
            if "duplicate column name" not in str(e): # Ignore error if column already exists
               logger.error(f"Error modifying users table: {e}")
            else:
               logger.info("'total_health_score' column already exists in users table.")


        # Create checked_meals table
        cursor.execute("""
             CREATE TABLE IF NOT EXISTS checked_meals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                checked_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                meal_name TEXT,
                estimated_nutrition TEXT, -- Store as JSON string or simple text
                health_assessment TEXT,
                assigned_score INTEGER DEFAULT 0,
                image_filename TEXT, -- Optional: store filename if needed
                FOREIGN KEY (user_id) REFERENCES users (id)
            );
        """)

        db.commit()
        logger.info("Database initialized/updated successfully (users, checked_meals).")
    except sqlite3.Error as e:
        logger.error(f"Database initialization/update error: {e}")
    finally:
        if db:
            db.close()

# --- User Functions (Keep existing add_user, check_password) ---
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
    """Retrieves a user by their username, including score."""
    conn = get_db()
    try:
        cursor = conn.cursor()
        # Ensure we select the score
        cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
        user = cursor.fetchone()
        return user # Returns a Row object or None
    except sqlite3.Error as e:
        logger.error(f"Error fetching user '{username}': {e}")
        return None
    finally:
        conn.close()

def get_user_by_id(user_id):
    """Retrieves a user by their ID, including score."""
    conn = get_db()
    try:
        cursor = conn.cursor()
         # Ensure we select the score
        cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        user = cursor.fetchone()
        return user # Returns a Row object or None
    except sqlite3.Error as e:
        logger.error(f"Error fetching user with ID '{user_id}': {e}")
        return None
    finally:
        conn.close()

def update_user_score(user_id, points_to_add):
    """Updates the user's total health score."""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE users SET total_health_score = total_health_score + ? WHERE id = ?",
            (points_to_add, user_id)
        )
        conn.commit()
        logger.info(f"Updated score for user ID {user_id} by {points_to_add} points.")
        return True
    except sqlite3.Error as e:
        logger.error(f"Error updating score for user ID {user_id}: {e}")
        return False
    finally:
        conn.close()

def check_password(stored_hash, provided_password):
    """Checks if the provided password matches the stored hash."""
    stored_hash_bytes = stored_hash.encode('utf-8')
    provided_password_bytes = provided_password.encode('utf-8')
    return bcrypt.checkpw(provided_password_bytes, stored_hash_bytes)
# --- Checked Meal Functions ---

def add_checked_meal(user_id, meal_name, nutrition, assessment, score, image_filename=None):
    """Adds a record of a checked meal."""
    conn = get_db()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO checked_meals
            (user_id, meal_name, estimated_nutrition, health_assessment, assigned_score, image_filename, checked_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (user_id, meal_name, nutrition, assessment, score, image_filename, datetime.datetime.now()))
        conn.commit()
        logger.info(f"Added checked meal '{meal_name}' for user ID {user_id}.")
        return True
    except sqlite3.Error as e:
        logger.error(f"Error adding checked meal for user ID {user_id}: {e}")
        return False
    finally:
        conn.close()

def get_user_checked_meals(user_id, limit=5):
    """Retrieves the most recent checked meals for a user, converting timestamp."""
    conn = get_db()
    meals_list = [] # Store results as dictionaries
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, user_id, checked_at, meal_name, estimated_nutrition,
                   health_assessment, assigned_score, image_filename
            FROM checked_meals
            WHERE user_id = ?
            ORDER BY checked_at DESC
            LIMIT ?
        """, (user_id, limit))
        fetched_rows = cursor.fetchall() # Fetch all rows

        for row in fetched_rows:
            # Convert row to a mutable dictionary
            meal_dict = dict(row)

            # --- Convert checked_at string to datetime object ---
            try:
                # Attempt parsing assuming ISO format (YYYY-MM-DD HH:MM:SS.ffffff)
                # Adjust the format string '%Y-%m-%d %H:%M:%S.%f' if SQLite stores it differently
                meal_dict['checked_at'] = datetime.datetime.fromisoformat(row['checked_at'])
                # Alternative if microseconds are not always present:
                # meal_dict['checked_at'] = datetime.datetime.strptime(row['checked_at'].split('.')[0], '%Y-%m-%d %H:%M:%S')
            except (ValueError, TypeError) as e:
                logger.warning(f"Could not parse timestamp '{row['checked_at']}': {e}. Using current time as fallback.")
                # Provide a fallback or handle the error differently if needed
                meal_dict['checked_at'] = datetime.datetime.now()

            meals_list.append(meal_dict)

        return meals_list # Return a list of dictionaries

    except sqlite3.Error as e:
        logger.error(f"Error fetching checked meals for user ID {user_id}: {e}")
        return [] # Return empty list on error
    finally:
        if conn:
            conn.close()


# IMPORTANT: Run this script once directly to ensure tables/columns are created/updated
# python database.py
if __name__ == '__main__':
    print("Initializing/Updating NutriCook database...")
    init_db()
    print("Database initialization/update complete.")