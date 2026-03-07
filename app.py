from __future__ import annotations

import os
from datetime import datetime

from flask import Flask, Response, jsonify, render_template, request
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from market_basket import MarketBasketService

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)

service = MarketBasketService()
service.reset_dataset()


def _error_response(message: str, status_code: int) -> tuple[Response, int]:
    return jsonify({"error": message}), status_code


def _build_upload_path(filename: str) -> str:
    safe_name = secure_filename(filename) or "dataset.csv"
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return os.path.join(UPLOAD_DIR, f"{timestamp}_{safe_name}")


@app.route("/")
def index() -> str:
    return render_template("index.html")


@app.route("/api/bootstrap")
def bootstrap() -> Response:
    return jsonify(service.build_bootstrap_payload())


@app.route("/api/pipeline/upload", methods=["POST"])
def upload_pipeline_csv() -> Response | tuple[Response, int]:
    uploaded: FileStorage | None = request.files.get("file")
    if uploaded is None or not uploaded.filename:
        return _error_response("Please choose a CSV file to upload.", 400)

    if not uploaded.filename.lower().endswith(".csv"):
        return _error_response("Only CSV uploads are supported.", 400)

    stored_path = _build_upload_path(uploaded.filename)
    uploaded.save(stored_path)

    try:
        payload = service.process_dataset(stored_path, uploaded.filename, "upload")
    except ValueError as exc:
        if os.path.exists(stored_path):
            os.remove(stored_path)
        return _error_response(str(exc), 400)

    return jsonify(payload)


@app.route("/api/iteration/<int:iteration_number>")
def get_iteration(iteration_number: int) -> Response | tuple[Response, int]:
    payload = service.get_iteration_payload(iteration_number)
    if payload is None:
        return _error_response(f"Iteration {iteration_number} not found.", 404)
    return jsonify(payload)


@app.route("/api/cross_sell/<item>")
def cross_sell_item(item: str) -> Response | tuple[Response, int]:
    payload = service.get_cross_sell_payload(item)
    if payload is None:
        return _error_response("No model computed yet.", 500)
    return jsonify(payload)


@app.route("/api/items")
def get_items() -> Response:
    return jsonify(service.get_items_payload())


@app.route("/api/summary")
def get_summary() -> Response:
    return jsonify(service.get_summary_payload())


if __name__ == "__main__":
    app.run(debug=False, port=5000)
