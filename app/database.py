from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from app.config import settings, BASE_DIR
from pathlib import Path

# Fix relative SQLite DB URL if needed
db_url = settings.DB_URL
if db_url.startswith("sqlite:///./") or db_url.startswith("sqlite:///"):
    # ensure storage directory exists
    rel_path = db_url.replace("sqlite:///", "")
    full_path = (BASE_DIR / rel_path).resolve()
    full_path.parent.mkdir(parents=True, exist_ok=True)
    engine_url = f"sqlite:///{full_path}"
else:
    engine_url = db_url

engine = create_engine(
    engine_url,
    connect_args={"check_same_thread": False} if engine_url.startswith("sqlite") else {}
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    from app.models.video import Video  # ensure models are registered
    Base.metadata.create_all(bind=engine)
    
    # Auto-migrate columns if table already exists in SQLite
    try:
        from sqlalchemy import text
        with engine.connect() as conn:
            conn.execute(text("ALTER TABLE videos ADD COLUMN progress_percent FLOAT DEFAULT 0.0"))
            conn.commit()
    except Exception:
        # Column already exists or table freshly created
        pass

