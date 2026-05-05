from fastapi.testclient import TestClient

from app import create_app
from database import get_db


class FakeDb:
    def __init__(self):
        self.rollbacks = 0

    def rollback(self):
        self.rollbacks += 1


class FakeRepository:
    def __init__(self):
        self.recipe = {
            "id": 42,
            "name": "Tomato Soup",
            "category": ["Soup"],
            "ingredients": ["tomato"],
            "ingredients_raw": ["1 tomato"],
            "instructions": "Cook.",
            "cooking_methods": [],
            "implements": [],
            "nutrition": None,
            "cuisine": "European",
        }
        self.inserted = []
        self.updated = []
        self.deleted = []

    def insert_recipe(self, db, recipe):
        self.inserted.append(recipe)
        return 42

    def get_recipe_by_id(self, db, recipe_id):
        return self.recipe if recipe_id == 42 else None

    def update_recipe(self, db, recipe_id, update_dict):
        self.updated.append((recipe_id, update_dict))
        self.recipe = {**self.recipe, **update_dict}
        return 1

    def delete_recipe(self, db, recipe_id):
        self.deleted.append(recipe_id)
        return 1 if recipe_id == 42 else 0


class FakeRecommender:
    def __init__(self):
        self.upserts = []
        self.removed = []
        self.ingredients_queries = []
        self.name_queries = []

    def find_recipe_by_ingredients(self, ingredients, k, category, cuisine):
        self.ingredients_queries.append((ingredients, k, category, cuisine))
        return [{"id": 42, "name": "Tomato Soup"}]

    def find_recipe_by_name(self, name, k, category, cuisine, ingredients):
        self.name_queries.append((name, k, category, cuisine, ingredients))
        return [{"id": 42, "name": "Tomato Soup"}]

    def get_suggestions(self, query, limit=5):
        return ["tomato", "onion", "garlic"][:limit]

    def upsert_embedding(self, recipe_id, recipe):
        self.upserts.append((recipe_id, recipe))

    def remove_recipe_from_indexes(self, recipe_id):
        self.removed.append(recipe_id)


def make_client():
    repo = FakeRepository()
    recommender = FakeRecommender()
    app = create_app(recipe_repo=repo, rec_engine=recommender)

    def fake_get_db():
        yield FakeDb()

    app.dependency_overrides[get_db] = fake_get_db
    return TestClient(app), repo, recommender


def test_query_by_ingredients_uses_recommender_with_filters():
    client, _, recommender = make_client()

    response = client.get(
        "/query_by_ingredients",
        params={"ingredients": "tomato, onion", "k": 3, "category": "Soup", "cuisine": "European"},
    )

    assert response.status_code == 200
    assert response.json()["results"][0]["name"] == "Tomato Soup"
    assert recommender.ingredients_queries == [("tomato, onion", 3, "Soup", "European")]


def test_query_by_name_passes_repeated_ingredients():
    client, _, recommender = make_client()

    response = client.get(
        "/query_by_name",
        params=[
            ("name", "soup"),
            ("ingredients", "tomato"),
            ("ingredients", "onion"),
        ],
    )

    assert response.status_code == 200
    assert recommender.name_queries[0][4] == ["tomato", "onion"]


def test_ingredient_suggestions_trims_short_query_and_excludes_items():
    client, _, _ = make_client()

    short_response = client.get("/ingredients/suggestions", params={"q": " t "})
    filtered_response = client.get(
        "/ingredients/suggestions",
        params={"q": "to", "limit": 2, "exclude": "tomato"},
    )

    assert short_response.json() == {"query": "t", "suggestions": []}
    assert filtered_response.json()["suggestions"] == ["onion", "garlic"]


def test_add_recipe_persists_and_upserts_embedding(sample_recipe_payload):
    client, repo, recommender = make_client()

    response = client.post("/add", json=sample_recipe_payload)

    assert response.status_code == 200
    assert response.json()["recipe_id"] == 42
    assert len(repo.inserted) == 1
    assert recommender.upserts[0][0] == 42


def test_update_recipe_handles_success_and_not_found():
    client, repo, recommender = make_client()

    success = client.patch("/recipes/42", json={"name": "Updated Soup"})
    missing = client.patch("/recipes/999", json={"name": "Missing"})

    assert success.status_code == 200
    assert repo.updated == [(42, {"name": "Updated Soup"})]
    assert recommender.upserts[0][0] == 42
    assert missing.status_code == 404


def test_delete_recipe_handles_success_and_not_found():
    client, repo, recommender = make_client()

    success = client.delete("/recipes/42")
    missing = client.delete("/recipes/999")

    assert success.status_code == 200
    assert repo.deleted == [42, 999]
    assert recommender.removed == [42]
    assert missing.status_code == 404
