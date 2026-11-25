"""Acceso a MongoDB de RCOFA. Las funciones reciben la base de datos abierta."""

import argparse
import csv
import json
import os
import re
import unicodedata
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timedelta
from functools import partial
from hashlib import sha256
from pathlib import Path
from random import Random

import pymongo
from bson import encode
from bson.errors import InvalidDocument
from pymongo.errors import ConnectionFailure, DuplicateKeyError, InvalidName, PyMongoError

from catalogos import CATEGORIAS_FENOMENO_INICIALES, OBSERVADORES_INICIALES


COLECCIONES = ('ubicaciones', 'categorias_fenomeno', 'observadores', 'avistamientos')
CARPETA_DATOS = Path(__file__).resolve().parent / 'data'
CANTONES_COSTEROS = {
    'Puntarenas', 'Esparza', 'Montes de Oro', 'Osa', 'Quepos', 'Golfito',
    'Parrita', 'Corredores', 'Garabito', 'Liberia', 'Nicoya', 'Santa Cruz',
    'Bagaces', 'Carrillo', 'Cañas', 'Abangares', 'Nandayure', 'La Cruz',
    'Hojancha', 'Limón', 'Pococí', 'Siquirres', 'Talamanca', 'Matina', 'Guácimo',
}
CANTONES_MONTANOSOS = {
    'Tarrazú', 'Aserrí', 'Mora', 'Acosta', 'Turrubares', 'Dota', 'Pérez Zeledón',
    'León Cortés', 'Puriscal', 'San Ramón', 'Zarcero', 'Poás', 'Valverde Vega',
    'Paraíso', 'Jiménez', 'Turrialba', 'Alvarado', 'Oreamuno', 'El Guarco',
    'Barva', 'Santa Bárbara', 'San Rafael', 'San Isidro', 'Tilarán',
    'Buenos Aires', 'Coto Brus',
}
POBLADOS_INSULARES = {
    'Isla del Coco', 'Isla Chira', 'Isla Venado', 'Isla Caballo', 'Isla San Lucas',
    'Isla Tortuga', 'Isla Cedros', 'Isla Jesucita', 'Isla Berrugate',
}


def _normalizar_nombre(texto):
    letras = unicodedata.normalize('NFD', texto.casefold())
    limpio = ''.join(letra for letra in letras if not unicodedata.combining(letra))
    return ' '.join(limpio.split())


_COSTEROS = {_normalizar_nombre(canton) for canton in CANTONES_COSTEROS}
_MONTANOSOS = {_normalizar_nombre(canton) for canton in CANTONES_MONTANOSOS}
_INSULARES = {_normalizar_nombre(poblado) for poblado in POBLADOS_INSULARES}


def clasificar_tipo_zona(provincia, canton, poblado):
    """Aplica la prioridad insular, costera, montañosa y urbana del enunciado."""
    if _normalizar_nombre(poblado) in _INSULARES:
        return 'Insular'
    canton = _normalizar_nombre(canton)
    if canton in _COSTEROS:
        return 'Costera'
    if canton in _MONTANOSOS:
        return 'Montañosa'
    return 'Urbana'


def leer_ubicaciones(ruta):
    documentos = []
    ocurrencias = Counter()
    with open(ruta, encoding='utf-8-sig', newline='') as archivo:
        lector = csv.reader(archivo, delimiter=';', strict=True)
        if next(lector, None) != ['Id', 'Provincia', 'Cantón', 'Distrito', 'Poblado']:
            raise ValueError('Encabezado de ubicaciones.csv no reconocido')
        for fila in lector:
            if len(fila) != 5 or not all(valor.strip() for valor in fila[:4]):
                raise ValueError(f'Fila inválida en ubicaciones.csv (línea {lector.line_num})')
            codigo, *nombres = fila
            provincia, canton, distrito, poblado = (valor.strip() for valor in nombres)
            # El sufijo conserva todas las copias indistinguibles sin depender del orden del CSV.
            huella = sha256(json.dumps(fila, ensure_ascii=False).encode('utf-8')).hexdigest()
            ocurrencias[huella] += 1
            documentos.append({
                '_id': f'{huella}-{ocurrencias[huella]}', 'idubi': codigo,
                'provincia': provincia, 'canton': canton, 'distrito': distrito,
                'poblado': poblado, 'tipo_zona': clasificar_tipo_zona(provincia, canton, poblado),
            })
    if not documentos:
        raise ValueError('El CSV no contiene ubicaciones')
    return documentos


