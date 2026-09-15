# Import create_engine function to establish database connections
from sqlalchemy import create_engine
# Import DeclarativeBase for model mapping and sessionmaker factory for DB session creation
from sqlalchemy.orm import DeclarativeBase, sessionmaker

# Import global settings module to retrieve database URL configurations
from app.core.config import settings

# Creates the core connection pool manager using the database_url from your Settings file.
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True, #Checks whether a database connection is still alive before using it.
                        # If a connection dropped or timed out,
                        # it automatically reconnects, preventing "connection lost" errors.
)

#Creates a database session factory.
# Calling SessionLocal() creates an active database workspace to perform queries, inserts, or updates.
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False, #Prevents SQLAlchemy from automatically pushing pending changes to the database
                    # before every query; changes are only pushed when explicitly requested.

    autocommit=False, #Ensures database actions are wrapped in a transaction.
                    # Nothing is permanently saved until you explicitly call db.commit().
)

#Uses SQLAlchemy 2.0's DeclarativeBase to create a parent class for all your database models (like User, Task, etc.).
# Any class inheriting from Base becomes mapped directly to a database table.
class Base(DeclarativeBase):
    pass


# Dependency generator function to yield database sessions per request and clean them up afterwards
def get_db():
    db = SessionLocal() # Opens a new database session when a request arrives.

    try:
        # Yield the active database session instance to the caller (e.g., FastAPI endpoint)
        yield db
    finally:
        # Guaranteed execution block to close the database session and release connection back to pool
        db.close()