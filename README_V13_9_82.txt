Santa Clara ERP V13.9.82 - Validación XSD SIFEN V150

- Integra motor de validación V150 mediante pysifen/sifen 0.2.0, generado desde XSD SIFEN.
- Agrega prueba “Generar y validar XML V150”.
- Producción NO se desbloquea por presencia del paquete: exige una validación XML exitosa registrada.
- Los errores XSD se guardan en Registro técnico para corregir el generador/campos.
- No modifica correlativos, puntos de expedición ni datos persistentes.
