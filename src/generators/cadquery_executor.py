"""CadQuery Executor — executes AI-generated CadQuery Python code to produce real STL/STEP files."""
from __future__ import annotations
import re
import sys
import traceback
from pathlib import Path


class CadQueryExecutor:
    """
    Executes AI-generated CadQuery code in a restricted namespace.

    The AI generates Python/CadQuery code as text.
    This executor runs it and captures the output file paths.

    Safety: exec() in a controlled namespace — no os, subprocess, open, etc.
    """

    ALLOWED_IMPORTS = {"cadquery", "cq", "math", "numpy", "np"}

    def __init__(self, output_dir: str = "") -> None:
        self._out_dir = Path(output_dir) if output_dir else Path.cwd()
        self._out_dir.mkdir(parents=True, exist_ok=True)

    # ── public ──────────────────────────────────────────────────────────────────

    def execute(self, code: str, base_name: str = "ai_result") -> dict:
        """
        Execute CadQuery code. Returns dict:
          {
            'success': bool,
            'stl': str | None,     # path to generated .stl
            'step': str | None,    # path to generated .step
            'error': str | None,
            'stdout': str,
          }
        """
        code = self._clean_code(code)
        stl_path  = str(self._out_dir / f"{base_name}.stl")
        step_path = str(self._out_dir / f"{base_name}.step")

        # Patch export paths in code so files land in output_dir
        code = self._patch_export_paths(code, stl_path, step_path)

        namespace = self._build_namespace(stl_path, step_path)
        stdout_lines: list[str] = []

        class _Capture:
            def write(self, s):
                if s.strip():
                    stdout_lines.append(s)
            def flush(self): pass

        old_stdout = sys.stdout
        sys.stdout = _Capture()
        try:
            exec(compile(code, "<ai_cadquery>", "exec"), namespace)
            sys.stdout = old_stdout
        except Exception:
            sys.stdout = old_stdout
            err = traceback.format_exc()
            return {
                "success": False,
                "stl": None,
                "step": None,
                "error": err,
                "stdout": "\n".join(stdout_lines),
            }

        # Check which files were created
        generated_stl  = stl_path  if Path(stl_path).exists()  else None
        generated_step = step_path if Path(step_path).exists() else None

        # Also scan namespace for any cq.Workplane or Assembly objects
        # that might not have been exported — auto-export them
        if not generated_stl and not generated_step:
            self._auto_export(namespace, stl_path, step_path)
            generated_stl  = stl_path  if Path(stl_path).exists()  else None
            generated_step = step_path if Path(step_path).exists() else None

        return {
            "success": True,
            "stl": generated_stl,
            "step": generated_step,
            "error": None,
            "stdout": "\n".join(stdout_lines),
        }

    # ── helpers ─────────────────────────────────────────────────────────────────

    def _clean_code(self, code: str) -> str:
        """Strip markdown fences and leading/trailing whitespace."""
        code = re.sub(r"```python\s*", "", code)
        code = re.sub(r"```\s*", "", code)
        return code.strip()

    def _patch_export_paths(self, code: str, stl_path: str, step_path: str) -> str:
        """Replace any export() filename with controlled output paths."""
        # Match: export(something, "filename.stl") → export(something, stl_path)
        code = re.sub(
            r'''exporters\.export\s*\(([^,]+),\s*["'][^"']+\.stl["']''',
            lambda m: f'exporters.export({m.group(1)}, r"{stl_path}"',
            code, flags=re.IGNORECASE
        )
        code = re.sub(
            r'''exporters\.export\s*\(([^,]+),\s*["'][^"']+\.step["']''',
            lambda m: f'exporters.export({m.group(1)}, r"{step_path}"',
            code, flags=re.IGNORECASE
        )
        code = re.sub(
            r'''assembly\.save\s*\(\s*["'][^"']+\.step["']''',
            f'assembly.save(r"{step_path}"',
            code, flags=re.IGNORECASE
        )
        code = re.sub(
            r'''asm\.save\s*\(\s*["'][^"']+\.step["']''',
            f'asm.save(r"{step_path}"',
            code, flags=re.IGNORECASE
        )
        return code

    def _build_namespace(self, stl_path: str, step_path: str) -> dict:
        """Build restricted execution namespace with cadquery available."""
        try:
            import cadquery as cq
            from cadquery import exporters, Assembly, Color, Location, Vector
        except ImportError:
            raise ImportError(
                "CadQuery nie jest zainstalowany.\n"
                "Zainstaluj: pip install cadquery\n"
                "Lub: pip install cadquery-ocp"
            )

        import math

        ns = {
            "__builtins__": {
                "print": print,
                "range": range,
                "len": len,
                "round": round,
                "abs": abs,
                "min": min,
                "max": max,
                "list": list,
                "tuple": tuple,
                "dict": dict,
                "str": str,
                "float": float,
                "int": int,
                "bool": bool,
                "True": True,
                "False": False,
                "None": None,
                "__import__": self._safe_import,
            },
            "cq": cq,
            "cadquery": cq,
            "exporters": exporters,
            "Assembly": Assembly,
            "Color": Color,
            "Location": Location,
            "Vector": Vector,
            "math": math,
            # Output paths available as variables in AI code
            "OUTPUT_STL": stl_path,
            "OUTPUT_STEP": step_path,
        }
        try:
            import numpy as np
            ns["np"] = np
            ns["numpy"] = np
        except ImportError:
            pass
        return ns

    def _safe_import(self, name, *args, **kwargs):
        if name in ("cadquery", "math", "numpy"):
            return __import__(name, *args, **kwargs)
        raise ImportError(f"Import '{name}' not allowed in AI code")

    def _auto_export(self, namespace: dict, stl_path: str, step_path: str) -> None:
        """If AI forgot to export, find CadQuery objects and export them."""
        try:
            import cadquery as cq
            from cadquery import exporters

            for var_name, obj in namespace.items():
                if var_name.startswith("_"):
                    continue
                if isinstance(obj, cq.Workplane):
                    exporters.export(obj, stl_path)
                    exporters.export(obj, step_path)
                    return
                if isinstance(obj, cq.Assembly):
                    obj.save(step_path)
                    exporters.export(obj.toCompound(), stl_path)
                    return
        except Exception:
            pass
