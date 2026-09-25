Santa Clara ERP V13.9.38 - SIFEN TEST
- Panel Configuración > SIFEN Facturación Electrónica.
- Bloqueo deliberado a ambiente TEST.
- Carga P12/PFX y validación de certificado/clave privada.
- La contraseña del certificado NO se persiste.
- Certificado y clave extraída se guardan en DATA_DIR/sifen con permisos restringidos.
- Prueba mTLS contra servicio de consulta SIFEN TEST.
- Registro técnico de pruebas.
- Configuración de RUC, DV, timbrado TEST, establecimiento, punto de expedición, CSC.
- No implementa todavía emisión XML completa ni transmisión de DE: requiere completar mapeo XML/XSD, firma XML y WS antes de producción.
