import uvicorn

from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from qdrant_client.http import models

from recommender_engine import RecommenderEngine
from database import get_db, engine, qd_client, QD_COLLECTION
from utils import extract_ner
from recipe_repository import RecipeRepository
from schemas.recipe import RecipeCreate, RecipeUpdate

api = FastAPI()

recipe_repository = RecipeRepository()
recommender_engine = RecommenderEngine(engine, qd_client, recipe_repository)


@api.get("/")
def index():
    return {"message": "Hello World"}


# Typical payload (ingredients = "avocado, tomato, toast")
@api.get("/query")
def query(ingredients: str, k: int = 5, category: str = None, cuisine: str = None):
    results = recommender_engine.find_recipe(ingredients, k, category, cuisine)
    return {"results": results.to_dict(orient='records')}


@api.post("/add")
def add_recipe(recipe: RecipeCreate, db: Session = Depends(get_db)):
    try:
        recipe_id = recipe_repository.insert_recipe(db, recipe)
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


@api.patch("/recipes/{recipe_id}")
def update_recipe(recipe_id: int, recipe_update: RecipeUpdate, db: Session = Depends(get_db)):
    """
    Update a recipe by ID with partial data. MySQL and Qdrant stay in sync.
    """
    try:
        existing_recipe = recipe_repository.get_recipe_by_id(db, recipe_id)
        if existing_recipe is None:
            raise HTTPException(status_code=404, detail=f"Recipe with id {recipe_id} not found")

        update_dict = recipe_update.dict(exclude_unset=True)
        merged_recipe = {**existing_recipe, **update_dict}

        rows_updated = recipe_repository.update_recipe(db, recipe_id, update_dict)
        if rows_updated == 0:
            raise HTTPException(status_code=500, detail="Failed to update recipe")

        ingredients_to_embed = ", ".join(merged_recipe["ingredients"])
        embedding = recommender_engine.model.encode(
            ingredients_to_embed,
            normalize_embeddings=True,
        )
        point = models.PointStruct(
            id=recipe_id,
            vector=embedding,
            payload={
                "ID": recipe_id,
                "category": merged_recipe["category"],
                "cuisine": merged_recipe["cuisine"],
                "cooking_methods": merged_recipe["cooking_methods"],
            },
        )
        try:
            qd_client.upsert(collection_name=QD_COLLECTION, points=[point])
        except Exception as qdrant_error:
            print(f"Warning: Failed to update recipe {recipe_id} in Qdrant: {str(qdrant_error)}")

        updated_recipe = recipe_repository.get_recipe_by_id(db, recipe_id)
        return {"message": "Recipe updated successfully", "recipe": updated_recipe}

    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error updating recipe: {str(e)}")


@api.delete("/recipes/{recipe_id}")
def delete_recipe(recipe_id: int, db: Session = Depends(get_db)):
    """
    Delete a recipe by ID from both MySQL and Qdrant.
    """
    try:
        # Delete from MySQL first (source of truth)
        rows_deleted = recipe_repository.delete_recipe(db, recipe_id)
        
        if rows_deleted == 0:
            raise HTTPException(status_code=404, detail=f"Recipe with id {recipe_id} not found")
        
        # Delete from Qdrant to keep it synchronized
        try:
            qd_client.delete(
                collection_name=QD_COLLECTION,
                points_selector=models.PointIdsList(
                    points=[recipe_id]
                )
            )
        except Exception as qdrant_error:
            # Log the Qdrant error but don't fail the request since MySQL delete succeeded
            # In production, you might want to log this to a monitoring system
            print(f"Warning: Failed to delete recipe {recipe_id} from Qdrant: {str(qdrant_error)}")
        
        return {
            "message": "Recipe deleted successfully",
            "recipe_id": recipe_id
        }
    
    except HTTPException:
        # Re-raise HTTP exceptions (like 404)
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error deleting recipe: {str(e)}")


if __name__ == "__main__":
    uvicorn.run("app:api", host="127.0.0.1", port=8000, reload=True)
