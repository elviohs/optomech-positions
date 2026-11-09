## Descarga

`optomech-positions-windows.zip` (en *Assets*, más abajo). Contiene `optomech-positions.exe`, un ejecutable de Windows que abre la interfaz gráfica sin instalar Python, y además `materiales.json`, los ejemplos, el README y el CHANGELOG. Se descomprime y el .exe se abre con doble clic; no necesita instalación.

- Tarda unos segundos en arrancar: se descomprime en una carpeta temporal cada vez que se abre.
- No está firmado digitalmente: si aparece «Windows protegió su PC», pulsar *Más información → Ejecutar de todas formas*. Algunos antivirus marcan los ejecutables de PyInstaller como sospechosos (falso positivo); si el antivirus corporativo lo bloquea, consultar con el servicio de informática.
- `materiales.json` debe quedar en la misma carpeta que el .exe; se puede editar para añadir materiales.
- Comprobación sin ventana: `optomech-positions.exe --autotest ejemplos\sistema_3_espejos\ejemplo_3_espejos.json salida.xlsx` calcula el ejemplo sintético, genera el Excel y escribe el registro en `salida.log`.

Con Python instalado se puede usar el código fuente, que incluye el modo consola (`cli.py`); ver el [README](https://github.com/elviohs/optomech-positions#readme).

## Novedades en {VERSION}

{CHANGES}

## Estado de validación

### Validado
- Conversión de ángulos Zemax→CREO y conversión térmica: coinciden con la herramienta de
  conversión del departamento en un sistema real de 8 espejos.
- Redondeo compatible con la función ROUND de Excel.
- Curvas de dilatación Al 6061-T6, AISI 304, 304L y 316 comprobadas contra las tablas de NIST.
- Comprobación de la ley de reflexión: error < 0,001° en un sistema real de 8 espejos,
  incluido un paraboloide fuera de eje.
- Estabilidad con temperaturas: reproduce un cálculo manual con ΔT uniforme (diferencia < 4 %).
- Estabilidad con desplazamientos: el ajuste de sólido rígido recupera un campo sintético conocido.
- {NTESTS} tests automáticos.
- Ejecutable Windows (.exe) generado por GitHub Actions y publicado en Releases: se descarga,
  arranca y supera una prueba de uso.

### Pendiente de validar
- Ejecutable en un PC sin Python (SmartScreen / antivirus corporativo).
- Importación de desplazamientos con exportaciones reales de ANSYS Mechanical
  (hasta ahora solo con ficheros sintéticos).
- Comparación del modelo de temperaturas (1er orden en X-Y) con desplazamientos termo-estructurales.
- Efecto de las perturbaciones en la calidad de imagen en Zemax.
- Uso con otros sistemas ópticos y por otros usuarios.
- Otras versiones de OpticStudio y prescription data exportado en inglés.
- Ciclo completo: posiciones de la herramienta introducidas y verificadas en CREO.

### Limitaciones conocidas
- Normal en el punto de impacto solo para superficies cónicas (STANDARD).
- Ficheros Zemax multiconfiguración: exportar una configuración cada vez.
- Un único banco de un solo material con un punto fijo.

Historial completo: [CHANGELOG.md](https://github.com/elviohs/optomech-positions/blob/{TAG}/CHANGELOG.md).
