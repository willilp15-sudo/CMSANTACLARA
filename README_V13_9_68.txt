Santa Clara ERP V13.9.68
- Corrección del importador para archivos .XLS legados que no usan contenedor OLE estándar.
- Se agrega lector tolerante de flujos BIFF antiguos/fragmentarios (caso Expected BOF record).
- Se mantienen XLS/XLSX/XLSM/CSV/TXT/TSV/XML/HTML.
- Si una variante binaria sigue sin ser reconocida, el sistema muestra la firma inicial del archivo para diagnóstico exacto en vez del mensaje genérico.
- No modifica ni reemplaza la base persistente /var/data/santa_clara_v8.db.
