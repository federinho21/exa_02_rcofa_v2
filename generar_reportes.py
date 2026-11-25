
from conexion_mongo import ConexionMongo
from config import (
    COLECCION_AVISTAMIENTOS,
    COLECCION_UBICACIONES,
    COLECCION_CATEGORIAS,
    COLECCION_OBSERVADORES,
)
from subrutinas import generar_y_cargar_avistamientos

CANTIDAD = 100000

with ConexionMongo() as conexion:

    reportes = conexion.obtener_coleccion(COLECCION_AVISTAMIENTOS)
    ubicaciones = conexion.obtener_coleccion(COLECCION_UBICACIONES)
    categorias = conexion.obtener_coleccion(COLECCION_CATEGORIAS)
    observadores = conexion.obtener_coleccion(COLECCION_OBSERVADORES)

    total = generar_y_cargar_avistamientos(
        col_avistamientos=reportes,
        col_ubicaciones=ubicaciones,
        col_categorias=categorias,
        col_observadores=observadores,
        cantidad=CANTIDAD,
        limpiar=True,
        lote=10000,
        semilla=None
    )

    codigos_unicos = reportes.distinct("codigo_reporte")

    print("\n========== RESULTADOS ==========")
    print(f"Reportes insertados: {total}")
    print(f"Códigos únicos: {len(codigos_unicos)}")

    print("\n========== COMPROBACIÓN ==========")

    for campo in [
        "telemetria_entorno",
        "datos_radar",
        "testimonio_visual",
        "sensores_ambientales",
        "alteracion_flora_fauna",
        "evidencia"
    ]:
        cantidad = reportes.count_documents({
            campo: {"$exists": True}
        })
        print(f"{campo}: {cantidad}")

    assert total == 100000
    assert len(codigos_unicos) == 100000

    print("\n¡GENERACIÓN E INSERCIÓN COMPLETADAS!")
