Santa Clara ERP V13.9.130 — Coherencia integral SIFEN
Base: V13.9.129.
- Completa dSubExo, dComi, dLiqTotIVA5, dLiqTotIVA10 y dIVAComi con cero cuando corresponde, para evitar operandos nulos en validaciones aritméticas SIFEN.
- Mantiene dLiqTotIVA5/10 exclusivamente como IVA de redondeo; con dRedon=0 son 0.
- Clasifica servicios también por descripción cuando el producto histórico no tiene metadatos suficientes.
- dFeEmiDE usa reloj America/Asuncion coherente con dFecFirma para documentos del día.
- Conserva CDC/QR, XSD, lote, firma, geografía, persistencia y diagnóstico XML.
