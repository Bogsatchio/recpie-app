from sentence_transformers import SentenceTransformer
from rapidfuzz import process, utils
from qdrant_client.http import models as qdrant_models

from recommender_engine.re_utils import (
    _build_boost_filter,
    _boost_score,
    _df_to_records,
    _enum_list,
    _enum_value,
    _hits_to_df,
    _normalize_ingredients,
    _penalize_score,
    _query_qdrant,
)

from database import QD_INGREDIENT_COLLECTION, QD_NAME_COLLECTION


class RecommenderEngine():

    def __init__(self, qd_client, recipe_repository):
        #self.model = SentenceTransformer("all-MiniLM-L6-v2")
        self.model = SentenceTransformer("all-mpnet-base-v2")
        self.qd_client = qd_client
        self.recipe_repository = recipe_repository
        self.recipes_collection = QD_INGREDIENT_COLLECTION
        self.names_collection = QD_NAME_COLLECTION
        self.ingredients_list = self.recipe_repository.get_ingredients_list()

    ### QUERY FUNCTIONALITIES
    def find_recipe_by_ingredients(self, user_ingredients: str, k: int = 5, category: str = None,
                                   cuisine: str = None) -> list[dict]:
        query_vec = self.model.encode(user_ingredients, normalize_embeddings=True)
        query_ingredients = _normalize_ingredients(user_ingredients)

        boost_filter = _build_boost_filter(category=category, cuisine=cuisine)
        results = _query_qdrant(
            self.qd_client,
            collection_name=self.recipes_collection,
            query_vec=query_vec,
            boost_filter=boost_filter,
            score_threshold=0.2,
        )

        hits = {
            hit.payload["ID"]: _penalize_score(
                _boost_score(
                    hit.score,
                    hit.payload,
                    query_ingredients,
                    category,
                    cuisine,
                ),
                hit.payload,
                query_ingredients,
                category,
                cuisine,
            )
            for hit in results.points
        }
        return _df_to_records(_hits_to_df(self.recipe_repository, hits, k))

    def find_recipe_by_name(
            self,
            recipe_name: str,
            k: int = 5,
            category: str = None,
            cuisine: str = None,
            ingredients: list[str] = None,
    ) -> list[dict]:
        query_vec = self.model.encode(recipe_name, normalize_embeddings=True)

        boost_filter = _build_boost_filter(category=category, cuisine=cuisine, ingredients=ingredients)
        results = _query_qdrant(
            self.qd_client,
            collection_name=self.names_collection,
            query_vec=query_vec,
            boost_filter=boost_filter,
            score_threshold=0.3,
        )

        hits = {
            hit.payload["ID"]: _penalize_score(
                _boost_score(
                    hit.score,
                    hit.payload,
                    ingredients,
                    category,
                    cuisine,
                ),
                hit.payload,
                ingredients,
                category,
                cuisine,
            )
            for hit in results.points
        }
        return _df_to_records(_hits_to_df(self.recipe_repository, hits, k))

    ### QDRANT CRUD OPERATIONS
    def upsert_embedding(self, recipe_id: int, recipe) -> None:
        """
        Embed recipe ingredients and upsert the vector + payload into Qdrant.
        Accepts a recipe object (Pydantic model or dict) with ingredients, category, cuisine, cooking_methods.
        """
        if isinstance(recipe, dict):
            ingredients = recipe["ingredients"]
            name = recipe["name"]
            category = _enum_list(recipe["category"])
            cuisine = _enum_value(recipe["cuisine"])
            cooking_methods = recipe["cooking_methods"]
        else:
            ingredients = recipe.ingredients
            name = recipe.name
            category = _enum_list(recipe.category)
            cuisine = _enum_value(recipe.cuisine)
            cooking_methods = recipe.cooking_methods

        ingredients_text = ", ".join(ingredients)
        embedding = self.model.encode(
            ingredients_text,
            normalize_embeddings=True,
        )
        point = qdrant_models.PointStruct(
            id=recipe_id,
            vector=embedding.tolist(),
            payload={
                "ID": recipe_id,
                "category": category,
                "cuisine": cuisine,
                "cooking_methods": cooking_methods,
            },
        )
        self.qd_client.upsert(
            collection_name=self.recipes_collection,
            points=[point],
        )

        name_embedding = self.model.encode(
            name,
            normalize_embeddings=True,
        )
        name_point = qdrant_models.PointStruct(
            id=recipe_id,
            vector=name_embedding.tolist(),
            payload={
                "ID": recipe_id,
                "ingredients": ingredients,
                "category": category,
                "cuisine": cuisine,
                "cooking_methods": cooking_methods,

            },
        )
        self.qd_client.upsert(
            collection_name=self.names_collection,
            points=[name_point],
        )

    def remove_recipe_from_indexes(self, recipe_id: int) -> None:
        """
        Remove a recipe's vector from Qdrant by ID.
        """
        self.qd_client.delete(
            collection_name=self.recipes_collection,
            points_selector=qdrant_models.PointIdsList(points=[recipe_id]),
        )

        self.qd_client.delete(
            collection_name=self.names_collection,
            points_selector=qdrant_models.PointIdsList(points=[recipe_id]),
        )

    ### FUZZY SEARCH
    def get_suggestions(self, user_input, limit=5):
        results = process.extract(
            user_input,
            self.ingredients_list,
            # scorer=fuzz.WRatio,
            processor=utils.default_process,
            limit=35
        )
        processed_results = []

        # Pre-lowercase user_input once for efficiency
        search_term = user_input.lower()

        for text, score, index in results:
            adjusted_score = score
            lowered_text = text.lower()

            # Penalty: Contains a space
            if " " in text:
                adjusted_score -= 5

            # Penalty: search_term not in match
            if search_term not in text.lower():
                adjusted_score -= 5

            # Penalty: 4+ characters longer than input
            if len(text) >= len(user_input) + 4:
                adjusted_score -= 5

            # Boost: user input only shorter than search term by less than 3 chars
            if len(text) - len(user_input) <= 3:
                adjusted_score += 5

            # Boost: match starts with search_term
            if lowered_text.startswith(search_term):
                adjusted_score += 5

            processed_results.append((text, adjusted_score, index))

        processed_results.sort(key=lambda x: x[1], reverse=True)

        return [match[0] for match in processed_results[:limit]]

        # results returns a list of tuples: (string, score, index)
        return [match[0] for match in results if match[1] > 60]