import runpy
import unittest
from contextlib import redirect_stdout
from datetime import datetime
from io import StringIO
from unittest.mock import Mock, call, patch

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
    def ejecutar(self, modulo, entradas):
        salida = StringIO()
        with patch('builtins.input', side_effect=entradas), redirect_stdout(salida):
            runpy.run_module(modulo, run_name='__main__')
        return salida.getvalue()

    def test_main_no_conecta_si_no_se_elige_consultas(self):
        with patch.object(subrutinas, 'conectar') as conectar:
            self.ejecutar('main', ['1', '0'])
        conectar.assert_not_called()

    def test_ambos_entrypoints_muestran_el_mismo_submenu_y_cierran_la_conexion(self):
        conexion = Mock()
        conexion.rcofa = mongomock.MongoClient().rcofa
        conexion.rcofa.avistamientos.insert_one({
            'codigo_reporte': 'LARGO', 'duracion_seg': 201, 'ubicacion': {'localidad': 'Chira'},
        })
        with patch.object(subrutinas, 'conectar', return_value=conexion) as conectar:
            directa = self.ejecutar('consultas_fenomenos', ['4', '0'])
            principal = self.ejecutar('main', ['4', '4', '0', '0'])
        self.assertIn('LARGO | 201 s', directa)
        self.assertIn(directa, principal)
        self.assertEqual(principal.count('\nRCOFA\n'), 2)
        self.assertEqual(conectar.call_args_list, [call(), call()])
        self.assertEqual(conexion.close.call_args_list, [call(), call()])

    def test_fallo_de_conexion_avisa_y_main_permite_reintentar(self):
        conexion = Mock()
        with patch.object(subrutinas, 'conectar', side_effect=[ConnectionFailure(), conexion]) as conectar:
            salida = self.ejecutar('main', ['4', '4', '0', '0'])
        self.assertIn('No se pudo conectar', salida)
        self.assertEqual(conectar.call_args_list, [call(), call()])
        conexion.close.assert_called_once_with()

    def test_perdida_de_conexion_en_una_consulta_cierra_y_vuelve_al_menu(self):
        conexion = Mock()
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
                    conexion = Mock()
                    with patch.object(subrutinas, 'conectar', return_value=conexion):
                        salida = self.ejecutar(modulo, prefijo + ['1', interrupcion])
                    self.assertEqual(salida.count('Saliendo.'), 1)
                    conexion.close.assert_called_once_with()

    def test_fallo_inesperado_se_propaga_y_cierra_la_conexion(self):
        conexion = Mock()
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
                    conexion = Mock()
                    error = ValueError('Fallo inesperado de la operación')
                    with patch.object(subrutinas, 'conectar', return_value=conexion), patch.object(
                        subrutinas, operacion, side_effect=error
                    ):
                        with self.assertRaises(RuntimeError) as excepcion:
                            self.ejecutar(modulo, prefijo + entradas + ['0', '0'])
                    self.assertIs(excepcion.exception.__cause__, error)
                    conexion.close.assert_called_once_with()
