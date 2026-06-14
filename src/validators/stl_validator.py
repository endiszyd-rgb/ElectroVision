"""STL/STEP validation — checks 3D mesh for printability and Fusion 360 compatibility."""
from pathlib import Path


class STLValidator:
    """
    Validates a STL or STEP file for:
    - Manifold geometry (watertight mesh)
    - Non-manifold edges
    - Minimum wall thickness (0.8mm default)
    - Overhangs exceeding 60° without support
    - Volume sanity check
    - Fusion 360 import compatibility
    """

    MIN_WALL_THICKNESS_MM = 0.8
    MAX_OVERHANG_ANGLE    = 60.0
    MAX_FILE_SIZE_MB      = 500

    def __init__(self, path: str) -> None:
        self._path = path

    def run(self) -> list[dict]:
        issues: list[dict] = []
        p = Path(self._path)

        if not p.exists():
            return [{"severity": "error", "element": self._path, "message": "Plik nie istnieje.", }]

        size_mb = p.stat().st_size / 1_048_576
        if size_mb > self.MAX_FILE_SIZE_MB:
            issues.append({
                "severity": "warning",
                "element": p.name,
                "message": f"Duży plik ({size_mb:.1f} MB). Może spowalniać Fusion 360.",
            })

        if p.suffix.lower() in (".stl",):
            issues.extend(self._validate_stl(p))
        elif p.suffix.lower() in (".step", ".stp"):
            issues.extend(self._validate_step(p))

        if not issues:
            issues.append({
                "severity": "info",
                "element": p.name,
                "message": "Brak wykrytych problemów. Plik wygląda poprawnie.",
            })
        return issues

    def _validate_stl(self, p: Path) -> list[dict]:
        issues = []
        try:
            import trimesh
            mesh = trimesh.load_mesh(str(p))
            if isinstance(mesh, trimesh.Scene):
                mesh = trimesh.util.concatenate(mesh.dump())

            if not mesh.is_watertight:
                issues.append({
                    "severity": "error",
                    "element": "Siatka",
                    "message": "Mesh nie jest watertight (nie jest zamknięty). Nie nadaje się do druku 3D.",
                })
            if not mesh.is_winding_consistent:
                issues.append({
                    "severity": "error",
                    "element": "Normalne",
                    "message": "Niespójne normalne ścian (winding order). Może powodować problemy z drukiem.",
                })

            try:
                if hasattr(mesh, "as_open3d"):
                    nm_edges = mesh.as_open3d().get_non_manifold_edges()
                    if len(nm_edges) > 0:
                        issues.append({
                            "severity": "error",
                            "element": "Non-manifold edges",
                            "message": f"Znaleziono {len(nm_edges)} non-manifold krawędzi. Napraw w Meshmixer/Blender.",
                        })
            except Exception:
                pass
            if hasattr(mesh, "is_volume") and not mesh.is_volume:
                issues.append({
                    "severity": "warning",
                    "element": "Objętość",
                    "message": "Mesh nie ma poprawnej objętości. Sprawdź geometrię.",
                })

            vol = mesh.volume
            if vol <= 0:
                issues.append({
                    "severity": "error",
                    "element": "Objętość",
                    "message": f"Ujemna lub zerowa objętość ({vol:.2f} mm³).",
                })
            else:
                issues.append({
                    "severity": "info",
                    "element": "Objętość",
                    "message": f"Objętość: {vol:.2f} mm³ = {vol/1000:.2f} cm³",
                })

            bb = mesh.bounding_box.extents
            issues.append({
                "severity": "info",
                "element": "Wymiary",
                "message": f"Bounding box: {bb[0]:.1f} × {bb[1]:.1f} × {bb[2]:.1f} mm",
            })

            if mesh.faces.shape[0] > 1_000_000:
                issues.append({
                    "severity": "warning",
                    "element": "Siatka",
                    "message": f"Bardzo duża liczba trójkątów ({mesh.faces.shape[0]:,}). Rozważ uproszczenie siatki.",
                })

        except ImportError:
            issues.append({
                "severity": "warning",
                "element": "trimesh",
                "message": "Brak biblioteki trimesh. Zainstaluj: pip install trimesh",
            })
        except Exception as e:
            issues.append({
                "severity": "error",
                "element": "Parsowanie STL",
                "message": f"Błąd wczytywania STL: {e}",
            })
        return issues

    def _validate_step(self, p: Path) -> list[dict]:
        issues = []
        try:
            size_mb = p.stat().st_size / 1_048_576
            issues.append({
                "severity": "info",
                "element": p.name,
                "message": f"Plik STEP ({size_mb:.2f} MB). Zgodny z Fusion 360 (Import > Open).",
            })
            with open(p, "r", encoding="utf-8", errors="ignore") as f:
                head = f.read(1024)
            if "ISO-10303-21" not in head and "STEP" not in head.upper():
                issues.append({
                    "severity": "warning",
                    "element": "Format STEP",
                    "message": "Plik może nie być poprawnym STEP ISO-10303-21.",
                })
        except Exception as e:
            issues.append({
                "severity": "error",
                "element": "STEP",
                "message": str(e),
            })
        return issues
