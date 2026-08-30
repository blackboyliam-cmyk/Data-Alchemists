from app.database import SessionLocal, migrate_constraints
from app.services.ingestion import fetch_agmarknet

migrate_constraints()
db = SessionLocal()
try:
    job = fetch_agmarknet(db)
    print(job.status, "ok", job.records_ok, "failed", job.records_failed)
    print((job.error_summary or "")[:400])
finally:
    db.close()
