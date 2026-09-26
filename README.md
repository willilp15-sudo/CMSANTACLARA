# Santa Clara ERP V13.9.92
Actualización acumulativa sobre V13.9.91.

Incluye corrección de validación XSD por elemento raíz, Panel de Salas/Internación con traslado de cama manteniendo la cuenta de la misma admisión, e importador de códigos geográficos SIFEN (XLSX/CSV).

La base SQLite persistente no se incluye en este paquete y las migraciones son aditivas.

## V13.9.98 — Autoprueba SIFEN autocontenida
- Corrige el diagnóstico que tomaba la última factura aunque no tuviera ítems.
- La autoprueba crea temporalmente, dentro de un SAVEPOINT, receptor B2C, producto/servicio, factura e ítem SIFEN completos.
- El SAVEPOINT se revierte siempre: no deja datos TEST ni consume correlativos.
- La prueba genera gCamItem, dCodInt, dDesProSer, unidad, cantidad, gValorItem, gValorRestaItem y gCamIVA antes de firmar/validar.
- La factura TEST se firma con el certificado instalado y luego se valida contra XSD V150.

V13.9.110: cajas autorizadas por usuario y control total ADMIN.


V13.9.124: dFecFirma corregida para America/Asuncion en Render; margen técnico de 5 segundos antes de transmisión para evitar SIFEN 1004.
