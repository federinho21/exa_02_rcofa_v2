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


MESES = (
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
)


def formatear_fecha_es(fecha: datetime) -> str:
    mes = MESES[fecha.month - 1]
    return f"{fecha.day:02d} de {mes} de {fecha.year} a las {fecha:%H:%M:%S}"


def filtrar_duracion_mayor_a(reportes: list[dict]) -> list[dict]:
    return [reporte for reporte in reportes if reporte.get("duracion_seg", 0) > 200]


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


def ejecutar_consultas():
    """Abre la conexión solo al entrar y la cierra al salir del submenú."""
    try:
        try:
            conexion = conectar()
        except pymongo.errors.PyMongoError:
            print('No se pudo conectar a MongoDB para consultar.')
            return

        try:
            menu_consultas(conexion.rcofa, leer=input)
        except pymongo.errors.ConnectionFailure:
            print('Se perdió la conexión a MongoDB durante la consulta.')
        finally:
            conexion.close()
    except ValueError as error:
        # El menú principal recupera ValueError de callbacks como errores de entrada.
        raise RuntimeError('Error inesperado en consultas') from error


# Parte 2: menú sin acceso a la base de datos.
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
            accion(*argumentos)
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
