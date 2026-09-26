Santa Clara ERP V13.9.114 - SIFEN por lote asíncrono

- Cambia Factura Electrónica de recepción síncrona a WS Recepción de Lote SIFEN V150.
- Construye rLoteDE, comprime ZIP y transmite xDE en Base64.
- Guarda dProtConsLote cuando SIFEN responde 0300 (lote recibido).
- Agrega consulta de resultado de lote por dProtConsLote.
- 0361 se trata como LOTE_PROCESANDO, nunca como rechazo.
- 0362 procesa el resultado individual por CDC y conserva código/mensaje real.
- Mantiene TEST sin valor fiscal y no altera base de datos, correlativos ni documentos existentes.
