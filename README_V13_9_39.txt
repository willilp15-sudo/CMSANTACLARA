Santa Clara ERP V13.9.39
- Al confirmar una venta, el sistema factura/cobra y abre automáticamente la factura.
- Botón de ventas: Facturar y cobrar.
- En ambiente SIFEN TEST, si certificado y configuración están completos, genera CDC TEST de 44 dígitos conforme a la estructura del Manual Técnico V150 (Factura=01, RUC, DV, establecimiento, punto, número, tipo contribuyente, fecha, emisión normal, código seguridad y DV módulo 11).
- El CDC TEST queda como TEST_GENERADO, NO ENVIADO / NO APROBADO y SIN VALOR FISCAL.
- No genera QR de Producción para CDC TEST.
- Se agregó Tipo de contribuyente (Persona Física/Jurídica) a Configuración SIFEN.
- No se habilita Producción ni se marca DTE aprobado sin respuesta real de SIFEN.
