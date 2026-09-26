Santa Clara ERP V13.9.94 — Corrección raíz rDE / XSD V150

- Corrige la regresión V13.9.93 que validaba rDE directamente contra DE_v150.xsd.
- rDE se valida contra siRecepDE_v150.xsd, tal como referencia el Manual Técnico V150.
- DE_v150.xsd queda como esquema estructural dependiente, no como raíz de validación del documento completo.
- Busca siRecepDE_v150.xsd dentro del paquete instalado sin asumir una única ruta.
- Si el esquema de recepción compila, muestra los errores XSD reales y no vuelve a caer en DE_v150.xsd.
- Producción permanece bloqueada hasta validación, firma y pruebas TEST reales.
