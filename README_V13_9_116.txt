SANTA CLARA ERP V13.9.116 — XML SIFEN V150 INTEGRADO

Cambios principales:
- rDE conserva el schemaLocation oficial indicado por DNIT: siRecepDE_v150.xsd.
- La prevalidación del elemento rDE usa DE_v150.xsd (Schema XML 18) cuando está disponible en el motor SIFEN.
- Maestro de Clientes alimenta gDatRec: contribuyentes exigen RUC-DV válido; no contribuyentes usan documento de identidad configurado.
- Factura alimenta gCamCond y forma de pago para operaciones al contado.
- venta_items + Maestro de Productos/Servicios alimentan gCamItem, gValorItem, gValorRestaItem y gCamIVA.
- Se bloquea el envío de facturas históricas sin detalle: no se inventan ítems fiscales.
- El envío por lote conserva el mismo schemaLocation del rDE firmado.

No elimina ni reemplaza la base de datos.
