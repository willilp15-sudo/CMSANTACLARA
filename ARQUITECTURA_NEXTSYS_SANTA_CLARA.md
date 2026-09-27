# Santa Clara ERP — reconstrucción sobre inventario Nextsys

Identidad: **Centro Médico Santa Clara / Grupo Santa Clara S.A.**

## Base Nextsys inventariada
Se identificaron 26 bibliotecas funcionales PowerBuilder en ambos paquetes: administracion, configuracion_inicial, consultas, contabilidad, estacion, facturas, fondo_fijo, importadora, informes, informes_base, modelos, notificaciones, punto_venta, restaurant, sanatorio y librerías auxiliares/integración. El manifiesto JSON conserva hashes y tamaños para trazabilidad.

La distribución Nextsys entregada está compilada (`.pbd/.dll/.exe`), no contiene fuentes PowerBuilder (`.pbl/.sr*`) ni un esquema SQL exportado. Por ello la lógica binaria no puede convertirse literalmente a Python. La reconstrucción funcional usa su inventario modular y relaciones observables como referencia y conserva las funciones específicas ya implementadas en Santa Clara.

## Arquitectura funcional conservada
Ventas/facturación; SIFEN; clientes/terceros; proveedores; productos y servicios; compras; stock/inventario; farmacia; caja/fondo fijo; bancos/tesorería; CxC; CxP; contabilidad; informes; usuarios/roles/permisos; sanatorio (agenda, recepción/ventas, consultorios, admisión, internación, enfermería, urgencias, quirófano, laboratorio, seguros); RRHH; importación/exportación y auditoría. Los módulos Nextsys no sanitarios (restaurant, importadora, estación/concentrador, transporte) quedan documentados en el inventario para no perder su existencia y para activación/migración posterior donde no existe equivalencia clínica directa.

## SIFEN
La implementación debe validarse contra Manual Técnico V150, XSD oficiales V150 y Notas Técnicas vigentes de DNIT. No se considera válida una transmisión real hasta completar ambiente de pruebas/homologación con certificado y credenciales reales del contribuyente.

## Corrección estructural incluida
Se movió el `app.run(...)` al final real de `app.py`. En el paquete anterior estaba antes de rutas agregadas posteriormente, impidiendo su registro al ejecutar directamente el archivo.
