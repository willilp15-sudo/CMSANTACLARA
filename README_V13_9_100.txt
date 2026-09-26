Santa Clara ERP V13.9.100
- Maestro único de Clientes ampliado con datos fiscales/receptor SIFEN.
- KuDE/factura reorganizada según factura modelo aportada: emisor, datos de venta/receptor, detalle, IVA y CDC.
- XML V150: después de XMLDSig genera gCamFuFD/dCarQR con DigestValue, IdCSC y hash SHA-256 según MT V150.
- QR TEST/PRODUCCION usa la URL correspondiente al ambiente configurado.
- El CSC no se incluye en la URL; se usa únicamente para calcular cHashQR.
- Prevalidación comprueba gCamFuFD y dCarQR antes del XSD.
