import json
from datetime import datetime
from typing import Any, Iterable, List, Optional
from pathlib import Path

import pandas as pd
from sqlalchemy import bindparam, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session


INSERT_RECIPE_SQL = text(Path("sql/insert_recipe.sql").read_text())


class RecipeRepository:
    """
    Persistence layer for recipes (MySQL).

    Responsibilities:
    - Map API/domain recipe input to SQL parameters
    - Execute inserts and simple read queries
    """

    def __init__(self) -> None:
        # Use module-level INSERT_RECIPE_SQL by default.
        self._insert_recipe_sql = INSERT_RECIPE_SQL

    def insert_recipe(self, db: Session, recipe: Any) -> int:
        """
        Insert a recipe row and return its new integer ID.

        `recipe` is expected to have attributes matching the current Pydantic model:
        - name, preparation_time, cooking_time, category, ingredients, ingredients_raw,
          instructions, cooking_methods, implements, nutrition, cuisine, number_of_steps, url
        """
        if self._insert_recipe_sql is None:
            raise ValueError("insert_recipe_sql is not configured for RecipeRepository")

        result = db.execute(
            self._insert_recipe_sql,
            {
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
                "number_of_steps": recipe.number_of_steps,
                "nutrition": json.dumps(recipe.nutrition),
                "url": str(recipe.url) if recipe.url is not None else None,
                # scalar
                "cuisine": recipe.cuisine,
            },
        )
        db.commit()

        recipe_id = result.lastrowid
        # MySQL drivers typically return int-compatible IDs here.
        return int(recipe_id)

    def get_recipes_by_ids(
        self,
        engine: Engine,
        ids: Iterable[int],
        *,
        columns: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """
        Fetch recipe rows for the given IDs.

        Returns an empty DataFrame if `ids` is empty.
        """
        ids_list = [int(i) for i in ids]
        if not ids_list:
            return pd.DataFrame()

        cols = columns or ["id", "name", "ingredients"]
        col_sql = ", ".join(cols)

        stmt = text(f"SELECT {col_sql} FROM recipes WHERE id IN :ids").bindparams(
            bindparam("ids", expanding=True)
        )

        return pd.read_sql(stmt, engine, params={"ids": ids_list})

    def get_recipe_by_id(self, db: Session, recipe_id: int) -> Optional[dict]:
        """
        Fetch a single recipe by ID.

        Returns a dictionary with recipe data, or None if not found.
        """
        stmt = text("""
            SELECT
                id, name, created_at, rating_value, rating_count,
                preparation_time, cooking_time, category, cuisine,
                ingredients, ingredients_raw, instructions, cooking_methods,
                implements, number_of_steps, nutrition, url
            FROM recipes
            WHERE id = :recipe_id
        """)
        result = db.execute(stmt, {"recipe_id": recipe_id})
        row = result.fetchone()

        if row is None:
            return None

        return {
            "id": row.id,
            "name": row.name,
            "created_at": row.created_at,
            "rating_value": row.rating_value,
            "rating_count": row.rating_count,
            "preparation_time": row.preparation_time,
            "cooking_time": row.cooking_time,
            "category": json.loads(row.category) if row.category else [],
            "cuisine": row.cuisine,
            "ingredients": json.loads(row.ingredients) if row.ingredients else [],
            "ingredients_raw": json.loads(row.ingredients_raw) if row.ingredients_raw else [],
            "instructions": json.loads(row.instructions) if row.instructions else [],
            "cooking_methods": json.loads(row.cooking_methods) if row.cooking_methods else [],
            "implements": json.loads(row.implements) if row.implements else [],
            "number_of_steps": row.number_of_steps,
            "nutrition": json.loads(row.nutrition) if row.nutrition else None,
            "url": row.url,
        }

    def update_recipe(self, db: Session, recipe_id: int, update_data: dict) -> int:
        """
        Update a recipe by ID with the provided data.

        Only fields present in update_data are updated.
        Returns the number of rows updated (0 or 1).
        """
        set_clauses = []
        params: dict = {"recipe_id": recipe_id}

        column_map = {
            "name": ("name", None),
            "preparation_time": ("preparation_time", None),
            "cooking_time": ("cooking_time", None),
            "category": ("category", json.dumps),
            "cuisine": ("cuisine", None),
            "ingredients": ("ingredients", json.dumps),
            "ingredients_raw": ("ingredients_raw", json.dumps),
            "instructions": ("instructions", json.dumps),
            "cooking_methods": ("cooking_methods", json.dumps),
            "implements": ("implements", json.dumps),
            "number_of_steps": ("number_of_steps", None),
            "nutrition": ("nutrition", lambda x: json.dumps(x) if x is not None else None),
            "url": ("url", lambda x: str(x) if x is not None else None),
        }

        for key, (col, serializer) in column_map.items():
            if key not in update_data:
                continue
            set_clauses.append(f"{col} = :{col}")
            params[col] = serializer(update_data[key]) if serializer else update_data[key]

        if not set_clauses:
            return 0

        stmt = text(f"UPDATE recipes SET {', '.join(set_clauses)} WHERE id = :recipe_id")
        result = db.execute(stmt, params)
        db.commit()
        return result.rowcount

    def delete_recipe(self, db: Session, recipe_id: int) -> int:
        """
        Delete a recipe by ID from MySQL.

        Returns the number of rows deleted (0 if recipe doesn't exist, 1 if deleted).
        """
        stmt = text("DELETE FROM recipes WHERE id = :recipe_id")
        result = db.execute(stmt, {"recipe_id": recipe_id})
        db.commit()
        return result.rowcount
