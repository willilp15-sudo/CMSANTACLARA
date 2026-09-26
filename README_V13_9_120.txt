Santa Clara ERP V13.9.120 - estabilización de configuración

1. SIFEN V150: rDE se valida contra siRecepDE_v150.xsd, no contra DE_v150.xsd.
2. Se conserva DATA_DIR persistente (/var/data en Render) y la base santa_clara_v8.db.
3. El llamador web integrado usa la misma base persistente y la cola llamados_pacientes.
4. No borrar/recrear el Persistent Disk de Render al desplegar nuevas versiones.
5. No crear un servicio Render nuevo para una actualización: desplegar sobre el mismo servicio.
6. SECRET_KEY debe mantenerse como variable persistente del mismo servicio; cambiarla cierra sesiones, pero no borra datos.
7. SIFEN, maestros, permisos y configuraciones se guardan en SQLite persistente; certificado/branding se guardan bajo DATA_DIR.
