"""Tests for service-layer business logic (no Databricks connection)."""
import pytest

import service


def test_add_lot_creates_product_lot_and_event(fake_db):
    fake_db.cursor._fetchone = [None, None]  # op_id dup check, then name_key lookup
    result = service.add_lot(name="Ground beef", qty_g=500)

    assert result["duplicate"] is False
    assert result["lot_id"]
    assert any("STOCK_IN" in sql for sql, _ in fake_db.cursor.statements)
    assert fake_db.connection.committed is True


def test_add_lot_is_idempotent(fake_db):
    fake_db.cursor._fetchone = [("existing-lot",)]
    result = service.add_lot(name="Ground beef", qty_g=500)
    assert result == {"lot_id": "existing-lot", "duplicate": True}
    assert fake_db.connect_calls == 1


def test_record_use_rejects_overuse(fake_db):
    fake_db.cursor._fetchone = [None, (200,)]  # op_id dup check, then balance
    with pytest.raises(ValueError):
        service.record_use(lot_id="lot-1", grams_used=300)
    assert fake_db.connection.rolled_back is True


def test_discard_empty_lot_is_noop(fake_db):
    fake_db.one_results = [{"lot_id": "lot-1", "grams_remaining": 0.0}]
    result = service.discard(lot_id="lot-1")
    assert result == {"lot_id": "lot-1", "grams_remaining": 0, "duplicate": False}
    assert fake_db.connect_calls == 0


def test_set_remaining_rejects_negative(fake_db):
    with pytest.raises(ValueError):
        service.set_remaining(lot_id="lot-1", grams_remaining=-5)


def test_add_shopping_item(fake_db):
    result = service.add_shopping_item(name="Milk", note="2L")
    assert result["item_id"]
    assert any("INSERT INTO stock.shopping_items" in sql for sql, _ in fake_db.cursor.statements)
    assert fake_db.connection.committed is True


def test_complete_shopping_item(fake_db):
    result = service.complete_shopping_item("item-1")
    assert result == {"item_id": "item-1", "done": True}
    assert any("UPDATE" in sql and "done_at" in sql for sql, _ in fake_db.cursor.statements)
