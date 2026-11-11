"""Business logic: inventory reads and atomic writes.

Writes run in native Postgres transactions (see ``atomic``): all statements in
a block commit together or roll back together. Primary/foreign keys and CHECK
constraints in Postgres enforce integrity at the database level.
"""
import uuid
from contextlib import contextmanager, suppress
from datetime import date, timedelta

import db
from catalog import categorize, normalize_name


@contextmanager
def atomic():
    """Yield a cursor whose statements commit together or not at all."""
    conn = db.connect(autocommit=False)
    cur = conn.cursor()
    try:
        yield cur
        conn.commit()
    except Exception:
        with suppress(Exception):
            conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def _is_conflict(error: Exception) -> bool:
    message = str(error).lower()
    return "concurrent" in message or "conflict" in message


# ---- reads ---------------------------------------------------------------

def list_inventory():
    """Product-level overview: in-stock or tracked products, low stock first."""
    return db.rows(
        f"SELECT * FROM {db.fq('v_product_stock')} "
        "WHERE lot_count > 0 OR min_stock_g IS NOT NULL "
        "ORDER BY low_stock DESC, name ASC"
    )


def list_lots(product_id: str):
    return db.rows(
        f"SELECT * FROM {db.fq('v_active_lot_stock')} WHERE product_id = %s ORDER BY added_date ASC",
        [product_id],
    )


def get_lot(lot_id: str):
    return db.one(
        f"SELECT * FROM {db.fq('v_current_lot_stock')} WHERE lot_id = %s",
        [lot_id],
    )


def lot_history(lot_id: str):
    return db.rows(
        f"SELECT * FROM {db.fq('inventory_events')} WHERE lot_id = %s ORDER BY event_time ASC",
        [lot_id],
    )


def lookup_product(code: str):
    """Find a product by its barcode (GTIN/EAN)."""
    return db.one(
        f"SELECT product_id, name, category, usual_package_size_g, default_best_before_days "
        f"FROM {db.fq('products')} WHERE gtin = %s LIMIT 1",
        [code],
    )


# ---- writes --------------------------------------------------------------

def _get_or_create_product(cur, *, name, gtin, shelf_life_days):
    """Return (product_id, default_best_before_days) for a product, matching by
    barcode first, then canonical name, else creating it."""
    key = normalize_name(name)
    category = categorize(name)
    if gtin:
        cur.execute(
            f"SELECT product_id, default_best_before_days FROM {db.fq('products')} WHERE gtin = %s LIMIT 1",
            [gtin],
        )
        row = cur.fetchone()
        if row:
            return row[0], row[1]
    cur.execute(
        f"SELECT product_id, default_best_before_days FROM {db.fq('products')} WHERE name_key = %s LIMIT 1",
        [key],
    )
    row = cur.fetchone()
    if row:
        return row[0], row[1]

    product_id = str(uuid.uuid4())
    cur.execute(
        f"INSERT INTO {db.fq('products')} "
        "(product_id, name, brand, gtin, preferred_unit, usual_package_size_g, "
        " name_key, category, default_best_before_days, created_at, updated_at) "
        "VALUES (%s, %s, NULL, %s, 'g', NULL, %s, %s, %s, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
        [product_id, name, gtin, key, category, shelf_life_days],
    )
    return product_id, shelf_life_days


def add_lot(*, name, gtin=None, qty_g, added_date=None, best_before=None,
            location=None, notes=None, actor=None, shelf_life_days=None, min_stock_g=None, op_id=None):
    """Create a product if needed, a lot, and its stock-in event, atomically."""
    op_id = op_id or str(uuid.uuid4())
    qty_g = float(qty_g)
    added = date.fromisoformat(added_date) if added_date else date.today()
    lot_id = str(uuid.uuid4())

    with atomic() as cur:
        cur.execute(
            f"SELECT lot_id FROM {db.fq('inventory_events')} WHERE op_id = %s LIMIT 1",
            [op_id],
        )
        dup = cur.fetchone()
        if dup:
            return {"lot_id": dup[0], "duplicate": True}

        product_id, default_bbd = _get_or_create_product(
            cur, name=name, gtin=gtin, shelf_life_days=shelf_life_days
        )
        if best_before is None and default_bbd is not None:
            best_before = (added + timedelta(days=int(default_bbd))).isoformat()

        # Remember the last-added package size so the next add is prefilled.
        cur.execute(
            f"UPDATE {db.fq('products')} SET usual_package_size_g = CAST(%s AS DECIMAL(10,2)), "
            "updated_at = CURRENT_TIMESTAMP WHERE product_id = %s",
            [qty_g, product_id],
        )

        if min_stock_g is not None:
            cur.execute(
                f"UPDATE {db.fq('products')} SET min_stock_g = CAST(%s AS NUMERIC(10,2)), "
                "updated_at = CURRENT_TIMESTAMP WHERE product_id = %s",
                [float(min_stock_g), product_id],
            )

        cur.execute(
            f"INSERT INTO {db.fq('lots')} "
            "(lot_id, product_id, added_date, best_before_date, location, notes, created_at) "
            "VALUES (%s, %s, CAST(%s AS DATE), CAST(%s AS DATE), %s, %s, CURRENT_TIMESTAMP)",
            [lot_id, product_id, added.isoformat(), best_before, location, notes],
        )

        cur.execute(
            f"INSERT INTO {db.fq('inventory_events')} "
            "(event_id, op_id, lot_id, event_type, quantity_delta_g, event_time, actor, method, note, reversed_event_id) "
            "VALUES (%s, %s, %s, 'STOCK_IN', CAST(%s AS DECIMAL(10,2)), CURRENT_TIMESTAMP, %s, 'SYSTEM', %s, NULL)",
            [str(uuid.uuid4()), op_id, lot_id, qty_g, actor, notes],
        )

    return {"lot_id": lot_id, "product_id": product_id, "duplicate": False}