def generar_avistamientos(ubicaciones, categorias, observadores, cantidad=10_000):
    """Genera reportes sintéticos reproducibles, sin conectarse ni escribir."""
    validar_entero(cantidad, 'cantidad')
    if not 1 <= cantidad <= 99_999_999:
        raise ValueError('La cantidad debe estar entre 1 y 99999999')
    if not ubicaciones or not categorias or not observadores:
        raise ValueError('Se requieren ubicaciones, categorías y observadores para generar reportes')
    azar = Random(0)
    sectores = sorted(ubicaciones, key=lambda ubicacion: ubicacion['_id'])
    azar.shuffle(sectores)
    inicio = datetime(2026, 1, 1)
    opcionales = (
        ('telemetria_entorno', {'temperatura_c': 24.5, 'viento_kmh': 12}),
        ('datos_radar', {'altitud_m': 1200, 'velocidad_kmh': 110}),
        ('testimonio_visual', {'relato': 'Luz intermitente en el horizonte'}),
        ('sensores_ambientales', {'ruido_db': 55}),
        ('alteracion_flora_fauna', {'observacion': 'Aves dispersas'}),
        ('evidencia', {'tipo': 'Registro simulado'}),
    )
    reportes = []
    for numero in range(1, cantidad + 1):
        sector = sectores[(numero - 1) % len(sectores)]
        codigo = f'REP-{numero:08d}'
        reporte = {
            '_id': codigo, 'codigo_reporte': codigo,
            'fecha_evento': inicio + timedelta(seconds=azar.randrange(365 * 86_400)),
            'duracion_seg': azar.randint(1, 600),
            'id_categoria': azar.choice(categorias)['_id'],
            'id_observador': azar.choice(observadores)['_id'],
            'ubicacion': {
                'id_sector': sector['_id'], 'provincia': sector['provincia'],
                'canton': sector['canton'], 'distrito': sector['distrito'],
                'localidad': sector['poblado'] or sector['distrito'],
            },
        }
        # El séptimo caso no añade campos opcionales.
        indice = numero % (len(opcionales) + 1)
        if indice < len(opcionales):
            campo, valor = opcionales[indice]
            reporte[campo] = dict(valor)
        reportes.append(reporte)
    return reportes


def conectar():
    """Comprueba la conexión configurada por el entorno antes de devolverla."""
    conex = pymongo.MongoClient(
        os.environ.get('MONGO_URI', 'mongodb://127.0.0.1:27017'),
        serverSelectionTimeoutMS=5000,
    )
    try:
        conex.admin.command('ping')
        return conex
    except BaseException:
        conex.close()
        raise


def preparar_base(db):
    existentes = db.list_collection_names()
    for nombre in COLECCIONES:
        if nombre not in existentes:
            db.create_collection(nombre)


def validar_entero(valor, campo):
    if type(valor) is not int:
        raise ValueError('{0} debe ser un entero'.format(campo))
    if not -(2**63) <= valor < 2**63:
        raise ValueError(f'{campo} fuera del rango de enteros BSON de 64 bits')


def validar_texto(valor, campo):
    if not isinstance(valor, str) or not valor.strip():
        raise ValueError('{0} debe ser un texto no vacío'.format(campo))


def validar_categoria(documento):
    validar_entero(documento['_id'], '_id')
    validar_texto(documento['nombre'], 'nombre')
    validar_texto(documento['descripcion'], 'descripcion')


def validar_observador(documento):
    validar_entero(documento['_id'], '_id')
    validar_texto(documento['alias_o_estacion'], 'alias_o_estacion')
    validar_texto(documento['rol'], 'rol')
    indice = documento['indice_confiabilidad']
    if type(indice) not in (int, float) or not 0 <= indice <= 1:
        raise ValueError('indice_confiabilidad debe estar entre 0.0 y 1.0')


