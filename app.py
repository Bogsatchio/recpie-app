import uvicorn
import json
from datetime import datetime
from typing import List, Optional, Dict, Any

from pydantic import BaseModel, Field, HttpUrl
from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker
from qdrant_client.http import models

from recommender_engine import RecommenderEngine
from database import get_db, engine, qd_client, QD_COLLECTION, INSERT_RECIPE_SQL
from utils import extract_ner

api = FastAPI()

DATABASE_URL = "mysql+pymysql://dev:dev@localhost:3306/recipe_dev"
SessionLocal = sessionmaker(bind=engine)
recommender_engine = RecommenderEngine(engine, qd_client)


class Recipe(BaseModel):
    name: str = Field(..., max_length=255)
    preparation_time: Optional[int] = Field(None, ge=0)
    cooking_time: Optional[int] = Field(None, ge=0)
    category: List[str] = Field(..., min_items=1)
    ingredients: List[str] = Field(..., min_items=1)
    ingredients_raw: List[str] = Field(..., min_items=1)
    instructions: List[str] = Field(..., min_items=1)

    cooking_methods: List[str] = Field(default_factory=list)
    implements: List[str] = Field(default_factory=list)

    nutrition: Optional[Dict[str, Any]] = None

    cuisine: str = Field(..., max_length=100)

    number_of_steps: Optional[int] = Field(None, ge=0)

    url: Optional[HttpUrl] = Field(None, max_length=500)


@api.get("/")
def index():
    return {"message": "Hello World"}


# Typical payload (ingredients = "avocado, tomato, toast")
@api.get("/query")
def query(ingredients: str, k: int = 5, category: str = None, cuisine: str = None):
    results = recommender_engine.find_recipe(ingredients, k, category, cuisine)
    return {"results": results.to_dict(orient='records')}


@api.post("/add")
def add_recipe(recipe: Recipe, db: Session = Depends(get_db)):
    try:
        result = db.execute(INSERT_RECIPE_SQL, {
            "name": recipe.name,
            "created_at": datetime.utcnow(),

            "rating_value": None,
            "rating_count": 0,

            "preparation_time": recipe.preparation_time,
            "cooking_time": recipe.cooking_time,

            # JSON columns
            "category": json.dumps(recipe.category),
            "ingredients": json.dumps(recipe.ingredients),
            "ingredients_raw": json.dumps(recipe.ingredients_raw),
            "instructions": json.dumps(recipe.instructions),
            "cooking_methods": json.dumps(recipe.cooking_methods),
            "implements": json.dumps(recipe.implements),
            "nutrition": json.dumps(recipe.nutrition),

            # scalar
            "cuisine": recipe.cuisine,
            "number_of_steps": recipe.number_of_steps,
            "url": recipe.url
        })

        db.commit()

        # Get the ID of the inserted recipe
        recipe_id = result.lastrowid
        ingredients_to_embed = ", ".join(recipe.ingredients)
        print(ingredients_to_embed)

        embedding = recommender_engine.model.encode(
            ingredients_to_embed,
            normalize_embeddings=True
        )

        point = models.PointStruct(
            id=recipe_id,
            vector=embedding,
            payload={
                "ID": recipe_id,
                "category": recipe.category,
                "cuisine": recipe.cuisine,
                "cooking_methods": recipe.cooking_methods
            }
        )

        qd_client.upsert(
            collection_name=QD_COLLECTION,
            points=[point]
        )

        return {
            "message": "Recipe added successfully",
            "recipe_id": recipe_id

        }

    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error adding recipe: {str(e)}")


if __name__ == "__main__":
    uvicorn.run("app:api", host="127.0.0.1", port=8000, reload=True)
