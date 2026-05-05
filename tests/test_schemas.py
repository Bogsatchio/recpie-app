import pytest
from pydantic import ValidationError

from schemas.recipe import RecipeCreate, RecipeUpdate


def test_recipe_create_accepts_valid_payload(sample_recipe_payload):
    recipe = RecipeCreate(**sample_recipe_payload)

    assert recipe.name == "Tomato Soup"
    assert recipe.category[0].value == "Soup"
    assert recipe.cuisine.value == "European"


def test_recipe_create_rejects_invalid_enum(sample_recipe_payload):
    sample_recipe_payload["cuisine"] = "Atlantis"

    with pytest.raises(ValidationError):
        RecipeCreate(**sample_recipe_payload)


def test_recipe_create_rejects_negative_time(sample_recipe_payload):
    sample_recipe_payload["cooking_time"] = -1

    with pytest.raises(ValidationError):
        RecipeCreate(**sample_recipe_payload)


def test_recipe_update_allows_partial_payload():
    update = RecipeUpdate(name="Updated Soup")

    assert update.name == "Updated Soup"
    assert update.cuisine is None
