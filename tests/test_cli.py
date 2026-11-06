import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "ejemplos" / "sistema_3_espejos"


def _profile_in(tmp_path):
    """Copia el perfil de ejemplo con rutas absolutas y salida en tmp_path."""
    d = json.loads((EXAMPLE / "ejemplo_3_espejos.json").read_text(encoding="utf-8"))
    ab = lambda p: str(EXAMPLE / p) if p else p
    d["zemax_file"] = ab(d.get("zemax_file", ""))
    d["fem_t0"] = ab(d.get("fem_t0", ""))
    for c in d.get("fem_cases", []):
        c["files"] = [ab(f) for f in c["files"]]
    d["disp_ref"] = [ab(f) for f in d.get("disp_ref", [])]
    d["out_dir"] = str(tmp_path)
    d["out_name"] = "cli.xlsx"
    p = tmp_path / "perfil.json"
    p.write_text(json.dumps(d), encoding="utf-8")
    return p


def test_cli_redirected_output_non_utf8(tmp_path):
    """Con la salida redirigida en una codificación sin 'α' (cp1252, como en Windows) no debe fallar."""
    env = dict(os.environ, PYTHONIOENCODING="cp1252")
    env.pop("PYTHONUTF8", None)
    r = subprocess.run([sys.executable, str(ROOT / "cli.py"), str(_profile_in(tmp_path))],
                       capture_output=True, env=env, cwd=tmp_path)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    assert "α" in r.stdout.decode("utf-8")
    assert (tmp_path / "cli.xlsx").exists()
