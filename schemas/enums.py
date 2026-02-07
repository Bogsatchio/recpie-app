from enum import Enum


class Cuisine(str, Enum):
    NORTH_AMERICAN = "North American"
    ASIAN = "Asian"
    EUROPEAN = "European"
    AFRICAN = "African"
    FUSION_INSPIRED = "Fusion & Inspired"
    LATIN_AMERICAN = "Latin American"
    MEDITERRANEAN = "Mediterranean"
    MIDDLE_EASTERN = "Middle Eastern"
    WORLD_FUSION = "World / Fusion"


class Category(str, Enum):
    BREAD = "Bread"
    BREAKFAST_BRUNCH = "Breakfast & Brunch"
    DRINKS = "Drinks"
    MAIN_COURSE = "Main Course"
    PANTRY_INGREDIENTS = "Pantry & Ingredients"
    SALAD = "Salad"
    SANDWICH = "Sandwich"
    SAUCE = "Sauce"
    SIDE_DISK = "Side Dish"
    SOUP = "Soup"
    SPICE_MIX = "Spice Mix"
    STARTERS_SNACKS = "Starters & Snacks"
    SWEETS_DESSERTS = "Sweets & Desserts"




