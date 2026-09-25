Santa Clara ERP V13.9.78 - Preparación segura SIFEN Producción

- Selector TEST / PRODUCCIÓN con bloqueo por diagnóstico.
- Endpoints oficiales separados: sifen-test.set.gov.py y sifen.set.gov.py.
- Configuración de timbrado e inicio de vigencia.
- XML versión 150 fijada en configuración.
- Diagnóstico: RUC/DV, timbrado, vigencia, CSC/IdCSC, certificado, puntos y transmisor.
- Prueba mTLS usa el ambiente seleccionado.
- Producción NO se activa mientras falte el transmisor XMLDSig + SOAP completo.

IMPORTANTE: esta versión NO afirma tener transmisión DTE de Producción completa. El diagnóstico la bloquea deliberadamente hasta implementar y validar XML V150/XSD, XMLDSig, SOAP y respuestas SIFEN.
No elimina ni reemplaza /var/data/santa_clara_v8.db.
