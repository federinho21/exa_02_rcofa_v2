"""Acceso a MongoDB de RCOFA. Las funciones reciben la base de datos abierta."""

import re
from datetime import datetime

import pymongo


COLECCIONES = ('ubicaciones', 'categorias_fenomeno', 'observadores', 'avistamientos')


def conectar(usuario='mongoDB', clave='mongo2008', host='127.0.0.1:27017'):
    """Conexión local con el mismo estilo usado en class_06."""
    conex = pymongo.MongoClient(
        host=[host], username=usuario, password=clave,
        authSource='admin', serverSelectionTimeoutMS=5000
    )
    try:
        conex.admin.command('ping')
        return conex
    except pymongo.errors.PyMongoError:
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


def cargar_ubicaciones(db, ubicaciones):
    """Recibe documentos ya normalizados y clasificados por Jefferson."""
    documentos = [dict(documento) for documento in ubicaciones]
    for documento in documentos:
        for campo in ('_id', 'provincia', 'canton', 'distrito', 'poblado'):
            validar_texto(documento[campo], campo)
        if documento['tipo_zona'] not in ('Costera', 'Insular', 'Montañosa', 'Urbana'):
            raise ValueError('tipo_zona no válido')
    if not documentos:
        return []
    return db.ubicaciones.insert_many(documentos).inserted_ids


def insertar_categoria(db, id_categoria, nombre, descripcion):
    documento = {'_id': id_categoria, 'nombre': nombre, 'descripcion': descripcion}
    validar_categoria(documento)
    return db.categorias_fenomeno.insert_one(documento).inserted_id


def cargar_categorias(db, categorias):
    documentos = [dict(documento) for documento in categorias]
    for documento in documentos:
        validar_categoria(documento)
    # El enunciado exige insert_one para este catálogo.
    return [insertar_categoria(db, d['_id'], d['nombre'], d['descripcion'])
            for d in documentos]


def insertar_observador(db, id_observador, alias_o_estacion, rol, indice_confiabilidad):
    documento = {'_id': id_observador, 'alias_o_estacion': alias_o_estacion,
                 'rol': rol, 'indice_confiabilidad': indice_confiabilidad}
    validar_observador(documento)
    documento['indice_confiabilidad'] = float(indice_confiabilidad)
    return db.observadores.insert_one(documento).inserted_id


def cargar_observadores(db, observadores):
    documentos = [dict(documento) for documento in observadores]
    for documento in documentos:
        validar_observador(documento)
        documento['indice_confiabilidad'] = float(documento['indice_confiabilidad'])
    if not documentos:
        return []
    return db.observadores.insert_many(documentos).inserted_ids


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
        return valor
    if isinstance(valor, str):
        return datetime.strptime(valor, '%Y-%m-%d %H:%M:%S')
    raise ValueError('La fecha debe ser datetime o texto YYYY-MM-DD HH:MM:SS')


def cargar_avistamientos(db, avistamientos):
    """Inserta los reportes de Kener, conservando sus campos opcionales."""
    categorias = {d['_id'] for d in db.categorias_fenomeno.find({}, {'_id': 1})}
    observadores = {d['_id'] for d in db.observadores.find({}, {'_id': 1})}
    sectores = {d['_id'] for d in db.ubicaciones.find({}, {'_id': 1})}
    documentos = []
    codigos = set()
    for reporte in avistamientos:
        documento = dict(reporte)
        codigo = documento['_id']
        if not isinstance(codigo, str) or re.fullmatch(r'REP-\d{8}', codigo) is None:
            raise ValueError('_id debe tener el formato REP-00000001')
        if codigo in codigos:
            raise ValueError('Código repetido en el lote: ' + codigo)
        codigos.add(codigo)
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
        documentos.append(documento)
    if not documentos:
        return []
    return db.avistamientos.insert_many(documentos).inserted_ids


def cargar_datos(db, ubicaciones, categorias, observadores, avistamientos):
    """Carga en orden de dependencias; usar con una base inicialmente vacía."""
    preparar_base(db)
    return {
        'ubicaciones': len(cargar_ubicaciones(db, ubicaciones)),
        'categorias_fenomeno': len(cargar_categorias(db, categorias)),
        'observadores': len(cargar_observadores(db, observadores)),
        'avistamientos': len(cargar_avistamientos(db, avistamientos)),
    }


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
CANTONES_COSTEROS = {
    "Puntarenas", "Esparza", "Montes de Oro", "Osa", "Quepos", "Golfito",
    "Parrita", "Corredores", "Garabito", "Liberia", "Nicoya", "Santa Cruz",
    "Bagaces", "Carrillo", "Cañas", "Abangares", "Nandayure", "La Cruz",
    "Hojancha", "Limón", "Pococí", "Siquirres", "Talamanca", "Matina", "Guácimo",
}

CANTONES_MONTANOSOS = {
    "Tarrazú", "Aserrí", "Mora", "Acosta", "Turrubares", "Dota",
    "Pérez Zeledón", "León Cortés", "Puriscal", "San Ramón", "Zarcero",
    "Poás", "Valverde Vega", "Paraíso", "Jiménez", "Turrialba", "Alvarado",
    "Oreamuno", "El Guarco", "Barva", "Santa Bárbara", "San Rafael",
    "San Isidro", "Tilarán", "Buenos Aires", "Coto Brus",
}

POBLADOS_INSULARES = {
    "Isla del Coco", "Isla Chira", "Isla Venado", "Isla Caballo",
    "Isla San Lucas", "Isla Tortuga", "Isla Cedros", "Isla Jesucita",
    "Isla Berrugate",
}


def normalizar_texto(texto):
    letras = unicodedata.normalize("NFKD", texto.casefold())
    limpio = "".join(letra for letra in letras if not unicodedata.combining(letra))
    return " ".join(limpio.split())


COSTEROS = {normalizar_texto(canton) for canton in CANTONES_COSTEROS}
MONTANOSOS = {normalizar_texto(canton) for canton in CANTONES_MONTANOSOS}
INSULARES = {normalizar_texto(poblado) for poblado in POBLADOS_INSULARES}


def clasificar_tipo_zona(provincia, canton, poblado):
    canton = normalizar_texto(canton)

    if normalizar_texto(poblado) in INSULARES:
        return "Insular"
    if canton in COSTEROS:
        return "Costera"
    if canton in MONTANOSOS:
        return "Montañosa"
    return "Urbana"
