# RCOFA — módulo de MongoDB (Ihann)

## Ejecutar

Con MongoDB local iniciado en `127.0.0.1:27017`, instalar `pip install -r requirements.txt`
y ejecutar `python carga_datos.py`. Esto crea las cuatro colecciones vacías en `rcofa`.
La conexión usa el usuario de clase `mongoDB`, contraseña `mongo2008`, autenticado
en `admin`. Ese usuario debe existir en el servidor; el programa no lo crea.
Las credenciales son las del entorno local de práctica.

## Contrato para el equipo

| Colección | Campos requeridos |
| --- | --- |
| `ubicaciones` | `_id` string, `provincia`, `canton`, `distrito`, `poblado`, `tipo_zona` |
| `categorias_fenomeno` | `_id` int, `nombre` string, `descripcion` string |
| `observadores` | `_id` int, `alias_o_estacion` string, `rol` string, `indice_confiabilidad` float entre 0 y 1 |
| `avistamientos` | `_id` string `REP-00000001`, `fecha_evento`, `duracion_seg` int no negativo, `id_categoria` int, `id_observador` int, `ubicacion` documento |

**Jefferson:** entregar listas de diccionarios de ubicaciones, categorías y observadores.
El `_id` de ubicación es el código del CSV convertido a string, conservando ceros
iniciales. Clasificar `tipo_zona` como `Insular`, `Costera`, `Montañosa` o `Urbana`.
Se conserva `poblado` como en class_06. La lectura del CSV y clasificación corresponden a su módulo.

**Kener:** entregar una lista de 10.000 avistamientos con códigos únicos. En cada
`ubicacion` incluir `id_sector` (igual a `ubicaciones._id`), `provincia`, `canton`,
`distrito` y `localidad` (copiar `poblado`). Usar IDs de categorías y observadores
existentes. `fecha_evento` puede ser un `datetime` o texto `YYYY-MM-DD HH:MM:SS`;
usar fechas sin zona horaria y el mismo criterio en todo el equipo.
La carga convierte texto con `datetime.strptime`. Los campos opcionales, como
`telemetria_entorno`, radar o testimonio, se conservan sin exigirlos a todos los reportes.
La generación corresponde a su módulo.

El enunciado usa tanto `_id` como `codigo_reporte`: guardamos ambos con el mismo
código. El generador puede entregar solo `_id`; la carga añade `codigo_reporte`.

**Fede:** abrir una conexión al iniciar y cerrarla al terminar. Las funciones no
imprimen ni piden entradas; retornan datos para el menú. El formato de fechas en
español y el filtro Python `duracion_seg > 200` corresponden a su módulo.

```python
from subrutinas import conectar, preparar_base, cargar_datos

conex = conectar()
try:
    db = conex.rcofa
    preparar_base(db)
    # Cuando estén disponibles las cuatro listas del equipo:
    # resumen = cargar_datos(db, ubicaciones, categorias, observadores, avistamientos)
finally:
    conex.close()
```

## Funciones en subrutinas.py

Todas reciben `db` como primer argumento, excepto `conectar` y los validadores.

- `cargar_ubicaciones(db, ubicaciones)`, `cargar_categorias(db, categorias)`,
  `cargar_observadores(db, observadores)`, `cargar_avistamientos(db, avistamientos)`:
  retornan listas de IDs insertados. Cargar en ese orden.
- `cargar_datos(db, ubicaciones, categorias, observadores, avistamientos)`:
  ejecuta las cuatro cargas y retorna cantidades por colección.
- `insertar_categoria(db, id_categoria, nombre, descripcion)`.
- `modificar_categoria(db, id_categoria, nombre, descripcion)`.
- `borrar_categoria(db, id_categoria)` y `listar_categorias(db)`.
- `insertar_observador(db, id_observador, alias_o_estacion, rol, indice_confiabilidad)`.
- `modificar_observador(db, id_observador, alias_o_estacion, rol, indice_confiabilidad)`.
- `borrar_observador(db, id_observador)` y `listar_observadores(db)`.
- `consultar_avistamientos(db, provincia=None, canton=None, id_categoria=None)`:
  combina los filtros enviados con AND y `$eq`; retorna solo código, fecha,
  duración y localidad. Orden: duración descendente y fecha ascendente.
- `consultar_rango_fechas(db, fecha_inicio, fecha_fin)`: incluye ambos extremos,
  devuelve todas las coincidencias sin límite y ordena por fecha.
- `consultar_reporte_completo(db)`: cruza los dos catálogos con `$lookup`;
  retorna código, fecha, duración, localidad, nombre_fenomeno y alias_observador.

Inserciones individuales retornan el ID. Modificaciones retornan `UpdateResult`:
usar `matched_count` para saber si existía y `modified_count` para saber si cambió.
Borrados retornan `DeleteResult` con `deleted_count`. No se permite borrar un
catálogo referenciado por reportes. Este control supone ejecución desde una sola
consola; no es una transacción frente a escrituras concurrentes.

Las excepciones se propagan para que el menú pueda informar el error. Campos
faltantes producen `KeyError`, valores inválidos `ValueError`, y errores de MongoDB
son `pymongo.errors.PyMongoError`. Los IDs duplicados no se sobrescriben.
Las cargas usan inserciones ordenadas y no son transacciones: un duplicado o fallo
del servidor puede dejar registros previos insertados. No repetir la carga completa
sobre una base poblada; revisar el error y usar una base de prueba para ensayos.

## Comprobaciones

`python carga_datos.py` verifica conexión y creación de colecciones.
`python consultas_fenomenos.py` y la opción 4 de `python main.py` abren el mismo menú de consultas sobre los datos ya cargados.
Las pruebas automáticas requieren `mongomock` y se ejecutan con:

```text
pip install mongomock
python -m unittest discover -s tests -v
```

Estas pruebas usan una base simulada; también debe comprobarse la carga con el CSV
real y los 10.000 reportes contra MongoDB local antes de integrar.
