# =============================================================================
# gui.py — Interfaz gráfica: Zemax -> CREO + estabilidad térmica ANSYS
# =============================================================================
from __future__ import annotations

import json
import queue
import threading
import traceback
import tkinter as tk
from dataclasses import asdict
from pathlib import Path
from tkinter import ttk, filedialog, messagebox

import core
import excel_out
import materials

APP_TITLE = "Posiciones optomecánicas — Zemax / CREO / ANSYS"
MANUAL_MAT = "(CTE manual)"

PARAM_FIELDS = [
    # (clave, etiqueta, tipo)
    ("t_cold_k", "T operación / frío (K)", float),
    ("t_warm_k", "T montaje / caliente (K)", float),
    ("cte_mean_ppm", "CTE medio T frío↔T caliente (ppm/K)", float),
    ("manual_factor_pct", "Factor total manual (%)", float),
    ("ref_x", "Punto fijo banco X (mm)", float),
    ("ref_y", "Punto fijo banco Y (mm)", float),
    ("ref_z", "Punto fijo banco Z (mm)", float),
    ("round_pos_mm", "Tolerancia posición (mm)", float),
    ("round_ang_deg", "Tolerancia ángulo (°)", float),
    ("cte_stab_ppm", "CTE a T operación (ppm/K)", float),
    ("fem_nodes", "Nodos FEM por punto", int),
    ("fem_warn_mm", "Aviso si nodo más cercano > (mm)", float),
]

COLS = [("include", "Incl.", 45), ("surf_id", "Sup.", 45), ("zemax_label", "Etiqueta Zemax", 130),
        ("acronym", "Acrónimo", 80), ("description", "Descripción", 150),
        ("pos_offset", "Offset pos.", 70), ("pos_step", "Tol. pos (mm)", 95),
        ("ang_step", "Tol. áng (°)", 80),
        ("override", "Override CREO tx;ty;tz", 170), ("fem_point", "Punto FEM x;y", 110)]
