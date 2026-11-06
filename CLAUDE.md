# CLAUDE.md — contexto del proyecto para Claude Code

## Qué es
Herramienta en Python para pasar posiciones de sistemas ópticos de Zemax (frío) a CREO (caliente),
con tolerancias de posicionado por elemento, curvas de dilatación NIST, vista 2D con comprobación de
la ley de reflexión y estudio de estabilidad térmica con resultados de ANSYS (temperaturas o
desplazamientos termo-estructurales). Interfaz tkinter, salida Excel (openpyxl).
Usuarios: ingenieros del Departamento de Mecánica del IAC. Idioma de la interfaz y de la
documentación: español.

## Estructura
- `core.py` — lectura de Zemax (GLOBAL VERTEX + SURFACE DATA SUMMARY), ángulos Zemax→CREO,
  conversión térmica, redondeo, ficheros ANSYS, estabilidad (temperaturas y desplazamientos),
  perfiles JSON.
- `geometry.py` — rayo central, punto de impacto en cónicas fuera de eje, ley de reflexión.
- `materials.py` + `materiales.json` — curvas ε(T) NIST (verificadas contra las tablas de NIST).
- `excel_out.py` — Excel de resultados.  `gui.py` — interfaz.  `cli.py` — línea de comandos.
- `tests/` — pytest.  `ejemplos/sistema_3_espejos/` — ejemplo SINTÉTICO (Zemax + ANSYS).
- `optomech-positions.spec`, `build_exe.bat` — ejecutable Windows con PyInstaller.
- `.github/workflows/` — `tests.yml` (Ubuntu + Windows) y `build-exe.yml` (compila el .exe al
  subir una etiqueta v*, lo verifica con `--autotest` y lo adjunta a la release).

## Comandos
- Tests: `python -m pytest -q`  (deben pasar todos antes de cualquier commit)
- Interfaz: `python gui.py [perfil.json]`
- Sin interfaz: `python cli.py ejemplos/sistema_3_espejos/ejemplo_3_espejos.json`
- Autoprueba: `python gui.py --autotest ejemplos/sistema_3_espejos/ejemplo_3_espejos.json salida.xlsx`
- Ejecutable local: `build_exe.bat`  →  `dist\optomech-positions.exe`

## Flujo para publicar una versión
1. Cambios + tests nuevos o adaptados + entrada en `CHANGELOG.md` (versión X.Y.Z).
2. `python -m pytest -q` en verde.
3. Comprobar con `git status` que no entra ningún dato real (ver reglas).
4. `git add -A`, `git commit -m "vX.Y.Z: …"`, `git push`.
5. `git tag vX.Y.Z` y `git push origin vX.Y.Z`. Usar siempre una etiqueta NUEVA; no forzar etiquetas ya publicadas.
6. Revisar GitHub Actions (`tests` y `build-exe`). Si algo falla, leer el log y corregir.
   La release debe contener `optomech-positions-windows.zip`.

## Reglas
- **Repositorio público: nunca subir datos de proyectos reales** (prescription data, ficheros
  FEM/ANSYS, capturas o perfiles de instrumentos como HARMONI). Los datos reales se guardan fuera
  del repositorio. No leer ni procesar datos de proyectos reales salvo petición expresa del usuario.
- No añadir dependencias nuevas (aparte de openpyxl) sin consultarlo: el .exe debe seguir siendo
  ligero y los compañeros pueden no tener permisos para instalar paquetes.
- Mantener la compatibilidad con Windows (es la plataforma de los usuarios) y con Python 3.9+.
- No cambiar las convenciones de cálculo sin validación explícita del usuario: los resultados deben
  coincidir con la herramienta de conversión Zemax-CREO del departamento.
  - Zemax: R = Rx·Ry·Rz (intrínseco). CREO: R = Rz·Ry·Rx; gimbal lock (ty = ±90°): tz = 0.
  - Térmica: P_cal = P_fijo + (P_frío − P_fijo)·(1 + f).
  - Redondeo: mitad hacia fuera (como ROUND de Excel).
- Toda comprobación de configuración nueva va en `core.validate_setup` (la usan GUI y CLI) con su test.
- Los perfiles antiguos deben seguir cargando (compatibilidad hacia atrás en `profile_from_dict`).
- Coeficientes de materiales: solo con `"verificado": true` si se han comprobado contra la fuente.
- Pedir confirmación antes de: subir a GitHub (push y etiquetas), borrar ficheros o reescribir el historial.

## Pendiente
- Decidir la licencia (fichero LICENSE).
- Configurar `git config user.name` / `user.email` en el equipo del usuario.
- Mejoras propuestas: comparación entre versiones del diseño, tolerancia de estabilidad por elemento,
  importar un trazado de rayo real de Zemax, ZOS-API, interfaz en inglés.
