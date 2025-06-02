# reset_db.py
from backend.models import Base
from backend.database import engine

print("WARNING: This will delete all data in the database!")
confirmation = input("Type 'YES' to confirm: ")

if confirmation == "YES":
    print("Dropping all tables...")
    Base.metadata.drop_all(bind=engine)
    print("Creating new tables...")
    Base.metadata.create_all(bind=engine)
    print("Database reset complete!")
else:
    print("Database reset cancelled.")

