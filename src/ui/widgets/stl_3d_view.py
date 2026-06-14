"""STL / STEP 3D Viewer.

Primary:  QWebEngineView + Three.js (PySide6-WebEngine, Python <=3.12)
Fallback: Pure QPainter + numpy soft-renderer (no extra deps, Python 3.13+)
"""
from __future__ import annotations
import math
import struct
import json
from pathlib import Path

import numpy as np
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel, QHBoxLayout, QPushButton
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import (
    QPainter, QColor, QBrush, QPen, QFont, QWheelEvent,
    QMouseEvent, QPolygonF
)

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from PySide6.QtCore import QUrl
    _WEBENGINE_OK = True
except ImportError:
    _WEBENGINE_OK = False


# ── Three.js HTML (used when WebEngine available) ─────────────────────────────

_HTML = """<!DOCTYPE html><html><head><meta charset="utf-8">
<style>*{margin:0;padding:0}body{background:#111;overflow:hidden}
#info{position:absolute;top:8px;left:8px;color:#888;font:11px monospace;pointer-events:none}
#stats{position:absolute;top:8px;right:8px;color:#666;font:10px monospace;text-align:right;pointer-events:none}
#controls{position:absolute;bottom:8px;left:8px;display:flex;gap:5px}
button{background:#2a2a2a;color:#ccc;border:1px solid #444;padding:4px 10px;border-radius:4px;cursor:pointer;font:11px monospace}
button:hover{background:#444;color:#fff}
#empty{position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);color:#555;font:14px monospace;text-align:center}
</style></head><body>
<div id="empty">Brak modelu<br><span style="font-size:11px;color:#444">Wygeneruj STL/STEP</span></div>
<div id="info">LPM: obrot &nbsp;|&nbsp; Scroll: zoom &nbsp;|&nbsp; PPM: przesun</div>
<div id="stats"></div>
<div id="controls">
<button onclick="resetView()">Reset</button>
<button onclick="toggleWire()">Wireframe</button>
<button onclick="fitView()">Dopasuj</button>
</div>
<script src="https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.160.0/examples/js/controls/OrbitControls.js"></script>
<script>
const scene=new THREE.Scene();scene.background=new THREE.Color(0x111111);
scene.add(new THREE.GridHelper(200,20,0x333333,0x222222));
scene.add(new THREE.AxesHelper(30));
const camera=new THREE.PerspectiveCamera(45,innerWidth/innerHeight,0.1,50000);
camera.position.set(100,-100,80);
const renderer=new THREE.WebGLRenderer({antialias:true});
renderer.setPixelRatio(devicePixelRatio);renderer.setSize(innerWidth,innerHeight);
renderer.shadowMap.enabled=true;document.body.appendChild(renderer.domElement);
const controls=new THREE.OrbitControls(camera,renderer.domElement);
controls.enableDamping=true;controls.dampingFactor=0.07;
scene.add(new THREE.AmbientLight(0xffffff,0.4));
const sun=new THREE.DirectionalLight(0xffffff,1.4);sun.position.set(100,-100,200);sun.castShadow=true;scene.add(sun);
scene.add(new THREE.PointLight(0x88aaff,0.6,2000));
let mesh=null,wireMode=false;
function loadMeshData(d){
  document.getElementById('empty').style.display='none';
  if(mesh){scene.remove(mesh);mesh.geometry.dispose();mesh.material.dispose();}
  const geo=new THREE.BufferGeometry();
  geo.setAttribute('position',new THREE.BufferAttribute(new Float32Array(d.vertices),3));
  geo.setIndex(new THREE.BufferAttribute(new Uint32Array(d.faces),1));
  geo.computeVertexNormals();geo.computeBoundingBox();
  mesh=new THREE.Mesh(geo,new THREE.MeshPhongMaterial({color:d.color||0x4a90d9,side:THREE.DoubleSide}));
  mesh.castShadow=true;scene.add(mesh);
  const bb=geo.boundingBox;
  document.getElementById('stats').innerHTML=`${(bb.max.x-bb.min.x).toFixed(1)} x ${(bb.max.y-bb.min.y).toFixed(1)} x ${(bb.max.z-bb.min.z).toFixed(1)} mm<br>${(d.faces.length/3).toLocaleString()} trojkatow`;
  fitView();
}
function resetView(){camera.position.set(100,-100,80);controls.target.set(0,0,0);controls.update();}
function fitView(){if(!mesh)return;const b=new THREE.Box3().setFromObject(mesh),c=b.getCenter(new THREE.Vector3()),s=b.getSize(new THREE.Vector3()),m=Math.max(s.x,s.y,s.z),d=m/2/Math.tan(camera.fov*Math.PI/360)*2.2;controls.target.copy(c);camera.position.copy(c).add(new THREE.Vector3(d*.7,-d*.7,d*.5));camera.near=d/100;camera.far=d*100;camera.updateProjectionMatrix();controls.update();}
function toggleWire(){if(!mesh)return;wireMode=!wireMode;mesh.material.wireframe=wireMode;}
window.addEventListener('resize',()=>{camera.aspect=innerWidth/innerHeight;camera.updateProjectionMatrix();renderer.setSize(innerWidth,innerHeight);});
(function animate(){requestAnimationFrame(animate);controls.update();renderer.render(scene,camera);})();
</script></body></html>"""


