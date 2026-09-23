# Santa Clara ERP Hospitalario V8 Integrado

Sistema en español que integra operación sanatorial, administración, inventario, finanzas y contabilidad en una sola base de datos.

## Circuitos vinculados
- Paciente → Admisión/Urgencias/Internación → cama → servicios/farmacia → cuenta paciente → factura → Libro Ventas → CxC → cobro → Caja/Banco → Contabilidad.
- Producto farmacéutico cargado al paciente → salida automática de stock → cuenta paciente.
- Compra → entrada de stock → Libro Compras → IVA Crédito → CxP → pago → Caja/Banco → Contabilidad.
- Venta administrativa → salida de stock/costo → Libro Ventas → IVA Débito → CxC → cobro → Contabilidad.
- Multimoneda PYG/USD/BRL/EUR con tipo de cambio histórico por fecha y diferencias de cambio en cobros/pagos.
- Alta de internación libera la cama.

## Instalación Windows
1. Ejecutar `instalar.bat`.
2. Ejecutar `iniciar.bat`.
3. Abrir http://127.0.0.1:5000

Usuario inicial: admin
Contraseña inicial: SantaClara2026!

Antes de uso real con pacientes: cambiar contraseña/SECRET_KEY, configurar backups, permisos por rol, políticas de seguridad y validar reglas fiscales/contables con el profesional responsable.

## V9 - Corrección y auditoría
- Edición de pacientes con actualización del tercero vinculado.
- Eliminación de pacientes solo cuando no existen admisiones relacionadas.
- Anulación transaccional de compras: revierte stock, CxP y asiento contable.
- Anulación transaccional de ventas: repone stock, cancela CxC y revierte asiento contable.
- Bloqueo de anulación cuando existen pagos/cobros vinculados.
- Auditoría con valores anteriores/nuevos y motivo.
- Los documentos contabilizados se anulan/revierten; no se borran físicamente.

## V10 - Consultas, liquidaciones e informes
- Registro de consultas con precio real y honorario fijo del médico (sin porcentajes).
- Cada consulta crea admisión de consulta y cargo a la cuenta del paciente.
- Liquidación diaria por médico; al cerrar genera CxP y asiento contable de honorarios.
- Informe mensual/por rango de consultas por especialidad, médico, paciente, precio, honorario y margen.
- Exportación de consultas a PDF y Excel.
- Liquidación individual del médico en PDF.
- Multimoneda con tipo de cambio histórico conservado en cada consulta.

## V10.3 - IVA configurable por producto y servicio
- Cada producto y servicio se clasifica como IVA 10%, IVA 5% o Exento.
- Compras y ventas toman automáticamente la tasa configurada en el maestro; ya no se elige manualmente en cada transacción.
- La cuenta del paciente conserva el IVA de cada cargo y la factura sanatorial calcula simultáneamente bases e IVA al 10%, 5% y exentas.
- Libro Compras y Libro Ventas muestran el desglose fiscal por tasa.
- La migración agrega los campos nuevos a bases existentes al iniciar el sistema.

## V11 - Sistema modular por roles y Farmacia Interna
- Usuarios con uno o varios roles y matriz de permisos por módulo/acción.
- Roles iniciales: ADMINISTRADOR, RECEPCION, ADMISION, ENFERMERIA y FARMACIA.
- Menú dinámico: cada usuario visualiza solo módulos habilitados.
- Enfermería solicita medicamentos/insumos; la solicitud no descuenta stock.
- Farmacia autoriza cantidades (incluida autorización parcial) y luego entrega.
- La entrega de Farmacia descuenta stock y genera automáticamente el cargo en la misma cuenta del paciente.
- Traslado Urgencias -> Internación conserva la misma admisión/cuenta.
- Auditoría de solicitud, autorización y entrega.
- El administrador gestiona usuarios, roles y permisos desde /admin/usuarios-roles.

