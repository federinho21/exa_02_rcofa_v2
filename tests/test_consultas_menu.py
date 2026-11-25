import runpy
import unittest
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
from io import StringIO
from unittest.mock import MagicMock, Mock, call, patch

import mongomock
from pymongo.errors import ConnectionFailure

import subrutinas


class ConsultasMenuTest(unittest.TestCase):
    def ejecutar(self, db, entradas):
        salida = StringIO()
        with redirect_stdout(salida):
            subrutinas.menu_consultas(db, leer=Mock(side_effect=entradas))
        return salida.getvalue()

    def test_valida_opciones_texto_e_id_y_envia_los_tres_filtros(self):
        db = object()
        entradas = ['?', '1', '?', '1', '1', ' ', '1', '3', '1.5',
                    '1', '1', ' San José ', '1', '2', ' Escazú ',
                    '1', '3', ' 7 ', '0']
        with patch.object(subrutinas, 'consultar_avistamientos', return_value=[]) as consultar:
            salida = self.ejecutar(db, entradas)
        self.assertEqual(consultar.call_args_list, [
            call(db, provincia='San José'), call(db, canton='Escazú'), call(db, id_categoria=7),
        ])
        self.assertEqual(salida.count('Opción inválida.'), 2)
        self.assertIn('texto no vacío', salida)
        self.assertIn('ID debe ser un entero', salida)
        self.assertEqual(salida.count('Sin resultados.'), 3)

    def test_id_categoria_rechaza_desbordamientos_y_acepta_ambos_limites_bson(self):
        db = object()
        minimo, maximo = -(2**63), 2**63 - 1
        entradas = ['1', '3', str(minimo - 1), '1', '3', str(maximo + 1),
                    '1', '3', str(minimo), '1', '3', str(maximo), '0']
        with patch.object(subrutinas, 'consultar_avistamientos', return_value=[]) as consultar:
            salida = self.ejecutar(db, entradas)
        self.assertEqual(consultar.call_args_list, [
            call(db, id_categoria=minimo), call(db, id_categoria=maximo),
        ])
        self.assertEqual(salida.count('fuera del rango'), 2)

    def test_id_de_catalogo_tambien_rechaza_desbordamiento_y_permite_reintentar(self):
        crear = Mock()
        leer = Mock(side_effect=['2', '2', str(2**63), '2', '7', 'Luz', 'Descripción', '0', '0'])
        escribir = Mock()
        subrutinas.menu_principal({'insertar_categoria': crear}, leer=leer, escribir=escribir)
        crear.assert_called_once_with(7, 'Luz', 'Descripción')
        self.assertIn('fuera del rango', '\n'.join(c.args[0] for c in escribir.call_args_list))

    def test_rango_inclusivo_sin_truncar_y_con_fechas_en_espanol(self):
        db = mongomock.MongoClient().rcofa
        db.avistamientos.insert_many([
            {'codigo_reporte': f'REP-{i:08d}', 'fecha_evento': datetime(2026, 10, 1, 12)}
            for i in range(1, 151)
        ] + [
            {'codigo_reporte': 'LIMITE-FINAL', 'fecha_evento': datetime(2026, 10, 1, 13)},
            {'codigo_reporte': 'FUERA-ANTES', 'fecha_evento': datetime(2026, 10, 1, 11, 59, 59)},
            {'codigo_reporte': 'FUERA-DESPUES', 'fecha_evento': datetime(2026, 10, 1, 13, 0, 1)},
        ])
        inicio, fin = '2026-10-01 12:00:00', '2026-10-01 13:00:00'
        salida = self.ejecutar(db, ['2', fin, inicio, '2', 'fecha inválida', fin,
                                    '2', inicio, fin, '0'])
        self.assertIn('La fecha inicial no puede ser posterior a la final', salida)
        self.assertEqual(salida.count('01 de Octubre de 2026 a las 12:00:00'), 150)
        self.assertIn('LIMITE-FINAL | 01 de Octubre de 2026 a las 13:00:00', salida)
        self.assertNotIn('FUERA-', salida)

    def test_reporte_cruzado_y_filtro_estricto_sobre_todos_los_resultados(self):
        db = object()
        reportes = [{'codigo_reporte': f'REP-{i:08d}', 'duracion_seg': 200}
                    for i in range(150)]
        reportes.append({'codigo_reporte': 'LARGO', 'duracion_seg': 201,
                         'nombre_fenomeno': 'Estela', 'alias_observador': 'Estación 1'})
        with patch.object(subrutinas, 'consultar_reporte_completo', return_value=reportes) as consultar:
            salida = self.ejecutar(db, ['3', '4', '0'])
        self.assertEqual(consultar.call_args_list, [call(db), call(db)])
        self.assertEqual(salida.count('REP-00000000 | 200 s'), 1)
        self.assertEqual(salida.count('LARGO | 201 s | Fenómeno: Estela | Observador: Estación 1'), 2)
        self.assertIn('sobre todo el reporte cruzado', salida)

    def test_reporte_vacio_y_filtro_sin_coincidencias(self):
        with patch.object(subrutinas, 'consultar_reporte_completo', side_effect=[
            [], [{'codigo_reporte': 'EXACTO', 'duracion_seg': 200}],
        ]):
            salida = self.ejecutar(object(), ['3', '4', '0'])
        self.assertEqual(salida.count('Sin resultados.'), 2)
        self.assertNotIn('EXACTO', salida)


