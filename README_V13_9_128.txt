Santa Clara ERP V13.9.128 - Motor aritmético SIFEN corregido
- Cálculos fiscales migrados a Decimal + ROUND_HALF_UP.
- dTotBruOpeItem se deriva obligatoriamente de cantidad x precio unitario.
- dTotOpeItem usa la misma base matemática que el XML.
- dBasGravIVA se calcula desde dTotOpeItem y dLiqIVAItem desde la base gravada, según V150.
- gTotSub suma exactamente los valores escritos en los ítems.
- dMonTiPag se deriva de los ítems para evitar discrepancias con totales históricos.
- Conserva CDC, QR, XSD, lote, hora/firma, geografía y demás correcciones anteriores.
