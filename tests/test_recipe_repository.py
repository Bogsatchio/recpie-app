import json
from types import SimpleNamespace

from recipe_repository import RecipeRepository
from schemas.recipe import RecipeCreate


class FakeResult:
    lastrowid = 42
    rowcount = 1


class FakeSession:
    def __init__(self, row=None):
        self.row = row
        self.executed = []
        self.commits = 0

    def execute(self, stmt, params=None):
        self.executed.append((stmt, params))
        return SimpleNamespace(fetchone=lambda: self.row, lastrowid=42, rowcount=1)

    def commit(self):
        self.commits += 1


def test_insert_recipe_serializes_structured_fields(sample_recipe_payload):
    repository = RecipeRepository(engine=object())
    db = FakeSession()
    recipe = RecipeCreate(**sample_recipe_payload)

    recipe_id = repository.insert_recipe(db, recipe)

    params = db.executed[0][1]
    assert recipe_id == 42
    assert json.loads(params["category"]) == ["Soup"]
    assert json.loads(params["ingredients"]) == ["tomato", "onion", "garlic"]
    assert json.loads(params["nutrition"]) == {"calories": 220}
    assert params["cuisine"] == "European"
    assert db.commits == 1


def test_get_recipe_by_id_decodes_json_columns():
    row = SimpleNamespace(
        id=7,
        name="Soup",
        created_at=None,
        rating_value=None,
        rating_count=0,
        preparation_time=5,
        cooking_time=10,
        category='["Soup"]',
        cuisine="European",
        ingredients='["tomato"]',
        ingredients_raw='["1 tomato"]',
        instructions="Cook.",
        cooking_methods='["simmer"]',
        implements='["pot"]',
        number_of_steps=1,
        nutrition='{"calories": 100}',
        url=None,
    )
    repository = RecipeRepository(engine=object())

    recipe = repository.get_recipe_by_id(FakeSession(row=row), 7)

    assert recipe["id"] == 7
    assert recipe["category"] == ["Soup"]
    assert recipe["ingredients"] == ["tomato"]
    assert recipe["nutrition"] == {"calories": 100}


def test_update_recipe_serializes_only_supplied_fields():
    repository = RecipeRepository(engine=object())
    db = FakeSession()

    rows = repository.update_recipe(
        db,
        7,
        {"name": "Updated", "ingredients": ["tomato"], "nutrition": None},
    )

    params = db.executed[0][1]
    assert rows == 1
    assert params["recipe_id"] == 7
    assert params["name"] == "Updated"
    assert params["ingredients"] == '["tomato"]'
    assert params["nutrition"] is None
    assert "cuisine" not in params
