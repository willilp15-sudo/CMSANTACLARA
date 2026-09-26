Santa Clara ERP V13.9.137 — CDC TEST limpio tras cambio estructural

Cambio principal:
- No cambia nuevamente IVA ni Grupo F.
- Agrega una acción controlada para generar un CDC nuevo SOLO en ambiente TEST cuando SIFEN ya rechazó definitivamente el DE con 10182.
- Conserva número de factura, cliente, ítems e importes; cambia únicamente código de seguridad/CDC y limpia protocolo/respuesta/QR previos.
- La acción aparece en Detalle SIFEN sólo para RECHAZADO con mensaje 10182.

Fundamento: la FAQ vigente de DNIT indica que un CDC rechazado puede reutilizarse siempre que la estructura de datos del DE no sea modificada. Durante las correcciones 132-136 la estructura y representación de importes sí cambiaron manteniendo el mismo CDC.

Uso recomendado:
1. Instalar esta versión en TEST.
2. Abrir el detalle del rechazo 10182.
3. Pulsar “Regenerar CDC TEST limpio”.
4. Confirmar que el CDC mostrado cambió.
5. Realizar un único envío y consultar el lote.

No habilita esta operación en PRODUCCION.
