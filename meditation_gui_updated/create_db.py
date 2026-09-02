# update_db_schema.py
import sqlite3

def update_schema():
    conn = sqlite3.connect('database.db')
    cursor = conn.cursor()

    # Add columns if needed
    cursor.execute("ALTER TABLE feedback ADD COLUMN before_meditation TEXT")
    cursor.execute("ALTER TABLE feedback ADD COLUMN after_meditation TEXT")
    cursor.execute("ALTER TABLE feedback ADD COLUMN helpful TEXT")
    cursor.execute("ALTER TABLE feedback ADD COLUMN suggestions TEXT")

    conn.commit()
    conn.close()

if __name__ == "__main__":
    update_schema()
