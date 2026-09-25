SANTA CLARA ERP V13.9.44
Multipunto de expedición DNIT + correlatividad independiente

- Administra múltiples establecimientos y puntos de expedición autorizados por DNIT.
- Cada punto tiene correlativo propio de Factura Electrónica.
- Permite marcar Factura Electrónica, Nota de Crédito y Nota de Débito por punto.
- Solo puntos activos, autorizados y habilitados para FE aparecen al facturar.
- Permite un punto predeterminado.
- Venta normal y Caja Central seleccionan punto de expedición.
- CDC TEST toma establecimiento y punto de la factura emitida.
- Migra automáticamente el punto anterior sin borrar datos.
- Corrige un defecto de V13.9.43: Compras ya no consume correlativos de Ventas y Ventas reserva correctamente su número.
- La reserva del número está dentro de la transacción: si la venta falla, rollback conserva el correlativo.

IMPORTANTE: marcar “Autorizado DNIT” solo refleja una autorización ya otorgada por DNIT; el ERP no crea autorizaciones ante DNIT.
No borrar /var/data/santa_clara_v8.db.
