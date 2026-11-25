import unittest
from unittest.mock import Mock, call

import subrutinas


class MenuTest(unittest.TestCase):
    def ejecutar(self, entradas, **acciones):
        leer = Mock(side_effect=entradas)
        escribir = Mock()
        subrutinas.menu_principal(acciones, leer=leer, escribir=escribir)
        return '\n'.join(str(c.args[0]) for c in escribir.call_args_list)

    def test_menu_raiz_descarta_opciones_invalidas_y_despacha_hasta_salir(self):
        acciones = Mock()
        salida = self.ejecutar(
            ['xyz', '9', ' 1 ', '4', '0', '1'],
            cargar=acciones.cargar, consultar=acciones.consultar,
        )
        self.assertEqual(salida.count('Opción inválida'), 2)
        self.assertEqual(acciones.mock_calls, [call.cargar(), call.consultar()])

    def test_acciones_no_conectadas_avisan_y_permiten_continuar(self):
        consultar = Mock()
        salida = self.ejecutar(['1', '4', '0'], consultar=consultar)
        self.assertIn('Acción no conectada: cargar.', salida)
        consultar.assert_called_once_with()

    def test_accion_no_conectada_en_submenu_avisa_y_permite_continuar(self):
        listar = Mock(return_value=[])
        salida = self.ejecutar(
            ['2', '3', '1', '0', '0'], listar_categorias=listar,
        )
        self.assertIn('Acción no conectada: modificar_categoria.', salida)
        listar.assert_called_once_with()

    def test_carga_y_consulta_muestran_value_error_y_permiten_reintentar(self):
        for opcion, clave in (('1', 'cargar'), ('4', 'consultar')):
            with self.subTest(accion=clave):
                accion = Mock(side_effect=[ValueError(f'Error al {clave}'), None])
                salida = self.ejecutar([opcion, opcion, '0'], **{clave: accion})
                self.assertIn(f'Error al {clave}', salida)
                self.assertEqual(accion.call_args_list, [call(), call()])

    def test_carga_no_oculta_otras_excepciones(self):
        cargar = Mock(side_effect=RuntimeError('Fallo inesperado'))
        with self.assertRaisesRegex(RuntimeError, 'Fallo inesperado'):
            self.ejecutar(['1', '0'], cargar=cargar)

    def test_listar_crear_y_modificar_ambos_catalogos(self):
        acciones = Mock()
        acciones.listar_categorias.return_value = [{'_id': 1, 'nombre': 'Luz'}]
        acciones.listar_observadores.return_value = []
        salida = self.ejecutar(
            ['2', '?', '1', '2', '1', ' Luz ', 'Descripción',
             '3', '1', 'Brillo', 'Otra descripción', '0',
             '3', '1', '2', '7', 'Estación', 'Piloto', '0',
             '3', '7', 'Nueva estación', 'Operador', '1', '0', '0'],
            listar_categorias=acciones.listar_categorias,
            insertar_categoria=acciones.insertar_categoria,
            modificar_categoria=acciones.modificar_categoria,
            listar_observadores=acciones.listar_observadores,
            insertar_observador=acciones.insertar_observador,
            modificar_observador=acciones.modificar_observador,
        )
        self.assertEqual(acciones.mock_calls, [
            call.listar_categorias(), call.insertar_categoria(1, 'Luz', 'Descripción'),
            call.modificar_categoria(1, 'Brillo', 'Otra descripción'),
            call.listar_observadores(), call.insertar_observador(7, 'Estación', 'Piloto', 0.0),
            call.modificar_observador(7, 'Nueva estación', 'Operador', 1.0),
        ])
        self.assertIn('Luz', salida)
        self.assertIn('Opción inválida', salida)

    def test_datos_invalidos_permiten_reintentar_o_volver_sin_ejecutar(self):
        insertar = Mock()
        modificar = Mock()
        salida = self.ejecutar(
            ['2', '2', '1.2', '2', '1', ' ', '2', '1', 'Luz', 'Descripción',
             '3', '1', 'Brillo', '', '0', '0'],
            insertar_categoria=insertar, modificar_categoria=modificar,
        )
        self.assertIn('ID debe ser un entero', salida)
        self.assertIn('nombre debe ser un texto no vacío', salida)
        self.assertIn('descripcion debe ser un texto no vacío', salida)
        insertar.assert_called_once_with(1, 'Luz', 'Descripción')
        modificar.assert_not_called()

    def test_confiabilidad_invalida_no_modifica_observador(self):
        for valor in ('NaN', 'inf', '-0.1', '1.1', 'texto'):
            with self.subTest(valor=valor):
                modificar = Mock()
                salida = self.ejecutar(
                    ['3', '3', '7', 'Estación', 'Piloto', valor, '0', '0'],
                    modificar_observador=modificar,
                )
                self.assertIn('Confiabilidad debe ser un número entre 0 y 1', salida)
                modificar.assert_not_called()

    def test_borrar_requiere_id_valido_y_confirmacion_explicita(self):
        acciones = Mock()
        salida = self.ejecutar(
            ['2', '4', 'x', '4', '10', '', '4', '11', 'no', '4', '12', ' Sí ', '0',
             '3', '4', '13', 'si', '0', '0'],
            borrar_categoria=acciones.borrar_categoria,
            borrar_observador=acciones.borrar_observador,
        )
        self.assertEqual(acciones.mock_calls, [call.borrar_categoria(12), call.borrar_observador(13)])
        self.assertEqual(salida.count('Borrado cancelado'), 2)

    def test_eof_y_ctrl_c_salen_sin_borrar_si_interrumpen_la_confirmacion(self):
        for interrupcion in (EOFError, KeyboardInterrupt):
            with self.subTest(interrupcion=interrupcion):
                borrar = Mock()
                self.ejecutar(['2', '4', '7', interrupcion], borrar_categoria=borrar)
                borrar.assert_not_called()
