"""Business logic: inventory reads and atomic writes.

The multi-table atomic writes use the Databricks SQL Connector with
`autocommit=False` and the standard DB-API commit/rollback model. This is the
documented pattern for interactive transactions on a SQL warehouse. The
milestone-1 spike must confirm multi-table atomicity; if `autocommit=False`
alone does not yield it, fall back to explicit `BEGIN TRANSACTION ... COMMIT`
(or the non-interactive `BEGIN ATOMIC ... END`) form.
"""
import uuid
from contextlib import contextmanager
from datetime import date

import db


@contextmanager
def atomic():
    """Yield a cursor whose statements commit together or not at all."""
    conn = db.connect(autocommit=False)
    cur = conn.cursor()
    try:
        yield cur
        conn.commit()
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        cur.close()
        conn.close()


def _is_conflict(error: Exception) -> bool:
    message = str(error).lower()
    return "concurrent" in message or "conflict" in message


def list_inventory():
    return db.rows(
        f"SELECT * FROM {db.fq('v_current_lot_stock')} ORDER BY added_date ASC"
    )


def get_lot(lot_id: str):
    return db.one(
        f"SELECT * FROM {db.fq('v_current_lot_stock')} WHERE lot_id = ?",
        [lot_id],
    )


def lot_history(lot_id: str):
    return db.rows(
        f"SELECT * FROM {db.fq('inventory_events')} WHERE lot_id = ? ORDER BY event_time ASC",
        [lot_id],
    )


def _already_processed(op_id: str):
    return db.one(
        f"SELECT lot_id FROM {db.fq('inventory_events')} WHERE op_id = ? LIMIT 1",
        [op_id],
    )


def add_lot(*, name, gtin=None, qty_g, added_date=None, best_before=None,
            location=None, notes=None, actor=None, op_id=None):
    """Create a product if needed, a lot, and its stock-in event, atomically."""
    op_id = op_id or str(uuid.uuid4())
    processed = _already_processed(op_id)
    if processed:
        return {"lot_id": processed["lot_id"], "duplicate": True}

    qty_g = float(qty_g)
    added_date = added_date or date.today().isoformat()
    product_id = str(uuid.uuid4())
    lot_id = str(uuid.uuid4())

    with atomic() as cur:
        if gtin:
            cur.execute(
                f"SELECT product_id FROM {db.fq('products')} WHERE gtin = ? LIMIT 1",
                [gtin],
            )
        else:
            cur.execute(
                f"SELECT product_id FROM {db.fq('products')} WHERE lower(name) = lower(?) LIMIT 1",
                [name],
            )
        row = cur.fetchone()
        if row:
            product_id = row[0]
        else:
            cur.execute(
                f"INSERT INTO {db.fq('products')} "
                "(product_id, name, brand, gtin, preferred_unit, usual_package_size_g, created_at, updated_at) "
                "VALUES (?, ?, NULL, ?, 'g', CAST(? AS DECIMAL(10,2)), current_timestamp(), current_timestamp())",
                [product_id, name, gtin, qty_g],
            )

        cur.execute(
            f"INSERT INTO {db.fq('lots')} "
            "(lot_id, product_id, added_date, best_before_date, location, notes, created_at) "
            "VALUES (?, ?, CAST(? AS DATE), CAST(? AS DATE), ?, ?, current_timestamp())",
            [lot_id, product_id, added_date, best_before, location, notes],
        )

        cur.execute(
            f"INSERT INTO {db.fq('inventory_events')} "
            "(event_id, op_id, lot_id, event_type, quantity_delta_g, event_time, actor, method, note, reversed_event_id) "
            "VALUES (?, ?, ?, 'STOCK_IN', CAST(? AS DECIMAL(10,2)), current_timestamp(), ?, 'SYSTEM', ?, NULL)",
            [str(uuid.uuid4()), op_id, lot_id, qty_g, actor, notes],
        )

    return {"lot_id": lot_id, "product_id": product_id, "duplicate": False}


def _apply_delta(*, lot_id, delta, event_type, method, actor, note, op_id):
    op_id = op_id or str(uuid.uuid4())
    processed = _already_processed(op_id)
    if processed:
        return {"lot_id": lot_id, "duplicate": True}

    for _attempt in range(3):
        try:
            with atomic() as cur:
                cur.execute(
                    f"SELECT COALESCE(SUM(quantity_delta_g), 0) FROM {db.fq('inventory_events')} WHERE lot_id = ?",
                    [lot_id],
                )
                balance = float(cur.fetchone()[0])
                new_balance = balance + delta
                if new_balance < -1e-9:
                    raise ValueError(
                        f"Not enough stock: about {balance:g} g available, "
                        f"{abs(delta):g} g requested"
                    )
                cur.execute(
                    f"INSERT INTO {db.fq('inventory_events')} "
                    "(event_id, op_id, lot_id, event_type, quantity_delta_g, event_time, actor, method, note, reversed_event_id) "
                    "VALUES (?, ?, ?, ?, CAST(? AS DECIMAL(10,2)), current_timestamp(), ?, ?, ?, NULL)",
                    [str(uuid.uuid4()), op_id, lot_id, event_type, delta, actor, method, note],
                )
            return {"lot_id": lot_id, "grams_remaining": new_balance, "duplicate": False}
        except Exception as error:
            if _is_conflict(error):
                continue
            raise

    raise RuntimeError("Could not commit the update after several attempts.")


def record_use(*, lot_id, grams_used, method="ESTIMATE", actor=None, note=None, op_id=None):
    return _apply_delta(
        lot_id=lot_id,
        delta=-float(grams_used),
        event_type="USE",
        method=method,
        actor=actor,
        note=note,
        op_id=op_id,
    )


def set_remaining(*, lot_id, grams_remaining, method="ESTIMATE", actor=None, note=None, op_id=None):
    grams_remaining = float(grams_remaining)
    current = get_lot(lot_id)
    if current is None:
        raise ValueError(f"Unknown lot: {lot_id}")
    delta = grams_remaining - float(current["grams_remaining"])
    return _apply_delta(
        lot_id=lot_id,
        delta=delta,
        event_type="ADJUST",
        method=method,
        actor=actor,
        note=note or f"Set remaining to {grams_remaining:g} g",
        op_id=op_id,
    )
