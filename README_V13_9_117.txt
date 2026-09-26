SANTA CLARA ERP V13.9.117 - CORRECCIÓN LLAMADOR

- Corrige monitor que permanecía en LLAMADA EN ESPERA.
- El servidor acepta el llamador cuando LLAMADOR_TOKEN aún no fue configurado en Render.
- Si LLAMADOR_TOKEN está configurado, mantiene validación segura por coincidencia exacta.
- Recupera llamadas ENTREGADAS no confirmadas para evitar llamadas perdidas tras una caída del monitor.
- El monitor busca llamador_config.json desde su propia carpeta y muestra claramente CONECTADO AL ERP o ERROR DE CONEXIÓN.
- Se conserva el flujo: médico/agenda -> cola -> monitor -> voz -> confirmación -> histórico.
