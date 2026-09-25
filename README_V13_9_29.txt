SANTA CLARA ERP V13.9.29 - EMERGENCIA DISCO / BACKUPS

- Corrige el riesgo de "database or disk is full" causado por acumulación de backups.
- Limpia backups antiguos al arrancar, ANTES de intentar crear nuevas copias.
- Backup automático continúa ejecutándose cada 5 minutos.
- Conserva hasta 24 copias de 5 minutos (2 horas), sujeto al espacio disponible.
- Conserva hasta 7 copias diarias locales, sujeto al espacio disponible.
- Reserva al menos 200 MB libres para la base activa y operaciones de SQLite.
- Limita los backups locales a aproximadamente 35% del disco.
- Si no hay espacio suficiente para una copia completa, omite ese backup temporalmente en vez de llenar el disco.
- Nunca elimina /var/data/santa_clara_v8.db ni /var/data/branding.
- Mantiene todas las funciones y centralización de V13.9.28.

IMPORTANTE: un backup en el mismo disco no sustituye un backup externo. Se recomienda almacenamiento externo independiente.