# ── Pure-QPainter soft renderer ───────────────────────────────────────────────

def _parse_stl(path: str) -> tuple[np.ndarray, np.ndarray]:
    """Return (vertices Nx3, normals Nx3) for all triangles."""
    data = Path(path).read_bytes()
    # ASCII STL starts with "solid"
    if data[:5] == b"solid" and b"facet" in data[:200]:
        return _parse_stl_ascii(data.decode("utf-8", errors="ignore"))
    return _parse_stl_binary(data)


def _parse_stl_binary(data: bytes) -> tuple[np.ndarray, np.ndarray]:
    if len(data) < 84:
        return np.zeros((0, 3, 3)), np.zeros((0, 3))
    n = struct.unpack_from("<I", data, 80)[0]
    n = min(n, (len(data) - 84) // 50)
    verts  = np.zeros((n, 3, 3), dtype=np.float32)
    normals = np.zeros((n, 3),   dtype=np.float32)
    offset = 84
    for i in range(n):
        normals[i] = struct.unpack_from("<fff", data, offset)
        verts[i, 0] = struct.unpack_from("<fff", data, offset + 12)
        verts[i, 1] = struct.unpack_from("<fff", data, offset + 24)
        verts[i, 2] = struct.unpack_from("<fff", data, offset + 36)
        offset += 50
    return verts, normals


def _parse_stl_ascii(text: str) -> tuple[np.ndarray, np.ndarray]:
    import re
    tris, normals = [], []
    nrm = np.array([0.0, 0.0, 1.0])
    cur = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("facet normal"):
            vals = re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", line)
            nrm = np.array([float(v) for v in vals[:3]], dtype=np.float32)
        elif line.startswith("vertex"):
            vals = re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", line)
            cur.append([float(v) for v in vals[:3]])
        elif line.startswith("endfacet") and len(cur) == 3:
            tris.append(cur)
            normals.append(nrm)
            cur = []
    if not tris:
        return np.zeros((0, 3, 3)), np.zeros((0, 3))
    return np.array(tris, dtype=np.float32), np.array(normals, dtype=np.float32)


def _rotation_matrix(yaw: float, pitch: float) -> np.ndarray:
    cy, sy = math.cos(yaw),   math.sin(yaw)
    cp, sp = math.cos(pitch), math.sin(pitch)
    Ry = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]], dtype=np.float64)
    Rx = np.array([[1, 0, 0], [0, cp, -sp], [0, sp, cp]], dtype=np.float64)
    return Rx @ Ry


