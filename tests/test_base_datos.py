import unittest
from datetime import datetime
from pathlib import Path

import mongomock
from pymongo.errors import DuplicateKeyError

from subrutinas import (
    preparar_base, cargar_datos, cargar_avistamientos, insertar_categoria,
    modificar_categoria, borrar_categoria, listar_categorias,
    insertar_observador, modificar_observador, borrar_observador,
    listar_observadores, consultar_avistamientos, consultar_rango_fechas,
    consultar_reporte_completo,
    clasificar_tipo_zona, leer_datos_iniciales, cargar_datos_iniciales,
)


class PruebasBaseDatos(unittest.TestCase):
    def setUp(self):
        self.conex = mongomock.MongoClient()
        self.db = self.conex.rcofa_pruebas
        self.ubicacion = {'_id': '001', 'provincia': 'Puntarenas',
                          'canton': 'Puntarenas', 'distrito': 'Chira',
                          'poblado': 'Isla Chira', 'tipo_zona': 'Insular'}
        self.categoria = {'_id': 1, 'nombre': 'Eco radar', 'descripcion': 'Eco no identificado'}
        self.observador = {'_id': 1, 'alias_o_estacion': 'Estación 1',
                           'rol': 'Operador radar', 'indice_confiabilidad': 0.9}
        cargar_datos(self.db, [self.ubicacion], [self.categoria], [self.observador], [])

    def tearDown(self):
        self.conex.close()

    def reporte(self, numero, fecha, duracion=200):
        return {'_id': 'REP-{0:08d}'.format(numero), 'fecha_evento': fecha,
                'duracion_seg': duracion, 'id_categoria': 1, 'id_observador': 1,
                'ubicacion': {'id_sector': '001', 'provincia': 'Puntarenas',
                              'canton': 'Puntarenas', 'distrito': 'Chira',
                              'localidad': 'Isla Chira'}}

    def test_preparacion_repetible(self):
        preparar_base(self.db)
        preparar_base(self.db)
        self.assertEqual(len(self.db.list_collection_names()), 4)
        self.assertEqual(self.db.ubicaciones.count_documents({}), 1)

    def test_csv_real_y_carga_inicial(self):
        carpeta = Path(__file__).resolve().parents[1] / 'data'
        ubicaciones, categorias, observadores, reportes = leer_datos_iniciales(carpeta)
        self.assertEqual(len(ubicaciones), 7116)
        self.assertEqual(len({u['_id'] for u in ubicaciones}), 7116)
        self.assertTrue(all(u['poblado'] for u in ubicaciones))
        self.assertEqual(ubicaciones[0]['idubi'], ubicaciones[1]['idubi'])
        self.assertEqual((len(categorias), len(observadores), len(reportes)), (4, 3, 4))
        db = self.conex.carga_inicial
        resumen = cargar_datos_iniciales(db, carpeta)
        self.assertEqual(resumen['ubicaciones'], 7116)
        self.assertEqual(resumen['avistamientos'], 4)
        with self.assertRaises(ValueError):
            cargar_datos_iniciales(db, carpeta)
        self.assertEqual(db.avistamientos.count_documents({}), 4)

    def test_prioridad_insular_y_zonas(self):
        self.assertEqual(clasificar_tipo_zona('Puntarenas', 'Puntarenas', 'Isla Chira'), 'Insular')
        self.assertEqual(clasificar_tipo_zona('Puntarenas', 'Osa', 'Otro'), 'Costera')
        self.assertEqual(clasificar_tipo_zona('San José', 'Dota', 'Otro'), 'Montañosa')
        self.assertEqual(clasificar_tipo_zona('San José', 'San José', 'Amón'), 'Urbana')

    def test_crud_catalogos(self):
        self.assertEqual(insertar_categoria(self.db, 2, 'Luz', 'Luz inmóvil'), 2)
        self.assertEqual(modificar_categoria(self.db, 2, 'Estela', 'Luz en movimiento').modified_count, 1)
        self.assertEqual(listar_categorias(self.db)[1]['nombre'], 'Estela')
        self.assertEqual(borrar_categoria(self.db, 2).deleted_count, 1)
        self.assertEqual(borrar_categoria(self.db, 2).deleted_count, 0)
        self.assertEqual(insertar_observador(self.db, 2, 'Ana', 'Testigo', 0.5), 2)
        self.assertEqual(modificar_observador(self.db, 2, 'Ana', 'Testigo', 0.8).modified_count, 1)
        self.assertEqual(listar_observadores(self.db)[1]['indice_confiabilidad'], 0.8)
        self.assertEqual(borrar_observador(self.db, 2).deleted_count, 1)
        self.assertEqual(modificar_categoria(self.db, 99, 'Luz', 'Luz inmóvil').matched_count, 0)

    def test_referencias_y_borrados(self):
        reporte = self.reporte(1, '2026-10-01 12:00:00')
        reporte['id_categoria'] = 99
        with self.assertRaises(ValueError):
            cargar_avistamientos(self.db, [reporte])
        self.assertEqual(self.db.avistamientos.count_documents({}), 0)
        reporte['id_categoria'] = 1
        cargar_avistamientos(self.db, [reporte])
        with self.assertRaises(ValueError):
            borrar_categoria(self.db, 1)
        with self.assertRaises(ValueError):
            borrar_observador(self.db, 1)

    def test_rango_inclusivo_sin_limite(self):
        reportes = [self.reporte(i, '2026-10-01 12:00:00') for i in range(1, 151)]
        reportes += [self.reporte(151, '2026-10-01 13:00:00'),
                     self.reporte(152, '2026-10-01 13:00:01')]
        cargar_avistamientos(self.db, reportes)
        resultado = consultar_rango_fechas(
            self.db, datetime(2026, 10, 1, 12), datetime(2026, 10, 1, 13))
        self.assertEqual(len(resultado), 151)
        with self.assertRaises(ValueError):
            consultar_rango_fechas(self.db, '2026-10-02 00:00:00', '2026-10-01 00:00:00')

    def test_filtro_proyeccion_orden_y_lookup(self):
        reportes = [self.reporte(1, '2026-10-01 12:00:00', 200),
                    self.reporte(2, '2026-10-01 13:00:00', 201),
                    self.reporte(3, '2026-10-01 11:00:00', 201)]
        reportes[0]['testimonio'] = 'Luz visible'
        cargar_avistamientos(self.db, reportes)
        resultado = consultar_avistamientos(self.db, provincia='Puntarenas', id_categoria=1)
        self.assertEqual([r['codigo_reporte'] for r in resultado],
                         ['REP-00000003', 'REP-00000002', 'REP-00000001'])
        self.assertEqual(set(resultado[0]), {'codigo_reporte', 'fecha_evento', 'duracion_seg', 'ubicacion'})
        self.assertEqual(resultado[0]['ubicacion'], {'localidad': 'Isla Chira'})
        self.assertEqual(consultar_avistamientos(self.db, provincia='San José'), [])
        completo = consultar_reporte_completo(self.db)
        self.assertEqual(completo[0]['nombre_fenomeno'], 'Eco radar')
        self.assertEqual(completo[0]['alias_observador'], 'Estación 1')
        self.assertEqual(completo[0]['duracion_seg'], 200)
        guardado = self.db.avistamientos.find_one({'_id': reportes[0]['_id']})
        self.assertEqual(guardado['testimonio'], 'Luz visible')
        self.assertIsInstance(guardado['fecha_evento'], datetime)
        self.assertNotIn('codigo_reporte', reportes[0])

    def test_duplicados_y_validacion(self):
        reporte = self.reporte(1, '2026-10-01 12:00:00')
        with self.assertRaises(ValueError):
            cargar_avistamientos(self.db, [reporte, reporte])
        self.assertEqual(self.db.avistamientos.count_documents({}), 0)
        cargar_avistamientos(self.db, [reporte])
        with self.assertRaises(DuplicateKeyError):
            insertar_categoria(self.db, 1, 'Otra', 'Otra categoría')
        with self.assertRaises(ValueError):
            insertar_observador(self.db, 2, 'Ana', 'Testigo', 1.5)
        with self.assertRaises(ValueError):
            insertar_categoria(self.db, '2', 'Luz', 'Luz inmóvil')


if __name__ == '__main__':
    unittest.main()
