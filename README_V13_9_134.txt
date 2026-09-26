Santa Clara ERP V13.9.134 — SIFEN cálculo canónico 4 decimales

- Mantiene estructura XSD V150 corregida de V13.9.133.
- Normaliza todos los importes monetarios generados por el motor SIFEN a 4 decimales con Decimal ROUND_HALF_UP.
- dBasGravIVA y dLiqIVAItem se calculan desde el mismo dTotOpeItem y quedan complementarios al total del ítem.
- dMonTiPag usa la misma escala de 4 decimales.
- Mantiene nodos opcionales solo cuando corresponden.
- Objetivo: evitar la falla interna 2500/calculo-coincide-info-xml (10182) observada con periódicos a 8 decimales.
