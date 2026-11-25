"""Preparación de MongoDB. Los datos se cargarán desde los módulos del equipo."""

from subrutinas import conectar, preparar_base, cargar_datos


if __name__ == '__main__':
    conex = conectar()
    try:
        db = conex.rcofa
        preparar_base(db)
        print('Conexión exitosa a MongoDB')
        print('Base de datos: {0}'.format(db.name))
        print('Colecciones: {0}'.format(db.list_collection_names()))
    finally:
        conex.close()
