# Santa Clara ERP — revisión contable consolidada (alcance limitado)

Paquete completo construido a partir de CMSANTACLARA-main (2).zip, integrando las funciones de asientos manuales del paquete parcial.

## Incorporado
- Formulario de asientos manuales para administración.
- Validación de partida doble y cuentas activas/imputables para asientos manuales.
- Consulta de detalles y reversión auditada de asientos manuales.
- Conservación del código de los módulos y rutas fiscales originales.

## No implementado ni garantizado
- Contabilización automática de todos los estados SIFEN y notas de crédito de ventas.
- Conciliación histórica completa de asientos pendientes.
- Eliminación de paneles duplicados y cierres de período.
- Pruebas de integración con base real de producción.

## Despliegue
No es necesario crear un entorno de pruebas externo. Antes de desplegar directamente en Render, guardar copia recuperable de código y base de datos, comprobar el esquema y los asientos en el sistema existente y tener preparado rollback. No sustituir una base de datos existente por archivos del ZIP. El despliegue directo a producción sigue teniendo riesgo.
