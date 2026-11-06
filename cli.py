# cli.py — Ejecución sin interfaz:  python cli.py ruta/perfil.json
import json, sys
from pathlib import Path
import core, excel_out


def main(profile):
    zf, prm, els, t0, cases, od, on, dref = core.profile_from_dict(
        json.loads(Path(profile).read_text(encoding="utf-8")), base=Path(profile).parent)
    warnings = []
    def log(m):
        print(m)
        if m.startswith(("[AVISO]", "[ERROR]")):
            warnings.append(m)
    errs = core.validate_setup(els, prm, cases, t0, dref)
    if errs:
        sys.exit("Errores en el perfil:\n  - " + "\n  - ".join(errs))
    surfs, info = core.read_zemax(zf)
    core.check_material(prm, log)
    res = core.compute_positions(surfs, els, prm, log)
    stab = core.run_stability(res, prm, t0, cases, dref, log)
    out = Path(od or "results") / (on or "posiciones.xlsx")
    print("Excel:", excel_out.write_workbook(out, zf, info, prm, res, stab, warnings, t0, cases, dref))


def _utf8_output():
    """Salida en UTF-8: al redirigir a un fichero en Windows, Python usa cp1252 y no puede escribir
    caracteres como 'α' o 'µ' (UnicodeEncodeError)."""
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):      # flujo sustituido (p. ej. por un IDE)
            pass


if __name__ == "__main__":
    _utf8_output()
    if len(sys.argv) < 2:
        sys.exit("Uso: python cli.py perfil.json")
    main(sys.argv[1])
