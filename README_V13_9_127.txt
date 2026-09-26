Santa Clara ERP V13.9.127 - IVA SIFEN V150 corregido

Corrección específica del rechazo SIFEN 2371:
- dIVA5/dIVA10 ahora suman exactamente los dLiqIVAItem escritos en XML.
- dBaseGrav5/dBaseGrav10 suman exactamente las bases escritas por ítem.
- dTotIVA se calcula como dIVA5 + dIVA10 con dRedon=0.
- Se eliminan dLiqTotIVA5 y dLiqTotIVA10 cuando no existe redondeo; esos campos son IVA del redondeo, no IVA total por tasa.
- Se mantienen las correcciones anteriores: CDC/QR, XSD, lote, hora de firma, tipo de transacción y geografía.
