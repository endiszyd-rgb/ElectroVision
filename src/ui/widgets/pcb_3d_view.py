"""3D PCB viewer: Three.js rendered inside Qt WebEngineView."""
import json
from PySide6.QtWidgets import QWidget, QVBoxLayout
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebChannel import QWebChannel
from PySide6.QtCore import QObject, Slot, QUrl, Signal
from PySide6.QtGui import QColor

from src.core.models.pcb_board import PCBBoard
from src.utils.colors import LAYER_COLORS


_HTML_TEMPLATE = """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  body { margin:0; background:#111; overflow:hidden; }
  canvas { display:block; }
  #info { position:absolute; top:8px; left:8px; color:#aaa; font:12px monospace; pointer-events:none; }
  #controls { position:absolute; bottom:8px; left:8px; display:flex; gap:6px; }
  button { background:#333; color:#ddd; border:1px solid #555; padding:4px 10px; border-radius:4px; cursor:pointer; font:12px monospace; }
  button:hover { background:#555; }
</style>
</head>
<body>
<div id="info">ElectroVision 3D &nbsp;|&nbsp; LPM: obróć &nbsp;|&nbsp; Scroll: zoom &nbsp;|&nbsp; PPM: pan</div>
<div id="controls">
  <button onclick="resetView()">Reset</button>
  <button onclick="toggleWire()">Wireframe</button>
  <button onclick="toggleLayers()">Warstwy</button>
</div>
<script src="https://cdn.jsdelivr.net/npm/three@0.160.0/build/three.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.160.0/examples/js/controls/OrbitControls.js"></script>
<script>
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x111111);

const camera = new THREE.PerspectiveCamera(45, innerWidth/innerHeight, 0.1, 10000);
camera.position.set(0, -80, 80);

const renderer = new THREE.WebGLRenderer({antialias:true});
renderer.setSize(innerWidth, innerHeight);
renderer.shadowMap.enabled = true;
document.body.appendChild(renderer.domElement);

const controls = new THREE.OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.05;

const ambientLight = new THREE.AmbientLight(0xffffff, 0.5);
scene.add(ambientLight);
const dirLight = new THREE.DirectionalLight(0xffffff, 1.2);
dirLight.position.set(50, -50, 100);
dirLight.castShadow = true;
scene.add(dirLight);
const pointLight = new THREE.PointLight(0x4499ff, 0.8, 500);
pointLight.position.set(-50, 50, 50);
scene.add(pointLight);

let wireMode = false;
let layersVisible = true;
const boardGroup = new THREE.Group();
scene.add(boardGroup);

function resetView() {
  camera.position.set(0, -80, 80);
  controls.target.set(0, 0, 0);
  controls.update();
}

function toggleWire() {
  wireMode = !wireMode;
  boardGroup.traverse(obj => {
    if (obj.material) obj.material.wireframe = wireMode;
  });
}

function toggleLayers() {
  layersVisible = !layersVisible;
  boardGroup.traverse(obj => {
    if (obj.userData.isLayer) obj.visible = layersVisible;
  });
}

function hexToColor(hex) {
  return new THREE.Color(parseInt(hex.replace('#','0x')));
}

function buildBoard(data) {
  while (boardGroup.children.length) boardGroup.remove(boardGroup.children[0]);
  if (!data) return;

  const W = data.width_mm  || 100;
  const H = data.height_mm || 80;
  const cx = data.origin_x || 0;
  const cy = data.origin_y || 0;

  // PCB substrate (FR4 green)
  const boardGeo = new THREE.BoxGeometry(W, H, 1.6);
  const boardMat = new THREE.MeshPhongMaterial({color:0x1a5c1a, shininess:30});
  const boardMesh = new THREE.Mesh(boardGeo, boardMat);
  boardMesh.receiveShadow = true;
  boardGroup.add(boardMesh);

  // Copper traces - F.Cu (top)
  if (data.traces) {
    data.traces.forEach(tr => {
      const dx = tr.x2 - tr.x1, dy = tr.y2 - tr.y1;
      const len = Math.sqrt(dx*dx+dy*dy);
      if (len < 0.01) return;
      const color = tr.layer === 'F.Cu' ? 0xd4a017 : 0x4a90d9;
      const z = tr.layer === 'F.Cu' ? 0.85 : -0.85;
      const geo = new THREE.BoxGeometry(len, Math.max(0.1, tr.width), 0.035);
      const mat = new THREE.MeshPhongMaterial({color, shininess:80});
      const mesh = new THREE.Mesh(geo, mat);
      mesh.userData.isLayer = true;
      const mx = (tr.x1 + tr.x2)/2 - cx;
      const my = -((tr.y1 + tr.y2)/2 - cy);
      mesh.position.set(mx, my, z);
      mesh.rotation.z = Math.atan2(dy, dx);
      boardGroup.add(mesh);
    });
  }

  // Vias
  if (data.vias) {
    data.vias.forEach(v => {
      const outerGeo = new THREE.CylinderGeometry(v.size/2, v.size/2, 1.7, 12);
      const outerMat = new THREE.MeshPhongMaterial({color:0xd4a017, shininess:80});
      const outer = new THREE.Mesh(outerGeo, outerMat);
      outer.position.set(v.x - cx, -(v.y - cy), 0);
      outer.rotation.x = Math.PI/2;
      outer.userData.isLayer = true;
      boardGroup.add(outer);

      const innerGeo = new THREE.CylinderGeometry(v.drill/2, v.drill/2, 1.8, 12);
      const innerMat = new THREE.MeshPhongMaterial({color:0x111111});
      const inner = new THREE.Mesh(innerGeo, innerMat);
      inner.position.copy(outer.position);
      inner.rotation.copy(outer.rotation);
      boardGroup.add(inner);
    });
  }

  // Components as colored boxes
  if (data.components) {
    data.components.forEach(comp => {
      const w = Math.max(1.0, comp.bb_w || 3);
      const h = Math.max(1.0, comp.bb_h || 3);
      const th = comp.layer === 'F.Cu' ? 0.3 : 0.3;
      const z  = comp.layer === 'F.Cu' ? 0.85 + th/2 : -0.85 - th/2;
      const colorMap = {
        resistor:   0xcc8800, capacitor:  0x4488cc, ic:         0x222222,
        led:        0x22cc44, connector:  0x888888, transistor: 0x555500,
        crystal:    0xaaaaaa, switch:     0xff4400, diode:      0x884400,
        inductor:   0x338855, fuse:       0xffaa00, generic:    0x445566,
      };
      const color = colorMap[comp.component_type] || 0x445566;
      const geo = new THREE.BoxGeometry(w, h, th);
      const mat = new THREE.MeshPhongMaterial({color, shininess:40});
      const mesh = new THREE.Mesh(geo, mat);
      mesh.castShadow = true;
      mesh.position.set(comp.x - cx, -(comp.y - cy), z);
      mesh.rotation.z = -(comp.rotation || 0) * Math.PI / 180;
      if (comp.layer !== 'F.Cu') mesh.scale.y = -1;
      mesh.userData.ref = comp.reference;
      boardGroup.add(mesh);
    });
  }

  // Center camera
  const box = new THREE.Box3().setFromObject(boardGroup);
  const center = box.getCenter(new THREE.Vector3());
  controls.target.copy(center);
  const size = box.getSize(new THREE.Vector3());
  camera.position.set(center.x, center.y - size.y * 1.2, center.z + size.z * 2.5);
  controls.update();
}

// Receive data from Python
if (window.qt && window.qt.webChannelTransport) {
  new QWebChannel(qt.webChannelTransport, function(channel) {
    window.bridge = channel.objects.bridge;
    bridge.boardDataChanged.connect(function(json_str) {
      try { buildBoard(JSON.parse(json_str)); } catch(e) { console.error(e); }
    });
    bridge.requestBoardData();
  });
}

window.addEventListener('resize', () => {
  camera.aspect = innerWidth / innerHeight;
  camera.updateProjectionMatrix();
  renderer.setSize(innerWidth, innerHeight);
});

function animate() {
  requestAnimationFrame(animate);
  controls.update();
  renderer.render(scene, camera);
}
animate();
</script>
</body>
</html>"""


