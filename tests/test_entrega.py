import re
import unittest
from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory

import mongomock

from subrutinas import (
    cargar_datos_iniciales,
    consultar_reporte_completo,
    filtrar_duracion_mayor_a,
)


class EntregaRcofaTest(unittest.TestCase):
    def test_carga_inicial_integra_y_rechaza_repeticion_sin_modificar_datos(self):
        db = mongomock.MongoClient().rcofa
        with TemporaryDirectory() as carpeta:
            (Path(carpeta) / "ubicaciones.csv").write_text(
                "Id;Provincia;Cantón;Distrito;Poblado\n"
                "010101;San José;Central;Carmen;Barrio Norte\n"
                "010101;San José;Central;Carmen;Barrio Sur\n"
                "010102;San José;Central;Merced;\n",
                encoding="utf-8",
            )
            conteos = cargar_datos_iniciales(db, carpeta)

            colecciones = ("ubicaciones", "categorias_fenomeno", "observadores", "avistamientos")
            originales = {
                nombre: {doc["_id"]: doc for doc in db[nombre].find()}
                for nombre in colecciones
            }
            self.assertEqual(conteos, {nombre: len(docs) for nombre, docs in originales.items()})
            self.assertEqual(conteos["avistamientos"], 10_000)

            ubicaciones = originales["ubicaciones"]
            self.assertEqual(len(ubicaciones), 3)
            self.assertEqual(
                {doc["poblado"] for doc in ubicaciones.values() if doc["distrito"] == "Carmen"},
                {"Barrio Norte", "Barrio Sur"},
            )
            self.assertEqual(sum(doc["distrito"] == "Merced" for doc in ubicaciones.values()), 1)

            formato_id = re.compile(r"REP-[0-9]{8}")
            campos_presentes = set()
            campos_comunes = None
            for codigo, avistamiento in originales["avistamientos"].items():
                self.assertIsNotNone(formato_id.fullmatch(codigo), codigo)
                self.assertIsInstance(avistamiento["fecha_evento"], datetime, codigo)
                ubicacion = avistamiento["ubicacion"]
                self.assertIn(ubicacion["id_sector"], ubicaciones, codigo)
                self.assertIn(avistamiento["id_categoria"], originales["categorias_fenomeno"], codigo)
                self.assertIn(avistamiento["id_observador"], originales["observadores"], codigo)
                presentes = {campo for campo, valor in avistamiento.items() if valor is not None}
                campos_presentes.update(presentes)
                campos_comunes = presentes if campos_comunes is None else campos_comunes & presentes
            self.assertTrue(campos_presentes - campos_comunes, "Ningún campo opcional varía")

            with self.assertRaises(ValueError):
                cargar_datos_iniciales(db, carpeta)

            self.assertEqual(
                {nombre: db[nombre].count_documents({}) for nombre in colecciones}, conteos
            )
            for nombre, docs in originales.items():
                actuales = {doc["_id"]: doc for doc in db[nombre].find()}
                self.assertTrue(actuales == docs, f"La segunda carga modificó {nombre}")

    def test_reporte_completo_resuelve_catalogos_y_filtra_estrictamente_mayor_a_200(self):
        db = mongomock.MongoClient().rcofa
        db.categorias_fenomeno.insert_many([
            {"_id": 1, "nombre": "Destello", "descripcion": "Luz breve"},
            {"_id": 2, "nombre": "Halo", "descripcion": "Círculo luminoso"},
        ])
        db.observadores.insert_many([
            {"_id": 11, "alias_o_estacion": "Estación Norte", "rol": "Estación", "indice_confiabilidad": 0.9},
            {"_id": 12, "alias_o_estacion": "Estación Sur", "rol": "Estación", "indice_confiabilidad": 0.8},
        ])
        fecha = datetime(2025, 1, 15, 12)
        casos = [
            ("REP-00000001", 199, 1, 12, "Carmen", "Destello", "Estación Sur"),
            ("REP-00000002", 200, 2, 11, "Merced", "Halo", "Estación Norte"),
            ("REP-00000003", 201, 1, 11, "Hospital", "Destello", "Estación Norte"),
        ]
        db.avistamientos.insert_many([
            {
                "_id": codigo,
                "codigo_reporte": codigo,
                "fecha_evento": fecha,
                "duracion_seg": duracion,
                "id_categoria": categoria,
                "id_observador": observador,
                "ubicacion": {"localidad": localidad},
            }
            for codigo, duracion, categoria, observador, localidad, _, _ in casos
        ])

        reporte = list(consultar_reporte_completo(db))
        self.assertCountEqual(
            [
                (fila["codigo_reporte"], fila["duracion_seg"], fila["localidad"],
                 fila["nombre_fenomeno"], fila["alias_observador"])
                for fila in reporte
            ],
            [
                (codigo, duracion, localidad, nombre, alias)
                for codigo, duracion, _, _, localidad, nombre, alias in casos
            ],
        )
        filtrado = list(filtrar_duracion_mayor_a(reporte, 200))
        self.assertEqual(filtrado, [fila for fila in reporte if fila["codigo_reporte"] == "REP-00000003"])
