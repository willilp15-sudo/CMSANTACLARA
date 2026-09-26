Santa Clara ERP V13.9.107
- Emisión de Factura Electrónica unificada y automática.
- Al registrar la venta: CDC -> XML V150 -> firma -> QR -> XSD -> envío SIFEN si PRODUCCIÓN está habilitada -> KuDE PDF.
- En TEST ejecuta automáticamente hasta XSD/QR sin transmisión fiscal.
- Eliminados de la factura los botones manuales Generar CDC/QR y Enviar a SIFEN.
- Tras emitir la venta se abre directamente el PDF/KuDE para impresión.
- Puntos de expedición: botón Eliminar. Si no tiene documentos, se borra; si tiene historial fiscal, se desactiva de forma segura.
