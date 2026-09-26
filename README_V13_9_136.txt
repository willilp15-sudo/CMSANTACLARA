Santa Clara ERP V13.9.136 - SIFEN Grupo F completo

Base: ZIP V13.9.135 subido por el usuario.
Cambio: el grupo gTotSub se emite completo y en secuencia XSD, incluyendo ceros explícitos para dSubExe, dSubExo, dSub10, dComi, dIVA10, dLiqTotIVA5, dLiqTotIVA10, dIVAComi y dBaseGrav10 cuando no aplican.
Se conservan: cálculo PYG, orden XSD V150, firma, QR, geografía y clasificación de transacción de versiones anteriores.
Motivo: aislar la falla genérica 2500/calculo-coincide-info-xml (10182) evitando valores ausentes/nulos en el evaluador de reglas, sin alterar los importes reales de la operación.