BOOL_COLS = {"include"}
STEP_COLS = {"pos_step", "ang_step"}


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("1180x820")
        self.minsize(1000, 700)

        self.surfaces = []
        self.zemax_info = {}
        self.elements: list[core.ElementCfg] = []
        self.fem_cases: list[tuple[str, str]] = []
        self.msgs = queue.Queue()

        self.v_zemax = tk.StringVar()
        self.v_show_all = tk.BooleanVar(value=False)
        self.v_ignore = tk.StringVar()
        self.v_manual = tk.BooleanVar(value=False)
        self.v_backcalc = tk.StringVar(value="exacto")
        self.v_units = tk.StringVar(value="auto")
        self.v_model = tk.StringVar(value="trayectoria")
        self.v_t0 = tk.StringVar()
        self.v_case_label = tk.StringVar(value="T+1h")
        self.v_out_dir = tk.StringVar(value=str(Path.cwd() / "results"))
        self.v_out_name = tk.StringVar(value="posiciones.xlsx")
        self.v_factor_info = tk.StringVar()
        self.v_material = tk.StringVar(value=MANUAL_MAT)
        self.v_mat_conv = tk.BooleanVar(value=False)
        self.v_mat_stab = tk.BooleanVar(value=True)
        self.v_mat_info = tk.StringVar()
        self.v_stab_info = tk.StringVar()
        self.pvars = {k: tk.StringVar() for k, _, _ in PARAM_FIELDS}
        self._set_params(core.Params())

        self._build()
        self.after(150, self._poll)

    # ------------------------------------------------------------------ layout
    def _build(self):
        top = ttk.Frame(self, padding=6)
        top.pack(fill="x")
        ttk.Button(top, text="Nuevo", command=self.new_profile).pack(side="left")
        ttk.Button(top, text="Abrir perfil…", command=self.load_profile).pack(side="left", padx=4)
        ttk.Button(top, text="Guardar perfil…", command=self.save_profile).pack(side="left", padx=4)
        ttk.Label(top, text="  (un perfil = sistema óptico + parámetros + tabla de elementos)",
                  foreground="#666").pack(side="left")

        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=6)
        nb.add(self._tab_system(nb), text="1 · Sistema óptico (Zemax)")
        nb.add(self._tab_bench(nb), text="2 · Banco óptico")
        nb.add(self._tab_stab(nb), text="3 · Estabilidad (ANSYS)")

        bottom = ttk.Frame(self, padding=6)
        bottom.pack(fill="both")
        out = ttk.Frame(bottom)
        out.pack(fill="x")
        ttk.Label(out, text="Carpeta salida").pack(side="left")
        ttk.Entry(out, textvariable=self.v_out_dir, width=60).pack(side="left", padx=4)
        ttk.Button(out, text="…", width=3,
                   command=lambda: self._pick_dir(self.v_out_dir)).pack(side="left")
        ttk.Label(out, text="  Fichero").pack(side="left")
        ttk.Entry(out, textvariable=self.v_out_name, width=28).pack(side="left", padx=4)
        self.btn_run = ttk.Button(out, text="▶  Calcular", command=self.run)
        self.btn_run.pack(side="right")

        self.log = tk.Text(bottom, height=11, font=("Consolas", 9), wrap="none")
        sb = ttk.Scrollbar(bottom, command=self.log.yview)
        self.log.configure(yscrollcommand=sb.set)
        self.log.pack(side="left", fill="both", expand=True, pady=(6, 0))
        sb.pack(side="right", fill="y", pady=(6, 0))
        self.log.tag_configure("warn", foreground="#b36b00")
        self.log.tag_configure("err", foreground="#c00000")
        self.log.tag_configure("ok", foreground="#1f7a1f")

    def _tab_system(self, parent):
        f = ttk.Frame(parent, padding=8)
        row = ttk.Frame(f)
        row.pack(fill="x")
        ttk.Label(row, text="Prescription data Zemax (.txt)").pack(side="left")
        ttk.Entry(row, textvariable=self.v_zemax, width=80).pack(side="left", padx=4, fill="x", expand=True)
        ttk.Button(row, text="…", width=3, command=self._pick_zemax).pack(side="left")
        ttk.Button(row, text="Leer superficies", command=self.read_zemax).pack(side="left", padx=4)
        row2 = ttk.Frame(f)
        row2.pack(fill="x", pady=(4, 0))
        ttk.Checkbutton(row2, text="Mostrar superficies sin etiqueta",
                        variable=self.v_show_all).pack(side="left")
        ttk.Label(row2, text="   Ignorar etiquetas (separadas por ';')").pack(side="left")
        ttk.Entry(row2, textvariable=self.v_ignore, width=40).pack(side="left", padx=4)
        ttk.Button(row2, text="Marcar todos", command=lambda: self._bulk(True)).pack(side="right")
        ttk.Button(row2, text="Desmarcar todos", command=lambda: self._bulk(False)).pack(side="right", padx=4)

        self.tree = ttk.Treeview(f, columns=[c for c, _, _ in COLS], show="headings", height=16)
        for c, t, w in COLS:
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="center" if c in BOOL_COLS | STEP_COLS | {"surf_id", "pos_offset"} else "w")
        self.tree.pack(fill="both", expand=True, pady=6)
        self.tree.bind("<Double-1>", self._edit_cell)

        ttk.Label(f, foreground="#555", justify="left", wraplength=1120, text=(
            "Doble clic para editar (Incl. se activa/desactiva con doble clic). Cualquier número de elementos.\n"
            "Tol. pos / Tol. áng: intervalo de tolerancia de posicionado de ese elemento (redondeo para CREO); "
            "vacío = valor por defecto de la pestaña 2.\n"
            "Offset pos.: superficies a avanzar solo para X,Y,Z (cuando la posición mecánica está en el "
            "coordinate break siguiente).  "
            "Override: ángulos CREO forzados (solo casos ty=±90° verificados en CREO); "
            "el programa avisa si cambian la orientación física.\n"
            "Punto FEM: punto X;Y donde muestrear la temperatura (p. ej. la pata de la montura). "
            "Vacío = posición del vértice.")).pack(anchor="w")
        return f

    def _tab_bench(self, parent):
        f = ttk.Frame(parent, padding=10)
        g = ttk.LabelFrame(f, text="Conversión frío ↔ caliente", padding=8)
        g.grid(row=0, column=0, sticky="nsew", padx=4, pady=4)
        keys = ["t_cold_k", "t_warm_k", "cte_mean_ppm", "manual_factor_pct"]
        self._param_rows(g, keys)
        ttk.Checkbutton(g, text="Usar factor total manual en lugar de CTE·ΔT", variable=self.v_manual,
                        command=self._update_factor).grid(row=len(keys), column=0, columnspan=2, sticky="w")
        ttk.Label(g, textvariable=self.v_factor_info, foreground="#1f4e9c").grid(
            row=len(keys) + 1, column=0, columnspan=2, sticky="w", pady=4)
        ttk.Label(g, text="Back-calc frío").grid(row=len(keys) + 2, column=0, sticky="w")
        ttk.Combobox(g, textvariable=self.v_backcalc, values=["exacto", "excel"], width=10,
                     state="readonly").grid(row=len(keys) + 2, column=1, sticky="w")
        for k in ("t_cold_k", "t_warm_k", "cte_mean_ppm", "manual_factor_pct"):
            self.pvars[k].trace_add("write", lambda *a: self._update_factor())

        g2 = ttk.LabelFrame(f, text="Punto fijo del banco (no se desplaza con la temperatura)", padding=8)
        g2.grid(row=0, column=1, sticky="nsew", padx=4, pady=4)
        self._param_rows(g2, ["ref_x", "ref_y", "ref_z"])
        ttk.Label(g2, foreground="#555", wraplength=330, justify="left", text=(
            "Se usa en la conversión frío↔caliente y como origen del desplazamiento en el "
            "estudio de estabilidad. Debe coincidir con la fijación real del banco al criostato.")
                  ).grid(row=3, column=0, columnspan=2, sticky="w", pady=4)

        g3 = ttk.LabelFrame(f, text="Tolerancia de posicionado por defecto (intervalo de redondeo)", padding=8)
        g3.grid(row=1, column=0, sticky="nsew", padx=4, pady=4)
        self._param_rows(g3, ["round_pos_mm", "round_ang_deg"])
        ttk.Label(g3, foreground="#555", wraplength=380, justify="left", text=(
            "Se aplica a los elementos sin tolerancia propia en la tabla. Redondeo con la mitad "
            "hacia fuera (igual que ROUND de Excel).")).grid(row=2, column=0, columnspan=2, sticky="w")

        g4 = ttk.LabelFrame(f, text="Material del banco (curvas en materiales.json)", padding=8)
        g4.grid(row=1, column=1, sticky="nsew", padx=4, pady=4)
        ttk.Label(g4, text="Material").grid(row=0, column=0, sticky="w")
        self.cb_mat = ttk.Combobox(g4, textvariable=self.v_material, width=28, state="readonly")
        self.cb_mat.grid(row=0, column=1, sticky="w", padx=6)
        self.cb_mat.bind("<<ComboboxSelected>>", lambda e: self._update_factor())
        ttk.Button(g4, text="Ver curva", command=self.show_curve).grid(row=0, column=2, padx=2)
        ttk.Button(g4, text="Recargar", command=self._reload_materials).grid(row=0, column=3, padx=2)
        ttk.Checkbutton(g4, text="Usar la curva para la conversión frío ↔ caliente",
                        variable=self.v_mat_conv, command=self._update_factor).grid(
            row=1, column=0, columnspan=4, sticky="w")
        ttk.Checkbutton(g4, text="Usar la curva para el estudio de estabilidad",
                        variable=self.v_mat_stab, command=self._update_factor).grid(
            row=2, column=0, columnspan=4, sticky="w")
        ttk.Label(g4, textvariable=self.v_mat_info, foreground="#1f4e9c", justify="left").grid(
            row=3, column=0, columnspan=4, sticky="w", pady=4)
        self._reload_materials()
        self._update_factor()
        return f

    def _tab_stab(self, parent):
        f = ttk.Frame(parent, padding=10)
        g = ttk.LabelFrame(f, text="Ficheros de temperatura ANSYS (Nodo, X, Y, Z, T)", padding=8)
        g.pack(fill="x")
        r = ttk.Frame(g); r.pack(fill="x")
        ttk.Label(r, text="Referencia T0").pack(side="left")
        ttk.Entry(r, textvariable=self.v_t0, width=80).pack(side="left", padx=4, fill="x", expand=True)
        ttk.Button(r, text="…", width=3, command=lambda: self._pick_file(self.v_t0)).pack(side="left")

        r2 = ttk.Frame(g); r2.pack(fill="x", pady=6)
        ttk.Label(r2, text="Nombre del caso").pack(side="left")
        ttk.Entry(r2, textvariable=self.v_case_label, width=12).pack(side="left", padx=4)
        ttk.Button(r2, text="Añadir fichero de caso…", command=self.add_case).pack(side="left")
        ttk.Button(r2, text="Quitar seleccionado", command=self.del_case).pack(side="left", padx=4)
        self.lst_cases = tk.Listbox(g, height=5)
        self.lst_cases.pack(fill="x")

        g2 = ttk.LabelFrame(f, text="Modelo", padding=8)
        g2.pack(fill="x", pady=8)
        ttk.Label(g2, textvariable=self.v_stab_info, foreground="#1f4e9c").grid(
            row=5, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self._param_rows(g2, ["cte_stab_ppm", "fem_nodes", "fem_warn_mm"])
        ttk.Label(g2, text="Unidades coordenadas FEM").grid(row=3, column=0, sticky="w")
        ttk.Combobox(g2, textvariable=self.v_units, values=["auto", "mm", "m"], width=10,
                     state="readonly").grid(row=3, column=1, sticky="w")
        ttk.Label(g2, text="Modelo de desplazamiento").grid(row=4, column=0, sticky="w")
        ttk.Combobox(g2, textvariable=self.v_model, values=["trayectoria", "local"], width=12,
                     state="readonly").grid(row=4, column=1, sticky="w")
        ttk.Label(f, foreground="#555", justify="left", wraplength=1050, text=(
            "trayectoria: ΔT medio a lo largo del segmento punto fijo → elemento (aproxima α∫ΔT·ds). "
            "local: ΔT en el elemento × distancia al punto fijo (solo válido si ΔT es uniforme).\n"
            "Ambos son aproximaciones de primer orden en X-Y. Para tilts y desplazamientos en Z, lo "
            "correcto es exportar los desplazamientos de un análisis termo-estructural de ANSYS.\n"
            "El CTE de estabilidad debe ser el instantáneo a la temperatura de operación, no el medio "
            "entre 130 K y 293 K.")).pack(anchor="w")
        return f

    def _param_rows(self, parent, keys):
        labels = {k: l for k, l, _ in PARAM_FIELDS}
        for i, k in enumerate(keys):
            ttk.Label(parent, text=labels[k]).grid(row=i, column=0, sticky="w", pady=2)
            ttk.Entry(parent, textvariable=self.pvars[k], width=12).grid(row=i, column=1, sticky="w", padx=6)

    # -------------------------------------------------------------- parámetros
    def _set_params(self, prm: core.Params):
        for k, _, _ in PARAM_FIELDS:
            self.pvars[k].set(str(getattr(prm, k)))
        self.v_manual.set(prm.use_manual_factor)
        self.v_backcalc.set(prm.backcalc_mode)
        self.v_units.set(prm.fem_units)
        self.v_model.set(prm.fem_model)
        self.v_ignore.set(prm.ignore_labels)
        self.v_material.set(prm.material or MANUAL_MAT)
        self.v_mat_conv.set(prm.mat_for_conversion)
        self.v_mat_stab.set(prm.mat_for_stability)

    def _get_params(self) -> core.Params:
        kw = {}
        for k, label, typ in PARAM_FIELDS:
            txt = self.pvars[k].get().strip().replace(",", ".")
            try:
                kw[k] = typ(float(txt)) if typ is int else typ(txt)
            except ValueError:
                raise ValueError(f"Valor no válido en '{label}': '{txt}'")
        mat = self.v_material.get()
        return core.Params(use_manual_factor=self.v_manual.get(), backcalc_mode=self.v_backcalc.get(),
                           fem_units=self.v_units.get(), fem_model=self.v_model.get(),
                           material="" if mat == MANUAL_MAT else mat,
                           mat_for_conversion=self.v_mat_conv.get(),
                           mat_for_stability=self.v_mat_stab.get(),
                           ignore_labels=self.v_ignore.get(), **kw)

    def _update_factor(self):
        if not hasattr(self, "v_mat_info"):
            return
        try:
            p = self._get_params()
            self.v_factor_info.set(f"Factor aplicado: {p.factor:.6f}  ({p.factor * 100:.4f} %)\n"
                                   f"← {p.factor_source()}")
            self.v_stab_info.set(f"Deformación en estabilidad: {p.stability_source()}")
            m = p.mat()
            if m:
                txt = (f"α({p.t_cold_k:g} K) = {m.alpha(p.t_cold_k) * 1e6:.2f} ppm/K    "
                       f"α({p.t_warm_k:g} K) = {m.alpha(p.t_warm_k) * 1e6:.2f} ppm/K\n"
                       f"Factor {p.t_cold_k:g}→{p.t_warm_k:g} K = {m.factor(p.t_cold_k, p.t_warm_k):.6f}   "
                       f"(CTE medio {m.mean_cte(p.t_cold_k, p.t_warm_k) * 1e6:.2f} ppm/K)\n"
                       f"Validez {m.t_min:g}–{m.t_max:g} K   "
                       + (f"error ajuste {m.fit_error_pct} %   " if m.fit_error_pct is not None else "") +
                       f"{'✔ verificado' if m.verified else '⚠ coeficientes NO verificados'}")
                self.v_mat_info.set(txt)
            else:
                self.v_mat_info.set("Sin material: se usan los CTE introducidos a mano.")
        except Exception as e:
            self.v_factor_info.set(f"Factor aplicado: (revisa los valores: {e})")

    def _reload_materials(self):
        try:
            names = list(materials.load_materials().keys())
        except Exception as e:
            messagebox.showerror("materiales.json", str(e)); names = []
        self.cb_mat["values"] = [MANUAL_MAT] + names
        if self.v_material.get() not in self.cb_mat["values"]:
            self.v_material.set(MANUAL_MAT)
        self._update_factor()

    def show_curve(self):
        try:
            p = self._get_params()
        except ValueError as e:
            messagebox.showerror("Parámetros", str(e)); return
        m = p.mat()
        if not m:
            messagebox.showinfo("Curva", "Selecciona un material."); return
        win = tk.Toplevel(self)
        win.title(f"Curva de dilatación — {m.name}")
        W, H, L, R, T, B = 760, 560, 70, 20, 30, 45
        cv = tk.Canvas(win, width=W, height=H, bg="white")
        cv.pack()
        t0, t1 = max(m.t_min, 1.0), m.t_max
        ts = [t0 + (t1 - t0) * i / 200 for i in range(201)]
        series = [("ε(T) = (L-L293)/L293  [%]", [m.strain(t) * 100 for t in ts], 0),
                  ("α(T)  [ppm/K]", [m.alpha(t) * 1e6 for t in ts], 1)]
        ph = (H - T - B) / 2 - 20
        for title, vals, k in series:
            y0 = T + k * (ph + 40)
            vmin, vmax = min(vals), max(vals)
            if vmax - vmin < 1e-12:
                vmax = vmin + 1
            X = lambda t: L + (t - t0) / (t1 - t0) * (W - L - R)
            Y = lambda v: y0 + ph - (v - vmin) / (vmax - vmin) * ph
            cv.create_rectangle(L, y0, W - R, y0 + ph, outline="#999")
            cv.create_text(L, y0 - 10, text=title, anchor="w", font=("Segoe UI", 9, "bold"))
            for j in range(5):
                v = vmin + (vmax - vmin) * j / 4
                cv.create_text(L - 6, Y(v), text=f"{v:.3g}", anchor="e", font=("Segoe UI", 8))
                cv.create_line(L, Y(v), W - R, Y(v), fill="#eee")
            for j in range(7):
                t = t0 + (t1 - t0) * j / 6
                cv.create_text(X(t), y0 + ph + 10, text=f"{t:.0f}", font=("Segoe UI", 8))
            cv.create_line(*[c for t, v in zip(ts, vals) for c in (X(t), Y(v))], fill="#1f4e9c", width=2)
            for tk_, col in ((p.t_cold_k, "#c00000"), (p.t_warm_k, "#1f7a1f")):
                if t0 <= tk_ <= t1:
                    cv.create_line(X(tk_), y0, X(tk_), y0 + ph, fill=col, dash=(4, 2))
        cv.create_text(W / 2, H - 12, text="T (K)     rojo: T operación   verde: T montaje",
                       font=("Segoe UI", 9))

    # ---------------------------------------------------------------- Zemax
    def _pick_zemax(self):
        p = filedialog.askopenfilename(title="Prescription data Zemax",
                                       filetypes=[("Texto", "*.txt"), ("Todos", "*.*")])
        if p:
            self.v_zemax.set(p)
            self.read_zemax()

    def read_zemax(self):
        path = self.v_zemax.get().strip()
        if not path:
            return
        try:
            self.surfaces, self.zemax_info = core.read_zemax(path)
        except Exception as e:
            messagebox.showerror("Zemax", str(e))
            return
        fresh = core.default_elements(self.surfaces, self.v_show_all.get(), self.v_ignore.get())
        # Emparejar por (etiqueta, nº de aparición) para tolerar etiquetas repetidas
        def keyed(lst):
            seen, out = {}, {}
            for e in lst:
                n = seen.get(e.zemax_label, 0); seen[e.zemax_label] = n + 1
                out[(e.zemax_label, n)] = e
            return out
        old_map, new_map = keyed(self.elements), keyed(fresh)
        merged = []
        for k, d in new_map.items():
            old = old_map.get(k)
            if old:
                if old.surf_id != d.surf_id:
                    self._log(f"[AVISO] '{d.zemax_label}' ha pasado de la superficie "
                              f"{old.surf_id} a la {d.surf_id}.", "warn")
                old.surf_id = d.surf_id
                merged.append(old)
            else:
                merged.append(d)
        for k, e in old_map.items():
            if k not in new_map and e.include:
                self._log(f"[AVISO] El elemento del perfil '{e.zemax_label}' ya no existe en el "
                          f"fichero Zemax.", "warn")
        self.elements = merged
        self._refresh_tree()
        self._log(f"Leídas {len(self.surfaces)} superficies de {Path(path).name} "
                  f"(referencia global: superficie {self.zemax_info.get('reference_surface')}).", "ok")

    def _refresh_tree(self):
        self.tree.delete(*self.tree.get_children())
        for i, e in enumerate(self.elements):
            vals = []
            for c, _, _ in COLS:
                v = getattr(e, c)
                if c in BOOL_COLS:
                    v = "✔" if v else "—"
                elif c in STEP_COLS and not str(v).strip():
                    v = "(def.)"
                vals.append(v)
            self.tree.insert("", "end", iid=str(i), values=vals)

    def _edit_cell(self, event):
        item = self.tree.identify_row(event.y)
        col = self.tree.identify_column(event.x)
        if not item or not col:
            return
        key = COLS[int(col[1:]) - 1][0]
        el = self.elements[int(item)]
        if key == "surf_id":
            return
        if key in BOOL_COLS:
            setattr(el, key, not getattr(el, key))
            self._refresh_tree()
            return
        x, y, w, h = self.tree.bbox(item, col)
        ent = ttk.Entry(self.tree)
        ent.insert(0, str(getattr(el, key)))
        ent.place(x=x, y=y, width=w, height=h)
        ent.focus_set()

        def commit(_=None):
            txt = ent.get().strip()
            try:
                if key == "pos_offset":
                    setattr(el, key, int(txt or 0))
                elif key in STEP_COLS:
                    if txt in ("", "(def.)"):
                        setattr(el, key, "")
                    else:
                        v = float(txt.replace(",", "."))
                        if v <= 0:
                            raise ValueError("La tolerancia debe ser > 0")
                        setattr(el, key, f"{v:g}")
                elif key == "override" and txt:
                    core.parse_triplet(txt, 3)
                    setattr(el, key, txt)
                elif key == "fem_point" and txt:
                    core.parse_triplet(txt, 2)
                    setattr(el, key, txt)
                else:
                    setattr(el, key, txt)
            except ValueError as e:
                messagebox.showerror("Valor no válido", str(e))
            ent.destroy()
            self._refresh_tree()

        ent.bind("<Return>", commit)
        ent.bind("<FocusOut>", commit)
        ent.bind("<Escape>", lambda _: ent.destroy())

    # ---------------------------------------------------------------- FEM
    def add_case(self):
        p = filedialog.askopenfilename(title="Fichero de temperatura ANSYS",
                                       filetypes=[("Texto", "*.txt *.csv"), ("Todos", "*.*")])
        if not p:
            return
        label = self.v_case_label.get().strip() or f"Caso {len(self.fem_cases) + 1}"
        self.fem_cases.append((label, p))
        self._refresh_cases()

    def del_case(self):
        sel = self.lst_cases.curselection()
        if sel:
            del self.fem_cases[sel[0]]
            self._refresh_cases()

    def _refresh_cases(self):
        self.lst_cases.delete(0, "end")
        for l, p in self.fem_cases:
            self.lst_cases.insert("end", f"{l}  —  {p}")

    def _bulk(self, value):
        for e in self.elements:
            e.include = value
        self._refresh_tree()

    # ---------------------------------------------------------------- perfiles
    def new_profile(self):
        if self.elements and not messagebox.askyesno("Nuevo", "¿Descartar el perfil actual?"):
            return
        self._set_params(core.Params())
        self.elements, self.surfaces, self.fem_cases = [], [], []
        self.v_zemax.set(""); self.v_t0.set("")
        self._refresh_tree(); self._refresh_cases(); self._update_factor()
        self._log("Perfil nuevo.", "ok")

    def save_profile(self):
        try:
            prm = self._get_params()
        except ValueError as e:
            messagebox.showerror("Parámetros", str(e)); return
        p = filedialog.asksaveasfilename(defaultextension=".json", filetypes=[("Perfil", "*.json")])
        if not p:
            return
        d = core.profile_to_dict(self.v_zemax.get(), prm, self.elements, self.v_t0.get(),
                                 self.fem_cases, self.v_out_dir.get(), self.v_out_name.get(),
                                 base=Path(p).parent)
        Path(p).write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")
        self._log(f"Perfil guardado: {p}", "ok")

    def load_profile(self, path=None):
        p = path or filedialog.askopenfilename(filetypes=[("Perfil", "*.json")])
        if not p:
            return
        try:
            d = json.loads(Path(p).read_text(encoding="utf-8"))
            zf, prm, els, t0, cases, od, on = core.profile_from_dict(d, base=Path(p).parent)
        except Exception as e:
            messagebox.showerror("Perfil", f"No se pudo leer el perfil:\n{e}"); return
        self._set_params(prm)
        self.elements = els
        self.v_zemax.set(zf); self.v_t0.set(t0)
        self.fem_cases = cases; self._refresh_cases()
        if od: self.v_out_dir.set(od)
        if on: self.v_out_name.set(on)
        self._update_factor()
        self._log(f"Perfil cargado: {p}", "ok")
        for label, fp in [("T0", t0)] + list(cases):
            if fp and not Path(fp).exists():
                self._log(f"[AVISO] No se encuentra el fichero FEM '{label}': {fp}", "warn")
        if zf and Path(zf).exists():
            self.read_zemax()
        else:
            self._refresh_tree()
            if zf:
                self._log(f"[AVISO] No se encuentra el fichero Zemax del perfil: {zf}", "warn")

    # ---------------------------------------------------------------- cálculo
    def run(self):
        try:
            prm = self._get_params()
        except ValueError as e:
            messagebox.showerror("Parámetros", str(e)); return
        if not self.surfaces:
            messagebox.showwarning("Zemax", "Primero lee un fichero Zemax."); return
        out = Path(self.v_out_dir.get()) / (self.v_out_name.get().strip() or "posiciones.xlsx")
        if out.suffix.lower() != ".xlsx":
            out = out.with_suffix(".xlsx")
        self.btn_run.state(["disabled"])
        args = (prm, list(self.elements), self.v_t0.get().strip(), list(self.fem_cases), out,
                self.v_zemax.get())
        threading.Thread(target=self._worker, args=args, daemon=True).start()

    def _worker(self, prm, elements, t0, cases, out, zemax_path):
        warnings = []

        def log(m):
            if m.startswith("[AVISO]") or m.startswith("[ERROR]"):
                warnings.append(m)
            self.msgs.put(m)

        try:
            log("=" * 70)
            log(f"Factor térmico {prm.factor:.6f} | punto fijo ({prm.ref_x}, {prm.ref_y}, {prm.ref_z})")
            core.check_material(prm, log)
            results = core.compute_positions(self.surfaces, elements, prm, log)
            log(f"{'Acr.':8s} {'X frío':>10s} {'Y frío':>10s} {'Z frío':>9s} | "
                f"{'X cal.r':>9s} {'Y cal.r':>9s} {'Z cal.r':>8s} | {'tx':>7s} {'ty':>7s} {'tz':>7s}")
            for r in results:
                c, w = r.cold, r.warm_rnd
                log(f"{r.cfg.acronym:8s} {c.x:10.3f} {c.y:10.3f} {c.z:9.3f} | {w.x:9.1f} {w.y:9.1f} "
                    f"{w.z:8.1f} | {w.tx:7.2f} {w.ty:7.2f} {w.tz:7.2f}")

            stability = []
            if cases:
                if not t0:
                    log("[ERROR] Hay casos FEM pero falta el fichero de referencia T0.")
                else:
                    log("Leyendo ficheros FEM…")
                    fem0 = core.read_fem(t0, prm.fem_units, log)
                    for label, fpath in cases:
                        if not Path(fpath).exists():
                            log(f"[AVISO] Caso '{label}': no existe {fpath}. Se omite.")
                            continue
                        fem1 = core.read_fem(fpath, prm.fem_units, log)
                        grid = core.build_dT_grid(fem0, fem1, prm, log)
                        st = core.compute_stability(results, grid, prm, log)
                        stability.append((label, st))
                        log(f"--- {label}: {'Acr.':6s} {'ΔT ef.(K)':>9s} {'dX (µm)':>9s} {'dY (µm)':>9s} "
                            f"{'dist.mín':>8s}")
                        for s in st:
                            log(f"    {s.acronym:12s} {s.mean_dT:9.4f} {s.dX * 1e3:9.2f} {s.dY * 1e3:9.2f} "
                                f"{s.min_dist:8.1f}")

            path = excel_out.write_workbook(out, zemax_path, self.zemax_info, prm, results,
                                            stability, warnings, t0, cases)
            log(f"[OK] Excel generado: {path}")
        except PermissionError:
            log(f"[ERROR] No se puede escribir {out}. ¿Está abierto en Excel?")
        except Exception as e:
            log(f"[ERROR] {e}")
            log(traceback.format_exc())
        finally:
            self.msgs.put(("__done__",))

    # ---------------------------------------------------------------- utilidades
    def _poll(self):
        try:
            while True:
                m = self.msgs.get_nowait()
                if isinstance(m, tuple):
                    self.btn_run.state(["!disabled"])
                    continue
                tag = "err" if "[ERROR]" in m else "warn" if "[AVISO]" in m else "ok" if "[OK]" in m else None
                self._log(m, tag)
        except queue.Empty:
            pass
        self.after(150, self._poll)

    def _log(self, m, tag=None):
        self.log.insert("end", m + "\n", tag or ())
        self.log.see("end")

    def _pick_file(self, var):
        p = filedialog.askopenfilename(filetypes=[("Texto", "*.txt *.csv"), ("Todos", "*.*")])
        if p:
            var.set(p)

    def _pick_dir(self, var):
        p = filedialog.askdirectory()
        if p:
            var.set(p)


if __name__ == "__main__":
    import sys
    app = App()
    if len(sys.argv) > 1:
        app.after(200, lambda: app.load_profile(sys.argv[1]))
    app.mainloop()