def validar_ubicacion(documento):
    for campo in ('_id', 'provincia', 'canton', 'distrito'):
        validar_texto(documento[campo], campo)
    if not isinstance(documento['poblado'], str):
        raise ValueError('poblado debe ser un texto (puede estar vacío)')
    if documento['tipo_zona'] not in ('Costera', 'Insular', 'Montañosa', 'Urbana'):
        raise ValueError('tipo_zona no válido')


def _preparar_lote(filas, validar):
    documentos = [dict(fila) for fila in filas]
    ids = set()
    for documento in documentos:
        validar(documento)
        identificador = documento['_id']
        if identificador in ids:
            raise ValueError(f'ID repetido en el lote: {identificador}')
        ids.add(identificador)
        try:
            encode(documento)
        except (InvalidDocument, OverflowError) as error:
            raise ValueError(f'Documento BSON inválido para el ID {identificador}') from error
    return documentos


def _insertar_lote(coleccion, documentos):
    return coleccion.insert_many(documentos).inserted_ids if documentos else []


def cargar_ubicaciones(db, ubicaciones):
    return _insertar_lote(db.ubicaciones, _preparar_lote(ubicaciones, validar_ubicacion))


def insertar_categoria(db, id_categoria, nombre, descripcion):
    documento = {'_id': id_categoria, 'nombre': nombre, 'descripcion': descripcion}
    validar_categoria(documento)
    return db.categorias_fenomeno.insert_one(documento).inserted_id


def cargar_categorias(db, categorias):
    return _insertar_categorias(db, _preparar_lote(categorias, validar_categoria))


def _insertar_categorias(db, documentos):
    # El enunciado exige insert_one para este catálogo.
    return [db.categorias_fenomeno.insert_one(d).inserted_id for d in documentos]


def insertar_observador(db, id_observador, alias_o_estacion, rol, indice_confiabilidad):
    documento = {'_id': id_observador, 'alias_o_estacion': alias_o_estacion,
                 'rol': rol, 'indice_confiabilidad': indice_confiabilidad}
    validar_observador(documento)
    documento['indice_confiabilidad'] = float(indice_confiabilidad)
    return db.observadores.insert_one(documento).inserted_id


def cargar_observadores(db, observadores):
    return _insertar_lote(db.observadores, _preparar_lote(observadores, _normalizar_observador))


def _normalizar_observador(documento):
    validar_observador(documento)
    documento['indice_confiabilidad'] = float(documento['indice_confiabilidad'])


def listar_categorias(db):
    return list(db.categorias_fenomeno.find().sort('_id', 1))


def listar_observadores(db):
    return list(db.observadores.find().sort('_id', 1))


def modificar_categoria(db, id_categoria, nombre, descripcion):
    validar_categoria({'_id': id_categoria, 'nombre': nombre, 'descripcion': descripcion})
    return db.categorias_fenomeno.update_one(
        {'_id': id_categoria}, {'$set': {'nombre': nombre, 'descripcion': descripcion}}
    )


def modificar_observador(db, id_observador, alias_o_estacion, rol, indice_confiabilidad):
    documento = {'_id': id_observador, 'alias_o_estacion': alias_o_estacion,
                 'rol': rol, 'indice_confiabilidad': indice_confiabilidad}
    validar_observador(documento)
    documento.pop('_id')
    documento['indice_confiabilidad'] = float(indice_confiabilidad)
    return db.observadores.update_one({'_id': id_observador}, {'$set': documento})


def borrar_categoria(db, id_categoria):
    validar_entero(id_categoria, 'id_categoria')
    if db.avistamientos.find_one({'id_categoria': id_categoria}, {'_id': 1}):
        raise ValueError('La categoría está referenciada por avistamientos')
    return db.categorias_fenomeno.delete_one({'_id': id_categoria})


def borrar_observador(db, id_observador):
    validar_entero(id_observador, 'id_observador')
    if db.avistamientos.find_one({'id_observador': id_observador}, {'_id': 1}):
        raise ValueError('El observador está referenciado por avistamientos')
    return db.observadores.delete_one({'_id': id_observador})


