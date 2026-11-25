"""Funciones disponibles para el menú de Fede; importar no abre conexiones."""

from subrutinas import (
    conectar,
    consultar_avistamientos,
    consultar_rango_fechas,
    consultar_reporte_completo,
)


if __name__ == '__main__':
    conex = conectar()
    try:
        db = conex.rcofa
        for reporte in consultar_reporte_completo(db):
            print('Reporte: {0} | Fenómeno: {1} | Observador: {2} | Localidad: {3}'.format(
                reporte['codigo_reporte'], reporte.get('nombre_fenomeno', 'Sin categoría'),
                reporte.get('alias_observador', 'Sin observador'), reporte['localidad']))
    finally:
        conex.close()
