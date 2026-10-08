# Santa Clara ERP — revisión técnica V13.14.2 (diagnóstico)

Este paquete NO declara corregido el error 500 ni certifica trazabilidad integral.
Se preservan los archivos operativos de V13.14.1 sin cambios.

## Comprobaciones estáticas
- Existen las rutas `/operacion-clinica`, `/mapa-sistema`, `/administracion-integral`.
- Existen sus tres plantillas HTML.
- Los nueve enlaces del centro de operaciones corresponden a rutas declaradas.

## Diagnóstico adicional
Ejecutar `python diagnostico_rutas_erp.py` desde el directorio raíz, en un entorno con las dependencias instaladas.
Genera `diagnostico_rutas_resultado.json` con las excepciones de renderizado, sin efectuar operaciones POST ni modificar la base de datos. Puede requerir configuración de entorno para renderizar correctamente.

**Atención:** el diagnóstico no sustituye las pruebas integrales con una base de prueba ni los logs de Render. No se debe subir el JSON a un repositorio público sin revisar datos sensibles.
