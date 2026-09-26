Santa Clara ERP V13.9.104

- Puntos de expedición editables desde un único maestro.
- Si establecimiento+punto ya existe y el formulario llega sin p_id, se actualiza el registro existente en vez de provocar UNIQUE constraint.
- Evita duplicar puntos.
- Punto predeterminado sincroniza establecimiento/punto/timbrado institucional para próximos documentos.
- KuDE/XML siguen usando establecimiento y punto de la factura emitida; documentos históricos no se reescriben.
- Si el punto ya tiene documentos, identidad fiscal/timbrado/correlativo permanecen protegidos.
