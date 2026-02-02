from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from qdrant_client import QdrantClient
from pathlib import Path

DATABASE_URL = "mysql+pymysql://dev:dev@localhost:3306/recipe_app"

# setup qdrant client connection
QD_COLLECTION = "recipes"
qd_client = QdrantClient(host="localhost", port=6333)


INSERT_RECIPE_SQL = text(Path("sql/insert_recipe.sql").read_text())


# Setup engine with pooling
engine = create_engine(DATABASE_URL, pool_size=20, max_overflow=20)

# Create the session factory
SessionLocal = sessionmaker(bind=engine)


# This dependency handles the "borrowing" and "returning"
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()