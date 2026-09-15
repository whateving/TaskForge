from fastapi import FastAPI

from app.api.jobs import router as jobs_router
from app.db.database import Base, engine

# Reads all models inheriting from Base (like your Job model)
# and creates their corresponding tables in PostgreSQL if they don't already exist.
Base.metadata.create_all(bind=engine)


app = FastAPI(
    title="TaskForge",
    description="Distributed background job processing platform",
    version="0.1.0",
)


app.include_router(jobs_router)


@app.get("/health")
def health_check():
    return {"status": "ok"}