Santa Clara ERP V13.9.92
- SIFEN: corrige la selección del XSD V150. La raíz rDE ya no se valida contra DE_v150.xsd; el validador selecciona únicamente un esquema que declare globalmente la raíz real del XML.
- Panel de Salas/Internación: disponibilidad/ocupación en tiempo real, traslado de cama conservando la misma admisión y toda su cuenta, historial de traslados.
- La liberación de cama al alta/cierre de cuenta se conserva y el panel calcula ocupación desde admisiones abiertas.
- Protección contra dos admisiones abiertas en la misma cama mediante índice único cuando la base no contiene inconsistencias previas.
- Catálogo geográfico SIFEN: importación XLSX/CSV de departamento, distrito, ciudad y barrio, con actualización sin duplicados.
- Clientes/Terceros: campos adicionales de barrio SIFEN.
- Migraciones aditivas; no elimina ni reemplaza la base persistente.
