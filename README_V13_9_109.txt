Santa Clara ERP V13.9.109
Corrección selección de punto de expedición en facturación

- La venta ahora respeta exactamente sifen_punto_id seleccionado en el formulario.
- Ya no fuerza el punto asociado a Caja/Recepción cuando el usuario elige otro punto autorizado.
- El correlativo, establecimiento, punto, CDC, XML SIFEN y KuDE quedan vinculados al mismo punto seleccionado.
- Se mantiene la validación de que el punto esté Activo + Autorizado DNIT + habilitado para Factura Electrónica.
- No modifica datos históricos ni la base de datos existente.