def convertir_fecha(valor):
    if isinstance(valor, datetime):
        if valor.tzinfo is None:
            return valor
        raise ValueError('La fecha no debe tener zona horaria')
    if isinstance(valor, str):
        return datetime.strptime(valor, '%Y-%m-%d %H:%M:%S')
    raise ValueError('La fecha debe ser datetime o texto YYYY-MM-DD HH:MM:SS')


def cargar_avistamientos(db, avistamientos):
    """Inserta los reportes, conservando sus campos opcionales."""
    categorias = {d['_id'] for d in db.categorias_fenomeno.find({}, {'_id': 1})}
    observadores = {d['_id'] for d in db.observadores.find({}, {'_id': 1})}
    sectores = {d['_id'] for d in db.ubicaciones.find({}, {'_id': 1})}
    documentos = _preparar_avistamientos(avistamientos, categorias, observadores, sectores)
    return _insertar_lote(db.avistamientos, documentos)


def _preparar_avistamientos(avistamientos, categorias, observadores, sectores):
    def validar(documento):
        codigo = documento['_id']
        if not isinstance(codigo, str) or re.fullmatch(r'REP-[0-9]{8}', codigo) is None:
            raise ValueError('_id debe tener el formato REP-00000001')
        if documento.get('codigo_reporte', codigo) != codigo:
            raise ValueError('codigo_reporte debe coincidir con _id')
        documento['codigo_reporte'] = codigo
        documento['fecha_evento'] = convertir_fecha(documento['fecha_evento'])
        validar_entero(documento['duracion_seg'], 'duracion_seg')
        if documento['duracion_seg'] < 0:
            raise ValueError('duracion_seg no puede ser negativa')
        validar_entero(documento['id_categoria'], 'id_categoria')
        validar_entero(documento['id_observador'], 'id_observador')
        if documento['id_categoria'] not in categorias:
            raise ValueError('Categoría inexistente')
        if documento['id_observador'] not in observadores:
            raise ValueError('Observador inexistente')
        ubicacion = documento['ubicacion']
        for campo in ('id_sector', 'provincia', 'canton', 'distrito', 'localidad'):
            validar_texto(ubicacion[campo], campo)
        if ubicacion['id_sector'] not in sectores:
            raise ValueError('Sector inexistente')
    return _preparar_lote(avistamientos, validar)


def cargar_datos(db, ubicaciones, categorias, observadores, avistamientos):
    """Valida todo en memoria y luego carga en orden de dependencias."""
    ubicaciones = _preparar_lote(ubicaciones, validar_ubicacion)
    categorias = _preparar_lote(categorias, validar_categoria)
    observadores = _preparar_lote(observadores, _normalizar_observador)
    avistamientos = _preparar_avistamientos(
        avistamientos, {d['_id'] for d in categorias},
        {d['_id'] for d in observadores}, {d['_id'] for d in ubicaciones},
    )
    preparar_base(db)
    return {
        'ubicaciones': len(_insertar_lote(db.ubicaciones, ubicaciones)),
        'categorias_fenomeno': len(_insertar_categorias(db, categorias)),
        'observadores': len(_insertar_lote(db.observadores, observadores)),
        'avistamientos': len(_insertar_lote(db.avistamientos, avistamientos)),
    }


def cargar_datos_iniciales(db, carpeta):
    """Solo carga en una base sin documentos. No elimina ni sobrescribe datos."""
    if any(db[nombre].find_one({}, {'_id': 1}) is not None
           for nombre in db.list_collection_names()):
        raise ValueError('La base ya contiene datos. Elegí una base vacía con --base.')
    ubicaciones = leer_ubicaciones(Path(carpeta) / 'ubicaciones.csv')
    categorias = CATEGORIAS_FENOMENO_INICIALES
    observadores = OBSERVADORES_INICIALES
    avistamientos = generar_avistamientos(ubicaciones, categorias, observadores)
    return cargar_datos(db, ubicaciones, categorias, observadores, avistamientos)