Usuario inicial: admin / SantaClara2026! (cambiar la contraseña para producción).


## V11.1 - Precios con IVA incluido
- Productos, insumos, medicamentos y servicios se registran con precio final IVA incluido.
- IVA configurable por ítem: 10%, 5% o Exento.
- El sistema desglosa automáticamente base imponible e IVA para ventas, compras y facturación sanatorial.
- Fórmula: base = total/(1+tasa); IVA = total-base.
- La cuenta del paciente conserva el precio final; la contabilidad registra ingreso neto e IVA Débito por separado.
- En compras, el costo final se desglosa en inventario neto + IVA Crédito.

## V12 - Recepción, Caja, Agendamiento y Consultorio Médico
- Se elimina Pacientes como módulo visible del menú; la ficha clínica/administrativa sigue existiendo como dato maestro interno.
- Recepción: panel de agenda del día y acceso a caja.
- Caja de Recepción: apertura por usuario, saldo inicial, cobros por forma de pago, arqueo y cierre con diferencia.
- Agendamiento: búsqueda/selección de paciente y alta rápida con botón + sin salir de la agenda; médico, especialidad, aseguradora, fecha, hora, motivo y precio.
- Médico: vista exclusiva de sus pacientes del día mediante vinculación Médico ↔ Usuario.
- Llamador por voz: usa Web Speech API del navegador y requiere permiso LLAMAR del rol médico.
- Historia clínica: consulta de antecedentes y nuevas evoluciones médicas.
- Configuración Sanatorial: vínculo entre ficha del médico y usuario del sistema.
- Conserva roles/permisos, flujo Enfermería → Farmacia, stock, IVA 10%/5%/exento con precios IVA incluido y módulos contables anteriores.

## V13.1 Operativa
- Basada en V12.
- CRUD real en maestros prioritarios (productos y clientes/proveedores), con búsqueda, alta directa, modificación y eliminación controlada.
- Compras/Ventas con accesos 🔍/➕ para crear/buscar terceros y productos sin perder el flujo.
- Compras/Ventas pueden anularse con reversión de stock, CxC/CxP y estado contable; no se borran físicamente.
- API de búsqueda para productos, pacientes, terceros y médicos preparada para selectores emergentes.
- La eliminación de maestros se bloquea cuando existen movimientos dependientes.


## V13.3 - Actualizaciones seguras
- La base `santa_clara_v8.db` es persistente y no se incluye/reemplaza en las actualizaciones.
- Antes de aplicar por primera vez V13.3 se crea una copia automática en `backups/`.
- Las modificaciones de estructura son migraciones incrementales; no eliminan registros.
- Dashboard simplificado.
- Usuarios y roles simplificados con listas desplegables.

## V13.5.7 - Código de barras
- Productos: campo Código de Barras compatible con lectores USB tipo teclado.
- Evita códigos de barras duplicados mediante índice único.
- Compras y Ventas: escaneo selecciona automáticamente el producto y pasa a cantidad.
- Enfermería/Farmacia: selección rápida de producto por escaneo.
- Migración incremental: agrega la columna codigo_barras sin reinicializar la base existente.

## V13.5.9 - Base de datos persistente entre versiones
- La base operativa ya no depende de la carpeta ZIP/versionada del programa.
- En Windows se guarda por defecto en `%LOCALAPPDATA%\SantaClaraERP\data\santa_clara_v8.db`.
- Al primer inicio, si todavía no existe la base persistente, el sistema busca una base `santa_clara_v8.db` de una instalación anterior en la carpeta actual o en carpetas hermanas y copia la más reciente.
- Las siguientes versiones que mantengan esta arquitectura abrirán siempre la misma base persistente.
- Se crea automáticamente una copia de seguridad diaria al primer inicio en `%LOCALAPPDATA%\SantaClaraERP\data\backups` y se conservan las 30 copias más recientes.
- `VER_BASE_DATOS.bat` abre la carpeta donde están la base persistente y sus respaldos.
- No elimine manualmente la carpeta `%LOCALAPPDATA%\SantaClaraERP` si desea conservar los datos.
- Opcional: la variable de entorno `SANTA_CLARA_DATA_DIR` permite definir otra ubicación persistente, por ejemplo una unidad de servidor con respaldo administrado.

