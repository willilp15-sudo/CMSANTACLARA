# Santa Clara ERP — revisión contable V2

## Alcance verificado
- Conserva las pantallas y rutas del paquete consolidado anterior.
- Incorpora validación de partida doble para TODOS los asientos generados por `asiento()`, incluyendo orígenes automáticos.
- Rechaza importes negativos, no finitos, líneas con Debe y Haber simultáneos, y asientos descuadrados antes de insertarlos.
- Conserva validación de cuentas imputables en asientos manuales.

## Límites pendientes (NO es una reconstrucción integral)
- No se ha completado el asiento de nota de crédito de venta ligado a aprobación SIFEN.
- No se ha verificado el enlace entre la cancelación fiscal SIFEN y la reversión de asientos.
- No se ha ejecutado una prueba transaccional sobre la base de datos real.
- No se han depurado de manera concluyente todos los maestros y pantallas duplicadas.

## Instalación
NO instalar directamente en producción sin respaldo de base de datos y comprobación de integraciones. El nuevo control podría bloquear operaciones antiguas que generan asientos descuadrados; eso evita registrar un asiento incorrecto pero puede impedir completar una operación hasta corregir su regla contable.
