# Santa Clara ERP V13.9.76

## Corrección rápida del importador Gasparini
- Corrige la detección de codificación: un CSV ANSI/Windows-1252 ya no se interpreta erróneamente como UTF-16.
- Corrige la detección de delimitador cuando `csv.Sniffer` no puede decidirlo. Se evalúan coma, punto y coma, tabulador y barra vertical y se elige la estructura tabular más coherente.
- Mantiene el aumento del límite de campos CSV de V13.9.75.
- Mantiene el reconocimiento específico de Compras Detalladas Gasparini sin encabezados.
- Probado contra el archivo real `compras detallada.csv`: Windows-1252, delimitador coma, 1.678 filas y aproximadamente 90/91 campos por registro.
- No modifica la base persistente ni elimina datos existentes.


V13.9.78: Preparación segura SIFEN Producción; activación bloqueada hasta transmisor XMLDSig/SOAP completo.
