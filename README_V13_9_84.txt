Santa Clara ERP V13.9.84 - Datos obligatorios del emisor TgEmis V150

- Corrige el error TgEmis.__init__ por ausencia de dDepEmi, dDesDepEmi, cCiuEmi, dDesCiuEmi y dTelEmi.
- Agrega a Configuración SIFEN los datos oficiales de departamento, distrito, ciudad, teléfono y dirección del emisor.
- El generador XML no inventa códigos geográficos: deben cargarse conforme al domicilio fiscal/autorizado.
- El diagnóstico de Producción verifica los datos obligatorios del emisor.
- Conserva correlativos, puntos de expedición, multirroles y base persistente.