def consultar_avistamientos(db, provincia=None, canton=None, id_categoria=None):
    filtro = {}
    for campo, valor in (('ubicacion.provincia', provincia),
                         ('ubicacion.canton', canton), ('id_categoria', id_categoria)):
        if valor is not None:
            if campo == 'id_categoria':
                validar_entero(valor, campo)
            filtro[campo] = {'$eq': valor}
    proyeccion = {'_id': 0, 'codigo_reporte': 1, 'fecha_evento': 1,
                 'duracion_seg': 1, 'ubicacion.localidad': 1}
    return list(db.avistamientos.find(filtro, proyeccion).sort(
        [('duracion_seg', -1), ('fecha_evento', 1)]))


def consultar_rango_fechas(db, fecha_inicio, fecha_fin):
    inicio = convertir_fecha(fecha_inicio)
    fin = convertir_fecha(fecha_fin)
    if inicio > fin:
        raise ValueError('La fecha inicial no puede ser posterior a la final')
    return list(db.avistamientos.find(
        {'fecha_evento': {'$gte': inicio, '$lte': fin}}
    ).sort('fecha_evento', 1))


def consultar_reporte_completo(db):
    return list(db.avistamientos.aggregate([
        {'$lookup': {'from': 'categorias_fenomeno', 'localField': 'id_categoria',
                     'foreignField': '_id', 'as': 'categoria'}},
        {'$lookup': {'from': 'observadores', 'localField': 'id_observador',
                     'foreignField': '_id', 'as': 'observador'}},
        {'$unwind': {'path': '$categoria', 'preserveNullAndEmptyArrays': True}},
        {'$unwind': {'path': '$observador', 'preserveNullAndEmptyArrays': True}},
        {'$project': {'_id': 0, 'codigo_reporte': 1, 'fecha_evento': 1,
                      'duracion_seg': 1, 'localidad': '$ubicacion.localidad',
                      'nombre_fenomeno': '$categoria.nombre',
                      'alias_observador': '$observador.alias_o_estacion'}},
        {'$sort': {'codigo_reporte': 1}}
    ]))


MESES = (
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
)


def formatear_fecha_es(fecha: datetime) -> str:
    mes = MESES[fecha.month - 1]
    return f"{fecha.day:02d} de {mes} de {fecha.year} a las {fecha:%H:%M:%S}"


def filtrar_duracion_mayor_a(reportes: list[dict], umbral: int = 200) -> list[dict]:
    return [reporte for reporte in reportes if reporte.get("duracion_seg", 0) > umbral]


def imprimir_reportes(reportes: list[dict]) -> None:
    if not reportes:
        print("Sin resultados.")
        return

    for reporte in reportes:
        partes = [reporte["codigo_reporte"]]
        if "fecha_evento" in reporte:
            partes.append(formatear_fecha_es(reporte["fecha_evento"]))
        if "duracion_seg" in reporte:
            partes.append(f'{reporte["duracion_seg"]} s')

        localidad = reporte.get("localidad")
        if localidad is None:
            localidad = reporte.get("ubicacion", {}).get("localidad")
        if localidad:
            partes.append(f"Localidad: {localidad}")

        for campo, etiqueta in (
            ("nombre_fenomeno", "Fenómeno"),
            ("alias_observador", "Observador"),
        ):
            if campo in reporte:
                partes.append(f"{etiqueta}: {reporte[campo]}")
        print(" | ".join(partes))


def _leer_id(leer, mensaje='ID: '):
    try:
        identificador = int(leer(mensaje))
    except ValueError:
        raise ValueError('ID debe ser un entero') from None
    if not -(2**63) <= identificador < 2**63:
        raise ValueError('ID fuera del rango de enteros BSON de 64 bits')
    return identificador


