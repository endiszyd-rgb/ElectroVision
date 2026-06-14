"""Client for ElectroVision Project Server (local or remote)."""
import json
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path


class ServerClient:
    """
    HTTP client for the ElectroVision Project Server.

    Usage
    -----
    client = ServerClient("http://localhost:8765")
    client.register("username", "password")
    client.login("username", "password")
    projects = client.list_projects()
    client.upload_project("My PCB", ["board.kicad_pcb", "bom.csv"])
    client.download_project("uuid", "/tmp/dest")
    """

    def __init__(self, base_url: str = "http://localhost:8765") -> None:
        self._base = base_url.rstrip("/")
        self._token: str = ""

    def _req(self, method: str, path: str, data=None, files=None) -> dict:
        url = f"{self._base}{path}"
        headers = {"Content-Type": "application/json"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"

        if files:
            body, content_type = self._encode_multipart(data or {}, files)
            headers["Content-Type"] = content_type
        elif data:
            body = json.dumps(data).encode()
        else:
            body = None

        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"HTTP {e.code}: {e.read().decode()}")
        except urllib.error.URLError as e:
            raise ConnectionError(f"Nie można połączyć z serwerem {self._base}: {e.reason}")

    def _encode_multipart(self, fields: dict, files: list[str]) -> tuple[bytes, str]:
        boundary = b"----ElectroVisionBoundary"
        parts = []
        for key, val in fields.items():
            parts.append(b"--" + boundary + b"\r\n")
            parts.append(f'Content-Disposition: form-data; name="{key}"\r\n\r\n'.encode())
            parts.append(str(val).encode() + b"\r\n")
        for file_path in files:
            p = Path(file_path)
            if p.exists():
                parts.append(b"--" + boundary + b"\r\n")
                parts.append(f'Content-Disposition: form-data; name="file_{p.stem}"; filename="{p.name}"\r\n\r\n'.encode())
                parts.append(p.read_bytes() + b"\r\n")
        parts.append(b"--" + boundary + b"--\r\n")
        body = b"".join(parts)
        content_type = f"multipart/form-data; boundary={boundary.decode()}"
        return body, content_type

    def health_check(self) -> bool:
        try:
            result = self._req("GET", "/api/health")
            return result.get("status") == "ok"
        except Exception:
            return False

    def register(self, username: str, password: str) -> str:
        result = self._req("POST", "/api/auth/register", {"username": username, "password": password})
        self._token = result.get("token", "")
        return self._token

    def login(self, username: str, password: str) -> str:
        result = self._req("POST", "/api/auth/login", {"username": username, "password": password})
        self._token = result.get("token", "")
        return self._token

    def list_projects(self) -> list[dict]:
        return self._req("GET", "/api/projects")

    def search_projects(self, query: str) -> list[dict]:
        return self._req("GET", f"/api/search?q={urllib.parse.quote(query)}")

    def upload_project(self, name: str, files: list[str], description: str = "", tags: list[str] = None) -> dict:
        fields = {
            "name": name,
            "description": description,
            "tags": ",".join(tags or []),
            "public": "true",
        }
        return self._req("POST", "/api/projects", data=fields, files=files)

    def download_project(self, project_id: str, dest_dir: str) -> str:
        url = f"{self._base}/api/projects/{project_id}/download"
        headers = {}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        dest = Path(dest_dir)
        dest.mkdir(parents=True, exist_ok=True)
        zip_path = str(dest / f"{project_id}.zip")
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=30) as resp:
            Path(zip_path).write_bytes(resp.read())
        import zipfile
        with zipfile.ZipFile(zip_path) as zf:
            zf.extractall(str(dest))
        Path(zip_path).unlink()
        return str(dest)

    def get_project_meta(self, project_id: str) -> dict:
        return self._req("GET", f"/api/projects/{project_id}")

    def delete_project(self, project_id: str) -> dict:
        return self._req("DELETE", f"/api/projects/{project_id}")

    @property
    def is_authenticated(self) -> bool:
        return bool(self._token)
