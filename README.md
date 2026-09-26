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


V13.9.131: corrige clasificación iTipTra usando aliases únicos del maestro y la descripción SIFEN final; evita colisión de columna descripcion proveniente de vi.*.


V13.9.135 SIFEN PYG SCALE 0
- Importes monetarios PYG se generan a 0 decimales.
- Base IVA e IVA por item se redondean HALF_UP a guaranies enteros; IVA se deriva como total gravado - base para conservar identidad.
- Otras monedas mantienen 4 decimales.
- Pago contado usa la misma escala monetaria que el DE.

V13.9.138 - Motor SIFEN alineado con MT150/NT13 y Guía DNIT:
- PYG ya no se trunca a escala 0 antes de las fórmulas: hasta 8 decimales.
- dBasGravIVA usa fórmula NT13 y dLiqIVAItem = dBasGravIVA * tasa/100.
- Se omiten campos opcionales de descuento/anticipo cuando valen cero.
- XMLDSig se genera con namespace por defecto, sin prefijo ds:.
- Prevalidación local bloquea prefijo en Signature y opcionales cero antes del envío.

## V13.9.139 — Reestructuración del núcleo SIFEN
- Se separó el cálculo fiscal del controlador Flask en `sifen_core/`.
- `calculator.py` implementa Decimal y la fórmula E735 de NT13.
- `validator.py` bloquea incoherencias antes de firmar/transmitir.
- El XML consume resultados del motor fiscal; ya no recalcula IVA por caminos distintos.
- Se mantienen XSD, firma, QR, transmisión y auditoría existentes mientras se desacoplan progresivamente.
- Esta entrega no declara aprobación SIFEN: la aprobación solo existe cuando SIFEN responde aprobado.


## V13.9.141 - corrección XSD dTasaIVA
- dTasaIVA (E734) se serializa como entero: 0, 5 o 10.
- Se conserva precisión decimal de hasta 8 posiciones para dPropIVA, dBasGravIVA y dLiqIVAItem.
- Corrige el rechazo local XSD tdTasaIVA causado por `5.00000000`.
