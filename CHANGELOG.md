# Cambios

## 1.5.3
- Corregido: `cli.py` fallaba (UnicodeEncodeError) al redirigir la salida a un fichero en Windows;
  la salida de la CLI se escribe ahora en UTF-8.

## 1.5.2 — revisión de fallos
- Validación de la configuración antes de calcular (GUI y CLI): acrónimos vacíos o repetidos,
  tolerancias, overrides y puntos FEM mal escritos, temperaturas iguales, material inexistente,
  casos sin T0 y nombres de caso que darían la misma pestaña en el Excel.
- Corregido: con acrónimos repetidos, los resultados de estabilidad se asignaban al elemento equivocado.
- Corregido: nombres de caso largos generaban pestañas de más de 31 caracteres (Excel puede no abrir el fichero).
- Nombres de caso únicos al añadirlos y renombrado con doble clic; cada pestaña de estabilidad indica
  el fichero del caso y el de referencia.
- El punto FEM admite x;y;z también en la tabla (antes la interfaz lo rechazaba).
- Lectura de CSV separados por comas; los modelos pequeños en mm ya no se interpretan como metros
  (umbral de extensión 5).
- Acrónimos por defecto útiles y únicos con etiquetas de varias palabras.
- Aviso si el perfil usa un material que no está en materiales.json (antes se cambiaba en silencio a CTE manual).
- Lanzadores .bat: admiten rutas de Python con espacios.

## 1.5.1
- Lectura robusta de ficheros con finales de línea anómalos (\r\r\n).
- Corrección de un test que fallaba en Windows; los tests automáticos se ejecutan también en Windows.
- CLAUDE.md con el contexto y las reglas del proyecto para trabajar con Claude Code.

## 1.5.0
- La tolerancia de posicionado por defecto pasa a la pestaña 1, junto al panel de tolerancias por
  elemento; la tabla muestra el valor por defecto aplicado.
- Ejecutable de Windows con PyInstaller (optomech-positions.spec, build_exe.bat) y workflow que lo
  compila, lo verifica (--autotest) y lo adjunta a la release al subir una etiqueta v*.
- materiales.json editable junto al ejecutable.

## 1.4.0
- Comprobación de espejos fuera de eje: el punto de impacto y la normal se calculan sobre la cónica
  (radio y cónica leídos de SURFACE DATA SUMMARY). Se muestra la distancia impacto − posición CREO.
- Lectura de tipo de superficie, radio, cónica y vidrio desde la tabla resumen de Zemax.

## 1.3.0
- Estabilidad con desplazamientos termo-estructurales de ANSYS (alternativa a temperaturas):
  1 fichero (UX, UY, UZ) o 3 ficheros por eje; unidades m/mm/µm desde la cabecera.
- Ajuste de sólido rígido por elemento con brazo de palanca: dX, dY, dZ y giros, en ejes
  globales y locales; ángulos Zemax perturbados; residuo del ajuste.
- Referencia opcional de desplazamientos (caso − referencia).
- Punto FEM admite x;y;z (búsqueda 3D de nodos).
- Formato de perfil v3 (compatible con perfiles anteriores).

## 1.2.0
- Pestaña "Vista 2D": planta/alzado/perfil con espejos, normales y rayo central; zoom, desplazamiento
  y detalles al pasar el ratón.
- Comprobación automática de la ley de reflexión en cada elemento (ok / transmisión / fuera de eje / error),
  con resumen en el registro al importar Zemax.
- Ejemplo sintético regenerado para que sea ópticamente coherente.

## 1.1.0
- Quitar elementos de la tabla tras importar Zemax (selección múltiple, tecla Supr); el perfil
  recuerda los elementos quitados y se pueden restaurar.
- Panel para asignar la tolerancia de posicionado (posición y ángulo) a uno o varios elementos.
- El Excel se abre automáticamente al terminar el cálculo (opcional).

## 1.0.0
- Versión inicial pública: conversión Zemax → CREO, tolerancias por elemento, curvas NIST
  (Al 6061-T6, AISI 304/304L/316), estudio de estabilidad con ficheros ANSYS, GUI, CLI y tests.
