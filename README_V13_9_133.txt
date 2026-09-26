Santa Clara ERP V13.9.133 — Corrección estructural SIFEN gTotSub

Corrección basada en el rechazo XSD real de V13.9.132:
- Restaura el orden estricto xs:sequence de los campos de IVA y bases en gTotSub.
- dIVA5/dIVA10 se generan antes de dTotIVA.
- dTotIVA se genera antes de dBaseGrav5/dBaseGrav10/dTBasGraIVA.
- dLiqTotIVA5/10 no se informan con redondeo cero.
- dIVAComi no se informa sin comisión.
- Se agrega barrera de prevalidación de orden gTotSub para impedir enviar XML desordenado.

Para una venta PYG gravada solo al 5%, el tramo esperado es:
dIVA5 -> dTotIVA -> dBaseGrav5 -> dTBasGraIVA.
