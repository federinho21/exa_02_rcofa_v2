if __name__ == '__main__':
    from subrutinas import ejecutar_consultas, menu_principal

    menu_principal({'consultar': ejecutar_consultas}, leer=input)