class _STLSoftView(QWidget):
    """Pure-QPainter STL renderer — no WebEngine needed."""

    BG    = QColor("#0d1117")
    GRID  = QColor("#1a1f2a")
    LIGHT = np.array([0.6, -0.5, 0.8], dtype=np.float64)  # normalised below

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tris:    np.ndarray | None = None   # (N, 3, 3) float32
        self._normals: np.ndarray | None = None   # (N, 3)   float32
        self._center  = np.zeros(3)
        self._scale   = 1.0
        self._yaw     = math.radians(-30)
        self._pitch   = math.radians(25)
        self._zoom    = 1.0
        self._pan     = np.array([0.0, 0.0])
        self._drag_start: QPointF | None = None
        self._drag_yaw   = 0.0
        self._drag_pitch = 0.0
        self._pan_start: QPointF | None = None
        self._pan_start_val = np.array([0.0, 0.0])
        self._wireframe  = False
        self._n_tris  = 0
        self._dims    = (0.0, 0.0, 0.0)

        # Normalise light vector
        l = self.LIGHT
        self.LIGHT = l / np.linalg.norm(l)

        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMinimumSize(300, 200)

    def load(self, tris: np.ndarray, normals: np.ndarray) -> None:
        self._tris   = tris.astype(np.float64)
        self._normals = normals.astype(np.float64)
        self._n_tris = len(tris)
        if self._n_tris:
            all_pts = tris.reshape(-1, 3)
            self._center = all_pts.mean(axis=0)
            span = all_pts.max(axis=0) - all_pts.min(axis=0)
            self._dims   = tuple(span.tolist())
            self._scale  = 0.4 * min(self.width() or 400, self.height() or 300) / max(span.max(), 1e-6)
            self._zoom   = 1.0
            self._pan[:] = 0
        self.update()

    def clear(self) -> None:
        self._tris = None
        self._n_tris = 0
        self.update()

    def toggle_wireframe(self) -> None:
        self._wireframe = not self._wireframe
        self.update()

    def reset_view(self) -> None:
        self._yaw   = math.radians(-30)
        self._pitch = math.radians(25)
        self._zoom  = 1.0
        self._pan[:] = 0
        self.update()

    def fit_view(self) -> None:
        if self._tris is not None and self._n_tris:
            all_pts = self._tris.reshape(-1, 3)
            span = all_pts.max(axis=0) - all_pts.min(axis=0)
            self._scale = 0.4 * min(self.width(), self.height()) / max(span.max(), 1e-6)
            self._zoom  = 1.0
            self._pan[:] = 0
        self.update()

    # ── Rendering ──────────────────────────────────────────────────────────────

    def paintEvent(self, _) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.fillRect(self.rect(), self.BG)

        cx = self.width()  / 2
        cy = self.height() / 2

        if self._tris is None or self._n_tris == 0:
            p.setPen(QColor("#555"))
            p.setFont(QFont("Consolas", 12))
            p.drawText(self.rect(), Qt.AlignCenter, "Brak modelu 3D\nWygeneruj STL lub wczytaj plik")
            return

        R = _rotation_matrix(self._yaw, self._pitch)
        s = self._scale * self._zoom

        # Transform all triangles: centre, rotate, scale, project
        tris = self._tris - self._center       # (N,3,3)
        flat = tris.reshape(-1, 3)             # (3N, 3)
        rot  = (R @ flat.T).T                  # (3N, 3)
        rot  = rot.reshape(-1, 3, 3)

        # Project normals for shading
        nrm = (R @ self._normals.T).T          # (N, 3)

        # Depth = average Z of triangle (painter's algorithm)
        depth = rot[:, :, 2].mean(axis=1)
        order = np.argsort(-depth)             # back to front

        # 2D screen coords
        sx = rot[:, :, 0] * s + cx + self._pan[0]
        sy = -rot[:, :, 1] * s + cy + self._pan[1]

        p.setPen(Qt.NoPen)

        for i in order:
            # Flat shading: dot(normal, light)
            nz = nrm[i]
            nn = np.linalg.norm(nz)
            if nn > 1e-8:
                nz = nz / nn
            diffuse = max(0.05, float(np.dot(nz, self.LIGHT)))
            # Base colour: blue-grey for enclosure, green for PCB
            b = int(min(255, diffuse * 200 + 30))
            g = int(min(255, diffuse * 160 + 20))
            r = int(min(255, diffuse * 120 + 15))
            color = QColor(r, g, b)

            pts = [QPointF(sx[i, j], sy[i, j]) for j in range(3)]

            if self._wireframe:
                p.setPen(QPen(QColor(80, 120, 160), 0.5))
                p.setBrush(Qt.NoBrush)
            else:
                p.setPen(Qt.NoPen)
                p.setBrush(QBrush(color))

            poly = QPolygonF(pts)
            p.drawPolygon(poly)

        # HUD
        p.setPen(QColor("#555"))
        p.setFont(QFont("Consolas", 8))
        dx, dy, dz = self._dims
        p.drawText(6, 14, f"{dx:.1f} x {dy:.1f} x {dz:.1f} mm  |  {self._n_tris} trojkatow")
        p.drawText(6, self.height() - 6,
                   "LPM: obrot  |  PPM: przesun  |  Scroll: zoom  |  W: wireframe  |  F: dopasuj")

    # ── Mouse / Keyboard ──────────────────────────────────────────────────────

    def mousePressEvent(self, e: QMouseEvent) -> None:
        if e.button() == Qt.LeftButton:
            self._drag_start = e.position()
            self._drag_yaw   = self._yaw
            self._drag_pitch = self._pitch
        elif e.button() == Qt.RightButton:
            self._pan_start     = e.position()
            self._pan_start_val = self._pan.copy()

    def mouseMoveEvent(self, e: QMouseEvent) -> None:
        if self._drag_start and e.buttons() & Qt.LeftButton:
            dx = e.position().x() - self._drag_start.x()
            dy = e.position().y() - self._drag_start.y()
            self._yaw   = self._drag_yaw   + dx * 0.008
            self._pitch = self._drag_pitch + dy * 0.008
            self._pitch = max(-math.pi / 2 + 0.05, min(math.pi / 2 - 0.05, self._pitch))
            self.update()
        elif self._pan_start and e.buttons() & Qt.RightButton:
            dx = e.position().x() - self._pan_start.x()
            dy = e.position().y() - self._pan_start.y()
            self._pan = self._pan_start_val + np.array([dx, dy])
            self.update()

    def mouseReleaseEvent(self, e: QMouseEvent) -> None:
        self._drag_start = None
        self._pan_start  = None

    def wheelEvent(self, e: QWheelEvent) -> None:
        delta = e.angleDelta().y()
        self._zoom *= 1.12 if delta > 0 else 0.89
        self._zoom  = max(0.05, min(self._zoom, 50.0))
        self.update()

    def keyPressEvent(self, e) -> None:
        if e.key() == Qt.Key_W:
            self.toggle_wireframe()
        elif e.key() == Qt.Key_F:
            self.fit_view()
        elif e.key() == Qt.Key_R:
            self.reset_view()


