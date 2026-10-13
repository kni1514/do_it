from __future__ import annotations

import queue
import threading
import uuid

from flask import Flask, jsonify, make_response, request

app = Flask(__name__)
pending_queries: queue.Queue[dict[str, str]] = queue.Queue()
requests: dict[str, dict[str, str]] = {}
requests_lock = threading.Lock()


@app.after_request
def add_local_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


@app.route("/ask", methods=["POST", "OPTIONS"])
def ask():
    if request.method == "OPTIONS":
        return make_response("", 204)
    data = request.get_json(silent=True) or {}
    query = data.get("query", "")
    if not isinstance(query, str) or not query.strip():
        return jsonify(error="query must be a non-empty string"), 400

    request_id = uuid.uuid4().hex
    with requests_lock:
        requests[request_id] = {"query": query.strip(), "status": "pending"}
    pending_queries.put({"id": request_id, "query": query.strip()})
    return jsonify(id=request_id), 202


@app.route("/query", methods=["GET", "OPTIONS"])
def next_query():
    if request.method == "OPTIONS":
        return make_response("", 204)
    try:
        item = pending_queries.get_nowait()
    except queue.Empty:
        return "", 204
    return jsonify(item)


@app.route("/response", methods=["POST", "OPTIONS"])
def submit_response():
    if request.method == "OPTIONS":
        return make_response("", 204)
    data = request.get_json(silent=True) or {}
    request_id = data.get("id")
    answer = data.get("response")
    if not isinstance(request_id, str) or not isinstance(answer, str):
        return jsonify(error="id and response are required"), 400
    with requests_lock:
        record = requests.get(request_id)
        if record is None:
            return jsonify(error="unknown request id"), 404
        record["response"] = answer
        record["status"] = "complete"
    return jsonify(ok=True)


@app.route("/result/<request_id>", methods=["GET", "OPTIONS"])
def result(request_id: str):
    if request.method == "OPTIONS":
        return make_response("", 204)
    with requests_lock:
        record = requests.get(request_id)
        if record is None:
            return jsonify(error="unknown request id"), 404
        if record["status"] == "complete":
            return jsonify(status="complete", response=record["response"])
    return jsonify(status="pending"), 202


if __name__ == "__main__":
    print("Local ChatGPT bridge listening at http://127.0.0.1:1514")
    app.run(host="127.0.0.1", port=1514, threaded=True)
