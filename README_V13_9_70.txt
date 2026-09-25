SANTA CLARA ERP V13.9.70 - LLAMADOR INDEPENDIENTE

- La PC del médico ya no reproduce voz. El botón solo encola la llamada en el servidor.
- Carpeta llamador_windows: aplicación separada para la PC/TV de sala de espera.
- Histórico diario: /llamador/historico con paciente, médico, consultorio, dispositivo y hora.
- Configurar en Render una variable de entorno LLAMADOR_TOKEN con un valor secreto largo.
- Copiar el mismo valor en llamador_windows/llamador_config.json en la PC del llamador.
- La aplicación consulta el ERP y reproduce las llamadas únicamente en el dispositivo configurado.
- No se modifica ni reemplaza la base persistente. La migración agrega columnas/tablas al iniciar.
