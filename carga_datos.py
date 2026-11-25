"""Carga inicial de RCOFA en una base vacía."""

from subrutinas import ejecutar_carga, ejecutar_cli


if __name__ == '__main__':
    ejecutar_cli(__doc__, ejecutar_carga)
