"""STL / STEP 3D Viewer — renders models using Three.js inside QWebEngineView (optional)."""
from __future__ import annotations
import json
from pathlib import Path
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Qt, QUrl

try:
    from PySide6.QtWebEngineWidgets import QWebEngineView
    _WEBENGINE_OK = True
except ImportError:
    _WEBENGINE_OK = False


_HTML = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  * { margin:0; padding:0; box-sizing:border-box; }
  body { background:#111; overflow:hidden; font-family:monospace; }
  canvas { display:block; }
  #info {
    position:absolute; top:8px; left:8px;
    color:#888; font-size:11px; pointer-events:none;
    line-height:1.6;
  }
  #controls {
    position:absolute; bottom:8px; left:8px;
    display:flex; gap:5px;
  }
  button {
    background:#2a2a2a; color:#ccc; border:1px solid #444;
    padding:4px 10px; border-radius:4px; cursor:pointer;
    font:11px monospace;
  }
  button:hover { background:#444; color:#fff; }
  #stats {
    position:absolute; top:8px; right:8px;
    color:#666; font-size:10px; text-align:right;
    pointer-events:none;
  }
  #empty {
    position:absolute; top:50%; left:50%;
    transform:translate(-50%, -50%);
    color:#555; font-size:14px; text-align:center;
  }
</style>
</head>
<body>
<div id="empty" id="emptyMsg">Brak modelu<br><span style="font-size:11px;color:#444">Wygeneruj STL/STEP lub wczytaj plik</span></div>
<div id="info">LPM: obróć &nbsp;|&nbsp; Scroll: zoom &nbsp;|&nbsp; PPM: przesuń</div>
<div id="stats"></div>
<div id="controls">
  <button onclick="resetView()">⟳ Reset</button>
  <button onclick="toggleWire()">⬡ Wireframe</button>
  <button onclick="toggleShading()">☀ Cieniowanie</button>
  <button onclick="fitView()">⊞ Dopasuj</button>
</div>

<script src="https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.160.0/examples/js/controls/OrbitControls.js"></script>

<script>
// ── Scene setup ─────────────────────────────────────────────────────────────
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x111111);
scene.add(new THREE.GridHelper(200, 20, 0x333333, 0x222222));
scene.add(new THREE.AxesHelper(30));

const camera = new THREE.PerspectiveCamera(45, innerWidth/innerHeight, 0.1, 50000);
camera.position.set(100, -100, 80);

const renderer = new THREE.WebGLRenderer({antialias:true});
renderer.setPixelRatio(window.devicePixelRatio);
renderer.setSize(innerWidth, innerHeight);
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
document.body.appendChild(renderer.domElement);

const controls = new THREE.OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.07;
controls.enablePan = true;

// Lighting
const ambient = new THREE.AmbientLight(0xffffff, 0.4);
scene.add(ambient);
const sun = new THREE.DirectionalLight(0xffffff, 1.4);
sun.position.set(100, -100, 200);
sun.castShadow = true;
scene.add(sun);
const fill = new THREE.PointLight(0x88aaff, 0.6, 2000);
fill.position.set(-100, 100, 50);
scene.add(fill);

// ── State ────────────────────────────────────────────────────────────────────
let currentMesh = null;
let wireMode = false;
let flatShading = false;

// ── Load mesh from JSON data ─────────────────────────────────────────────────
function loadMeshData(data) {
  document.getElementById('empty').style.display = 'none';

  if (currentMesh) {
    scene.remove(currentMesh);
    currentMesh.geometry.dispose();
    currentMesh.material.dispose();
  }

  const vertices = new Float32Array(data.vertices);
  const indices  = new Uint32Array(data.faces);

  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.BufferAttribute(vertices, 3));
  geo.setIndex(new THREE.BufferAttribute(indices, 1));
  geo.computeVertexNormals();
  geo.computeBoundingSphere();
  geo.computeBoundingBox();

  const mat = new THREE.MeshPhongMaterial({
    color: data.color || 0x4a90d9,
    specular: 0x222222,
    shininess: 40,
    side: THREE.DoubleSide,
    flatShading: false,
  });

  currentMesh = new THREE.Mesh(geo, mat);
  currentMesh.castShadow = true;
  currentMesh.receiveShadow = true;
  scene.add(currentMesh);

  // Update stats
  const bb = geo.boundingBox;
  const dx = (bb.max.x - bb.min.x).toFixed(1);
  const dy = (bb.max.y - bb.min.y).toFixed(1);
  const dz = (bb.max.z - bb.min.z).toFixed(1);
  document.getElementById('stats').innerHTML =
    `${dx} × ${dy} × ${dz} mm<br>` +
    `${(indices.length/3).toLocaleString()} trójkątów`;

  fitView();
}

