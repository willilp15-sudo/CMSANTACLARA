Santa Clara ERP V13.9.103
Corrección transmisión SOAP SIFEN V150:
- soap:Envelope usa prefijo soap explícito.
- rEnviDe usa el namespace SIFEN como namespace por defecto (sin ns0).
- dId y xDE heredan el namespace SIFEN sin prefijos automáticos.
- bloqueo preventivo si el payload final contiene ns0/ns1/etc.
- no modifica base de datos ni credenciales.
