# Santa Clara ERP V13.9.76

## Corrección rápida del importador Gasparini
- Corrige la detección de codificación: un CSV ANSI/Windows-1252 ya no se interpreta erróneamente como UTF-16.
- Corrige la detección de delimitador cuando `csv.Sniffer` no puede decidirlo. Se evalúan coma, punto y coma, tabulador y barra vertical y se elige la estructura tabular más coherente.
- Mantiene el aumento del límite de campos CSV de V13.9.75.
- Mantiene el reconocimiento específico de Compras Detalladas Gasparini sin encabezados.
- Probado contra el archivo real `compras detallada.csv`: Windows-1252, delimitador coma, 1.678 filas y aproximadamente 90/91 campos por registro.
- No modifica la base persistente ni elimina datos existentes.


V13.9.78: Preparación segura SIFEN Producción; activación bloqueada hasta transmisor XMLDSig/SOAP completo.

## V13.9.80 — Generador estructural DE XML V150
- Generador rDE/DE V150 para FE, NCE y NDE en modo TEST/prevalidación.
- Composición de CDC y DV, gOpeDE, gTimb, datos generales, emisor/receptor, ítems IVA y documento asociado.
- Prueba desde Configuración > SIFEN usando la última factura, sin firma ni transmisión.
- Producción permanece bloqueada hasta validar el XML generado contra los XSD oficiales vigentes de DNIT.
- No modifica correlativos ni la base persistente existente.


## V13.9.81 - Usuarios multirroles
- Un usuario puede tener varios roles simultáneos.
- Alta de usuario permite selección múltiple de roles.
- Administración de usuarios permite agregar/quitar varios roles en una sola operación.
- Los permisos efectivos se obtienen de la unión de los permisos de todos sus roles mediante la tabla usuario_roles existente.
- No modifica correlativos SIFEN ni datos operativos existentes.
