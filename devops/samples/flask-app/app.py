"""
Flask Sample Application
A simple REST API for testing the DevOps automation pipeline.
"""

from flask import Flask, jsonify, request
import os

app = Flask(__name__)

# Sample data store
items = [
    {"id": 1, "name": "Item 1", "description": "First item"},
    {"id": 2, "name": "Item 2", "description": "Second item"},
]


@app.route("/")
def home():
    """Home endpoint."""
    return jsonify({
        "message": "Welcome to Flask Sample API",
        "version": "1.0.0",
        "endpoints": ["/", "/health", "/api/items"],
    })


@app.route("/health")
def health():
    """Health check endpoint for load balancers."""
    return jsonify({"status": "healthy", "service": "flask-sample"})


@app.route("/api/items", methods=["GET"])
def get_items():
    """Get all items."""
    return jsonify({"items": items, "count": len(items)})


@app.route("/api/items/<int:item_id>", methods=["GET"])
def get_item(item_id):
    """Get a specific item."""
    item = next((i for i in items if i["id"] == item_id), None)
    if item:
        return jsonify(item)
    return jsonify({"error": "Item not found"}), 404


@app.route("/api/items", methods=["POST"])
def create_item():
    """Create a new item."""
    data = request.get_json()
    if not data or "name" not in data:
        return jsonify({"error": "Name is required"}), 400
    
    new_id = max(i["id"] for i in items) + 1 if items else 1
    new_item = {
        "id": new_id,
        "name": data["name"],
        "description": data.get("description", ""),
    }
    items.append(new_item)
    return jsonify(new_item), 201


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
