Santa Clara ERP V13.9.102
KuDE + Producción SIFEN segura

- KuDE PDF usa CDC/QR del rDE firmado y solo se identifica como KuDE/DTE cuando SIFEN devuelve estado aprobado/aceptado.
- Añade confirmación explícita de habilitación externa DNIT antes de activar Producción.
- Producción exige diagnóstico completo, XSD V150 OK y conexión mTLS OK.
- Añade envío sincrónico real de FE a SIFEN Producción desde la factura, con confirmación de efectos fiscales.
- Guarda respuesta/estado y solo habilita representación como DTE aprobado cuando la respuesta de SIFEN es aprobada/aceptada.
- No almacena ni solicita por chat claves privadas o contraseñas del certificado.
