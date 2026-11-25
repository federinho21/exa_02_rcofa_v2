import csv
import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import mongomock

import subrutinas as rcofa


class IntegracionLocalTest(unittest.TestCase):
    def test_csv_conserva_duplicados_y_poblado_vacio_con_ids_estables(self):
        filas = [
            ['001', 'Puntarenas', 'Puntarenas', 'Chira', 'Isla Chira'],
            ['001', 'Puntarenas', 'Puntarenas', 'Chira', 'Otro'],
            ['001', 'Puntarenas', 'Puntarenas', 'Chira', ''],
        ]
        filas.append(filas[0])
        with TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / 'ubicaciones.csv'

            def leer(filas):
                with ruta.open('w', encoding='utf-8-sig', newline='') as archivo:
                    escritor = csv.writer(archivo, delimiter=';')
                    escritor.writerow(['Id', 'Provincia', 'Cantón', 'Distrito', 'Poblado'])
                    escritor.writerows(filas)
                return {d['_id']: d for d in rcofa.leer_ubicaciones(ruta)}

            original = leer(filas)
            self.assertEqual(original, leer(reversed(filas)))
        self.assertEqual(len(original), 4)
        self.assertEqual({d['idubi'] for d in original.values()}, {'001'})
        self.assertEqual(sum(d['poblado'] == '' for d in original.values()), 1)
        self.assertEqual(sum(d['tipo_zona'] == 'Insular' for d in original.values()), 2)

    def test_solo_la_lista_del_enunciado_clasifica_como_insular(self):
        for poblado in ('Isla Bejuco', 'Isla Damas'):
            with self.subTest(poblado=poblado):
                self.assertEqual(rcofa.clasificar_tipo_zona('Puntarenas', 'Quepos', poblado),
                                 'Costera')

    def test_carga_csv_real_y_reportes_sinteticos(self):
        db = mongomock.MongoClient().integracion
        carpeta = Path(__file__).resolve().parents[1] / 'data'
        self.assertEqual(rcofa.cargar_datos_iniciales(db, carpeta), {
            'ubicaciones': 7116, 'categorias_fenomeno': 5,
            'observadores': 10, 'avistamientos': 10000,
        })
        self.assertEqual(db.ubicaciones.count_documents({'poblado': ''}), 2)
        self.assertEqual(db.avistamientos.count_documents({}), 10000)
        reporte = db.avistamientos.find_one({'_id': 'REP-00010000'})
        self.assertEqual(reporte['codigo_reporte'], reporte['_id'])
        self.assertIsInstance(reporte['fecha_evento'], datetime)
        self.assertIsNotNone(db.ubicaciones.find_one(reporte['ubicacion']['id_sector']))

    def test_rechaza_una_base_poblada_aun_sin_las_colecciones_del_proyecto(self):
        db = mongomock.MongoClient().integracion
        db.otra.insert_one({'_id': 1})
        with self.assertRaisesRegex(ValueError, 'ya contiene datos'):
            rcofa.cargar_datos_iniciales(db, Path('ruta_inexistente'))
        self.assertEqual(db.list_collection_names(), ['otra'])
        self.assertEqual(db.otra.find_one(), {'_id': 1})

    def test_valida_los_reportes_antes_de_crear_colecciones(self):
        db = mongomock.MongoClient().integracion
        carpeta = Path(__file__).resolve().parents[1] / 'data'
        reporte = {'_id': 'no es un código REP'}
        with patch.object(rcofa, 'generar_avistamientos', return_value=[reporte]):
            with self.assertRaisesRegex(ValueError, 'REP-00000001'):
                rcofa.cargar_datos_iniciales(db, carpeta)
        self.assertEqual(db.list_collection_names(), [])