# ── Public widget ─────────────────────────────────────────────────────────────

class STL3DView(QWidget):
    """Unified 3D viewer — WebEngine (Three.js) when available, QPainter fallback otherwise."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(2)

        self._current_path = ""
        self._soft: _STLSoftView | None = None
        self._web_view = None

        if _WEBENGINE_OK:
            self._web_view = QWebEngineView()
            self._web_view.setHtml(_HTML)
            root.addWidget(self._web_view)
        else:
            # Toolbar
            tb = QHBoxLayout()
            for label, fn in [
                ("Reset (R)",    lambda: self._soft.reset_view()),
                ("Dopasuj (F)",  lambda: self._soft.fit_view()),
                ("Wireframe (W)",lambda: self._soft.toggle_wireframe()),
            ]:
                btn = QPushButton(label)
                btn.setFixedHeight(22)
                btn.setStyleSheet(
                    "QPushButton{background:#161b22;color:#aaa;border:1px solid #2a2a3a;"
                    "font-size:9px;padding:0 6px;}"
                    "QPushButton:hover{background:#2a2a3a;}"
                )
                btn.clicked.connect(fn)
                tb.addWidget(btn)
            tb.addStretch()
            root.addLayout(tb)

            self._soft = _STLSoftView()
            root.addWidget(self._soft, 1)

    # ── Public API ────────────────────────────────────────────────────────────

    def load_stl(self, path: str, color: int = 0x4a90d9) -> None:
        if not Path(path).exists():
            return
        self._current_path = path
        if self._web_view:
            self._load_stl_webengine(path, color)
        else:
            self._load_stl_soft(path)

    def load_step(self, path: str) -> None:
        if not Path(path).exists():
            return
        try:
            import cadquery as cq
            import tempfile, os
            result = cq.importers.importStep(path)
            tmp = tempfile.mktemp(suffix=".stl")
            cq.exporters.export(result, tmp)
            self.load_stl(tmp, color=0x90a0b0)
            try:
                os.remove(tmp)
            except Exception:
                pass
        except ImportError:
            pass
        except Exception:
            pass

    def clear(self) -> None:
        self._current_path = ""
        if self._web_view:
            self._web_view.setHtml(_HTML)
        elif self._soft:
            self._soft.clear()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _load_stl_webengine(self, path: str, color: int) -> None:
        try:
            import trimesh
            mesh = trimesh.load(path, force="mesh")
            verts = mesh.vertices.flatten().tolist()
            faces = mesh.faces.flatten().tolist()
            data  = json.dumps({"vertices": verts, "faces": faces, "color": color})
            self._web_view.page().runJavaScript(f"loadMeshData({data})")
        except Exception as e:
            js = f"document.getElementById('empty').innerHTML='Blad: {str(e)[:80]}';document.getElementById('empty').style.display='block';"
            self._web_view.page().runJavaScript(js)

    def _load_stl_soft(self, path: str) -> None:
        try:
            tris, normals = _parse_stl(path)
            if len(tris) == 0:
                return
            # Recompute normals if they're all zero
            if not np.any(np.abs(normals) > 1e-6):
                v0, v1, v2 = tris[:, 0], tris[:, 1], tris[:, 2]
                cross = np.cross(v1 - v0, v2 - v0)
                norm  = np.linalg.norm(cross, axis=1, keepdims=True)
                norm[norm < 1e-12] = 1.0
                normals = cross / norm
            self._soft.load(tris, normals)
        except Exception:
            pass
