import uvicorn
from pathlib import Path

from fastapi import FastAPI, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session

from recommender_engine.recommender_engine import RecommenderEngine
from database import get_db, engine, qd_client
from recipe_repository import RecipeRepository
from schemas.enums import Category, Cuisine
from schemas.recipe import RecipeCreate, RecipeUpdate

api = FastAPI()

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
api.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

recipe_repository = RecipeRepository(engine)
recommender_engine = RecommenderEngine(qd_client, recipe_repository)


@api.get("/", response_class=HTMLResponse)
def index(request: Request):
    static_version = (BASE_DIR / "static" / "app.js").stat().st_mtime_ns
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "cuisines": [cuisine.value for cuisine in Cuisine],
            "categories": [category.value for category in Category],
            "static_version": static_version,
        },
    )


# Typical payload (ingredients = "avocado, tomato, toast")
@api.get("/query_by_ingredients")
def query_by_ingredients(
    ingredients: str,
    k: int = 5,
    category: Category | None = None,
    cuisine: Cuisine | None = None,
):
    results = recommender_engine.find_recipe_by_ingredients(
        ingredients,
        k,
        category.value if category else None,
        cuisine.value if cuisine else None,
    )
    return {"results": results}


# Typical payload (name = "lasagna")
@api.get("/query_by_name")
def query_by_name(
    name: str,
    k: int = 5,
    category: Category | None = None,
    cuisine: Cuisine | None = None,
    ingredients: list[str] = Query(None),
):
    results = recommender_engine.find_recipe_by_name(
        name,
        k,
        category.value if category else None,
        cuisine.value if cuisine else None,
        ingredients,
    )
    return {"results": results}


# recipes table CRUD

@api.post("/add")
def add_recipe(recipe: RecipeCreate, db: Session = Depends(get_db)):
    try:
        recipe_id = recipe_repository.insert_recipe(db, recipe)
        recommender_engine.upsert_embedding(recipe_id=recipe_id, recipe=recipe)
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

        try:
            recommender_engine.upsert_embedding(recipe_id=recipe_id, recipe=merged_recipe)
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
            recommender_engine.remove_recipe_from_indexes(recipe_id)
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
