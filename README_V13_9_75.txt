SANTA CLARA ERP V13.9.75 - CORRECCION IMPORTADOR GASPARINI COMPRAS DETALLADAS

Cambios:
- Corrige CSV: field larger than field limit (131072) elevando el limite de campo de forma segura.
- Reconoce el archivo real "compras detallada.csv" exportado por Gasparini aun cuando NO contiene fila de encabezados.
- Mapeo verificado para este layout: factura, fecha, proveedor, RUC/DV, moneda, producto, codigo, cantidad, costo unitario, importe de linea, clasificacion e IVA identificable.
- Agrupa multiples lineas por factura/proveedor para reconstruir el detalle de la compra.
- Normaliza Gs a PYG.
- Como este archivo de compras detalladas no contiene de forma verificable el estado/forma de pago, no se inventa ese dato: la compra se importa pendiente y puede reconciliarse/actualizarse posteriormente con CxP Gasparini.
- Mantiene compatibilidad con XLS/XLSX/XLSM/CSV/TXT/TSV/XML/HTML y lectores legados existentes.
- No modifica ni reemplaza la base persistente de Render.
