"""Tests for product name normalization and categorization."""
from catalog import categorize, normalize_name


def test_normalize_drops_filler_and_sorts():
    assert normalize_name("Ground beef") == "beef"
    assert normalize_name("minced BEEF") == "beef"
    assert normalize_name("beef ground") == "beef"


def test_normalize_keeps_distinct_products_apart():
    assert normalize_name("Green peas") == "green peas"
    assert normalize_name("peas green") == "green peas"


def test_normalize_handles_filler_only_names():
    # "mince" is a filler word but should not collapse to an empty key.
    assert normalize_name("mince") == "mince"


def test_normalize_strips_quantity_tokens():
    assert normalize_name("Beef 500g") == "beef"


def test_categorize_meat():
    assert categorize("ground beef") == "Meat"
    assert categorize("Pork chops") == "Meat"


def test_categorize_poultry_wins_over_meat():
    assert categorize("chicken breast") == "Poultry"


def test_categorize_pasta():
    assert categorize("Penne") == "Pasta & grains"


def test_categorize_fish():
    assert categorize("Salmon fillet") == "Fish & seafood"


def test_categorize_multi_word_keyword():
    assert categorize("ice cream") == "Dairy"


def test_categorize_unknown_returns_none():
    assert categorize("wibble wobble") is None
