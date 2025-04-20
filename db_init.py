import sqlite3

conn = sqlite3.connect('receipts.db')
c = conn.cursor()

c.execute("""
CREATE TABLE IF NOT EXISTS receipts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT    NOT NULL,      -- Discord user ID
    amount REAL     NOT NULL,      -- Extracted receipt amount
    date TEXT       NOT NULL,      -- Transaction date/time as string
    city TEXT       NOT NULL,      -- Extracted city name
    image_path TEXT NOT NULL,      -- Local path to the saved image
    created_at TEXT DEFAULT CURRENT_TIMESTAMP  -- Insert timestamp
)
""")
conn.commit()
conn.close()