def _record(*, lot_id, delta=None, target=None, event_type, method, actor, note, op_id):
    """Insert one ledger event, validating the balance, with retry on conflict.

    Exactly one of `delta` (relative) or `target` (absolute grams remaining)
    must be given.
    """
    op_id = op_id or str(uuid.uuid4())

    for _attempt in range(3):
        try:
            with atomic() as cur:
                cur.execute(
                    f"SELECT lot_id FROM {db.fq('inventory_events')} WHERE op_id = %s LIMIT 1",
                    [op_id],
                )
                dup = cur.fetchone()
                if dup:
                    return {"lot_id": dup[0], "duplicate": True}

                cur.execute(
                    f"SELECT COALESCE(SUM(quantity_delta_g), 0) FROM {db.fq('inventory_events')} WHERE lot_id = %s",
                    [lot_id],
                )
                balance = float(cur.fetchone()[0])
                if target is not None:
                    delta = target - balance
                new_balance = balance + delta
                if new_balance < -1e-9:
                    raise ValueError(
                        f"Not enough stock: about {balance:g} g available"
                    )
                cur.execute(
                    f"INSERT INTO {db.fq('inventory_events')} "
                    "(event_id, op_id, lot_id, event_type, quantity_delta_g, event_time, actor, method, note, reversed_event_id) "
                    "VALUES (%s, %s, %s, %s, CAST(%s AS DECIMAL(10,2)), CURRENT_TIMESTAMP, %s, %s, %s, NULL)",
                    [str(uuid.uuid4()), op_id, lot_id, event_type, delta, actor, method, note],
                )
            return {"lot_id": lot_id, "grams_remaining": new_balance, "duplicate": False}
        except Exception as error:
            if _is_conflict(error):
                continue
            raise

    raise RuntimeError("Could not commit the update after several attempts.")


def record_use(*, lot_id, grams_used, method="ESTIMATE", actor=None, note=None, op_id=None):
    return _record(
        lot_id=lot_id, delta=-float(grams_used), event_type="USE",
        method=method, actor=actor, note=note, op_id=op_id,
    )


def set_remaining(*, lot_id, grams_remaining, method="ESTIMATE", actor=None, note=None, op_id=None):
    grams_remaining = float(grams_remaining)
    if grams_remaining < 0:
        raise ValueError("Grams remaining cannot be negative.")
    return _record(
        lot_id=lot_id, target=grams_remaining, event_type="ADJUST",
        method=method, actor=actor,
        note=note or f"Set remaining to {grams_remaining:g} g", op_id=op_id,
    )


def discard(*, lot_id, actor=None, note=None, op_id=None):
    """Throw away everything that remains (distinct from using it)."""
    lot = get_lot(lot_id)
    if lot is None:
        raise ValueError(f"Unknown lot: {lot_id}")
    if float(lot["grams_remaining"]) <= 0:
        return {"lot_id": lot_id, "grams_remaining": 0, "duplicate": False}
    return _record(
        lot_id=lot_id, target=0, event_type="DISCARD", method="ESTIMATE",
        actor=actor, note=note or "Discarded remaining", op_id=op_id,
    )


# ---- shopping list -------------------------------------------------------

def list_shopping():
    return db.rows(
        f"SELECT * FROM {db.fq('shopping_items')} WHERE done_at IS NULL ORDER BY created_at ASC"
    )


def add_shopping_item(*, name, note=None):
    item_id = str(uuid.uuid4())
    with atomic() as cur:
        cur.execute(
            f"INSERT INTO {db.fq('shopping_items')} (item_id, name, note) VALUES (%s, %s, %s)",
            [item_id, name, note],
        )
    return {"item_id": item_id}


def complete_shopping_item(item_id):
    with atomic() as cur:
        cur.execute(
            f"UPDATE {db.fq('shopping_items')} SET done_at = CURRENT_TIMESTAMP WHERE item_id = %s",
            [item_id],
        )
    return {"item_id": item_id, "done": True}