class _PCBBridge(QObject):
    boardDataChanged = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._data: str = "null"

    def set_board(self, board: PCBBoard | None) -> None:
        if board is None:
            self._data = "null"
        else:
            bb = board.bounding_box
            cx = (bb[0] + bb[2]) / 2
            cy = (bb[1] + bb[3]) / 2
            payload = {
                "width_mm":  board.width_mm,
                "height_mm": board.height_mm,
                "origin_x":  cx,
                "origin_y":  cy,
                "traces": [
                    {"x1": t.x1, "y1": t.y1, "x2": t.x2, "y2": t.y2,
                     "width": t.width, "layer": t.layer}
                    for t in board.traces
                ],
                "vias": [
                    {"x": v.x, "y": v.y, "drill": v.drill, "size": v.size}
                    for v in board.vias
                ],
                "components": [
                    {
                        "reference": c.reference,
                        "value": c.value,
                        "x": c.x, "y": c.y,
                        "rotation": c.rotation,
                        "layer": c.layer,
                        "component_type": c.component_type,
                        "bb_w": max(p.width  for p in c.pads) * 3 if c.pads else 3.0,
                        "bb_h": max(p.height for p in c.pads) * 3 if c.pads else 3.0,
                    }
                    for c in board.components
                ],
            }
            self._data = json.dumps(payload)
        self.boardDataChanged.emit(self._data)

    @Slot()
    def requestBoardData(self) -> None:
        self.boardDataChanged.emit(self._data)


class PCB3DView(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._bridge = _PCBBridge(self)
        self._channel = QWebChannel(self)
        self._channel.registerObject("bridge", self._bridge)

        self._view = QWebEngineView(self)
        self._view.page().setWebChannel(self._channel)
        self._view.setHtml(_HTML_TEMPLATE)

        layout.addWidget(self._view)

    def set_board(self, board: PCBBoard | None) -> None:
        self._bridge.set_board(board)
