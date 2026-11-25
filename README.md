# RCOFA — Registro de avistamientos

## Instalación y ejecución

Para usar la aplicación necesitás Python 3.9 o posterior y un servidor MongoDB
accesible. En un entorno de práctica, instalá las dependencias con:

```text
python -m venv .venv
```

Activá el entorno (`.venv\Scripts\Activate.ps1` en PowerShell o
`source .venv/bin/activate` en bash) y ejecutá:

```text
python -m pip install -r requirements.txt
python carga_datos.py --base rcofa_pruebas
python main.py --base rcofa_pruebas
```

Los tres puntos de entrada (`main.py`, `carga_datos.py` y
`consultas_fenomenos.py`) usan `MONGO_URI` si está definida. Por defecto
conectan a `mongodb://127.0.0.1:27017` sin credenciales. Si tu servidor requiere
autenticación, configurá la URI en el entorno sin guardarla en el repositorio.
Para elegir la base se usa `--base`, luego `MONGO_DB_NAME` y por último `rcofa`.
Usá la misma base al cargar y al consultar.

También podés cargar desde la opción 1 del menú principal o abrir solo el menú
de consultas con `python consultas_fenomenos.py --base rcofa_pruebas`. El menú
principal abre la conexión al elegir una operación que la requiere y la cierra
al salir o interrumpir la ejecución.

## Carga inicial: no borra ni sobrescribe

Resultado esperado: **7.116 ubicaciones**, **5 categorías**, **10 observadores**
y **10.000 avistamientos sintéticos**. El CSV del equipo está en
`data/ubicaciones.csv`; los dos catálogos se definen únicamente en `catalogos.py`.
No se usan reportes de ejemplo como fuente.

- El `idubi` conserva el código original, incluidos ceros iniciales; no es
  único. El `_id` de ubicación combina una huella SHA-256 de los cinco campos
  originales y un número de ocurrencia. Se conserva cada copia de una fila
  idéntica: no se puede distinguir cuál copia física es cuál, pero el conjunto
  de IDs no cambia al reordenar las filas. Los nombres se muestran sin espacios
  en los bordes.
- Los dos poblados vacíos se conservan como texto vacío en el catálogo. Para
  esos sectores, el reporte muestra el distrito como localidad. La clasificación
  da prioridad a poblado insular, cantón costero, cantón montañoso y, por último,
  zona urbana. La zona insular se limita a los nueve poblados del enunciado:
  que el nombre contenga «Isla» no basta.
- Cada reporte guarda `_id` y `codigo_reporte` iguales (`REP-00000001` a
  `REP-00010000`), categoría y observador existentes y `ubicacion.id_sector`
  igual al `_id` de su ubicación. La fecha se guarda como BSON datetime sin
  zona horaria explícita; si se recibe texto `YYYY-MM-DD HH:MM:SS`, se convierte
  con `datetime.strptime`. Los campos opcionales varían entre reportes y
  algunos reportes no tienen ninguno.

La carga inicial rechaza bases que ya contienen documentos y valida todos los
datos antes de escribir. No elimina registros. Las inserciones **no son una
transacción**: si falla MongoDB durante la carga, puede quedar una carga
parcial. Revisá esa base y, para reintentar, elegí otra vacía; no corras dos
cargas simultáneas en la misma base.

## Consultas y catálogos

El menú permite listar, crear, modificar y borrar categorías y observadores.
El borrado individual requiere confirmación y se bloquea si un avistamiento
referencia el registro.

Las cuatro consultas son: filtro por provincia, cantón o categoría;
rango de fechas inclusivo; reporte cruzado que muestra el fenómeno y el
observador; y filtro en Python por duración estrictamente mayor a 200 segundos.

## Pruebas

```text
python -m pip install mongomock
python -m unittest discover -s tests -v
```

Las pruebas usan bases simuladas, no requieren conectarse a MongoDB.

## Antes de publicar

Confirmá que el equipo tiene permiso para redistribuir `data/ubicaciones.csv`.
Las versiones anteriores incluyeron credenciales: antes de hacer público el
repositorio, tratá esas credenciales como expuestas (revocá o rotá las que
sigan vigentes) y resolvé su exposición en el historial con los responsables.
Que no aparezcan en el código actual no elimina su presencia histórica.
