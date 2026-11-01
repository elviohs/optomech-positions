# cli.py — Ejecución sin interfaz:  python cli.py ruta/perfil.json
import json, sys
from pathlib import Path
import core, excel_out


def main(profile):
    zf, prm, els, t0, cases, od, on = core.profile_from_dict(
        json.loads(Path(profile).read_text(encoding="utf-8")), base=Path(profile).parent)
    warnings = []
    def log(m):
        print(m)
        if m.startswith(("[AVISO]", "[ERROR]")):
            warnings.append(m)
    surfs, info = core.read_zemax(zf)
    core.check_material(prm, log)
    res = core.compute_positions(surfs, els, prm, log)
    stab = []
    if t0 and cases:
        f0 = core.read_fem(t0, prm.fem_units, log)
        for label, f in cases:
            if not Path(f).exists():
                log(f"[AVISO] Caso '{label}': no existe {f}. Se omite.")
                continue
            stab.append((label, core.compute_stability(
                res, core.build_dT_grid(f0, core.read_fem(f, prm.fem_units, log), prm, log), prm, log)))
    out = Path(od or "results") / (on or "posiciones.xlsx")
    print("Excel:", excel_out.write_workbook(out, zf, info, prm, res, stab, warnings, t0, cases))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit("Uso: python cli.py perfil.json")
    main(sys.argv[1])
