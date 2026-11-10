"""Product name normalization and automatic categorization.

Two concerns live here:

* ``normalize_name`` builds a canonical key so that "ground beef" and "beef"
  are treated as the same product. Filler words (ground, minced, frozen, ...)
  are dropped and the remaining tokens are sorted and deduplicated.

* ``categorize`` assigns a category (Meat, Pasta & grains, ...) from a keyword
  seed list. This is a starting point; extend ``CATEGORY_KEYWORDS`` to improve
  coverage.
"""
import re

# Words that carry no identity and are dropped when building a name key.
FILLER_WORDS = {
    "ground", "minced", "mince", "chopped", "diced", "sliced", "shredded",
    "grated", "frozen", "fresh", "raw", "cooked", "organic", "bio", "lean",
    "premium", "pieces", "chunks", "extra", "fine",
}

# Ordered so more specific categories win. Keywords are matched against the
# lowercased tokens of the product name (whole tokens, or whole substrings for
# multi-word keywords).
CATEGORY_KEYWORDS = [
    ("Poultry", ["chicken", "turkey", "duck", "quail", "goose"]),
    ("Meat", ["beef", "pork", "lamb", "veal", "steak", "sausage", "sausages",
              "bacon", "ham", "meatball", "meatballs", "burger", "burgers",
              "ribs", "roast", "goulash"]),
    ("Fish & seafood", ["salmon", "cod", "tuna", "shrimp", "prawn", "prawns",
                        "fish", "mackerel", "haddock", "mussel", "mussels",
                        "scallop", "scallops", "tilapia", "herring", "sardine",
                        "crab", "lobster"]),
    ("Vegetables", ["broccoli", "peas", "carrot", "carrots", "spinach",
                    "cauliflower", "corn", "bean", "beans", "vegetable",
                    "vegetables", "onion", "onions", "pepper", "peppers",
                    "leek", "kale", "zucchini", "mushroom", "mushrooms",
                    "tomato", "tomatoes", "cabbage", "brussels", "asparagus",
                    "celery"]),
    ("Fruit & berries", ["berry", "berries", "apple", "apples", "mango",
                         "banana", "bananas", "fruit", "strawberry",
                         "strawberries", "raspberry", "raspberries",
                         "blueberry", "blueberries", "peach", "pineapple",
                         "melon", "grapes", "cherry", "cherries", "plum"]),
    ("Pasta & grains", ["pasta", "penne", "spaghetti", "rice", "noodle",
                        "noodles", "couscous", "quinoa", "macaroni",
                        "tagliatelle", "farfalle", "fusilli", "risotto",
                        "oats", "bulgur"]),
    ("Bread & bakery", ["bread", "bagel", "bagels", "roll", "rolls",
                        "croissant", "baguette", "pizza", "dough", "bun",
                        "buns", "naan", "pita", "tortilla", "waffle"]),
    ("Dairy", ["cheese", "butter", "milk", "cream", "yogurt", "mozzarella",
               "parmesan", "ice cream"]),
    ("Prepared meals", ["lasagna", "lasagne", "curry", "stew", "soup",
                        "casserole", "pie", "burrito", "bolognese", "chili",
                        "meal"]),
    ("Sweets & desserts", ["cake", "cookie", "cookies", "dessert", "chocolate",
                           "pancake", "brownie", "pastry"]),
    ("Sauces & stock", ["sauce", "stock", "broth", "gravy", "pesto", "ketchup",
                        "mayo", "salsa"]),
    ("Herbs & spices", ["basil", "parsley", "coriander", "dill", "herb",
                        "herbs", "spice", "spices", "ginger", "garlic"]),
    ("Snacks", ["chips", "nuts", "crackers", "pretzel", "popcorn", "crisps"]),
]


def _tokens(name: str):
    """Lowercased alphanumeric tokens, dropping quantity-like tokens."""
    raw = re.findall(r"[a-z0-9]+", (name or "").lower())
    return [t for t in raw if not re.match(r"^\d", t)]


def normalize_name(name: str) -> str:
    """Canonical product key: significant tokens, sorted and deduplicated."""
    tokens = _tokens(name)
    significant = [t for t in tokens if t not in FILLER_WORDS]
    if not significant:  # e.g. a name made only of filler words ("mince")
        significant = tokens
    return " ".join(sorted(set(significant)))


def categorize(name: str) -> str | None:
    """Return a category for a product name, or None if unknown."""
    tokens = _tokens(name)
    lowered = " ".join(tokens)
    for category, keywords in CATEGORY_KEYWORDS:
        for keyword in keywords:
            if " " in keyword:
                if keyword in lowered:
                    return category
            elif keyword in tokens:
                return category
    return None
