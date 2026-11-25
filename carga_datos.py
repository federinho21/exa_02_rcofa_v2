"""Carga el CSV real, catálogos iniciales y cuatro avistamientos de ejemplo."""

import argparse
from pathlib import Path

from pymongo.errors import PyMongoError

from subrutinas import conectar, cargar_datos_iniciales


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base', default='rcofa', help='Base vacía donde cargar los datos')
    argumentos = parser.parse_args()
    conex = None
    try:
        conex = conectar()
        db = conex[argumentos.base]
        resumen = cargar_datos_iniciales(db, Path(__file__).resolve().parent / 'data')
        print('Base de datos: {0}'.format(db.name))
        for coleccion, cantidad in resumen.items():
            print('{0}: {1} documentos insertados'.format(coleccion, cantidad))
        print('Los 4 avistamientos son ejemplos; falta integrar el generador de 10.000 reportes.')
    except (PyMongoError, ValueError, KeyError, OSError) as error:
        print('No se completó la carga: {0}'.format(error))
        raise SystemExit(1)
    finally:
        if conex is not None:
            conex.close()
