"""Menú de consultas de RCOFA, sin modificaciones en la base."""

from subrutinas import (
    consultar_avistamientos,
    consultar_rango_fechas,
    consultar_reporte_completo,
    ejecutar_cli,
    ejecutar_consultas,
)


if __name__ == '__main__':
    ejecutar_cli(__doc__, ejecutar_consultas)
