Santa Clara ERP V13.9.91 — Maestros SIFEN + validación XSD directa

Cambios principales:
- Clientes/proveedores: agrega datos fiscales SIFEN del receptor (naturaleza, tipo de operación, tipo de contribuyente/documento, país, dirección y geografía codificada).
- Productos/servicios: agrega descripción y unidad de medida SIFEN; los XML FE/NCE/NDE toman estos datos del maestro.
- dDesProSer: se genera siempre desde la descripción SIFEN/nombre/descripcion con fallback controlado y longitud acotada.
- Validación V150: elimina el paso defectuoso RDe.from_xml() que producía falsos errores de constructor como "dDesProSer missing". El XML original se valida directamente con lxml contra los XSD V150 instalados dentro del paquete pysifen/sifen.
- Migraciones exclusivamente aditivas; no elimina ni reemplaza la base de datos persistente.

Seguridad:
- Producción SIFEN continúa bloqueada hasta completar validación XSD, firma, mTLS, TEST y respuesta real de SIFEN.