def menu_consultas(db, *, leer):
    """Ejecuta consultas sobre una base ya abierta, sin modificarla."""
    campos = {'1': 'provincia', '2': 'canton', '3': 'id_categoria'}
    while True:
        print('\nConsultas\n1. Por provincia, cantón o categoría\n2. Rango de fechas'
              '\n3. Reporte cruzado\n4. Duración mayor a 200 s (filtro Python)\n0. Volver')
        opcion = leer('Opción: ').strip()
        if opcion == '0':
            return
        try:
            if opcion == '1':
                campo = campos.get(leer('1. Provincia / 2. Cantón / 3. Categoría: ').strip())
                if campo is None:
                    raise ValueError('Opción inválida.')
                if campo == 'id_categoria':
                    valor = _leer_id(leer, 'ID de categoría: ')
                else:
                    etiqueta = 'Provincia' if campo == 'provincia' else 'Cantón'
                    valor = leer(f'{etiqueta}: ').strip()
                    validar_texto(valor, etiqueta)
            elif opcion == '2':
                inicio = leer('Fecha inicial (YYYY-MM-DD HH:MM:SS): ').strip()
                fin = leer('Fecha final (YYYY-MM-DD HH:MM:SS): ').strip()
                inicio, fin = convertir_fecha(inicio), convertir_fecha(fin)
                if inicio > fin:
                    raise ValueError('La fecha inicial no puede ser posterior a la final')
            elif opcion not in ('3', '4'):
                raise ValueError('Opción inválida.')
        except ValueError as error:
            print(str(error))
            continue

        if opcion == '1':
            reportes = consultar_avistamientos(db, **{campo: valor})
        elif opcion == '2':
            reportes = consultar_rango_fechas(db, inicio, fin)
        else:
            reportes = consultar_reporte_completo(db)
            if opcion == '4':
                print('Duración mayor a 200 s: filtro Python sobre todo el reporte cruzado.')
                reportes = filtrar_duracion_mayor_a(reportes)
        imprimir_reportes(reportes)


def ejecutar_consultas(db):
    try:
        menu_consultas(db, leer=input)
    except ValueError as error:
        # La entrada inválida ya se maneja dentro del submenú.
        raise RuntimeError('Error inesperado en consultas') from error


def ejecutar_carga(db):
    try:
        resumen = cargar_datos_iniciales(db, CARPETA_DATOS)
    except (OSError, csv.Error, UnicodeError) as error:
        raise ValueError('No se pudo leer data/ubicaciones.csv. Revisá el archivo y su formato.') from error
    print(f'Base de datos: {db.name}')
    for coleccion, cantidad in resumen.items():
        print(f'{coleccion}: {cantidad} documentos insertados')


@contextmanager
def _sesion_mongo(base):
    conexion = None

    def operar(accion, *argumentos):
        nonlocal conexion
        if conexion is None:
            try:
                conexion = conectar()
            except (PyMongoError, ValueError):
                raise ValueError('No se pudo conectar a MongoDB. Revisá MONGO_URI y el servidor.') from None
        try:
            return accion(conexion[base], *argumentos)
        except InvalidName:
            raise ValueError('Nombre de base inválido. Revisá --base o MONGO_DB_NAME.') from None
        except DuplicateKeyError:
            raise ValueError('Ya existe un registro con ese ID.') from None
        except ConnectionFailure:
            raise ValueError('Se perdió la conexión a MongoDB durante la operación.') from None
        except PyMongoError:
            raise ValueError('MongoDB no completó la operación. Revisá el estado y los permisos de la base.') from None

    try:
        yield operar
    finally:
        if conexion is not None:
            conexion.close()


def ejecutar_cli(descripcion, accion=None):
    parser = argparse.ArgumentParser(description=descripcion)
    parser.add_argument('--base', default=os.environ.get('MONGO_DB_NAME', 'rcofa'),
                        help='Base de MongoDB (por defecto MONGO_DB_NAME o rcofa)')
    argumentos = parser.parse_args()
    with _sesion_mongo(argumentos.base) as operar:
        if accion is None:
            operaciones = {
                'cargar': ejecutar_carga, 'consultar': ejecutar_consultas,
                'listar_categorias': listar_categorias, 'insertar_categoria': insertar_categoria,
                'modificar_categoria': modificar_categoria, 'borrar_categoria': borrar_categoria,
                'listar_observadores': listar_observadores, 'insertar_observador': insertar_observador,
                'modificar_observador': modificar_observador, 'borrar_observador': borrar_observador,
            }
            menu_principal({nombre: partial(operar, funcion) for nombre, funcion in operaciones.items()},
                           leer=input)
        else:
            try:
                operar(accion)
            except ValueError as error:
                parser.exit(1, f'{error}\n')
            except (EOFError, KeyboardInterrupt) as error:
                if isinstance(error, KeyboardInterrupt) and accion is ejecutar_carga:
                    parser.exit(130, '\nCarga interrumpida: puede haber quedado una carga parcial. '
                                     'Revisá la base antes de reintentar.\n')
                print('\nSaliendo.')