## V13.6.0 - Compras con múltiples ítems
- Una factura de compra admite múltiples productos.
- Grilla editable de cantidad y costo final IVA incluido.
- Lector de código de barras con agregado consecutivo; repetir código incrementa cantidad.
- IVA 10%, 5% y exento calculado por cada ítem y consolidado en la cabecera.
- Cada ítem genera su entrada de stock y actualiza costo.
- Mantiene contado, crédito, crédito en cuotas, CxP y asiento contable.
- Mantiene la base de datos persistente de V13.5.9 sin reinicializarla.


## V13.6.1 — Códigos internos automáticos
Los movimientos reciben un código interno automático, único y no editable (COM, VEN, STK, CXC, CXP, ASI, BAN, ADM, FAC, FAR, CAJ, APE, REC, LIQ y SEG). Los registros históricos reciben código sin modificar sus datos. Los códigos anulados no se reutilizan y la numeración permanece en la base persistente.

## V13.6.2 — Ventas en cuotas
- Ventas admite CONTADO, CRÉDITO y CRÉDITO EN CUOTAS.
- Permite entrega inicial y plan de cuotas con vencimiento e importe.
- Valida que entrega inicial + cuotas coincida con el total.
- Crea CxC sólo por el saldo financiado.
- Los cobros posteriores se aplican automáticamente a las cuotas más antiguas.
- Estados de cuota: PENDIENTE, PARCIAL, PAGADA y visualización VENCIDA.
- Conserva la base de datos persistente y aplica migración incremental.


V13.6.5.1 FIX Configuración Empresa
- Corrige Error 500 al abrir /configuracion-empresa: la ruta usaba has_perm(), disponible solo en Jinja, en lugar de user_has() del backend.
- Agrega import de pathlib.Path requerido para guardar logos.
- No reinicializa ni reemplaza la base de datos persistente.

## V13.7.0 - Migración histórica 2026 y ficha avanzada de productos
- Importación incremental, sin borrar la base persistente, del Plan de Cuentas entregado por Santa Clara.
- Importación de stock/productos con código, código de barras, precio, IVA, depósito, stock mínimo y cantidad por depósito.
- Importación de libros de Compras y Ventas 2026 a nivel de comprobante, conservando fecha, tercero, RUC, timbrado, IVA 5/10, exentas y total.
- Importación del Diario 2026 con cuentas, debe/haber y enlace al plan de cuentas.
- Nueva ficha de producto ampliada inspirada en el formato operativo proporcionado: clasificación, código, barras, resumido, costos/precios, IVA, moneda, tipo, presentación, genérico, laboratorio, distribuidora, droga, indicación, posología, controlado, especialidad, clasificaciones, descripción, vencimiento y lote.
- Los reportes fuente no identifican el detalle producto/cantidad de cada factura de compra/venta; por integridad contable no se inventan esas líneas. El stock sí se migra por producto y depósito.

## V13.8.1 - Compras integrales
- Ver detalle completo de cada compra y sus productos.
- Modificar compra recalculando stock, CxP, cuotas, IVA, Libro Compras y Contabilidad.
- Eliminar compra sin pagos aplicados elimina sus efectos activos de stock, CxP, cuotas, caja/banco inicial y asientos.
- Si existen pagos aplicados, se exige revertirlos antes de modificar/eliminar.
- Auditoría conserva la trazabilidad de modificaciones y eliminaciones.