// ── Controls ────────────────────────────────────────────────────────────────
function resetView() {
  camera.position.set(100, -100, 80);
  controls.target.set(0, 0, 0);
  controls.update();
}

function fitView() {
  if (!currentMesh) return;
  const box = new THREE.Box3().setFromObject(currentMesh);
  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());
  const maxDim = Math.max(size.x, size.y, size.z);
  const fov = camera.fov * (Math.PI / 180);
  const dist = Math.abs(maxDim / 2 / Math.tan(fov / 2)) * 2.2;

  controls.target.copy(center);
  camera.position.copy(center).add(new THREE.Vector3(dist*0.7, -dist*0.7, dist*0.5));
  camera.near = dist / 100;
  camera.far  = dist * 100;
  camera.updateProjectionMatrix();
  controls.update();
}

function toggleWire() {
  if (!currentMesh) return;
  wireMode = !wireMode;
  currentMesh.material.wireframe = wireMode;
}

function toggleShading() {
  if (!currentMesh) return;
  flatShading = !flatShading;
  currentMesh.material.flatShading = flatShading;
  currentMesh.material.needsUpdate = true;
}

// ── Resize ──────────────────────────────────────────────────────────────────
window.addEventListener('resize', () => {
  camera.aspect = innerWidth / innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
});

// ── Render loop ─────────────────────────────────────────────────────────────
(function animate() {
  requestAnimationFrame(animate);
  controls.update();
  renderer.render(scene, camera);
})();

// ── Python bridge ────────────────────────────────────────────────────────────
// Called from Python: page.runJavaScript("loadMeshData(" + json + ")")
</script>
</body>
</html>
"""


class STL3DView(QWidget):
    """3D viewer for STL/STEP files using Three.js inside QWebEngineView."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._current_path: str = ""

        if not _WEBENGINE_OK:
            lbl = QLabel("⚠  Widok 3D STL niedostępny (brak PySide6.QtWebEngineWidgets)")
            lbl.setStyleSheet("color: #888; background: #0d1117; padding: 20px; font-family: Consolas;")
            lbl.setAlignment(Qt.AlignCenter)
            layout.addWidget(lbl)
            self._view = None
            return

        self._view = QWebEngineView()
        self._view.setHtml(_HTML)
        layout.addWidget(self._view)

    def load_stl(self, path: str, color: int = 0x4a90d9) -> None:
        """Load and display an STL file."""
        if not self._view or not Path(path).exists():
            return
        self._current_path = path

        try:
            import trimesh
            import json as _json

            mesh = trimesh.load(path, force="mesh")
            if hasattr(mesh, "vertices") and hasattr(mesh, "faces"):
                verts = mesh.vertices.flatten().tolist()
                faces = mesh.faces.flatten().tolist()
                data = _json.dumps({"vertices": verts, "faces": faces, "color": color})
                self._view.page().runJavaScript(f"loadMeshData({data})")
            else:
                self._show_error("Nie można załadować pliku STL")
        except ImportError:
            self._show_error(
                "Brak biblioteki trimesh.\n"
                "Zainstaluj: pip install trimesh"
            )
        except Exception as e:
            self._show_error(f"Błąd ładowania STL: {e}")

    def load_step(self, path: str) -> None:
        """Load STEP via CadQuery → convert to STL mesh → display."""
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
            self._show_error("Brak CadQuery. Zainstaluj: pip install cadquery")
        except Exception as e:
            self._show_error(f"Błąd STEP: {e}")

    def clear(self) -> None:
        self._current_path = ""
        self._view.setHtml(_HTML)

    def _show_error(self, msg: str) -> None:
        js = f"document.getElementById('empty').innerHTML = '{msg.replace(chr(10), '<br>')}'; document.getElementById('empty').style.display='block';"
        self._view.page().runJavaScript(js)