def _leer_argumentos_catalogo(leer, catalogo, operacion):
    identificador = _leer_id(leer)
    if operacion == '4':
        return [identificador]

    campos = ('nombre', 'descripcion') if catalogo == 'categoria' else ('alias_o_estacion', 'rol')
    argumentos = [identificador]
    for campo in campos:
        valor = leer(f'{campo}: ').strip()
        validar_texto(valor, campo)
        argumentos.append(valor)
    if catalogo == 'observador':
        try:
            confianza = float(leer('Confiabilidad (0 a 1): '))
        except ValueError:
            raise ValueError('Confiabilidad debe ser un número entre 0 y 1') from None
        if not 0 <= confianza <= 1:
            raise ValueError('Confiabilidad debe ser un número entre 0 y 1')
        argumentos.append(confianza)
    return argumentos


def _menu_catalogo(catalogo, acciones, leer, escribir):
    plural = {'categoria': 'categorias', 'observador': 'observadores'}[catalogo]
    opciones = {
        '1': f'listar_{plural}',
        '2': f'insertar_{catalogo}',
        '3': f'modificar_{catalogo}',
        '4': f'borrar_{catalogo}',
    }
    titulo = 'Categorías' if catalogo == 'categoria' else 'Observadores'
    while True:
        escribir(f'\n{titulo}\n1. Listar\n2. Crear\n3. Modificar\n4. Borrar\n0. Volver')
        opcion = leer('Opción: ').strip()
        if opcion == '0':
            return
        clave = opciones.get(opcion)
        if clave is None:
            escribir('Opción inválida.')
            continue
        accion = acciones.get(clave)
        if accion is None:
            escribir(f'Acción no conectada: {clave}.')
            continue

        try:
            if opcion == '1':
                filas = accion()
                if filas is not None:
                    for fila in filas:
                        escribir(str(fila))
                    if not filas:
                        escribir('No hay registros.')
                continue
            argumentos = _leer_argumentos_catalogo(leer, catalogo, opcion)
            if opcion == '4':
                confirmacion = leer(f'¿Borrar el ID {argumentos[0]}? Escriba sí para confirmar: ')
                if confirmacion.strip().casefold() not in ('sí', 'si'):
                    escribir('Borrado cancelado.')
                    continue
            resultado = accion(*argumentos)
            if opcion == '2':
                escribir('Registro creado.')
            elif opcion == '3' and resultado is not None:
                escribir('Registro actualizado.' if resultado.matched_count else 'ID no encontrado.')
            elif opcion == '4' and resultado is not None:
                escribir('Registro borrado.' if resultado.deleted_count else 'ID no encontrado.')
        except ValueError as error:
            escribir(str(error))


def menu_principal(acciones=None, *, leer=input, escribir=print):
    """Despacha callbacks por nombre, con las firmas CRUD de Ihann sin `db`.

    `cargar` y `consultar` se llaman sin argumentos y manejan su propio flujo.
    Los callbacks `listar_*` pueden devolver una lista para mostrar o None.
    """
    if acciones is None:
        acciones = {}
    try:
        while True:
            escribir('\nRCOFA\n1. Cargar datos\n2. Categorías\n3. Observadores\n4. Consultas\n0. Salir')
            opcion = leer('Opción: ').strip()
            if opcion == '0':
                return
            if opcion in ('2', '3'):
                catalogo = 'categoria' if opcion == '2' else 'observador'
                _menu_catalogo(catalogo, acciones, leer, escribir)
            elif opcion in ('1', '4'):
                clave = 'cargar' if opcion == '1' else 'consultar'
                accion = acciones.get(clave)
                if accion is None:
                    escribir(f'Acción no conectada: {clave}.')
                else:
                    try:
                        accion()
                    except ValueError as error:
                        escribir(str(error))
            else:
                escribir('Opción inválida.')
    except (EOFError, KeyboardInterrupt):
        escribir('\nSaliendo.')
