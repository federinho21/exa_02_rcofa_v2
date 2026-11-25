import unittest
from contextlib import redirect_stdout
from datetime import datetime
from io import StringIO

from subrutinas import filtrar_duracion_mayor_a, formatear_fecha_es, imprimir_reportes


class TestPresentacion(unittest.TestCase):
    def test_solo_conserva_reportes_de_mas_de_200_segundos(self):
        reportes = [{"duracion_seg": segundos} for segundos in (199, 200, 201)]
        reportes.append({"codigo_reporte": "sin duración"})
        self.assertEqual(filtrar_duracion_mayor_a(reportes), [reportes[2]])
        self.assertEqual(filtrar_duracion_mayor_a([]), [])

    def test_formatea_meses_en_espanol(self):
        self.assertEqual(
            formatear_fecha_es(datetime(2025, 2, 3, 14, 5, 9)),
            "03 de Febrero de 2025 a las 14:05:09",
        )
        self.assertEqual(
            formatear_fecha_es(datetime(2025, 10, 1)),
            "01 de Octubre de 2025 a las 00:00:00",
        )

    def test_muestra_codigo_fecha_duracion_y_localidad(self):
        reporte = {
            "codigo_reporte": "REP-00000001",
            "fecha_evento": datetime(2025, 10, 1),
            "duracion_seg": 201,
            "ubicacion": {"localidad": "Isla Chira"},
        }
        salida = StringIO()
        with redirect_stdout(salida):
            imprimir_reportes([reporte])

        self.assertIn("REP-00000001", salida.getvalue())
        self.assertIn("01 de Octubre de 2025", salida.getvalue())
        self.assertIn("201 s", salida.getvalue())
        self.assertIn("Isla Chira", salida.getvalue())

    def test_muestra_fenomeno_y_observador_de_un_reporte_cruzado(self):
        reporte = {
            "codigo_reporte": "REP-00000002",
            "localidad": "Puntarenas",
            "nombre_fenomeno": "Estela luminosa",
            "alias_observador": "Estación 1",
        }
        salida = StringIO()
        with redirect_stdout(salida):
            imprimir_reportes([reporte])

        self.assertIn("Puntarenas", salida.getvalue())
        self.assertIn("Estela luminosa", salida.getvalue())
        self.assertIn("Estación 1", salida.getvalue())

    def test_avisa_cuando_no_hay_resultados(self):
        salida = StringIO()
        with redirect_stdout(salida):
            imprimir_reportes([])
        self.assertEqual(salida.getvalue().strip(), "Sin resultados.")
