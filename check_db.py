import sqlite3, os

# Check root db
for db_path in ['incidentpilot.db', 'apps/api/incidentpilot.db']:
    if os.path.exists(db_path):
        c = sqlite3.connect(db_path)
        tables = [r[0] for r in c.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        print(f"{db_path}: {tables}")
        c.close()
    else:
        print(f"{db_path}: NOT FOUND")
