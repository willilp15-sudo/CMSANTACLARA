SANTA CLARA ERP V13.9.89 - AUDITORIA INTEGRAL XML V150

Correcciones acumuladas del generador SIFEN V150:
- gEmis usa cDepEmi (no dDepEmi).
- gValorItem ahora contiene un gValorRestaItem real.
- gValorRestaItem incluye dTotOpeItem y campos de descuentos/anticipos en cero cuando no aplican.
- gCamIVA incluye dBasExe, obligatorio en el binding V150.
- Se genera gTotSub completo con subtotales, totales, IVA 5/10, bases gravadas y valores cero obligatorios.
- Se agregó prevalidación estructural previa al binding para detectar varios faltantes en una sola ejecución.
- No modifica correlativos, timbrado, puntos, base persistente, depósitos, transferencias ni usuarios.

IMPORTANTE:
La validación local no equivale a aprobación de SIFEN. Producción debe seguir bloqueada hasta que el DE completo sea firmado, transmitido y aceptado por SIFEN.
