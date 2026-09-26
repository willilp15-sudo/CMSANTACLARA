Santa Clara ERP V13.9.113

- El ambiente TEST ahora transmite la FE al Web Service TEST de SIFEN después de XMLDSig y XSD V150.
- TEST guarda HTTP, XML/SOAP, código, mensaje, estado e intento; sigue sin valor fiscal.
- Un fallo local o de conexión se registra como ERROR_ENVIO, nunca como RECHAZADO.
- RECHAZADO queda reservado a una respuesta real recibida de SIFEN.
- Se agregó la ruta de Reintentar para Facturas Electrónicas desde Monitor SIFEN.
- Facturas antiguas marcadas RECHAZADO con 0 intentos y sin SOAP se reclasifican como NO_ENVIADO.
- No se eliminan facturas, CDC, correlativos, puntos, cajas ni datos existentes.
