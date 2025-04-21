import sqlite3

DB_NAME = "receipts.db"

def get_connection():
    """
    Returns a new SQLite connection. Uses check_same_thread=False
    to avoid issues in multi-threaded environments like Discord bots.
    """
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def init_db():
    """
    Initializes the receipts table if it doesn't exist.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS receipts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        amount TEXT NOT NULL,
        date TEXT NOT NULL,
        city TEXT NOT NULL,
        image_path TEXT NOT NULL,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )
    """)
    conn.commit()
    conn.close()
