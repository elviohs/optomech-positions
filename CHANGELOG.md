# Cambios

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
