"""Google Drive integration for ElectroVision projects.

Features:
- Upload project files (PCB, BOM, STL, code) to Google Drive folder
- Download projects from Drive
- List shared PCB design folders

Requires: pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib
"""

from pathlib import Path
import json
import io


_SCOPES = ["https://www.googleapis.com/auth/drive.file"]
_TOKEN_FILE = Path.home() / ".electrovision" / "gdrive_token.json"
_CREDS_FILE = Path.home() / ".electrovision" / "gdrive_credentials.json"


class GoogleDriveClient:
    """
    Manages Google Drive sync for ElectroVision projects.

    First-time setup
    ----------------
    1. Go to Google Cloud Console → Create project → Enable Drive API
    2. Create OAuth2 credentials (Desktop app)
    3. Download credentials.json → save to ~/.electrovision/gdrive_credentials.json
    4. Call authenticate() — opens browser for consent

    Usage
    -----
    client = GoogleDriveClient()
    client.authenticate()
    folder_id = client.create_folder("ElectroVision Projects")
    client.upload_file("my_board.kicad_pcb", folder_id)
    """

    def __init__(self) -> None:
        self._service = None
        _TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)

    def _ensure_service(self) -> None:
        if self._service:
            return
        try:
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from google.auth.transport.requests import Request
            from googleapiclient.discovery import build
        except ImportError:
            raise ImportError(
                "Zainstaluj: pip install google-api-python-client google-auth-oauthlib"
            )

        creds = None
        if _TOKEN_FILE.exists():
            creds = Credentials.from_authorized_user_file(str(_TOKEN_FILE), _SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            elif _CREDS_FILE.exists():
                flow = InstalledAppFlow.from_client_secrets_file(str(_CREDS_FILE), _SCOPES)
                creds = flow.run_local_server(port=0)
                _TOKEN_FILE.write_text(creds.to_json())
            else:
                raise FileNotFoundError(
                    f"Brak pliku credentials.json Google Drive.\n"
                    f"Umieść go w: {_CREDS_FILE}\n"
                    f"Pobierz z: Google Cloud Console → APIs → Credentials"
                )
        self._service = build("drive", "v3", credentials=creds)

    def authenticate(self) -> dict:
        self._ensure_service()
        about = self._service.about().get(fields="user").execute()
        return about.get("user", {})

    def create_folder(self, name: str, parent_id: str = "") -> str:
        self._ensure_service()
        meta = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
        if parent_id:
            meta["parents"] = [parent_id]
        folder = self._service.files().create(body=meta, fields="id").execute()
        return folder.get("id", "")

    def upload_file(self, local_path: str, folder_id: str = "") -> str:
        from googleapiclient.http import MediaFileUpload
        self._ensure_service()
        p = Path(local_path)
        meta = {"name": p.name}
        if folder_id:
            meta["parents"] = [folder_id]
        media = MediaFileUpload(str(p), resumable=True)
        f = self._service.files().create(body=meta, media_body=media, fields="id,webViewLink").execute()
        return f.get("webViewLink", f.get("id", ""))

    def upload_project(self, project_name: str, files: list[str]) -> str:
        self._ensure_service()
        root_id = self._get_or_create_root()
        proj_id = self.create_folder(project_name, root_id)
        links = []
        for f in files:
            if Path(f).exists():
                link = self.upload_file(f, proj_id)
                links.append(link)
        return f"Przesłano {len(links)} plików do Google Drive (folder: {project_name})"

    def list_projects(self) -> list[dict]:
        self._ensure_service()
        root_id = self._get_or_create_root()
        results = self._service.files().list(
            q=f"'{root_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false",
            fields="files(id, name, createdTime, modifiedTime)",
        ).execute()
        return results.get("files", [])

    def download_file(self, file_id: str, dest: str) -> str:
        from googleapiclient.http import MediaIoBaseDownload
        self._ensure_service()
        request = self._service.files().get_media(fileId=file_id)
        buf = io.BytesIO()
        downloader = MediaIoBaseDownload(buf, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        Path(dest).write_bytes(buf.getvalue())
        return dest

    def download_project(self, folder_id: str, dest_dir: str) -> list[str]:
        self._ensure_service()
        results = self._service.files().list(
            q=f"'{folder_id}' in parents and trashed=false",
            fields="files(id, name)",
        ).execute()
        dest = Path(dest_dir)
        dest.mkdir(parents=True, exist_ok=True)
        downloaded = []
        for item in results.get("files", []):
            out = str(dest / item["name"])
            try:
                self.download_file(item["id"], out)
                downloaded.append(out)
            except Exception:
                pass
        return downloaded

    def _get_or_create_root(self) -> str:
        results = self._service.files().list(
            q="name='ElectroVision' and mimeType='application/vnd.google-apps.folder' and trashed=false",
            fields="files(id)",
        ).execute()
        files = results.get("files", [])
        if files:
            return files[0]["id"]
        return self.create_folder("ElectroVision")
