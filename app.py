"""Flask app for the Stock Tracker (Databricks App)."""
import os

from flask import Flask, jsonify, request, send_from_directory

import db
import service

app = Flask(__name__)

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

_bootstrapped = False


@app.get("/")
def index():
    global _bootstrapped
    if not _bootstrapped:
        try:
            db.bootstrap()
            _bootstrapped = True
        except Exception:
            pass
    return send_from_directory(STATIC_DIR, "index.html")


@app.get("/health")
def health():
    db.one("SELECT 1 AS ok")
    return jsonify({"status": "ok"})


@app.get("/api/inventory")
def inventory():
    return jsonify(service.list_inventory())


@app.get("/api/products/lookup")
def product_lookup():
    code = (request.args.get("code") or "").strip()
    if not code:
        return jsonify({"error": "code is required"}), 400
    return jsonify({"product": service.lookup_product(code)})


@app.get("/api/products/<product_id>/lots")
def product_lots(product_id):
    return jsonify(service.list_lots(product_id))


@app.get("/api/lots/<lot_id>")
def lot_detail(lot_id):
    return jsonify({
        "lot": service.get_lot(lot_id),
        "history": service.lot_history(lot_id),
    })


@app.post("/api/lots")
def create_lot():
    payload = request.get_json(force=True) or {}
    name = (payload.get("name") or "").strip()
    qty_g = payload.get("qty_g")

    if not name:
        return jsonify({"error": "name is required"}), 400
    if qty_g is None:
        return jsonify({"error": "qty_g is required"}), 400
    try:
        qty_g = float(qty_g)
    except (TypeError, ValueError):
        return jsonify({"error": "qty_g must be a number"}), 400
    if qty_g <= 0:
        return jsonify({"error": "qty_g must be positive"}), 400

    result = service.add_lot(
        name=name,
        gtin=payload.get("gtin") or None,
        qty_g=qty_g,
        added_date=payload.get("added_date"),
        best_before=payload.get("best_before"),
        location=payload.get("location"),
        notes=payload.get("notes"),
        actor=payload.get("actor"),
        shelf_life_days=payload.get("shelf_life_days"),
        op_id=payload.get("op_id"),
    )
    return jsonify(result), 201


def _run_lot_action(lot_id, fn):
    payload = request.get_json(force=True) or {}
    try:
        result = fn(
            lot_id=lot_id,
            actor=payload.get("actor"),
            note=payload.get("note"),
            op_id=payload.get("op_id"),
        )
    except ValueError as error:
        return jsonify({"error": str(error)}), 409
    return jsonify(result)


@app.post("/api/lots/<lot_id>/use")
def use_lot(lot_id):
    payload = request.get_json(force=True) or {}
    grams_used = payload.get("grams_used")
    if grams_used is None:
        return jsonify({"error": "grams_used is required"}), 400
    try:
        result = service.record_use(
            lot_id=lot_id,
            grams_used=float(grams_used),
            method=payload.get("method", "ESTIMATE"),
            actor=payload.get("actor"),
            note=payload.get("note"),
            op_id=payload.get("op_id"),
        )
    except ValueError as error:
        return jsonify({"error": str(error)}), 409
    return jsonify(result)


@app.post("/api/lots/<lot_id>/remaining")
def remaining_lot(lot_id):
    payload = request.get_json(force=True) or {}
    grams_remaining = payload.get("grams_remaining")
    if grams_remaining is None:
        return jsonify({"error": "grams_remaining is required"}), 400
    try:
        result = service.set_remaining(
            lot_id=lot_id,
            grams_remaining=float(grams_remaining),
            method=payload.get("method", "ESTIMATE"),
            actor=payload.get("actor"),
            note=payload.get("note"),
            op_id=payload.get("op_id"),
        )
    except ValueError as error:
        return jsonify({"error": str(error)}), 409
    return jsonify(result)


@app.post("/api/lots/<lot_id>/discard")
def discard_lot(lot_id):
    return _run_lot_action(lot_id, service.discard)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
