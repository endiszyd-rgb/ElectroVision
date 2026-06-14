"""
ElectroVision Project Server — Flask REST API

Allows users to upload, download, share and browse ElectroVision projects.

Endpoints
---------
GET  /api/projects              — list all public projects
GET  /api/projects/<id>         — get project metadata
POST /api/projects              — upload new project (multipart/form-data)
GET  /api/projects/<id>/files   — list project files
GET  /api/projects/<id>/download — download project ZIP
DELETE /api/projects/<id>       — delete project (requires token)

POST /api/auth/register         — register user
POST /api/auth/login            — login, returns token

GET  /api/search?q=esp32        — search projects

Run
---
  python -m server.app
or via ElectroVision: menu Tools → Start Local Server
"""

import os
import json
import uuid
import zipfile
import hashlib
import io
from pathlib import Path
from datetime import datetime
from functools import wraps

try:
    from flask import Flask, request, jsonify, send_file, abort, g
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False

STORAGE_DIR = Path(__file__).parent / "storage" / "projects"
USERS_FILE  = Path(__file__).parent / "storage" / "users.json"
SERVER_HOST = os.environ.get("EV_SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.environ.get("EV_SERVER_PORT", "8765"))


def _load_users() -> dict:
    if USERS_FILE.exists():
        return json.loads(USERS_FILE.read_text(encoding="utf-8"))
    return {}


def _save_users(users: dict) -> None:
    USERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    USERS_FILE.write_text(json.dumps(users, indent=2, ensure_ascii=False), encoding="utf-8")


def _hash_password(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


def create_app() -> "Flask":
    if not FLASK_AVAILABLE:
        raise ImportError("Zainstaluj Flask: pip install flask")

    app = Flask(__name__)
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)

    def _require_token(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            token = request.headers.get("Authorization", "").replace("Bearer ", "")
            users = _load_users()
            user = next((u for u in users.values() if u.get("token") == token), None)
            if not user:
                abort(401)
            g.current_user = user
            return f(*args, **kwargs)
        return decorated

    def _list_projects_meta() -> list[dict]:
        projects = []
        for folder in sorted(STORAGE_DIR.iterdir()):
            meta_file = folder / "meta.json"
            if meta_file.exists():
                try:
                    meta = json.loads(meta_file.read_text(encoding="utf-8"))
                    if meta.get("public", True):
                        projects.append(meta)
                except Exception:
                    pass
        return projects

    @app.route("/api/projects", methods=["GET"])
    def list_projects():
        return jsonify(_list_projects_meta())

    @app.route("/api/projects/<project_id>", methods=["GET"])
    def get_project(project_id):
        meta_file = STORAGE_DIR / project_id / "meta.json"
        if not meta_file.exists():
            abort(404)
        return jsonify(json.loads(meta_file.read_text(encoding="utf-8")))

    @app.route("/api/projects", methods=["POST"])
    @_require_token
    def upload_project():
        name        = request.form.get("name", "Untitled")
        description = request.form.get("description", "")
        public      = request.form.get("public", "true").lower() == "true"
        tags        = request.form.get("tags", "").split(",")

        project_id = str(uuid.uuid4())
        proj_dir   = STORAGE_DIR / project_id
        proj_dir.mkdir(parents=True, exist_ok=True)

        saved_files = []
        for key, file in request.files.items():
            dest = proj_dir / file.filename
            file.save(str(dest))
            saved_files.append(file.filename)

        meta = {
            "id":          project_id,
            "name":        name,
            "description": description,
            "public":      public,
            "tags":        [t.strip() for t in tags if t.strip()],
            "owner":       g.current_user["username"],
            "created_at":  datetime.utcnow().isoformat(),
            "files":       saved_files,
        }
        (proj_dir / "meta.json").write_text(json.dumps(meta, indent=2, ensure_ascii=False), encoding="utf-8")
        return jsonify({"id": project_id, "message": "Projekt zapisany", "files": saved_files}), 201

    @app.route("/api/projects/<project_id>/files", methods=["GET"])
    def list_project_files(project_id):
        proj_dir = STORAGE_DIR / project_id
        if not proj_dir.exists():
            abort(404)
        files = [f.name for f in proj_dir.iterdir() if f.name != "meta.json"]
        return jsonify(files)

    @app.route("/api/projects/<project_id>/download", methods=["GET"])
    def download_project(project_id):
        proj_dir = STORAGE_DIR / project_id
        if not proj_dir.exists():
            abort(404)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            for f in proj_dir.iterdir():
                zf.write(str(f), f.name)
        buf.seek(0)
        return send_file(buf, mimetype="application/zip", as_attachment=True,
                         download_name=f"{project_id}.zip")

    @app.route("/api/projects/<project_id>", methods=["DELETE"])
    @_require_token
    def delete_project(project_id):
        proj_dir = STORAGE_DIR / project_id
        if not proj_dir.exists():
            abort(404)
        meta_file = proj_dir / "meta.json"
        if meta_file.exists():
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            if meta.get("owner") != g.current_user["username"]:
                abort(403)
        import shutil
        shutil.rmtree(str(proj_dir))
        return jsonify({"message": "Projekt usunięty"})

    @app.route("/api/search", methods=["GET"])
    def search():
        q = request.args.get("q", "").lower()
        results = [
            p for p in _list_projects_meta()
            if q in p.get("name", "").lower()
            or q in p.get("description", "").lower()
            or any(q in t.lower() for t in p.get("tags", []))
        ]
        return jsonify(results)

    @app.route("/api/auth/register", methods=["POST"])
    def register():
        data = request.get_json()
        users = _load_users()
        username = data.get("username", "")
        if not username or username in users:
            return jsonify({"error": "Nazwa zajęta lub pusta"}), 400
        token = str(uuid.uuid4())
        users[username] = {
            "username": username,
            "password": _hash_password(data.get("password", "")),
            "token": token,
            "created_at": datetime.utcnow().isoformat(),
        }
        _save_users(users)
        return jsonify({"token": token, "username": username}), 201

    @app.route("/api/auth/login", methods=["POST"])
    def login():
        data  = request.get_json()
        users = _load_users()
        username = data.get("username", "")
        pw_hash  = _hash_password(data.get("password", ""))
        user = users.get(username)
        if not user or user["password"] != pw_hash:
            return jsonify({"error": "Nieprawidłowe dane"}), 401
        user["token"] = str(uuid.uuid4())
        _save_users(users)
        return jsonify({"token": user["token"], "username": username})

    @app.route("/api/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok", "version": "0.1.0", "service": "ElectroVision Server"})

    return app


if __name__ == "__main__":
    app = create_app()
    print(f"ElectroVision Server uruchomiony na http://{SERVER_HOST}:{SERVER_PORT}")
    app.run(host=SERVER_HOST, port=SERVER_PORT, debug=False)