class ConsultasEntrypointsTest(unittest.TestCase):
    def ejecutar(self, modulo, entradas, argumentos=()):
        salida = StringIO()
        with patch('sys.argv', [modulo, *argumentos]), patch(
            'builtins.input', side_effect=entradas
        ), redirect_stdout(salida):
            runpy.run_module(modulo, run_name='__main__')
        return salida.getvalue()

    def test_main_no_conecta_al_navegar_sin_operar(self):
        with patch.object(subrutinas, 'conectar') as conectar:
            self.ejecutar('main', ['2', '0', '3', '0', '0'])
        conectar.assert_not_called()

    def test_main_usa_base_elegida_y_comparte_conexion_para_crud_y_consultas(self):
        cliente = mongomock.MongoClient()
        with patch.dict('os.environ', {'MONGO_DB_NAME': 'base_del_entorno'}), patch.object(
            subrutinas, 'conectar', return_value=cliente
        ) as conectar, patch.object(cliente, 'close', wraps=cliente.close) as cerrar:
            salida = self.ejecutar('main', [
                '2', '2', '17', 'Luz', 'Descripción', '2', '17', 'Otra', 'Descripción',
                '1', '0', '4', '3', '0', '0',
            ], ['--base', 'aislada'])
        self.assertIn('Ya existe', salida)
        self.assertIn('Luz', salida)
        self.assertEqual(cliente.aislada.categorias_fenomeno.find_one(17)['nombre'], 'Luz')
        self.assertEqual(cliente.list_database_names(), ['aislada'])
        conectar.assert_called_once_with()
        cerrar.assert_called_once_with()

    def test_carga_y_consulta_comparten_base_del_entorno(self):
        cliente = mongomock.MongoClient()

        def cargar(db, carpeta):
            db.avistamientos.insert_one({'codigo_reporte': 'CARGADO', 'duracion_seg': 201})
            return {'avistamientos': 1}

        with patch.dict('os.environ', {'MONGO_DB_NAME': 'base_del_entorno'}), patch.object(
            subrutinas, 'conectar', return_value=cliente
        ), patch.object(subrutinas, 'cargar_datos_iniciales', side_effect=cargar):
            carga = self.ejecutar('carga_datos', [])
            consulta = self.ejecutar('consultas_fenomenos', ['3', '0'])
        self.assertIn('Base de datos: base_del_entorno', carga)
        self.assertIn('CARGADO | 201 s', consulta)

    def test_ctrl_c_en_carga_directa_avisa_carga_parcial_sale_130_y_cierra(self):
        cliente = mongomock.MongoClient()
        errores = StringIO()

        def interrumpir(db, carpeta):
            db.ubicaciones.insert_one({'_id': 'sector'})
            raise KeyboardInterrupt

        with patch.object(subrutinas, 'conectar', return_value=cliente), patch.object(
            cliente, 'close', wraps=cliente.close
        ) as cerrar, patch.object(
            subrutinas, 'cargar_datos_iniciales', side_effect=interrumpir
        ), redirect_stderr(errores):
            with self.assertRaises(SystemExit) as salida:
                self.ejecutar('carga_datos', [], ['--base', 'interrumpida'])
        self.assertEqual(salida.exception.code, 130)
        self.assertIn('carga parcial', errores.getvalue())
        self.assertEqual(cliente.interrumpida.ubicaciones.count_documents({}), 1)
        cerrar.assert_called_once_with()

    def test_ambos_entrypoints_muestran_el_mismo_submenu_y_cierran_la_conexion(self):
        db = mongomock.MongoClient().rcofa
        db.avistamientos.insert_one({
            'codigo_reporte': 'LARGO', 'duracion_seg': 201, 'ubicacion': {'localidad': 'Chira'},
        })
        conexion = MagicMock(**{'__getitem__.return_value': db})
        with patch.object(subrutinas, 'conectar', return_value=conexion) as conectar:
            directa = self.ejecutar('consultas_fenomenos', ['4', '0'])
            principal = self.ejecutar('main', ['4', '4', '0', '0'])
        self.assertIn('LARGO | 201 s', directa)
        self.assertIn(directa, principal)
        self.assertEqual(principal.count('\nRCOFA\n'), 2)
        self.assertEqual(conectar.call_args_list, [call(), call()])
        self.assertEqual(conexion.close.call_args_list, [call(), call()])

    def test_fallo_de_conexion_avisa_y_main_permite_reintentar(self):
        conexion = MagicMock()
        with patch.object(subrutinas, 'conectar', side_effect=[ConnectionFailure(), conexion]) as conectar:
            salida = self.ejecutar('main', ['4', '4', '0', '0'])
        self.assertIn('No se pudo conectar', salida)
        self.assertEqual(conectar.call_args_list, [call(), call()])
        conexion.close.assert_called_once_with()

    def test_perdida_de_conexion_en_una_consulta_cierra_y_vuelve_al_menu(self):
        conexion = MagicMock()
        with patch.object(subrutinas, 'conectar', return_value=conexion), patch.object(
            subrutinas, 'consultar_reporte_completo', side_effect=ConnectionFailure()
        ):
            salida = self.ejecutar('main', ['4', '3', '0'])
        self.assertIn('Se perdió la conexión', salida)
        self.assertEqual(salida.count('\nRCOFA\n'), 2)
        conexion.close.assert_called_once_with()

    def test_eof_y_ctrl_c_salen_en_ambos_entrypoints_y_cierran(self):
        for modulo, prefijo in [('main', ['4']), ('consultas_fenomenos', [])]:
            for interrupcion in (EOFError, KeyboardInterrupt):
                with self.subTest(modulo=modulo, interrupcion=interrupcion):
                    conexion = MagicMock()
                    with patch.object(subrutinas, 'conectar', return_value=conexion):
                        salida = self.ejecutar(modulo, prefijo + ['1', interrupcion])
                    self.assertEqual(salida.count('Saliendo.'), 1)
                    conexion.close.assert_called_once_with()

    def test_fallo_inesperado_se_propaga_y_cierra_la_conexion(self):
        conexion = MagicMock()
        with patch.object(subrutinas, 'conectar', return_value=conexion), patch.object(
            subrutinas, 'consultar_reporte_completo', side_effect=RuntimeError('Fallo inesperado')
        ):
            with self.assertRaisesRegex(RuntimeError, 'Fallo inesperado'):
                self.ejecutar('main', ['4', '3'])
        conexion.close.assert_called_once_with()

    def test_value_error_de_operacion_se_propaga_con_causa_y_cierra_en_ambas_entradas(self):
        for modulo, prefijo in [('main', ['4']), ('consultas_fenomenos', [])]:
            for operacion, entradas in [
                ('consultar_reporte_completo', ['3']),
                ('consultar_rango_fechas', ['2', '2026-10-01 12:00:00', '2026-10-01 13:00:00']),
            ]:
                with self.subTest(modulo=modulo, operacion=operacion):
                    conexion = MagicMock()
                    error = ValueError('Fallo inesperado de la operación')
                    with patch.object(subrutinas, 'conectar', return_value=conexion), patch.object(
                        subrutinas, operacion, side_effect=error
                    ):
                        with self.assertRaises(RuntimeError) as excepcion:
                            self.ejecutar(modulo, prefijo + entradas + ['0', '0'])
                    self.assertIs(excepcion.exception.__cause__, error)
                    conexion.close.assert_called_once_with()
