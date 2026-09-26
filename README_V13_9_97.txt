Santa Clara ERP V13.9.97

Reestructuración de maestros:
- CLIENTES es el único maestro visible para pacientes/clientes.
- PROVEEDORES es el único maestro visible para proveedores/terceros.
- Se conservan tablas internas y vínculos históricos para no romper admisiones, historia clínica, facturación, CxC/CxP ni SIFEN.
- /terceros queda solo como compatibilidad y redirige a /proveedores.
- Menús y accesos de compras/ventas apuntan a los maestros nuevos.
