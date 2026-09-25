Santa Clara ERP V13.9.52
- Centro visible de Notas de Crédito de ventas y compras.
- PDF/impresión directa desde el centro.
- Notas de Crédito pendientes visibles en Monitor SIFEN con acción de reintento/cola.
- Diagnóstico del sistema para tablas fiscales y numeración duplicada.
- Auditoría estática: app.py compila y todos los url_for de plantillas apuntan a endpoints existentes.
IMPORTANTE: esta versión NO simula aprobación SIFEN. El estado PENDIENTE_ENVIO persiste hasta implementar/activar generación XML NCE/FE, firma XMLDSig y transmisión real al WS SIFEN con respuesta de DNIT.
