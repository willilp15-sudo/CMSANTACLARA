Santa Clara ERP V13.9.132 - SIFEN V150 / gTotSub condicional

Corrección basada en Manual Técnico SIFEN V150, grupo F:
- No genera dSubExe/dSub5/dSub10 si no existe una operación de esa clase.
- No genera dIVA5/dBaseGrav5 si no existen ítems al 5%.
- No genera dIVA10/dBaseGrav10 si no existen ítems al 10%.
- Elimina dLiqTotIVA5 y dLiqTotIVA10 cuando dRedon=0: son IVA del redondeo, no IVA normal.
- Elimina dComi y dIVAComi cuando no existe comisión.
- Conserva los campos obligatorios de totales, descuentos, anticipos y redondeo.
- Conserva Decimal a 8 decimales y la clasificación mercadería/servicio de V13.9.131.

Caso observado: SUERO ANTIOFIDICO POLIV X 10ML, PYG 460.000, IVA 5%.
Para ese caso gTotSub debe contener dSub5, dIVA5, dTotIVA, dBaseGrav5 y dTBasGraIVA,
pero no nodos opcionales de exenta, 10%, comisión o IVA de redondeo.
