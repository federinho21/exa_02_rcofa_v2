"""Funciones disponibles para el menú de Fede; importar no abre conexiones."""

from subrutinas import (
    conectar,
    consultar_avistamientos,
    consultar_rango_fechas,
    consultar_reporte_completo,
    ejecutar_consultas,
)


if __name__ == '__main__':
    try:
        ejecutar_consultas()
    except (EOFError, KeyboardInterrupt):
        print('\nSaliendo.')
