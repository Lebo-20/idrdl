import json
import sqlite3
import os

PROCESSED_FILE = "processed.json"
DB_PATH = "bot_data.db"

def migrate():
    if not os.path.exists(PROCESSED_FILE):
        print("No processed.json found. Skipping migration.")
        return

    try:
        with open(PROCESSED_FILE, "r") as f:
            data = json.load(f)
            if not isinstance(data, list):
                print("Invalid processed.json content.")
                return
    except Exception as e:
        print(f"Error reading processed.json: {e}")
        return

    print(f"Migrating {len(data)} IDs from processed.json to SQLite...")

    conn = sqlite3.connect(DB_PATH)
    # Ensure table exists
    conn.execute("CREATE TABLE IF NOT EXISTS processed (book_id TEXT PRIMARY KEY)")
    
    count = 0
    for bid in data:
        try:
            conn.execute("INSERT OR IGNORE INTO processed (book_id) VALUES (?)", (str(bid),))
            count += 1
        except: pass
    
    conn.commit()
    conn.close()
    print(f"Successfully migrated {count} IDs.")
    
    # Optional: Backup the old file
    os.rename(PROCESSED_FILE, PROCESSED_FILE + ".bak")
    print(f"Old file renamed to {PROCESSED_FILE}.bak")

if __name__ == "__main__":
    migrate()