## V13.9.0 – Arquitectura operativa tipo NextSys
- Reorganización del menú principal por módulos ERP: Administración, Facturación, Compras, Stock, Sanatorio, Contabilidad, Informes y Controles.
- Barra superior compacta con submenús desplegables para evitar saturación lateral.
- Conserva rutas y procesos existentes; no reinicializa ni sustituye la base SQLite.
- Mantiene el botón Volver en pantallas internas y la identidad Santa Clara.
- Esta versión reproduce mediante implementación propia la estructura operativa observable de NextSys, sin copiar código propietario.

## V13.9.1 - Conciliación bancaria y portal web de turnos
- Nuevo módulo Bancos > Conciliación Bancaria.
- Conciliación por cuenta y período, carga de extracto, asociación con movimientos internos, pendientes y cierre controlado.
- Nuevo portal público `/turnos-web`, sin necesidad de iniciar sesión, conectado a horarios médicos y agenda interna.
- El paciente selecciona fecha/especialidad/horario y registra documento, nombre, teléfono, email y motivo.
- La reserva web se inserta directamente en la misma tabla de agenda utilizada por Recepción y Consultorio.
- Se mantiene la base persistente existente; las tablas nuevas se crean de forma incremental.

## V13.9.2 – Informes bajo demanda y productos sin preselección
- Los informes operativos y contables ya no cargan registros al abrirse: muestran resultados únicamente después de pulsar Consultar.
- Compras y Ventas abren con la grilla de ítems vacía y sin producto preseleccionado.
- Los productos se consultan bajo demanda por código de barras, código interno o nombre.
- El lector de código de barras puede agregar directamente un resultado exacto.
- No se reinicializa ni reemplaza la base de datos persistente existente.

## V13.9.3 – Carga de Compras y Ventas bajo demanda
- Carga de Compras y Carga de Ventas ya no muestran el historial completo al abrir.
- Las operaciones aparecen únicamente después de realizar una búsqueda por comprobante, tercero, estado o fecha.
- La carga de una operación nueva sigue iniciando sin productos preseleccionados.

## V13.9.4 - Control de timbrado en Compras
- Cambio limitado al módulo Compras; no se modificaron otros menús.
- Carga y modificación de compras requieren N.º de Timbrado y Fecha de vencimiento del timbrado.
- Se bloquea el guardado cuando la fecha del comprobante es posterior al vencimiento del timbrado.
- El timbrado queda almacenado con la compra y visible en el detalle.
- En compras al contado permanecen ocultos vencimiento financiero y plan de cuotas; se muestran según condición de crédito.
- Migración incremental: agrega columnas sin reinicializar ni eliminar la base existente.


## V13.9.5 - Ticket térmico de agendamiento
- Agrega impresión/reimpresión de turnos desde Agenda.
- Ticket optimizado para papel térmico de 80 mm con logo Santa Clara.
- Incluye paciente, fecha/hora, motivo, médico, especialidad, seguro/particular y responsable del agendamiento.
- Al registrar una consulta se abre el comprobante listo para imprimir.
- Registra cada impresión en impresiones_agenda para auditoría.
- No modifica otros menús ni reinicializa datos existentes.


## V13.9.6 - Corrección de Roles y Permisos
- Corregido el problema que volvía a conceder permisos predeterminados al reiniciar el sistema.
- Una vez guardados los permisos de un rol, el arranque ya no vuelve a activar permisos desmarcados.
- Protección reforzada del lado del servidor: Ver, Crear, Editar, Anular, Facturar, Cobrar, Autorizar, Entregar, etc. se validan por separado.
- Las rutas de Compras, Ventas, Stock, Caja/Bancos, Contabilidad, Agenda, Admisión, Enfermería, Farmacia, Informes y Configuración quedan sujetas a permisos.
- No reinicializa la base ni elimina usuarios, roles o datos existentes.


## V13.9.7 - Inicio institucional
- Se retiró la información del Dashboard de la pantalla Inicio.
- Inicio muestra únicamente el logo de Centro Médico Santa Clara, centrado y adaptable.
- No se modificaron los demás menús ni la base de datos.


