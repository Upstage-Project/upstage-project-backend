# create_tables.py
from app.db.session import engine
from app.db.models import Base  # models.py 안에 Base가 있어야 함

Base.metadata.create_all(bind=engine)
print("✅ tables created")
