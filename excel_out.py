# =============================================================================
# excel_out.py — Escritura del Excel de resultados
# =============================================================================
import datetime as _dt
import re

import core
from version import __version__
from dataclasses import asdict
from pathlib import Path

BLUE, GREEN, GOLD, PINK, GREY, LILAC = "DDEEFF", "DDFFDD", "FFF0CC", "FFE0E0", "EEEEEE", "EDE3FA"
SUB6 = ["X (mm)", "Y (mm)", "Z (mm)", "Tilt X (°)", "Tilt Y (°)", "Tilt Z (°)"]


def _safe_sheet(name):
    return re.sub(r"[\[\]\*\?/\\:]", "_", name)[:31]


def write_workbook(path, zemax_file, zemax_info, prm, results, stability, warnings,
                   fem_t0="", fem_cases=(), disp_ref=()):
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    hf, df, tf = Font(bold=True, size=9), Font(size=9), Font(bold=True, size=11)
    side = Side(style="thin", color="BBBBBB")
    bd = Border(left=side, right=side, top=side, bottom=side)
    fill = lambda c: PatternFill("solid", fgColor=c)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)

    wb = openpyxl.Workbook()

    # --------------------------------------------------------------- Parámetros
    ws = wb.active
    ws.title = "Parametros"
    ws["A1"] = "Parámetros del cálculo"; ws["A1"].font = tf
    rows = [
        ("Fecha", _dt.datetime.now().strftime("%Y-%m-%d %H:%M")),
        ("Versión del programa", __version__),
        ("Fichero Zemax", zemax_file),
        ("Superficie de referencia Zemax", zemax_info.get("reference_surface")),
        ("T frío (K)", prm.t_cold_k), ("T caliente (K)", prm.t_warm_k),
        ("CTE medio (ppm/K)", prm.cte_mean_ppm),
        ("Factor manual", "Sí" if prm.use_manual_factor else "No"),
        ("Factor térmico aplicado", prm.factor),
        ("Origen del factor", prm.factor_source()),
        ("Material", prm.material or "(CTE manual)"),
        ("Fuente curva material", (prm.mat().source if prm.mat() else "")),
        ("Curva verificada", ("Sí" if prm.mat().verified else "NO") if prm.mat() else ""),
        ("Error de ajuste de la curva (%)", (prm.mat().fit_error_pct if prm.mat() else "") or ""),
        ("α a T operación (ppm/K)", round(prm.mat().alpha(prm.t_cold_k) * 1e6, 3) if prm.mat() else ""),
        ("Origen deformación estabilidad", prm.stability_source()),
        ("Punto fijo banco X / Y / Z (mm)", f"{prm.ref_x} / {prm.ref_y} / {prm.ref_z}"),
        ("Tolerancia posición por defecto (mm)", prm.round_pos_mm),
        ("Tolerancia ángulo por defecto (°)", prm.round_ang_deg),
        ("Back-calc", prm.backcalc_mode),
        ("CTE estabilidad (ppm/K)", prm.cte_stab_ppm),
        ("Modelo estabilidad", prm.fem_model),
        ("Nodos FEM por punto", prm.fem_nodes),
        ("Unidades FEM", prm.fem_units),
        ("Nodos ajuste sólido rígido (desplazamientos)", prm.disp_nodes),
        ("Unidades desplazamiento", prm.disp_units),
        ("FEM T0 (temperaturas)", fem_t0),
        ("Referencia desplazamientos", "; ".join(disp_ref) or "(ninguna: desplazamientos absolutos)"),
    ] + [(f"Caso '{l}' ({'temperaturas' if k == 'temp' else 'desplazamientos'})", "; ".join(fs))
         for l, fs, k in fem_cases]
    for i, (k, v) in enumerate(rows, 3):
        ws.cell(i, 1, k).font = hf
        ws.cell(i, 2, v).font = df
    ws.column_dimensions["A"].width = 34
    ws.column_dimensions["B"].width = 70

    def header_block(ws, r0, c0, title, subs, color):
        ws.merge_cells(start_row=r0, start_column=c0, end_row=r0, end_column=c0 + len(subs) - 1)
        c = ws.cell(r0, c0, title); c.font = hf; c.fill = fill(color); c.alignment = center
        for j, s in enumerate(subs):
            h = ws.cell(r0 + 1, c0 + j, s); h.font = hf; h.fill = fill(color); h.alignment = center
            ws.column_dimensions[get_column_letter(c0 + j)].width = 12

    def fixed_cols(ws, r):
        for j, s in enumerate(["Acrónimo", "Descripción", "Superficie"], 1):
            ws.cell(r, j, s).font = hf
        ws.column_dimensions["A"].width = 10
        ws.column_dimensions["B"].width = 24
        ws.column_dimensions["C"].width = 9

    def put(ws, r, c, v, color, fmt="0.0000"):
        cell = ws.cell(r, c, v)
        cell.font = df; cell.fill = fill(color); cell.border = bd
        if isinstance(v, float):
            cell.number_format = fmt

    # ----------------------------------------------------------- Posiciones CREO
    ws = wb.create_sheet("Posiciones CREO")
    ws["A1"] = "Posiciones CREO (frío -> caliente -> redondeado -> back-calc)"; ws["A1"].font = tf
    ws["A2"] = f"Factor {prm.factor:.6f} | punto fijo ({prm.ref_x}, {prm.ref_y}, {prm.ref_z}) mm | back-calc {prm.backcalc_mode}"
    ws["A2"].font = Font(italic=True, size=8)
    groups = [("Cold CREO (T frío)", BLUE), ("Warm CREO sin redondear", GREEN),
              ("Warm redondeado — entrada CREO", GOLD), ("Cold back-calc", PINK),
              ("Residuo de redondeo (back-calc − frío)", GREY)]
    fixed_cols(ws, 5)
    for g, (t, col) in enumerate(groups):
        header_block(ws, 4, 4 + 6 * g, t, SUB6, col)
    header_block(ws, 4, 34, "Tolerancia aplicada", ["Pos. (mm)", "Áng. (°)"], LILAC)
    header_block(ws, 4, 36, "Override", ["Δ orient. (°)"], LILAC)
    header_block(ws, 4, 37, "Redondeo", ["Δ orient. redondeo (°)"], LILAC)
    for i, r in enumerate(results):
        row = 6 + i
        ws.cell(row, 1, r.cfg.acronym).font = df
        ws.cell(row, 2, r.cfg.description).font = df
        ws.cell(row, 3, r.surface.surf_id).font = df
        resid = [b - c for b, c in zip(r.cold_back.as_list(), r.cold.as_list())]
        for g, vals in enumerate([r.cold.as_list(), r.warm.as_list(), r.warm_rnd.as_list(),
                                  r.cold_back.as_list(), resid]):
            for j, v in enumerate(vals):
                put(ws, row, 4 + 6 * g + j, float(v), groups[g][1])
        put(ws, row, 34, float(r.pos_step), LILAC, "0.000")
        put(ws, row, 35, float(r.ang_step), LILAC, "0.000")
        put(ws, row, 36, round(r.override_dev_deg, 3) if r.override_used else "", LILAC)
        put(ws, row, 37, float(r.round_dev_deg), LILAC, "0.0000")
    ws.freeze_panes = "D6"

    # ------------------------------------------------------------ Zemax global
    ws = wb.create_sheet("Zemax global")
    ws["A1"] = "Coordenadas globales y ángulos tal como los da Zemax (frío)"; ws["A1"].font = tf
    fixed_cols(ws, 5)
    header_block(ws, 4, 4, "Posición (superficie de posición)", SUB6[:3], BLUE)
    header_block(ws, 4, 7, "Ángulos Zemax (superficie etiquetada)", SUB6[3:], LILAC)
    for i, r in enumerate(results):
        row = 6 + i
        ws.cell(row, 1, r.cfg.acronym).font = df
        ws.cell(row, 2, r.cfg.description).font = df
        ws.cell(row, 3, r.surface.surf_id).font = df
        for j, v in enumerate([r.pos_surface.x, r.pos_surface.y, r.pos_surface.z]):
            put(ws, row, 4 + j, float(v), BLUE)
        for j, v in enumerate([r.surface.tilt_x, r.surface.tilt_y, r.surface.tilt_z]):
            put(ws, row, 7 + j, float(v), LILAC)
    ws.freeze_panes = "D6"

    # -------------------------------------------------------------- Estabilidad
    def urad(v):
        return float(v * 1e6)

    files_of = {l: fs for l, fs, _ in fem_cases}
    for label, stab in stability:
        ws = wb.create_sheet(core.sheet_name_for_case(label))
        kind = stab[0].kind if stab else "temp"
        ws["A1"] = f"Estabilidad — {label} (posiciones en frío para Zemax)"; ws["A1"].font = tf
        if kind == "temp":
            ws["A2"] = (f"Origen: temperaturas ANSYS | {prm.stability_source()} | modelo '{prm.fem_model}' | "
                        f"{prm.fem_nodes} nodos | punto fijo ({prm.ref_x}, {prm.ref_y}) mm. "
                        f"Modelo 1er orden en X-Y: sin dZ ni giros.")
        else:
            ws["A2"] = (f"Origen: desplazamientos termo-estructurales ANSYS | ajuste de sólido rígido con "
                        f"{prm.disp_nodes} nodos | desplazamiento en el elemento con brazo de palanca | "
                        f"{'relativo a la referencia' if disp_ref else 'absoluto (sin referencia)'}.")
        ws["A2"].font = Font(italic=True, size=8)
        from pathlib import Path as _P
        fn = "; ".join(_P(f).name for f in files_of.get(label, []))
        ref = (_P(fem_t0).name if kind == "temp" else "; ".join(_P(f).name for f in disp_ref)) or "—"
        ws["A3"] = f"Fichero del caso: {fn}   |   Referencia: {ref}"
        ws["A3"].font = Font(italic=True, size=8)
        fixed_cols(ws, 5)
        header_block(ws, 4, 4, "Posición global perturbada (frío)", SUB6[:3], BLUE)
        header_block(ws, 4, 7, "Ángulos Zemax perturbados", SUB6[3:], LILAC)
        header_block(ws, 4, 10, "Desplazamiento global", ["dX (mm)", "dY (mm)", "dZ (mm)"], GOLD)
        header_block(ws, 4, 13, "Giro global", ["θX (µrad)", "θY (µrad)", "θZ (µrad)"], GOLD)
        header_block(ws, 4, 16, "Desplazamiento en ejes locales (Rᵀ·d)",
                     ["dx loc (mm)", "dy loc (mm)", "dz loc (mm)"], GREEN)
        header_block(ws, 4, 19, "Giro en ejes locales (Rᵀ·θ)",
                     ["θx loc (µrad)", "θy loc (µrad)", "θz loc (µrad)"], GREEN)
        header_block(ws, 4, 22, "Datos FEM",
                     ["ΔT efectivo (K)", "N nodos", "Dist. mín (mm)", "Residuo ajuste (µm)"], GREY)
        smap = {s.acronym: s for s in stab}
        for i, r in enumerate(results):
            s = smap.get(r.cfg.acronym)
            if not s:
                continue
            row = 6 + i
            ws.cell(row, 1, r.cfg.acronym).font = df
            ws.cell(row, 2, r.cfg.description).font = df
            ws.cell(row, 3, r.surface.surf_id).font = df
            base = (r.pos_surface.x, r.pos_surface.y, r.pos_surface.z)
            for j, v in enumerate([base[0] + s.dX, base[1] + s.dY, base[2] + s.dZ]):
                put(ws, row, 4 + j, float(v), BLUE, "0.000000")
            ang = (r.surface.tilt_x, r.surface.tilt_y, r.surface.tilt_z)
            for j, v in enumerate(ang):
                put(ws, row, 7 + j, float(v + s.d_tilt_zemax[j]), LILAC, "0.000000")
            for j, v in enumerate([s.dX, s.dY, s.dZ]):
                put(ws, row, 10 + j, float(v), GOLD, "0.000000")
            for j in range(3):
                put(ws, row, 13 + j, urad(s.rot[j]) if s.rot else "—", GOLD, "0.00")
            for j, v in enumerate([s.dX_loc, s.dY_loc, s.dZ_loc]):
                put(ws, row, 16 + j, float(v), GREEN, "0.000000")
            for j in range(3):
                put(ws, row, 19 + j, urad(s.rot_loc[j]) if s.rot_loc else "—", GREEN, "0.00")
            put(ws, row, 22, float(s.mean_dT) if s.mean_dT is not None else "—", GREY, "0.0000")
            put(ws, row, 23, s.n_nodes, GREY)
            put(ws, row, 24, float(s.min_dist), GREY, "0.0")
            put(ws, row, 25, float(s.fit_rms_um) if s.fit_rms_um is not None else "—", GREY, "0.000")
        ws.freeze_panes = "D6"

    # ------------------------------------------------------------------- Avisos
    ws = wb.create_sheet("Avisos")
    ws["A1"] = "Avisos del cálculo"; ws["A1"].font = tf
    ws.column_dimensions["A"].width = 140
    for i, w in enumerate(warnings or ["(ninguno)"], 3):
        ws.cell(i, 1, w).font = df

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path