## V13.9.8 - Flujo de Consultorio y Facturación Posterior
- Agendar ya no factura ni cobra automáticamente.
- Turnos quedan pendientes de facturación.
- Separación de pendientes Particular / Seguro.
- Registro de consultas realizadas para liquidación interna.
- Registro de procedimientos realizados por médico.
- Cierre de consultorio por médico con consultas, procedimientos, particular, seguro y honorarios.
- Liquidación interna conserva detalle de las prestaciones incluidas.
- Migración no destructiva de la base existente.


## V13.9.9 - Módulo Laboratorio LACED
- Menú Laboratorio simplificado.
- Registro único de análisis/estudios.
- Particular: pendiente y facturación de venta al contado.
- Seguro: envío automático al circuito existente de Pendientes de Facturación del Seguro.
- Liquidación LACED: 80% LACED / 20% Santa Clara para servicios normales, particulares y seguros.
- Estudios admisionales: 85% LACED / 15% Santa Clara.
- Detalle de cada liquidación y bloqueo de doble liquidación.
- Permisos independientes mediante módulo LABORATORIO.


## V13.9.10 - Corrección Laboratorio y Cambio de Contraseña
- LABORATORIO incorporado al catálogo de módulos de Roles y Permisos.
- Migración puntual: ADMINISTRADOR recibe acceso completo al nuevo módulo Laboratorio.
- Los permisos existentes de los demás roles no se alteran ni se restauran automáticamente.
- El administrador puede asignar VER/CREAR/EDITAR/FACTURAR/etc. de Laboratorio desde Roles y Permisos.
- Cada usuario autenticado dispone de Cambiar mi contraseña.
- Para cambiarla se exige contraseña actual, nueva contraseña y confirmación.
- La nueva contraseña debe tener al menos 6 caracteres y ser distinta de la actual.
- El cambio queda registrado en auditoría sin guardar la contraseña en el registro de auditoría.


## V13.9.11 - PDF e impresión de Liquidación LACED
- Descarga PDF desde listado y detalle.
- Impresión directa desde el detalle.
- PDF incluye logo, período, detalle por prestación, porcentajes y totales LACED/Santa Clara.


## V13.9.12 - Clientes = Pacientes
- Todos los terceros registrados como CLIENTE se sincronizan automáticamente como pacientes.
- El selector de Agendamiento muestra también todos los clientes existentes.
- Se conserva tercero_id para que facturación, cuenta corriente y ficha del paciente correspondan a la misma persona.
- Se evita duplicar pacientes ya vinculados y se intenta vincular registros existentes por documento.
- Crear un paciente continúa creando su correspondiente cliente, manteniendo el modelo unificado.


## V13.9.13 - Búsqueda directa de Pacientes y Proveedores
- Se eliminaron las listas desplegables extensas para seleccionar pacientes.
- Pacientes se buscan escribiendo nombre o número de cédula, con resultados en tiempo real.
- Aplicado a Agendamiento, Laboratorio, Procedimientos y Admisión.
- Proveedores se buscan escribiendo nombre o RUC.
- Aplicado a Carga de Compras y Modificación de Compras.
- El formulario exige seleccionar un resultado válido antes de guardar.
- Se mantiene la unificación Cliente = Paciente de V13.9.12.


## V13.9.14 - Agenda operativa tipo grilla
- Agenda diaria estructurada por horario, paciente, seguro, estado, facturación, profesional, observación y teléfono.
- Casilla Fact. para seleccionar los turnos que se desean procesar.
- Procesamiento múltiple desde la misma agenda.
- Turnos por seguro seleccionados pasan directamente a Pendientes de Facturación del Seguro.
- Turnos particulares seleccionados quedan preparados para el circuito de facturación particular.
- Se mantienen estados operativos y llamado de pacientes.
