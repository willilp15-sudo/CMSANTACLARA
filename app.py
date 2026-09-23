from flask import Flask,render_template,request,redirect,session,flash,jsonify,send_file
import sqlite3,os,hashlib,datetime,shutil,io
from pathlib import Path
app=Flask(__name__); app.secret_key=os.environ.get('SECRET_KEY','cambiar-en-produccion')

# V13.5.9 - Base de datos persistente fuera de la carpeta de cada versión.
# En Windows se guarda en %LOCALAPPDATA%\SantaClaraERP\data. De esta forma,
# reemplazar/descomprimir una nueva versión del programa no reemplaza los datos.
def _directorio_datos_persistente():
 base=os.environ.get('SANTA_CLARA_DATA_DIR')
 if base:return os.path.abspath(os.path.expandvars(os.path.expanduser(base)))
 local=os.environ.get('LOCALAPPDATA')
 if local:return os.path.join(local,'SantaClaraERP','data')
 return os.path.join(os.path.expanduser('~'),'.santa_clara_erp','data')

DATA_DIR=_directorio_datos_persistente()
os.makedirs(DATA_DIR,exist_ok=True)
DB=os.path.join(DATA_DIR,'santa_clara_v8.db')

def _buscar_base_anterior():
 # 1) Una base incluida junto a app.py (instalaciones antiguas).
 aqui=os.path.dirname(os.path.abspath(__file__))
 candidatos=[]
 local_db=os.path.join(aqui,'santa_clara_v8.db')
 if os.path.isfile(local_db):candidatos.append(local_db)
 # 2) Versiones hermanas dentro de Descargas/otra carpeta común.
 padre=os.path.dirname(aqui)
 try:
  for nombre in os.listdir(padre):
   ruta=os.path.join(padre,nombre)
   if not os.path.isdir(ruta) or os.path.abspath(ruta)==os.path.abspath(aqui):continue
   cand=os.path.join(ruta,'santa_clara_v8.db')
   if os.path.isfile(cand):candidatos.append(cand)
 except OSError:pass
 if not candidatos:return None
 return max(candidatos,key=lambda x:os.path.getmtime(x))

def preparar_base_persistente():
 if os.path.exists(DB):return
 anterior=_buscar_base_anterior()
 if anterior:
  shutil.copy2(anterior,DB)
  print('[Santa Clara] Base existente importada a:',DB)
 else:
  print('[Santa Clara] Se creará una nueva base persistente en:',DB)

def backup_inicio():
 if not os.path.exists(DB):return
 carpeta=os.path.join(DATA_DIR,'backups');os.makedirs(carpeta,exist_ok=True)
 # Una copia por día al primer inicio; conserva las 30 más recientes.
 hoy=datetime.date.today().strftime('%Y%m%d')
 destino=os.path.join(carpeta,'santa_clara_'+hoy+'.db')
 if not os.path.exists(destino):
  try:shutil.copy2(DB,destino)
  except OSError:pass
 try:
  copias=sorted([os.path.join(carpeta,x) for x in os.listdir(carpeta) if x.startswith('santa_clara_') and x.endswith('.db')],key=os.path.getmtime,reverse=True)
  for viejo in copias[30:]:
   try:os.remove(viejo)
   except OSError:pass
 except OSError:pass

preparar_base_persistente()

def db():
 c=sqlite3.connect(DB);c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON');return c
def h(s):return hashlib.sha256(s.encode()).hexdigest()
def now():return datetime.datetime.now().isoformat(timespec='seconds')
LOGO_PATH=os.path.join(os.path.dirname(__file__),'static','logo_santa_clara_cropped.png')
def pdf_logo(width=120,height=82):
 from reportlab.platypus import Image
 if os.path.exists(LOGO_PATH):
  im=Image(LOGO_PATH,width=width,height=height); im.hAlign='LEFT'; return im
 return None
def monto_letras(n):
 n=int(round(float(n or 0))); u=['','UNO','DOS','TRES','CUATRO','CINCO','SEIS','SIETE','OCHO','NUEVE','DIEZ','ONCE','DOCE','TRECE','CATORCE','QUINCE','DIECISEIS','DIECISIETE','DIECIOCHO','DIECINUEVE','VEINTE','VEINTIUNO','VEINTIDOS','VEINTITRES','VEINTICUATRO','VEINTICINCO','VEINTISEIS','VEINTISIETE','VEINTIOCHO','VEINTINUEVE']; d=['','','TREINTA','CUARENTA','CINCUENTA','SESENTA','SETENTA','OCHENTA','NOVENTA']; ce=['','CIENTO','DOSCIENTOS','TRESCIENTOS','CUATROCIENTOS','QUINIENTOS','SEISCIENTOS','SETECIENTOS','OCHOCIENTOS','NOVECIENTOS']
 def sub(x):
  if x==0:return ''
  if x==100:return 'CIEN'
  if x<30:return u[x]
  if x<100:return d[x//10]+((' Y '+u[x%10]) if x%10 else '')
  return ce[x//100]+((' '+sub(x%100)) if x%100 else '')
 def conv(x):
  if x<1000:return sub(x)
  if x<1000000:
   q,r=divmod(x,1000);return ('MIL' if q==1 else sub(q)+' MIL')+((' '+sub(r)) if r else '')
  if x<1000000000:
   q,r=divmod(x,1000000);return ('UN MILLON' if q==1 else conv(q)+' MILLONES')+((' '+conv(r)) if r else '')
  q,r=divmod(x,1000000000);return ('MIL MILLONES' if q==1 else conv(q)+' MIL MILLONES')+((' '+conv(r)) if r else '')
 return conv(n)+' GUARANIES'
def desglosar_iva_incluido(importe, iva_pct):
 # El importe recibido es el precio FINAL, con IVA incluido.
 importe=float(importe or 0); tasa=float(iva_pct or 0)
 if tasa<=0:return importe,0.0
 base=importe/(1.0+tasa/100.0)
 return base,importe-base
def init():
 c=db();c.executescript('''
CREATE TABLE IF NOT EXISTS institucion_config(id INTEGER PRIMARY KEY CHECK(id=1),nombre TEXT DEFAULT 'CENTRO MEDICO SANTA CLARA',ruc TEXT DEFAULT '',timbrado TEXT DEFAULT '',direccion TEXT DEFAULT '',telefono TEXT DEFAULT '',email TEXT DEFAULT '');
CREATE TABLE IF NOT EXISTS usuarios(id INTEGER PRIMARY KEY,nombre TEXT,usuario TEXT UNIQUE,clave TEXT,rol TEXT,activo INT DEFAULT 1);
CREATE TABLE IF NOT EXISTS monedas(codigo TEXT PRIMARY KEY,nombre TEXT,simbolo TEXT,decimales INT DEFAULT 2,activa INT DEFAULT 1);
CREATE TABLE IF NOT EXISTS tipos_cambio(id INTEGER PRIMARY KEY,fecha TEXT,moneda TEXT,tipo REAL,fuente TEXT,UNIQUE(fecha,moneda));
CREATE TABLE IF NOT EXISTS plan_cuentas(codigo TEXT PRIMARY KEY,nombre TEXT,tipo TEXT,moneda TEXT DEFAULT 'PYG',imputable INT DEFAULT 1);
CREATE TABLE IF NOT EXISTS terceros(id INTEGER PRIMARY KEY,tipo TEXT,ruc TEXT,nombre TEXT,telefono TEXT,email TEXT,moneda TEXT DEFAULT 'PYG');
CREATE TABLE IF NOT EXISTS productos(id INTEGER PRIMARY KEY,codigo TEXT UNIQUE,nombre TEXT,categoria TEXT,costo_pyg REAL DEFAULT 0,precio_pyg REAL DEFAULT 0,stock REAL DEFAULT 0,stock_min REAL DEFAULT 0);
CREATE TABLE IF NOT EXISTS compras(id INTEGER PRIMARY KEY,fecha TEXT,proveedor_id INT,numero TEXT,moneda TEXT,tipo_cambio REAL,gravado REAL,iva REAL,exento REAL,total REAL,total_pyg REAL,estado TEXT DEFAULT 'CONFIRMADA');
CREATE TABLE IF NOT EXISTS compra_items(id INTEGER PRIMARY KEY,compra_id INT,producto_id INT,cantidad REAL,costo REAL,total REAL,total_pyg REAL);
CREATE TABLE IF NOT EXISTS ventas(id INTEGER PRIMARY KEY,fecha TEXT,cliente_id INT,numero TEXT,moneda TEXT,tipo_cambio REAL,gravado REAL,iva REAL,exento REAL,total REAL,total_pyg REAL,estado TEXT DEFAULT 'CONFIRMADA');
CREATE TABLE IF NOT EXISTS venta_items(id INTEGER PRIMARY KEY,venta_id INT,producto_id INT,cantidad REAL,precio REAL,total REAL,total_pyg REAL,costo_pyg REAL);
CREATE TABLE IF NOT EXISTS stock_mov(id INTEGER PRIMARY KEY,fecha TEXT,producto_id INT,tipo TEXT,cantidad REAL,costo_pyg REAL,origen_tipo TEXT,origen_id INT);
CREATE TABLE IF NOT EXISTS cxc(id INTEGER PRIMARY KEY,venta_id INT,tercero_id INT,moneda TEXT,tipo_cambio_origen REAL,importe REAL,saldo REAL,importe_pyg REAL,estado TEXT DEFAULT 'PENDIENTE');
CREATE TABLE IF NOT EXISTS cxp(id INTEGER PRIMARY KEY,compra_id INT,tercero_id INT,moneda TEXT,tipo_cambio_origen REAL,importe REAL,saldo REAL,importe_pyg REAL,estado TEXT DEFAULT 'PENDIENTE');
CREATE TABLE IF NOT EXISTS asientos(id INTEGER PRIMARY KEY,fecha TEXT,numero TEXT UNIQUE,concepto TEXT,origen_tipo TEXT,origen_id INT,moneda TEXT,tipo_cambio REAL,estado TEXT DEFAULT 'CONFIRMADO');
CREATE TABLE IF NOT EXISTS asiento_det(id INTEGER PRIMARY KEY,asiento_id INT,cuenta TEXT,debe_pyg REAL DEFAULT 0,haber_pyg REAL DEFAULT 0,importe_moneda REAL DEFAULT 0,moneda TEXT,tipo_cambio REAL,detalle TEXT);
CREATE TABLE IF NOT EXISTS caja_banco(id INTEGER PRIMARY KEY,fecha TEXT,tipo TEXT,medio TEXT,moneda TEXT,tipo_cambio REAL,importe REAL,importe_pyg REAL,concepto TEXT,origen_tipo TEXT,origen_id INT);
CREATE TABLE IF NOT EXISTS auditoria(id INTEGER PRIMARY KEY,fecha TEXT,usuario TEXT,accion TEXT,detalle TEXT);
CREATE TABLE IF NOT EXISTS pacientes(id INTEGER PRIMARY KEY,documento TEXT,nombre TEXT,fecha_nacimiento TEXT,telefono TEXT,direccion TEXT,tercero_id INT);
CREATE TABLE IF NOT EXISTS aseguradoras(id INTEGER PRIMARY KEY,nombre TEXT,ruc TEXT,tercero_id INT,moneda TEXT DEFAULT 'PYG');
CREATE TABLE IF NOT EXISTS medicos(id INTEGER PRIMARY KEY,nombre TEXT,registro TEXT,especialidad TEXT,tercero_id INT);
CREATE TABLE IF NOT EXISTS habitaciones(id INTEGER PRIMARY KEY,nombre TEXT,tipo TEXT);
CREATE TABLE IF NOT EXISTS camas(id INTEGER PRIMARY KEY,habitacion_id INT,codigo TEXT UNIQUE,estado TEXT DEFAULT 'LIBRE');
CREATE TABLE IF NOT EXISTS admisiones(id INTEGER PRIMARY KEY,fecha TEXT,paciente_id INT,tipo TEXT,medico_id INT,aseguradora_id INT,moneda TEXT,tipo_cambio REAL,estado TEXT DEFAULT 'ABIERTA',cama_id INT);
CREATE TABLE IF NOT EXISTS servicios(id INTEGER PRIMARY KEY,codigo TEXT UNIQUE,nombre TEXT,categoria TEXT,precio_pyg REAL,cuenta_ingreso TEXT DEFAULT '4.1.01');
CREATE TABLE IF NOT EXISTS cargos_paciente(id INTEGER PRIMARY KEY,fecha TEXT,admision_id INT,tipo TEXT,referencia_id INT,descripcion TEXT,cantidad REAL,precio REAL,moneda TEXT,tipo_cambio REAL,total REAL,total_pyg REAL,facturado INT DEFAULT 0);
CREATE TABLE IF NOT EXISTS facturas_sanatorio(id INTEGER PRIMARY KEY,fecha TEXT,admision_id INT,tercero_id INT,numero TEXT,moneda TEXT,tipo_cambio REAL,subtotal REAL,iva REAL,total REAL,total_pyg REAL,estado TEXT DEFAULT 'EMITIDA');
CREATE TABLE IF NOT EXISTS enfermeria(id INTEGER PRIMARY KEY,fecha TEXT,admision_id INT,nota TEXT,usuario TEXT);

''')
 c.execute("INSERT OR IGNORE INTO institucion_config(id,nombre) VALUES(1,'CENTRO MEDICO SANTA CLARA')")
 for x in [('PYG','Guaraní','Gs.',0),('USD','Dólar estadounidense','US$',2),('BRL','Real brasileño','R$',2),('EUR','Euro','€',2)]:c.execute('INSERT OR IGNORE INTO monedas(codigo,nombre,simbolo,decimales) VALUES(?,?,?,?)',x)
 cuentas=[('1.1.01','Caja y Bancos','ACTIVO'),('1.1.02','Clientes','ACTIVO'),('1.1.03','Inventarios','ACTIVO'),('1.1.04','IVA Crédito Fiscal','ACTIVO'),('2.1.01','Proveedores','PASIVO'),('2.1.02','IVA Débito Fiscal','PASIVO'),('4.1.01','Ventas de mercaderías','INGRESO'),('4.1.02','Servicios sanatoriales','INGRESO'),('4.1.03','Honorarios y procedimientos','INGRESO'),('5.1.01','Costo de Ventas','EGRESO'),('5.2.01','Pérdida por Diferencia de Cambio','EGRESO'),('4.2.01','Ganancia por Diferencia de Cambio','INGRESO')]
 for x in cuentas:c.execute('INSERT OR IGNORE INTO plan_cuentas(codigo,nombre,tipo) VALUES(?,?,?)',x)
 # Plan de cuentas referencial paraguayo para sanatorio. INSERT OR IGNORE preserva cuentas y datos existentes.
 cuentas_py=[('1','ACTIVO','ACTIVO'),('1.1','ACTIVO CORRIENTE','ACTIVO'),('1.1.01','Caja y Bancos','ACTIVO'),('1.1.02','Créditos por Ventas / Clientes','ACTIVO'),('1.1.03','Inventarios','ACTIVO'),('1.1.04','IVA Crédito Fiscal','ACTIVO'),('1.2','ACTIVO NO CORRIENTE','ACTIVO'),('1.2.01','Propiedad, Planta y Equipo','ACTIVO'),('1.2.02','Depreciación Acumulada','ACTIVO'),('2','PASIVO','PASIVO'),('2.1','PASIVO CORRIENTE','PASIVO'),('2.1.01','Proveedores','PASIVO'),('2.1.02','IVA Débito Fiscal','PASIVO'),('2.1.03','Honorarios Médicos a Pagar','PASIVO'),('2.1.04','Obligaciones Laborales','PASIVO'),('2.1.05','Impuestos y Retenciones a Pagar','PASIVO'),('3','PATRIMONIO NETO','PATRIMONIO'),('3.1.01','Capital','PATRIMONIO'),('3.1.02','Reservas','PATRIMONIO'),('3.1.03','Resultados Acumulados','PATRIMONIO'),('4','INGRESOS','INGRESO'),('4.1.01','Ventas de Medicamentos y Productos','INGRESO'),('4.1.02','Servicios Sanatoriales','INGRESO'),('4.1.03','Consultas y Procedimientos','INGRESO'),('4.1.04','Cirugías','INGRESO'),('4.2.01','Ganancia por Diferencia de Cambio','INGRESO'),('5','COSTOS Y GASTOS','EGRESO'),('5.1.01','Costo de Ventas','EGRESO'),('5.2.01','Pérdida por Diferencia de Cambio','EGRESO'),('5.3.01','Honorarios Médicos','EGRESO'),('5.4.01','Sueldos y Jornales','EGRESO'),('5.4.02','Cargas Sociales','EGRESO'),('5.5.01','Servicios Básicos','EGRESO'),('5.5.02','Mantenimiento y Reparaciones','EGRESO'),('5.5.03','Depreciaciones','EGRESO')]
 for x in cuentas_py:c.execute('INSERT OR IGNORE INTO plan_cuentas(codigo,nombre,tipo) VALUES(?,?,?)',x)
 if not c.execute('select 1 from usuarios').fetchone():c.execute('insert into usuarios(nombre,usuario,clave,rol) values(?,?,?,?)',('Administrador','admin',h('SantaClara2026!'),'ADMIN'))
 # Migración IVA por producto/servicio y desglose fiscal
 for tabla,col,defn in [
  ('productos','iva_pct','REAL DEFAULT 10'),('servicios','iva_pct','REAL DEFAULT 10'),('compra_items','iva_pct','REAL DEFAULT 10'),('venta_items','iva_pct','REAL DEFAULT 10'),('cargos_paciente','iva_pct','REAL DEFAULT 10'),
  ('compras','gravado_10','REAL DEFAULT 0'),('compras','iva_10','REAL DEFAULT 0'),('compras','gravado_5','REAL DEFAULT 0'),('compras','iva_5','REAL DEFAULT 0'),('compras','exento_iva','REAL DEFAULT 0'),
  ('ventas','gravado_10','REAL DEFAULT 0'),('ventas','iva_10','REAL DEFAULT 0'),('ventas','gravado_5','REAL DEFAULT 0'),('ventas','iva_5','REAL DEFAULT 0'),('ventas','exento_iva','REAL DEFAULT 0'),
  ('facturas_sanatorio','gravado_10','REAL DEFAULT 0'),('facturas_sanatorio','iva_10','REAL DEFAULT 0'),('facturas_sanatorio','gravado_5','REAL DEFAULT 0'),('facturas_sanatorio','iva_5','REAL DEFAULT 0'),('facturas_sanatorio','exento_iva','REAL DEFAULT 0')]:
  cols=[r['name'] for r in c.execute(f'pragma table_info({tabla})').fetchall()]
  if col not in cols:c.execute(f'alter table {tabla} add column {col} {defn}')
 # Migración incremental del Plan de Cuentas editable. No elimina ni reemplaza cuentas existentes.
 pc_cols=[r['name'] for r in c.execute('pragma table_info(plan_cuentas)').fetchall()]
 for col,defn in [('cuenta_padre','TEXT'),('naturaleza','TEXT'),('activa','INTEGER DEFAULT 1')]:
  if col not in pc_cols:c.execute(f'alter table plan_cuentas add column {col} {defn}')
 c.execute("update plan_cuentas set naturaleza=case when tipo in ('ACTIVO','EGRESO') then 'DEUDORA' else 'ACREEDORA' end where naturaleza is null or trim(naturaleza)='' ")
 c.execute("update plan_cuentas set activa=1 where activa is null")
 # Migración V13.5.0: condiciones de pago y cuotas de compras. Preserva todos los datos existentes.
 comp_cols=[r['name'] for r in c.execute('pragma table_info(compras)').fetchall()]
 for col,defn in [('condicion_pago',"TEXT DEFAULT 'CREDITO'"),('fecha_vencimiento','TEXT'),('entrega_inicial','REAL DEFAULT 0'),('medio_pago_inicial','TEXT'),('referencia_pago','TEXT'),('timbrado','TEXT'),('timbrado_vencimiento','TEXT')]:
  if col not in comp_cols:c.execute(f'alter table compras add column {col} {defn}')
 c.execute('''CREATE TABLE IF NOT EXISTS compra_cuotas(
   id INTEGER PRIMARY KEY, compra_id INTEGER NOT NULL, numero INTEGER NOT NULL,
   fecha_vencimiento TEXT NOT NULL, importe REAL NOT NULL DEFAULT 0,
   pagado REAL NOT NULL DEFAULT 0, estado TEXT NOT NULL DEFAULT 'PENDIENTE',
   UNIQUE(compra_id,numero))''')
 c.execute("update compras set condicion_pago='CREDITO' where condicion_pago is null or trim(condicion_pago)=''")
 # Migración V13.6.2: ventas a crédito en cuotas. Preserva ventas y CxC existentes.
 vcols=[r['name'] for r in c.execute('pragma table_info(ventas)').fetchall()]
 for col,defn in [('entrega_inicial','REAL DEFAULT 0'),('fecha_vencimiento','TEXT')]:
  if col not in vcols:c.execute(f'alter table ventas add column {col} {defn}')
 c.execute('''CREATE TABLE IF NOT EXISTS venta_cuotas(
   id INTEGER PRIMARY KEY, venta_id INTEGER NOT NULL, numero INTEGER NOT NULL,
   fecha_vencimiento TEXT NOT NULL, importe REAL NOT NULL DEFAULT 0,
   pagado REAL NOT NULL DEFAULT 0, estado TEXT NOT NULL DEFAULT 'PENDIENTE',
   UNIQUE(venta_id,numero))''')
 c.commit();c.close()
def audit(a,d=''):
 c=db();c.execute('insert into auditoria(fecha,usuario,accion,detalle) values(?,?,?,?)',(now(),session.get('user','sistema'),a,d));c.commit();c.close()
def asiento(c,fecha,concepto,origen_tipo,origen_id,moneda,tc,lineas):
 num=f'ASI-{datetime.datetime.now():%Y%m%d%H%M%S%f}';cur=c.execute('insert into asientos(fecha,numero,concepto,origen_tipo,origen_id,moneda,tipo_cambio) values(?,?,?,?,?,?,?)',(fecha,num,concepto,origen_tipo,origen_id,moneda,tc));aid=cur.lastrowid
 for cuenta,debe,haber,imp,det in lineas:c.execute('insert into asiento_det(asiento_id,cuenta,debe_pyg,haber_pyg,importe_moneda,moneda,tipo_cambio,detalle) values(?,?,?,?,?,?,?,?)',(aid,cuenta,debe,haber,imp,moneda,tc,det))
 return aid
def tc_fecha(c,fecha,moneda,tc_form):
 if moneda=='PYG':return 1.0
 tc=float(tc_form or 0)
 if tc<=0:
  r=c.execute('select tipo from tipos_cambio where fecha=? and moneda=?',(fecha,moneda)).fetchone();tc=float(r['tipo']) if r else 0
 if tc<=0:raise ValueError('Debe indicar el tipo de cambio para '+moneda)
 c.execute('insert into tipos_cambio(fecha,moneda,tipo,fuente) values(?,?,?,?) on conflict(fecha,moneda) do update set tipo=excluded.tipo,fuente=excluded.fuente',(fecha,moneda,tc,'Manual'))
 return tc
@app.before_request
def auth():
 if request.endpoint not in ('login','static','agenda_web_publica','agenda_web_reservar','agenda_web_confirmacion') and 'user' not in session:return redirect('/login')
@app.route('/login',methods=['GET','POST'])
def login():
 if request.method=='POST':
  c=db();u=c.execute('select * from usuarios where usuario=? and clave=? and activo=1',(request.form['usuario'],h(request.form['clave']))).fetchone();c.close()
  if u:session['user']=u['usuario'];session['name']=u['nombre'];return redirect('/')
  flash('Usuario o contraseña incorrectos')
 return render_template('login.html')
@app.get('/logout')
def logout():session.clear();return redirect('/login')
@app.route('/')
def home():
 c=db();stats={'Ventas (Gs.)':c.execute('select coalesce(sum(total_pyg),0) from ventas').fetchone()[0],'Compras (Gs.)':c.execute('select coalesce(sum(total_pyg),0) from compras').fetchone()[0],'CxC (Gs.)':c.execute('select coalesce(sum(importe_pyg*(saldo/importe)),0) from cxc where importe<>0').fetchone()[0],'CxP (Gs.)':c.execute('select coalesce(sum(importe_pyg*(saldo/importe)),0) from cxp where importe<>0').fetchone()[0]};c.close();return render_template('dashboard.html',stats=stats)
@app.route('/tipos-cambio',methods=['GET','POST'])
def tipos_cambio():
 c=db()
 if request.method=='POST':c.execute('insert into tipos_cambio(fecha,moneda,tipo,fuente) values(?,?,?,?) on conflict(fecha,moneda) do update set tipo=excluded.tipo,fuente=excluded.fuente',(request.form['fecha'],request.form['moneda'],float(request.form['tipo']),request.form.get('fuente','Manual')));c.commit();audit('TIPO_CAMBIO',request.form['moneda']);return redirect('/tipos-cambio')
 rows=c.execute('select * from tipos_cambio order by fecha desc,moneda').fetchall();mons=c.execute("select * from monedas where codigo<>'PYG'").fetchall();c.close();return render_template('exchange.html',rows=rows,mons=mons)
@app.route('/terceros',methods=['GET','POST'])
def terceros():
 c=db()
 if request.method=='POST':c.execute('insert into terceros(tipo,ruc,nombre,telefono,email,moneda) values(?,?,?,?,?,?)',(request.form['tipo'],request.form['ruc'],request.form['nombre'],request.form.get('telefono'),request.form.get('email'),request.form['moneda']));c.commit();return redirect('/terceros')
 rows=c.execute('select * from terceros order by nombre').fetchall();mons=c.execute('select * from monedas').fetchall();c.close();return render_template('thirdparties.html',rows=rows,mons=mons)
def init_v1357_codigo_barras():
 c=db()
 try:
  tabla=c.execute("select 1 from sqlite_master where type='table' and name='productos'").fetchone()
  if not tabla:
   # Protección adicional: si la tabla base no existe por una instalación incompleta, no ejecutar ALTER TABLE.
   return
  cols=[r['name'] for r in c.execute('pragma table_info(productos)').fetchall()]
  if 'codigo_barras' not in cols:
   c.execute('alter table productos add column codigo_barras TEXT')
  c.execute("create unique index if not exists ux_productos_codigo_barras on productos(codigo_barras) where codigo_barras is not null and trim(codigo_barras)<>''")
  c.commit()
 finally:
  c.close()
# La migración se ejecuta después de init(), junto con el resto de migraciones.

@app.route('/productos',methods=['GET','POST'])
def productos():
 c=db()
 if request.method=='POST':
  try:
   cb=(request.form.get('codigo_barras') or '').strip() or None
   if cb and c.execute('select 1 from productos where codigo_barras=?',(cb,)).fetchone():raise ValueError('Código de barras ya registrado en otro producto.')
   c.execute('insert into productos(codigo,codigo_barras,nombre,categoria,costo_pyg,precio_pyg,stock,stock_min,iva_pct,resumido,moneda,tipo_producto,presentacion,generico,laboratorio,distribuidora,droga,indicacion,posologia,tipo_controlado,especialidad,clasif_general,clasif_parcial,descripcion,vencimiento_control,lote_control,permitir_salida,activo) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(request.form['codigo'],cb,request.form['nombre'],request.form.get('categoria',''),float(request.form.get('costo_pyg') or 0),float(request.form.get('precio_pyg') or 0),float(request.form.get('stock') or 0),float(request.form.get('stock_min') or 0),float(request.form.get('iva_pct') or 0),request.form.get('resumido',''),request.form.get('moneda','PYG'),request.form.get('tipo_producto',''),request.form.get('presentacion',''),request.form.get('generico',''),request.form.get('laboratorio',''),request.form.get('distribuidora',''),request.form.get('droga',''),request.form.get('indicacion',''),request.form.get('posologia',''),request.form.get('tipo_controlado',''),request.form.get('especialidad',''),request.form.get('clasif_general',''),request.form.get('clasif_parcial',''),request.form.get('descripcion',''),1 if request.form.get('vencimiento_control') else 0,1 if request.form.get('lote_control') else 0,1 if request.form.get('permitir_salida') else 0,1));c.commit();flash('Producto registrado correctamente.')
  except Exception as e:c.rollback();flash('No se pudo registrar el producto: '+str(e))
  c.close();return redirect('/productos')
 rows=c.execute('select * from productos order by nombre').fetchall();c.close();return render_template('products.html',rows=rows)
@app.route('/compras',methods=['GET','POST'])
def compras():
 c=db()
 if request.method=='POST':
  try:
   import json
   fecha=request.form['fecha'];mon=request.form['moneda'];tc=tc_fecha(c,fecha,mon,request.form.get('tipo_cambio'));sid=int(request.form['proveedor_id'])
   items=json.loads(request.form.get('items_json') or '[]')
   if not items: raise ValueError('Agregue al menos un ítem a la compra.')
   detalle=[];total=grav=iva=exento=g10=i10=g5=i5=0.0
   for x in items:
    pid=int(x.get('producto_id') or 0);qty=float(x.get('cantidad') or 0);cost=float(x.get('costo') or 0)
    if pid<=0 or qty<=0 or cost<0: raise ValueError('Revise producto, cantidad y costo de todos los ítems.')
    prod=c.execute('select * from productos where id=?',(pid,)).fetchone()
    if not prod: raise ValueError('Uno de los productos ya no existe.')
    iva_pct=float(prod['iva_pct'] or 0);bruto=qty*cost;base,iva_item=desglosar_iva_incluido(bruto,iva_pct)
    total+=bruto;iva+=iva_item
    if iva_pct==10:g10+=base;i10+=iva_item;grav+=base
    elif iva_pct==5:g5+=base;i5+=iva_item;grav+=base
    else:exento+=bruto
    detalle.append((pid,qty,cost,base,iva_pct))
   totg=total*tc;ivag=iva*tc
   condicion=request.form.get('condicion_pago','CONTADO').upper(); venc=request.form.get('fecha_vencimiento') or None; entrega=max(0,float(request.form.get('entrega_inicial') or 0)); medio=request.form.get('medio_pago_inicial') or None; ref=request.form.get('referencia_pago') or None; timbrado=(request.form.get('timbrado') or '').strip(); timbrado_venc=(request.form.get('timbrado_vencimiento') or '').strip()
   if not timbrado: raise ValueError('Debe cargar el número de timbrado del comprobante.')
   if not timbrado_venc: raise ValueError('Debe cargar la fecha de vencimiento del timbrado.')
   if fecha > timbrado_venc: raise ValueError('No se puede registrar la compra: el timbrado del comprobante se encuentra vencido para la fecha indicada.')
   if condicion=='CONTADO': entrega=total; venc=None
   elif condicion=='CREDITO': entrega=0
   elif condicion=='CUOTAS':
    if entrega>total: raise ValueError('La entrega inicial no puede superar el total de la compra.')
   else: raise ValueError('Condición de pago no válida.')
   cur=c.execute('insert into compras(fecha,proveedor_id,numero,moneda,tipo_cambio,gravado,iva,exento,total,total_pyg,gravado_10,iva_10,gravado_5,iva_5,exento_iva,condicion_pago,fecha_vencimiento,entrega_inicial,medio_pago_inicial,referencia_pago,timbrado,timbrado_vencimiento) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(fecha,sid,request.form['numero'],mon,tc,grav,iva,exento,total,totg,g10,i10,g5,i5,exento,condicion,venc,entrega,medio,ref,timbrado,timbrado_venc));cid=cur.lastrowid
   for pid,qty,cost,base,iva_pct in detalle:
    c.execute('insert into compra_items(compra_id,producto_id,cantidad,costo,total,total_pyg,iva_pct) values(?,?,?,?,?,?,?)',(cid,pid,qty,cost,base,base*tc,iva_pct))
    costo_unit_pyg=(base/qty*tc if qty else 0)
    c.execute('update productos set stock=stock+?,costo_pyg=? where id=?',(qty,costo_unit_pyg,pid))
    c.execute('insert into stock_mov(fecha,producto_id,tipo,cantidad,costo_pyg,origen_tipo,origen_id) values(?,?,?,?,?,?,?)',(fecha,pid,'ENTRADA',qty,costo_unit_pyg,'COMPRA',cid))
   saldo=max(0,total-entrega)
   if saldo>0:c.execute('insert into cxp(compra_id,tercero_id,moneda,tipo_cambio_origen,importe,saldo,importe_pyg) values(?,?,?,?,?,?,?)',(cid,sid,mon,tc,saldo,saldo,saldo*tc))
   if condicion=='CREDITO':
    if not venc: raise ValueError('Debe indicar la fecha de vencimiento para una compra a crédito.')
    c.execute('insert into compra_cuotas(compra_id,numero,fecha_vencimiento,importe) values(?,?,?,?)',(cid,1,venc,saldo))
   elif condicion=='CUOTAS':
    cuotas=json.loads(request.form.get('cuotas_json') or '[]')
    if saldo>0 and not cuotas: raise ValueError('Debe cargar al menos una cuota para el saldo financiado.')
    suma=round(sum(float(x.get('importe') or 0) for x in cuotas),2)
    if abs(suma-round(saldo,2))>0.01: raise ValueError(f'La suma de cuotas ({suma:,.2f}) debe ser igual al saldo financiado ({saldo:,.2f}).')
    for n,x in enumerate(cuotas,1):
     fv=x.get('fecha'); imp=float(x.get('importe') or 0)
     if not fv or imp<=0: raise ValueError('Cada cuota debe tener vencimiento e importe mayor a cero.')
     c.execute('insert into compra_cuotas(compra_id,numero,fecha_vencimiento,importe) values(?,?,?,?)',(cid,n,fv,imp))
   if entrega>0:c.execute('insert into caja_banco(fecha,tipo,medio,moneda,tipo_cambio,importe,importe_pyg,concepto,origen_tipo,origen_id) values(?,?,?,?,?,?,?,?,?,?)',(fecha,'EGRESO',medio or 'EFECTIVO',mon,tc,entrega,entrega*tc,'Pago/entrega compra '+request.form['numero'],'COMPRA',cid))
   lineas=[('1.1.03',grav*tc,0,grav,'Inventario'),('1.1.04',ivag,0,iva,'IVA crédito')]
   if exento>0: lineas.append(('1.1.03',exento*tc,0,exento,'Inventario exento'))
   if entrega>0: lineas.append(('1.1.01',0,entrega*tc,entrega,'Pago/entrega inicial'))
   if saldo>0: lineas.append(('2.1.01',0,saldo*tc,saldo,'Proveedor'))
   asiento(c,fecha,'Compra '+request.form['numero'],'COMPRA',cid,mon,tc,lineas);c.commit();audit('COMPRA',str(cid));flash('Compra registrada correctamente con '+str(len(detalle))+' ítem(s).')
  except Exception as e:c.rollback();flash(str(e))
  return redirect('/compras')
 q=(request.args.get('q') or '').strip(); buscado=bool(q); rows=[]
 if buscado:
  like='%'+q+'%'
  rows=c.execute("select x.*,t.nombre tercero from compras x join terceros t on t.id=x.proveedor_id where x.numero like ? or t.nombre like ? or coalesce(x.estado,'') like ? or x.fecha like ? order by x.id desc limit 200",(like,like,like,like)).fetchall()
 ters=c.execute("select * from terceros where tipo in ('PROVEEDOR','AMBOS')").fetchall();prods=[];mons=c.execute('select * from monedas').fetchall();c.close();return render_template('transaction.html',kind='Compra',rows=rows,ters=ters,prods=prods,mons=mons,buscado=buscado,q=q)



def _compra_tiene_pagos(c, compra_id):
    return c.execute("select 1 from caja_banco where origen_tipo='PAGO' and origen_id in (select id from cxp where compra_id=?) limit 1",(compra_id,)).fetchone() is not None

def _quitar_efectos_compra(c, compra_id, borrar_documento=False):
    # Quita todos los efectos activos de una compra para edición/eliminación atómica.
    items=c.execute('select * from compra_items where compra_id=?',(compra_id,)).fetchall()
    for it in items:
        c.execute('update productos set stock=stock-? where id=?',(float(it['cantidad'] or 0),it['producto_id']))
    c.execute("delete from stock_mov where origen_tipo in ('COMPRA','ANULACION_COMPRA','ANULACION_COMPRA_EDICION') and origen_id=?",(compra_id,))
    c.execute("delete from caja_banco where origen_tipo='COMPRA' and origen_id=?",(compra_id,))
    c.execute('delete from compra_cuotas where compra_id=?',(compra_id,))
    c.execute('delete from cxp where compra_id=?',(compra_id,))
    aids=[r['id'] for r in c.execute("select id from asientos where origen_tipo in ('COMPRA','REV_COMPRA') and origen_id=?",(compra_id,)).fetchall()]
    for aid in aids:c.execute('delete from asiento_det where asiento_id=?',(aid,))
    c.execute("delete from asientos where origen_tipo in ('COMPRA','REV_COMPRA') and origen_id=?",(compra_id,))
    c.execute('delete from compra_items where compra_id=?',(compra_id,))
    if borrar_documento:c.execute('delete from compras where id=?',(compra_id,))

def _aplicar_compra_desde_form(c, compra_id, form):
    import json
    fecha=form['fecha']; mon=form['moneda']; tc=tc_fecha(c,fecha,mon,form.get('tipo_cambio')); sid=int(form['proveedor_id'])
    items=json.loads(form.get('items_json') or '[]')
    if not items:raise ValueError('Agregue al menos un ítem a la compra.')
    detalle=[];total=grav=iva=exento=g10=i10=g5=i5=0.0
    for x in items:
        pid=int(x.get('producto_id') or 0);qty=float(x.get('cantidad') or 0);cost=float(x.get('costo') or 0)
        if pid<=0 or qty<=0 or cost<0:raise ValueError('Revise producto, cantidad y costo de todos los ítems.')
        prod=c.execute('select * from productos where id=?',(pid,)).fetchone()
        if not prod:raise ValueError('Uno de los productos ya no existe.')
        iva_pct=float(prod['iva_pct'] or 0);bruto=qty*cost;base,iva_item=desglosar_iva_incluido(bruto,iva_pct)
        total+=bruto;iva+=iva_item
        if iva_pct==10:g10+=base;i10+=iva_item;grav+=base
        elif iva_pct==5:g5+=base;i5+=iva_item;grav+=base
        else:exento+=bruto
        detalle.append((pid,qty,cost,base,iva_pct))
    condicion=form.get('condicion_pago','CONTADO').upper();venc=form.get('fecha_vencimiento') or None;entrega=max(0,float(form.get('entrega_inicial') or 0));medio=form.get('medio_pago_inicial') or None;ref=form.get('referencia_pago') or None;timbrado=(form.get('timbrado') or '').strip();timbrado_venc=(form.get('timbrado_vencimiento') or '').strip()
    if not timbrado:raise ValueError('Debe cargar el número de timbrado del comprobante.')
    if not timbrado_venc:raise ValueError('Debe cargar la fecha de vencimiento del timbrado.')
    if fecha > timbrado_venc:raise ValueError('No se puede guardar la compra: el timbrado del comprobante se encuentra vencido para la fecha indicada.')
    if condicion=='CONTADO':entrega=total;venc=None
    elif condicion=='CREDITO':entrega=0
    elif condicion=='CUOTAS':
        if entrega>total:raise ValueError('La entrega inicial no puede superar el total de la compra.')
    else:raise ValueError('Condición de pago no válida.')
    totg=total*tc;ivag=iva*tc
    c.execute('''update compras set fecha=?,proveedor_id=?,numero=?,moneda=?,tipo_cambio=?,gravado=?,iva=?,exento=?,total=?,total_pyg=?,gravado_10=?,iva_10=?,gravado_5=?,iva_5=?,exento_iva=?,condicion_pago=?,fecha_vencimiento=?,entrega_inicial=?,medio_pago_inicial=?,referencia_pago=?,timbrado=?,timbrado_vencimiento=?,estado='CONFIRMADA' where id=?''',(fecha,sid,form['numero'],mon,tc,grav,iva,exento,total,totg,g10,i10,g5,i5,exento,condicion,venc,entrega,medio,ref,timbrado,timbrado_venc,compra_id))
    for pid,qty,cost,base,iva_pct in detalle:
        c.execute('insert into compra_items(compra_id,producto_id,cantidad,costo,total,total_pyg,iva_pct) values(?,?,?,?,?,?,?)',(compra_id,pid,qty,cost,base,base*tc,iva_pct))
        costo_unit_pyg=(base/qty*tc if qty else 0);c.execute('update productos set stock=stock+?,costo_pyg=? where id=?',(qty,costo_unit_pyg,pid));c.execute('insert into stock_mov(fecha,producto_id,tipo,cantidad,costo_pyg,origen_tipo,origen_id) values(?,?,?,?,?,?,?)',(fecha,pid,'ENTRADA',qty,costo_unit_pyg,'COMPRA',compra_id))
    saldo=max(0,total-entrega)
    if saldo>0:c.execute('insert into cxp(compra_id,tercero_id,moneda,tipo_cambio_origen,importe,saldo,importe_pyg) values(?,?,?,?,?,?,?)',(compra_id,sid,mon,tc,saldo,saldo,saldo*tc))
    if condicion=='CREDITO':
        if not venc:raise ValueError('Debe indicar la fecha de vencimiento para una compra a crédito.')
        c.execute('insert into compra_cuotas(compra_id,numero,fecha_vencimiento,importe) values(?,?,?,?)',(compra_id,1,venc,saldo))
    elif condicion=='CUOTAS':
        cuotas=json.loads(form.get('cuotas_json') or '[]');suma=round(sum(float(x.get('importe') or 0) for x in cuotas),2)
        if saldo>0 and not cuotas:raise ValueError('Debe cargar al menos una cuota para el saldo financiado.')
        if abs(suma-round(saldo,2))>0.01:raise ValueError(f'La suma de cuotas ({suma:,.2f}) debe ser igual al saldo financiado ({saldo:,.2f}).')
        for n,x in enumerate(cuotas,1):
            fv=x.get('fecha');imp=float(x.get('importe') or 0)
            if not fv or imp<=0:raise ValueError('Cada cuota debe tener vencimiento e importe mayor a cero.')
            c.execute('insert into compra_cuotas(compra_id,numero,fecha_vencimiento,importe) values(?,?,?,?)',(compra_id,n,fv,imp))
    if entrega>0:c.execute('insert into caja_banco(fecha,tipo,medio,moneda,tipo_cambio,importe,importe_pyg,concepto,origen_tipo,origen_id) values(?,?,?,?,?,?,?,?,?,?)',(fecha,'EGRESO',medio or 'EFECTIVO',mon,tc,entrega,entrega*tc,'Pago/entrega compra '+form['numero'],'COMPRA',compra_id))
    lineas=[('1.1.03',grav*tc,0,grav,'Inventario'),('1.1.04',ivag,0,iva,'IVA crédito')]
    if exento>0:lineas.append(('1.1.03',exento*tc,0,exento,'Inventario exento'))
    if entrega>0:lineas.append(('1.1.01',0,entrega*tc,entrega,'Pago/entrega inicial'))
    if saldo>0:lineas.append(('2.1.01',0,saldo*tc,saldo,'Proveedor'))
    asiento(c,fecha,'Compra '+form['numero'],'COMPRA',compra_id,mon,tc,lineas)

@app.get('/compras/<int:compra_id>/ver')
def compra_ver(compra_id):
    c=db();comp=c.execute('select co.*,t.nombre tercero,t.ruc from compras co left join terceros t on t.id=co.proveedor_id where co.id=?',(compra_id,)).fetchone()
    if not comp:c.close();flash('Compra no encontrada.');return redirect('/compras')
    items=c.execute('select ci.*,p.codigo,p.nombre from compra_items ci left join productos p on p.id=ci.producto_id where ci.compra_id=? order by ci.id',(compra_id,)).fetchall();cuotas=c.execute('select * from compra_cuotas where compra_id=? order by numero,id',(compra_id,)).fetchall();c.close()
    return render_template('purchase_detail.html',comp=comp,items=items,cuotas=cuotas)

@app.route('/compras/<int:compra_id>/editar',methods=['GET','POST'])
def compra_editar(compra_id):
    c=db();comp=c.execute('select * from compras where id=?',(compra_id,)).fetchone()
    if not comp:c.close();flash('Compra no encontrada.');return redirect('/compras')
    if comp['estado']=='ANULADA':c.close();flash('Una compra anulada no puede modificarse.');return redirect('/compras')
    if request.method=='POST':
        try:
            if _compra_tiene_pagos(c,compra_id):raise ValueError('No se puede modificar: primero debe revertir los pagos aplicados a esta compra.')
            antes={'compra':dict(comp),'items':[dict(x) for x in c.execute('select * from compra_items where compra_id=?',(compra_id,)).fetchall()]}
            c.execute('SAVEPOINT editar_compra');_quitar_efectos_compra(c,compra_id,False);_aplicar_compra_desde_form(c,compra_id,request.form);desp=c.execute('select * from compras where id=?',(compra_id,)).fetchone();audit_change(c,'MODIFICAR','COMPRAS',compra_id,antes,{'compra':dict(desp)},request.form.get('motivo','Modificación de compra'));c.execute('RELEASE editar_compra');c.commit();flash('Compra modificada. Stock, CxP, cuotas, Libro Compras, IVA y Contabilidad fueron actualizados.')
        except Exception as e:
            try:c.execute('ROLLBACK TO editar_compra')
            except:pass
            c.rollback();flash('No se pudo modificar la compra: '+str(e))
        c.close();return redirect(f'/compras/{compra_id}/ver')
    items=c.execute('select ci.*,p.codigo,p.nombre from compra_items ci left join productos p on p.id=ci.producto_id where ci.compra_id=? order by ci.id',(compra_id,)).fetchall();cuotas=c.execute('select * from compra_cuotas where compra_id=? order by numero,id',(compra_id,)).fetchall();ters=c.execute("select * from terceros where tipo in ('PROVEEDOR','AMBOS') order by nombre").fetchall();prods=c.execute('select * from productos order by nombre').fetchall();mons=c.execute('select * from monedas where activa=1 order by codigo').fetchall();c.close();return render_template('purchase_edit.html',comp=comp,items=items,cuotas=cuotas,ters=ters,prods=prods,mons=mons)

@app.post('/compras/<int:compra_id>/eliminar')
def compra_eliminar(compra_id):
    c=db();comp=c.execute('select * from compras where id=?',(compra_id,)).fetchone()
    if not comp:c.close();return redirect('/compras')
    try:
        if _compra_tiene_pagos(c,compra_id):raise ValueError('No se puede eliminar: primero debe revertir los pagos aplicados a esta compra.')
        antes={'compra':dict(comp),'items':[dict(x) for x in c.execute('select * from compra_items where compra_id=?',(compra_id,)).fetchall()]};_quitar_efectos_compra(c,compra_id,True);audit_change(c,'ELIMINAR','COMPRAS',compra_id,antes,{},request.form.get('motivo','Eliminación de compra'));c.commit();flash('Compra eliminada de Compras, Stock, CxP, cuotas, Libro Compras, IVA y Contabilidad.')
    except Exception as e:c.rollback();flash(str(e))
    c.close();return redirect('/compras')

@app.route('/compras/<int:compra_id>/cuotas',methods=['GET','POST'])
def compra_cuotas(compra_id):
 c=db();comp=c.execute('select co.*,t.nombre tercero from compras co left join terceros t on t.id=co.proveedor_id where co.id=?',(compra_id,)).fetchone()
 if not comp:c.close();flash('Compra no encontrada.');return redirect('/compras')
 if request.method=='POST':
  try:
   accion=request.form.get('accion');qid=int(request.form.get('cuota_id') or 0)
   if accion=='NUEVA':
    prox=c.execute('select coalesce(max(numero),0)+1 from compra_cuotas where compra_id=?',(compra_id,)).fetchone()[0];c.execute('insert into compra_cuotas(compra_id,numero,fecha_vencimiento,importe) values(?,?,?,?)',(compra_id,prox,request.form['fecha_vencimiento'],float(request.form['importe'])))
   elif accion=='MODIFICAR':
    q=c.execute('select * from compra_cuotas where id=? and compra_id=?',(qid,compra_id)).fetchone()
    if not q or float(q['pagado'] or 0)>0:raise ValueError('No se puede modificar una cuota que ya tiene pagos aplicados.')
    c.execute('update compra_cuotas set fecha_vencimiento=?,importe=? where id=?',(request.form['fecha_vencimiento'],float(request.form['importe']),qid))
   elif accion=='ELIMINAR':
    q=c.execute('select * from compra_cuotas where id=? and compra_id=?',(qid,compra_id)).fetchone()
    if not q or float(q['pagado'] or 0)>0:raise ValueError('No se puede eliminar una cuota que ya tiene pagos aplicados.')
    c.execute('delete from compra_cuotas where id=?',(qid,))
   suma=c.execute('select coalesce(sum(importe),0) from compra_cuotas where compra_id=?',(compra_id,)).fetchone()[0];esperado=max(0,float(comp['total'] or 0)-float(comp['entrega_inicial'] or 0))
   c.execute('update cxp set importe=?,saldo=max(0,?-coalesce((importe-saldo),0)),importe_pyg=?*tipo_cambio_origen where compra_id=?',(suma,suma,suma,compra_id));c.commit();audit('CUOTAS_COMPRA',f'{compra_id}:{accion}:{qid}');flash(f'Plan actualizado. Cuotas: {suma:,.2f}; saldo originalmente financiado: {esperado:,.2f}.')
  except Exception as e:c.rollback();flash(str(e))
  return redirect(f'/compras/{compra_id}/cuotas')
 cuotas=c.execute('select * from compra_cuotas where compra_id=? order by numero,id',(compra_id,)).fetchall();c.close();return render_template('purchase_installments.html',comp=comp,cuotas=cuotas)

@app.get('/ventas')
def ventas_unificado():
 c=db();ap=caja_abierta(c) if 'caja_abierta' in globals() else None
 hoy=datetime.date.today().isoformat()
 try:
  agenda_hoy=c.execute('select count(*) from agenda where fecha=?',(hoy,)).fetchone()[0]
  pendientes=c.execute("select count(*) from agenda where fecha=? and coalesce(cobrado,0)=0",(hoy,)).fetchone()[0]
  ventas_hoy=c.execute('select coalesce(sum(total_pyg),0) from ventas where fecha=?',(hoy,)).fetchone()[0]
 except Exception:
  agenda_hoy=pendientes=0;ventas_hoy=0
 c.close()
 return render_template('ventas_unificado.html',ap=ap,hoy=hoy,agenda_hoy=agenda_hoy,pendientes=pendientes,ventas_hoy=ventas_hoy)

@app.route('/ventas/carga',methods=['GET','POST'])
def ventas():
 c=db()
 if request.method=='POST':
  try:
   fecha=request.form['fecha'];mon=request.form['moneda'];tc=tc_fecha(c,fecha,mon,request.form.get('tipo_cambio'))
   condicion=(request.form.get('condicion_venta') or 'CONTADO').upper();medio=(request.form.get('forma_cobro') or '').strip();ref=(request.form.get('referencia_cobro') or '').strip();cuenta_id=int(request.form.get('cuenta_bancaria_id') or 0) or None;pos_id=int(request.form.get('terminal_pos_id') or 0) or None
   if condicion not in ('CONTADO','CREDITO','CUOTAS'):raise ValueError('Condición de venta inválida')
   entrega=max(0,float(request.form.get('entrega_inicial_venta') or 0));venc=request.form.get('fecha_vencimiento_venta') or None
   if condicion=='CONTADO':entrega=0
   if condicion=='CREDITO' and not venc:raise ValueError('Debe indicar la fecha de vencimiento para la venta a crédito')
   if condicion in ('CONTADO','CUOTAS') and (condicion=='CONTADO' or entrega>0) and medio not in ('Efectivo','Banco','Transferencia','POS'):raise ValueError('Seleccione la forma de cobro')
   if condicion in ('CONTADO','CUOTAS') and (condicion=='CONTADO' or entrega>0) and medio=='Efectivo' and not caja_abierta(c):raise ValueError('Debe abrir Recepción y Caja antes de registrar un cobro en efectivo')
   if condicion in ('CONTADO','CUOTAS') and (condicion=='CONTADO' or entrega>0) and medio in ('Banco','Transferencia','POS') and not cuenta_id:raise ValueError('Seleccione la cuenta bancaria receptora')
   if condicion in ('CONTADO','CUOTAS') and (condicion=='CONTADO' or entrega>0) and medio=='POS' and not pos_id:raise ValueError('Seleccione la terminal POS')
   import json
   raw=request.form.get('items_json','')
   if raw:
    try: items=json.loads(raw)
    except Exception: raise ValueError('No se pudo leer el detalle de la venta')
   else:
    # Compatibilidad con formularios/versiones anteriores.
    items=[{'producto_id':request.form.get('producto_id'),'cantidad':request.form.get('cantidad'),'precio':request.form.get('costo')}]
   if not isinstance(items,list) or not items:raise ValueError('Agregue al menos un ítem a la venta')
   detalle=[];total=grav=iva=exento=g10=i10=g5=i5=costg=0.0
   acumulado_stock={}
   for it in items:
    try: pid=int(it.get('producto_id') or 0);qty=float(it.get('cantidad') or 0);price=float(it.get('precio') or 0)
    except Exception: raise ValueError('Revise producto, cantidad y precio de los ítems')
    if pid<=0 or qty<=0 or price<0:raise ValueError('Cada ítem debe tener producto, cantidad mayor a cero y precio válido')
    p=c.execute('select * from productos where id=?',(pid,)).fetchone()
    if not p:raise ValueError('Uno de los productos ya no existe')
    acumulado_stock[pid]=acumulado_stock.get(pid,0)+qty
    if float(p['stock'] or 0)<acumulado_stock[pid]:raise ValueError('Stock insuficiente para '+p['nombre'])
    iva_pct=float(p['iva_pct'] or 0);line_total=qty*price;base,line_iva=desglosar_iva_incluido(line_total,iva_pct)
    total+=line_total;iva+=line_iva;cost_line=qty*float(p['costo_pyg'] or 0);costg+=cost_line
    if iva_pct==10:g10+=base;i10+=line_iva;grav+=base
    elif iva_pct==5:g5+=base;i5+=line_iva;grav+=base
    else:exento+=line_total
    detalle.append((p,pid,qty,price,line_total,base,line_iva,iva_pct,cost_line))
   tid=int(request.form['proveedor_id']);totg=total*tc;ivag=iva*tc
   if condicion=='CUOTAS' and entrega>total:raise ValueError('La entrega inicial no puede superar el total de la venta')
   cuotas_venta=[]
   if condicion=='CUOTAS':
    cuotas_venta=json.loads(request.form.get('venta_cuotas_json') or '[]');saldo_fin=round(total-entrega,2)
    if saldo_fin>0 and not cuotas_venta:raise ValueError('Debe cargar al menos una cuota para el saldo financiado')
    suma=round(sum(float(x.get('importe') or 0) for x in cuotas_venta),2)
    if abs(suma-saldo_fin)>0.01:raise ValueError(f'La suma de cuotas ({suma:,.2f}) debe ser igual al saldo financiado ({saldo_fin:,.2f})')
   cur=c.execute('insert into ventas(fecha,cliente_id,numero,moneda,tipo_cambio,gravado,iva,exento,total,total_pyg,gravado_10,iva_10,gravado_5,iva_5,exento_iva,condicion_venta,forma_cobro,referencia_cobro,entrega_inicial,fecha_vencimiento) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(fecha,tid,request.form['numero'],mon,tc,grav,iva,exento,total,totg,g10,i10,g5,i5,exento,condicion,medio or None,ref or None,entrega,venc));vid=cur.lastrowid
   c.execute('update ventas set cuenta_bancaria_id=?,terminal_pos_id=? where id=?',(cuenta_id,pos_id,vid))
   for p,pid,qty,price,line_total,base,line_iva,iva_pct,cost_line in detalle:
    c.execute('insert into venta_items(venta_id,producto_id,cantidad,precio,total,total_pyg,costo_pyg,iva_pct) values(?,?,?,?,?,?,?,?)',(vid,pid,qty,price,line_total,line_total*tc,cost_line,iva_pct));c.execute('update productos set stock=stock-? where id=?',(qty,pid));c.execute('insert into stock_mov(fecha,producto_id,tipo,cantidad,costo_pyg,origen_tipo,origen_id) values(?,?,?,?,?,?,?)',(fecha,pid,'SALIDA',-qty,p['costo_pyg'],'VENTA',vid))
   saldo=0 if condicion=='CONTADO' else (total-entrega if condicion=='CUOTAS' else total);estado='PAGADO' if saldo<=0.0001 else 'PENDIENTE';c.execute('insert into cxc(venta_id,tercero_id,moneda,tipo_cambio_origen,importe,saldo,importe_pyg,estado) values(?,?,?,?,?,?,?,?)',(vid,tid,mon,tc,saldo,saldo,saldo*tc,estado))
   if condicion=='CREDITO':c.execute('insert into venta_cuotas(venta_id,numero,fecha_vencimiento,importe) values(?,?,?,?)',(vid,1,venc,total))
   elif condicion=='CUOTAS':
    for n,x in enumerate(cuotas_venta,1):
     fv=x.get('fecha');imp=float(x.get('importe') or 0)
     if not fv or imp<=0:raise ValueError('Cada cuota debe tener vencimiento e importe mayor a cero')
     c.execute('insert into venta_cuotas(venta_id,numero,fecha_vencimiento,importe) values(?,?,?,?)',(vid,n,fv,imp))
   cobro_inicial=total if condicion=='CONTADO' else (entrega if condicion=='CUOTAS' else 0)
   if cobro_inicial>0:
    c.execute('insert into caja_banco(fecha,tipo,medio,moneda,tipo_cambio,importe,importe_pyg,concepto,origen_tipo,origen_id,cuenta_bancaria_id,terminal_pos_id) values(?,?,?,?,?,?,?,?,?,?,?,?)',(fecha,'INGRESO',medio,mon,tc,cobro_inicial,cobro_inicial*tc,'Cobro inicial venta','VENTA',vid,cuenta_id,pos_id))
    if medio=='Efectivo':
     ap=caja_abierta(c);fid=c.execute("select id from formas_cobro where nombre='Efectivo'").fetchone();c.execute("insert into movimientos_caja(apertura_id,fecha,tipo,forma_cobro_id,concepto,importe_pyg,origen_tipo,origen_id,usuario) values(?,?,'INGRESO',?,?,?,?,?,?)",(ap['id'],now(),fid['id'] if fid else None,'Cobro inicial venta',cobro_inicial*tc,'VENTA',vid,session.get('user')))
   base_total=grav+exento;lineas=[]
   if cobro_inicial>0:lineas.append(('1.1.01',cobro_inicial*tc,0,cobro_inicial,'Cobro inicial'))
   if saldo>0:lineas.append(('1.1.02',saldo*tc,0,saldo,'Cuenta a cobrar'))
   lineas += [('4.1.01',0,base_total*tc,base_total,'Venta'),('2.1.02',0,ivag,iva,'IVA débito'),('5.1.01',costg,0,0,'Costo de venta'),('1.1.03',0,costg,0,'Salida inventario')]
   asiento(c,fecha,'Venta '+request.form['numero'],'VENTA',vid,mon,tc,lineas);c.commit();audit('VENTA',str(vid));flash('Venta registrada con '+str(len(detalle))+' ítem(s).')
  except Exception as e:c.rollback();flash(str(e))
  finally:c.close()
  return redirect('/ventas/carga')
 q=(request.args.get('q') or '').strip(); buscado=bool(q); rows=[]
 if buscado:
  like='%'+q+'%'
  rows=c.execute("select x.*,t.nombre tercero from ventas x join terceros t on t.id=x.cliente_id where x.numero like ? or t.nombre like ? or coalesce(x.estado,'') like ? or x.fecha like ? order by x.id desc limit 200",(like,like,like,like)).fetchall()
 ters=c.execute("select * from terceros where tipo in ('CLIENTE','AMBOS')").fetchall();prods=[];mons=c.execute('select * from monedas').fetchall();cuentas=c.execute('select * from cuentas_bancarias where activo=1 order by banco,alias').fetchall();poses=c.execute('select * from terminales_pos where activo=1 order by nombre').fetchall();c.close();return render_template('transaction.html',kind='Venta',rows=rows,ters=ters,prods=prods,mons=mons,cuentas=cuentas,poses=poses,buscado=buscado,q=q)

@app.route('/ventas/recepcion-caja',methods=['GET','POST'])
def recepcion_caja_unificada():
 c=db();ap=caja_abierta(c);hoy=datetime.date.today().isoformat()
 if request.method=='POST':
  op=request.form.get('op')
  if op=='abrir':
   if ap:flash('Ya tiene una caja abierta.')
   else:c.execute('insert into aperturas_caja(caja_id,usuario,fecha_apertura,saldo_inicial) values(?,?,?,?)',(int(request.form['caja_id']),session['user'],now(),float(request.form.get('saldo_inicial') or 0)));c.commit();flash('Caja abierta correctamente.')
  elif op=='cerrar':
   if not ap:flash('No existe una caja abierta.')
   else:
    movsum=c.execute("select coalesce(sum(case when tipo='INGRESO' then importe_pyg else -importe_pyg end),0) from movimientos_caja where apertura_id=?",(ap['id'],)).fetchone()[0];sistema=float(ap['saldo_inicial'])+float(movsum);decl=float(request.form.get('total_declarado') or 0);c.execute("update aperturas_caja set fecha_cierre=?,total_sistema=?,total_declarado=?,diferencia=?,estado='CERRADA' where id=?",(now(),sistema,decl,decl-sistema,ap['id']));c.commit();flash('Caja cerrada. Diferencia: Gs. {:,.0f}'.format(decl-sistema))
  c.close();return redirect('/ventas/recepcion-caja')
 rows=c.execute('''select g.*,p.nombre paciente,p.documento,p.telefono,m.nombre medico,e.nombre especialidad from agenda g join pacientes p on p.id=g.paciente_id join medicos m on m.id=g.medico_id left join especialidades e on e.id=g.especialidad_id where g.fecha=? order by g.hora,g.id''',(hoy,)).fetchall();cajas=c.execute('select * from cajas where activo=1').fetchall();hist=c.execute('select * from aperturas_caja where usuario=? order by id desc limit 10',(session['user'],)).fetchall();mov=[]
 if ap:mov=c.execute('''select m.*,f.nombre forma from movimientos_caja m left join formas_cobro f on f.id=m.forma_cobro_id where m.apertura_id=? order by m.id desc''',(ap['id'],)).fetchall()
 c.close();return render_template('reception_cash_unified.html',rows=rows,ap=ap,hoy=hoy,cajas=cajas,hist=hist,mov=mov)

@app.route('/ventas/cobrar/<int:cxc_id>',methods=['GET','POST'])
def cobrar_venta_credito(cxc_id):
 c=db();r=c.execute('''select x.*,v.numero factura,t.nombre cliente,t.ruc from cxc x join ventas v on v.id=x.venta_id join terceros t on t.id=x.tercero_id where x.id=?''',(cxc_id,)).fetchone()
 if not r:c.close();flash('Cuenta por cobrar no encontrada.');return redirect('/finanzas')
 if request.method=='POST':
  try:
   if float(r['saldo'] or 0)<=0:raise ValueError('La cuenta ya está pagada')
   imp=float(request.form['importe']);
   if imp<=0 or imp>float(r['saldo']):raise ValueError('Importe de cobro inválido')
   medio=request.form['medio'];ref=request.form.get('referencia','').strip();cuenta_id=int(request.form.get('cuenta_bancaria_id') or 0) or None;pos_id=int(request.form.get('terminal_pos_id') or 0) or None
   if medio in ('Banco','Transferencia','POS') and not cuenta_id:raise ValueError('Seleccione la cuenta bancaria receptora')
   if medio=='POS' and not pos_id:raise ValueError('Seleccione la terminal POS')
   fecha=request.form['fecha'];tc=tc_fecha(c,fecha,r['moneda'],request.form.get('tipo_cambio'));pyg=imp*tc;anterior=float(r['saldo']);restante=anterior-imp
   c.execute("update cxc set saldo=?,estado=? where id=?",(restante,'PAGADO' if restante<=0.0001 else 'PENDIENTE',cxc_id))
   # Aplicar el cobro a las cuotas más antiguas pendientes.
   por_aplicar=imp
   for q in c.execute("select * from venta_cuotas where venta_id=? and estado<>'PAGADA' order by fecha_vencimiento,numero",(r['venta_id'],)).fetchall():
    if por_aplicar<=0:break
    pend=max(0,float(q['importe'] or 0)-float(q['pagado'] or 0));aplica=min(pend,por_aplicar);nuevo=float(q['pagado'] or 0)+aplica
    c.execute("update venta_cuotas set pagado=?,estado=? where id=?",(nuevo,'PAGADA' if nuevo>=float(q['importe'] or 0)-0.0001 else 'PARCIAL',q['id']));por_aplicar-=aplica
   c.execute('insert into caja_banco(fecha,tipo,medio,moneda,tipo_cambio,importe,importe_pyg,concepto,origen_tipo,origen_id,cuenta_bancaria_id,terminal_pos_id) values(?,?,?,?,?,?,?,?,?,?,?,?)',(fecha,'INGRESO',medio,r['moneda'],tc,imp,pyg,'Cobro venta a crédito','COBRO',cxc_id,cuenta_id,pos_id))
   if medio=='Efectivo':
    ap=caja_abierta(c)
    if not ap:raise ValueError('Debe abrir Recepción y Caja para cobrar en efectivo')
    fid=c.execute("select id from formas_cobro where nombre='Efectivo'").fetchone();c.execute("insert into movimientos_caja(apertura_id,fecha,tipo,forma_cobro_id,concepto,importe_pyg,origen_tipo,origen_id,usuario) values(?,?,'INGRESO',?,?,?,?,?,?)",(ap['id'],now(),fid['id'] if fid else None,'Cobro factura '+r['factura'],pyg,'COBRO',cxc_id,session.get('user')))
   n='REC-'+datetime.datetime.now().strftime('%Y%m%d')+'-'+str(c.execute('select coalesce(max(id),0)+1 from recibos_pago').fetchone()[0]).zfill(6);cur=c.execute('insert into recibos_pago(numero,fecha,cxc_id,venta_id,tercero_id,moneda,tipo_cambio,importe,importe_pyg,saldo_anterior,saldo_restante,medio,referencia,usuario) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(n,now(),cxc_id,r['venta_id'],r['tercero_id'],r['moneda'],tc,imp,pyg,anterior,restante,medio,ref,session.get('user')))
   c.execute('update recibos_pago set cuenta_bancaria_id=?,terminal_pos_id=? where id=?',(cuenta_id,pos_id,cur.lastrowid))
   asiento(c,fecha,'Cobro '+n,'COBRO_VENTA',cur.lastrowid,r['moneda'],tc,[('1.1.01',pyg,0,imp,'Cobro'),('1.1.02',0,imp*r['tipo_cambio_origen'],imp,'Cancela cliente')]);c.commit();audit('RECIBO_PAGO',n);rid=cur.lastrowid;c.close();return redirect('/recibos/'+str(rid))
  except Exception as e:c.rollback();flash(str(e))
 formas=['Efectivo','Banco','Transferencia','POS'];cuentas=c.execute('select * from cuentas_bancarias where activo=1 order by banco,alias').fetchall();poses=c.execute('select * from terminales_pos where activo=1 order by nombre').fetchall();c.close();return render_template('credit_payment.html',r=r,formas=formas,cuentas=cuentas,poses=poses)

@app.get('/ventas/<int:venta_id>/cuotas')
def venta_cuotas(venta_id):
 c=db();v=c.execute('select v.*,t.nombre tercero from ventas v left join terceros t on t.id=v.cliente_id where v.id=?',(venta_id,)).fetchone()
 if not v:c.close();flash('Venta no encontrada.');return redirect('/ventas/carga')
 cuotas=c.execute("select *,case when estado<>'PAGADA' and date(fecha_vencimiento)<date('now','localtime') then 'VENCIDA' else estado end estado_visual from venta_cuotas where venta_id=? order by numero",(venta_id,)).fetchall();c.close()
 return render_template('sale_installments.html',v=v,cuotas=cuotas)

@app.get('/recibos/<int:rid>')
def recibo_pago(rid):
 c=db();r=c.execute('''select rp.*,v.numero factura,t.nombre cliente,t.ruc,cb.banco,cb.numero_cuenta,cb.alias cuenta_alias,tp.nombre terminal_pos from recibos_pago rp join ventas v on v.id=rp.venta_id join terceros t on t.id=rp.tercero_id left join cuentas_bancarias cb on cb.id=rp.cuenta_bancaria_id left join terminales_pos tp on tp.id=rp.terminal_pos_id where rp.id=?''',(rid,)).fetchone();c.close()
 if not r:return 'Recibo no encontrado',404
 c=db();inst=c.execute('select * from institucion_config where id=1').fetchone();c.close();return render_template('receipt.html',r=r,inst=inst,monto_letras=monto_letras(r['importe']))

def cancelar(tipo,i):
 c=db();tab='cxc' if tipo=='COBRO' else 'cxp';r=c.execute(f'select * from {tab} where id=?',(i,)).fetchone()
 if not r:return redirect('/finanzas')
 imp=min(float(request.form['importe']),r['saldo']);fecha=request.form['fecha'];mon=r['moneda'];tc=tc_fecha(c,fecha,mon,request.form.get('tipo_cambio'));pyg=imp*tc;orig=imp*r['tipo_cambio_origen'];dif=pyg-orig;c.execute(f"update {tab} set saldo=saldo-?,estado=case when saldo-?<=0.0001 then 'PAGADO' else 'PENDIENTE' end where id=?",(imp,imp,i));c.execute('insert into caja_banco(fecha,tipo,medio,moneda,tipo_cambio,importe,importe_pyg,concepto,origen_tipo,origen_id) values(?,?,?,?,?,?,?,?,?,?)',(fecha,'INGRESO' if tipo=='COBRO' else 'EGRESO',request.form['medio'],mon,tc,imp,pyg,tipo,tipo,i))
 if tipo=='COBRO':
  lines=[('1.1.01',pyg,0,imp,'Cobro'),('1.1.02',0,orig,imp,'Cancela cliente')]
  if dif>0:lines.append(('4.2.01',0,dif,0,'Ganancia cambio'))
  elif dif<0:lines.append(('5.2.01',-dif,0,0,'Pérdida cambio'))
 else:
  lines=[('2.1.01',orig,0,imp,'Cancela proveedor'),('1.1.01',0,pyg,imp,'Pago')]
  if dif>0:lines.append(('5.2.01',dif,0,0,'Pérdida cambio'))
  elif dif<0:lines.append(('4.2.01',0,-dif,0,'Ganancia cambio'))
 asiento(c,fecha,tipo,tipo,i,mon,tc,lines);c.commit();c.close();audit(tipo,str(i));return redirect('/finanzas')
@app.post('/cobrar/<int:i>')
def cobrar(i):return cancelar('COBRO',i)
@app.post('/pagar/<int:i>')
def pagar(i):return cancelar('PAGO',i)
@app.route('/finanzas')
def finanzas():
 c=db();rx=c.execute('select x.*,t.nombre tercero from cxc x join terceros t on t.id=x.tercero_id order by x.id desc').fetchall();px=c.execute('select x.*,t.nombre tercero from cxp x join terceros t on t.id=x.tercero_id order by x.id desc').fetchall();mov=c.execute('select * from caja_banco order by id desc').fetchall();c.close();return render_template('finance.html',rx=rx,px=px,mov=mov)
@app.route('/contabilidad')
def contabilidad():
 c=db();asi=c.execute('select * from asientos order by id desc').fetchall();det=c.execute('select d.*,p.nombre cuenta_nombre,a.numero,a.fecha,a.concepto from asiento_det d join asientos a on a.id=d.asiento_id left join plan_cuentas p on p.codigo=d.cuenta order by d.id desc').fetchall();bal=c.execute('select p.codigo,p.nombre,coalesce(sum(d.debe_pyg),0) debe,coalesce(sum(d.haber_pyg),0) haber,coalesce(sum(d.debe_pyg-d.haber_pyg),0) saldo from plan_cuentas p left join asiento_det d on d.cuenta=p.codigo group by p.codigo,p.nombre order by p.codigo').fetchall();c.close();return render_template('accounting.html',asi=asi,det=det,bal=bal)
@app.route('/libros')
def libros():
 c=db();compras=c.execute('select x.*,t.nombre from compras x join terceros t on t.id=x.proveedor_id order by fecha,id').fetchall();ventas=c.execute('select x.*,t.nombre from ventas x join terceros t on t.id=x.cliente_id order by fecha,id').fetchall();c.close();return render_template('books.html',compras=compras,ventas=ventas)
@app.get('/api/tc')
def api_tc():
 c=db();r=c.execute('select tipo from tipos_cambio where fecha=? and moneda=?',(request.args.get('fecha'),request.args.get('moneda'))).fetchone();c.close();return jsonify({'tipo':r['tipo'] if r else None})

@app.route('/pacientes',methods=['GET','POST'])
def pacientes():
 c=db()
 if request.method=='POST':
  cur=c.execute("insert into terceros(tipo,ruc,nombre,telefono,moneda) values('CLIENTE',?,?,?,'PYG')",(request.form['documento'],request.form['nombre'],request.form.get('telefono')));tid=cur.lastrowid;c.execute('insert into pacientes(documento,nombre,fecha_nacimiento,telefono,direccion,tercero_id) values(?,?,?,?,?,?)',(request.form['documento'],request.form['nombre'],request.form.get('fecha_nacimiento'),request.form.get('telefono'),request.form.get('direccion'),tid));c.commit();return redirect('/pacientes')
 rows=c.execute('select * from pacientes order by id desc').fetchall();c.close();return render_template('hospital_patients.html',rows=rows)
@app.route('/config-sanatorio',methods=['GET','POST'])
def config_sanatorio():
 c=db()
 # Migración compatible para instalaciones existentes
 cols=[r['name'] for r in c.execute('pragma table_info(medicos)').fetchall()]
 if 'precio_consulta' not in cols:c.execute('alter table medicos add column precio_consulta REAL DEFAULT 0')
 if 'honorario_consulta' not in cols:c.execute('alter table medicos add column honorario_consulta REAL DEFAULT 0')
 c.execute('CREATE TABLE IF NOT EXISTS especialidades(id INTEGER PRIMARY KEY,nombre TEXT UNIQUE,precio_consulta REAL DEFAULT 0,honorario_medico REAL DEFAULT 0,activo INT DEFAULT 1)')
 ecols=[r['name'] for r in c.execute('pragma table_info(especialidades)').fetchall()]
 if 'minutos_consulta' not in ecols:c.execute('alter table especialidades add column minutos_consulta INT DEFAULT 15')
 if request.method=='POST':
  k=request.form['kind']
  if k=='servicio':c.execute('insert into servicios(codigo,nombre,categoria,precio_pyg,cuenta_ingreso,iva_pct) values(?,?,?,?,?,?)',(request.form['codigo'],request.form['nombre'],request.form['categoria'],float(request.form['precio']),request.form['cuenta'],float(request.form.get('iva_pct') or 0)))
  elif k=='especialidad':
   nombre=request.form['nombre'].strip(); precio=float(request.form.get('precio_consulta') or 0); hon=float(request.form.get('honorario_medico') or 0); mins=int(request.form.get('minutos_consulta') or 15)
   c.execute('insert into especialidades(nombre,precio_consulta,honorario_medico,minutos_consulta,activo) values(?,?,?,?,1) on conflict(nombre) do update set precio_consulta=excluded.precio_consulta,honorario_medico=excluded.honorario_medico,minutos_consulta=excluded.minutos_consulta,activo=1',(nombre,precio,hon,mins))
  elif k=='actualizar_especialidad':
   eid=int(request.form['especialidad_id']); old=c.execute('select nombre from especialidades where id=?',(eid,)).fetchone(); nombre=request.form['nombre'].strip(); precio=float(request.form.get('precio_consulta') or 0); hon=float(request.form.get('honorario_medico') or 0); mins=int(request.form.get('minutos_consulta') or 15); activo=1 if request.form.get('activo')=='1' else 0
   if old:
    c.execute('update especialidades set nombre=?,precio_consulta=?,honorario_medico=?,minutos_consulta=?,activo=? where id=?',(nombre,precio,hon,mins,activo,eid))
    c.execute('update medicos set especialidad=? where especialidad=?',(nombre,old['nombre']))
  elif k=='estado_especialidad':
   c.execute('update especialidades set activo=? where id=?',(int(request.form['activo']),int(request.form['especialidad_id'])))
  elif k=='medico':
   esp=request.form['especialidad']; precio=float(request.form.get('precio_consulta') or 0); hon=float(request.form.get('honorario_consulta') or 0)
   c.execute('insert or ignore into especialidades(nombre,precio_consulta,honorario_medico) values(?,?,?)',(esp,precio,hon))
   c.execute('insert into medicos(nombre,registro,especialidad,precio_consulta,honorario_consulta) values(?,?,?,?,?)',(request.form['nombre'],request.form['registro'],esp,precio,hon))
  elif k=='actualizar_medico':
   c.execute('update medicos set especialidad=?,precio_consulta=?,honorario_consulta=? where id=?',(request.form['especialidad'],float(request.form.get('precio_consulta') or 0),float(request.form.get('honorario_consulta') or 0),int(request.form['medico_id'])))
  elif k=='aseguradora':
   cur=c.execute("insert into terceros(tipo,ruc,nombre,moneda) values('CLIENTE',?,?,?)",(request.form['ruc'],request.form['nombre'],request.form['moneda']));c.execute('insert into aseguradoras(nombre,ruc,tercero_id,moneda) values(?,?,?,?)',(request.form['nombre'],request.form['ruc'],cur.lastrowid,request.form['moneda']))
  elif k=='cama':
   hid=c.execute('select id from habitaciones where nombre=?',(request.form['habitacion'],)).fetchone()
   if not hid:hid=c.execute('insert into habitaciones(nombre,tipo) values(?,?)',(request.form['habitacion'],request.form.get('tipo','Internación'))).lastrowid
   else:hid=hid['id']
   c.execute('insert into camas(habitacion_id,codigo) values(?,?)',(hid,request.form['codigo']))
  c.commit();return redirect('/config-sanatorio')
 data={x:c.execute('select * from '+x+' order by id desc').fetchall() for x in ['servicios','medicos','aseguradoras']};data['especialidades']=c.execute('select * from especialidades order by activo desc,nombre').fetchall();data['camas']=c.execute('select c.*,h.nombre habitacion from camas c join habitaciones h on h.id=c.habitacion_id').fetchall();mons=c.execute('select * from monedas').fetchall();c.close();return render_template('hospital_config.html',data=data,mons=mons)
@app.route('/admisiones',methods=['GET','POST'])
def hospital_admisiones():
 c=db()
 if request.method=='POST':
  fecha=request.form['fecha'];mon=request.form['moneda'];tc=tc_fecha(c,fecha,mon,request.form.get('tipo_cambio'));cama=int(request.form['cama_id']) if request.form.get('cama_id') else None
  cur=c.execute('insert into admisiones(fecha,paciente_id,tipo,medico_id,aseguradora_id,moneda,tipo_cambio,cama_id) values(?,?,?,?,?,?,?,?)',(fecha,int(request.form['paciente_id']),request.form['tipo'],request.form.get('medico_id') or None,request.form.get('aseguradora_id') or None,mon,tc,cama));
  if cama:c.execute("update camas set estado='OCUPADA' where id=?",(cama,))
  c.commit();audit('ADMISION',str(cur.lastrowid));return redirect('/admisiones')
 rows=c.execute('select a.*,p.nombre paciente,m.nombre medico,ca.codigo cama from admisiones a join pacientes p on p.id=a.paciente_id left join medicos m on m.id=a.medico_id left join camas ca on ca.id=a.cama_id order by a.id desc').fetchall();pats=c.execute('select * from pacientes').fetchall();med=c.execute('select * from medicos').fetchall();aseg=c.execute('select * from aseguradoras').fetchall();camas=c.execute("select * from camas where estado='LIBRE'").fetchall();mons=c.execute('select * from monedas').fetchall();c.close();return render_template('hospital_admissions.html',rows=rows,pats=pats,med=med,aseg=aseg,camas=camas,mons=mons)
@app.route('/cuenta-paciente/<int:aid>',methods=['GET','POST'])
def cuenta_paciente(aid):
 c=db();a=c.execute('select a.*,p.nombre paciente,p.tercero_id paciente_tercero,sg.tercero_id seguro_tercero from admisiones a join pacientes p on p.id=a.paciente_id left join aseguradoras sg on sg.id=a.aseguradora_id where a.id=?',(aid,)).fetchone()
 if request.method=='POST':
  fecha=request.form['fecha'];mon=request.form['moneda'];tc=tc_fecha(c,fecha,mon,request.form.get('tipo_cambio'));tipo=request.form['tipo'];ref=int(request.form['referencia_id']);qty=float(request.form['cantidad'])
  if tipo=='PRODUCTO':
   if not user_has('FARMACIA','ENTREGAR'):
    flash('Los productos y medicamentos deben solicitarse desde Enfermería y ser autorizados/entregados por Farmacia Interna.');c.close();return redirect(f'/cuenta-paciente/{aid}')
   x=c.execute('select * from productos where id=?',(ref,)).fetchone()
   if x['stock']<qty:flash('Stock insuficiente');c.close();return redirect(f'/cuenta-paciente/{aid}')
   price=x['precio_pyg']/tc;desc=x['nombre'];c.execute('update productos set stock=stock-? where id=?',(qty,ref));c.execute('insert into stock_mov(fecha,producto_id,tipo,cantidad,costo_pyg,origen_tipo,origen_id) values(?,?,?,?,?,?,?)',(fecha,ref,'SALIDA',-qty,x['costo_pyg'],'PACIENTE',aid))
  else:
   x=c.execute('select * from servicios where id=?',(ref,)).fetchone();price=x['precio_pyg']/tc;desc=x['nombre']
  iva_pct=float(x['iva_pct'] or 0);total=qty*price;c.execute('insert into cargos_paciente(fecha,admision_id,tipo,referencia_id,descripcion,cantidad,precio,moneda,tipo_cambio,total,total_pyg,iva_pct) values(?,?,?,?,?,?,?,?,?,?,?,?)',(fecha,aid,tipo,ref,desc,qty,price,mon,tc,total,total*tc,iva_pct));c.commit();return redirect(f'/cuenta-paciente/{aid}')
 cargos=c.execute('select * from cargos_paciente where admision_id=? order by id',(aid,)).fetchall();prods=c.execute('select * from productos').fetchall();serv=c.execute('select * from servicios').fetchall();mons=c.execute('select * from monedas').fetchall();total=sum(x['total_pyg'] for x in cargos if not x['facturado']);c.close();return render_template('hospital_account.html',a=a,cargos=cargos,prods=prods,serv=serv,mons=mons,total=total)
@app.post('/facturar-admision/<int:aid>')
def facturar_admision(aid):
 c=db();a=c.execute('select a.*,p.tercero_id paciente_tercero,sg.tercero_id seguro_tercero from admisiones a join pacientes p on p.id=a.paciente_id left join aseguradoras sg on sg.id=a.aseguradora_id where a.id=?',(aid,)).fetchone();items=c.execute('select * from cargos_paciente where admision_id=? and facturado=0',(aid,)).fetchall()
 if not a:
  c.close();flash('Admisión no encontrada.');return redirect('/admisiones')
 # V13.6.3: las cuentas de URGENCIA/INTERNACION/QUIROFANO con seguro no se facturan
 # directamente al cerrar la cuenta. Quedan pendientes para facturación consolidada al seguro.
 if a['aseguradora_id'] and a['tipo'] in ('URGENCIA','INTERNACION','QUIROFANO'):
  c.close();flash('Esta cuenta corresponde a un seguro. Cierre la cuenta para enviarla a Pendientes de Facturación de Seguros.');return redirect(f'/cuenta-paciente/{aid}')
 if not items:flash('No hay cargos pendientes');c.close();return redirect(f'/cuenta-paciente/{aid}')
 fecha=request.form['fecha'];mon=request.form['moneda'];tc=tc_fecha(c,fecha,mon,request.form.get('tipo_cambio'))
 # Los cargos del paciente ya contienen precios FINALES con IVA incluido.
 total10_pyg=sum(x['total_pyg'] for x in items if float(x['iva_pct'] or 0)==10);total5_pyg=sum(x['total_pyg'] for x in items if float(x['iva_pct'] or 0)==5);exento_pyg=sum(x['total_pyg'] for x in items if float(x['iva_pct'] or 0)==0)
 base10_pyg,iva10_pyg=desglosar_iva_incluido(total10_pyg,10);base5_pyg,iva5_pyg=desglosar_iva_incluido(total5_pyg,5)
 subtotal_pyg=base10_pyg+base5_pyg+exento_pyg;iva_pyg=iva10_pyg+iva5_pyg;totg=total10_pyg+total5_pyg+exento_pyg
 subtotal=subtotal_pyg/tc;iva=iva_pyg/tc;total=totg/tc;ter=a['seguro_tercero'] or a['paciente_tercero'];num=request.form['numero'];cur=c.execute('insert into facturas_sanatorio(fecha,admision_id,tercero_id,numero,moneda,tipo_cambio,subtotal,iva,total,total_pyg,gravado_10,iva_10,gravado_5,iva_5,exento_iva) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(fecha,aid,ter,num,mon,tc,subtotal,iva,total,totg,base10_pyg/tc,iva10_pyg/tc,base5_pyg/tc,iva5_pyg/tc,exento_pyg/tc));fid=cur.lastrowid;c.execute('update cargos_paciente set facturado=1 where admision_id=? and facturado=0',(aid,));c.execute('insert into ventas(fecha,cliente_id,numero,moneda,tipo_cambio,gravado,iva,exento,total,total_pyg,gravado_10,iva_10,gravado_5,iva_5,exento_iva) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(fecha,ter,num,mon,tc,(base10_pyg+base5_pyg)/tc,iva,exento_pyg/tc,total,totg,base10_pyg/tc,iva10_pyg/tc,base5_pyg/tc,iva5_pyg/tc,exento_pyg/tc));vid=c.execute('select last_insert_rowid()').fetchone()[0];c.execute('insert into cxc(venta_id,tercero_id,moneda,tipo_cambio_origen,importe,saldo,importe_pyg) values(?,?,?,?,?,?,?)',(vid,ter,mon,tc,total,total,totg));asiento(c,fecha,'Factura sanatorial '+num,'FACTURA_SANATORIO',fid,mon,tc,[('1.1.02',totg,0,total,'Paciente/Seguro'),('4.1.02',0,subtotal_pyg,subtotal,'Servicios sanatoriales'),('2.1.02',0,iva_pyg,iva,'IVA débito')]);c.commit();audit('FACTURA_SANATORIO',str(fid));return redirect(f'/cuenta-paciente/{aid}')
@app.post('/alta/<int:aid>')
def alta(aid):
 c=db();a=c.execute('select * from admisiones where id=?',(aid,)).fetchone()
 if not a:
  c.close();flash('Admisión no encontrada.');return redirect('/admisiones')
 asegurado=bool(a['aseguradora_id']) and a['tipo'] in ('URGENCIA','INTERNACION','QUIROFANO')
 nuevo_estado='PENDIENTE_FACTURACION' if asegurado else 'ALTA'
 c.execute("update admisiones set estado=?,fecha_cierre=?,cerrado_por=? where id=?",(nuevo_estado,now(),session.get('user'),aid))
 if a['cama_id']:c.execute("update camas set estado='LIBRE' where id=?",(a['cama_id'],))
 if asegurado:
  # Genera los pendientes únicamente al cerrar la cuenta; no crea venta, factura, CxC ni asiento todavía.
  for r in c.execute('select cp.*,a.aseguradora_id,a.paciente_id from cargos_paciente cp join admisiones a on a.id=cp.admision_id where cp.admision_id=? and cp.facturado=0',(aid,)).fetchall():
   cat,iva=clasificar_cargo_seguro(c,r)
   c.execute("insert or ignore into seguro_pendientes(fecha,aseguradora_id,paciente_id,origen_tipo,origen_id,categoria,descripcion,importe_pyg,iva_pct,estado) values(?,?,?,?,?,?,?,?,?,'PENDIENTE')",(r['fecha'],r['aseguradora_id'],r['paciente_id'],'CARGO',r['id'],cat,r['descripcion'],r['total_pyg'],iva))
 c.commit();c.close()
 audit('CIERRE_CUENTA_SEGURO' if asegurado else 'ALTA',str(aid))
 flash('Cuenta cerrada. Quedó pendiente de facturación al seguro.' if asegurado else 'Alta registrada correctamente.')
 return redirect('/admisiones')
@app.route('/enfermeria',methods=['GET','POST'])
def hospital_enfermeria():
 c=db()
 if request.method=='POST':c.execute('insert into enfermeria(fecha,admision_id,nota,usuario) values(?,?,?,?)',(request.form['fecha'],request.form['admision_id'],request.form['nota'],session['user']));c.commit();return redirect('/enfermeria')
 rows=c.execute('select e.*,p.nombre paciente from enfermeria e join admisiones a on a.id=e.admision_id join pacientes p on p.id=a.paciente_id order by e.id desc').fetchall();ads=c.execute("select a.id,a.tipo,p.nombre paciente from admisiones a join pacientes p on p.id=a.paciente_id where a.estado='ABIERTA' and a.tipo in ('URGENCIA','INTERNACION','QUIROFANO')").fetchall();prods=c.execute('select * from productos where stock>0 order by nombre').fetchall();c.close();return render_template('hospital_nursing.html',rows=rows,ads=ads,prods=prods)


# ===== V9: correcciones, anulaciones y auditoría transaccional =====
def snapshot(row):
 return dict(row) if row else {}
def audit_change(c,accion,modulo,registro_id,antes=None,despues=None,motivo=''):
 import json
 c.execute('insert into auditoria(fecha,usuario,accion,detalle) values(?,?,?,?)',(now(),session.get('user','sistema'),accion,json.dumps({'modulo':modulo,'id':registro_id,'antes':antes or {},'despues':despues or {},'motivo':motivo},ensure_ascii=False)))
def reverse_asientos(c,origen_tipo,origen_id,fecha,motivo):
 rows=c.execute("select * from asientos where origen_tipo=? and origen_id=? and estado='CONFIRMADO'",(origen_tipo,origen_id)).fetchall()
 for a in rows:
  ds=c.execute('select * from asiento_det where asiento_id=?',(a['id'],)).fetchall()
  lines=[(d['cuenta'],d['haber_pyg'],d['debe_pyg'],-(d['importe_moneda'] or 0),f"Reversión: {d['detalle'] or ''}") for d in ds]
  asiento(c,fecha,'REVERSIÓN '+a['numero']+' - '+motivo,'REV_'+origen_tipo,origen_id,a['moneda'],a['tipo_cambio'],lines)
  c.execute("update asientos set estado='ANULADO' where id=?",(a['id'],))

@app.post('/anular-compra/<int:i>')
def anular_compra(i):
 c=db(); r=c.execute('select * from compras where id=?',(i,)).fetchone(); motivo=request.form.get('motivo','Corrección de registro')
 if not r or r['estado']=='ANULADA': c.close(); return redirect('/compras')
 pagos=c.execute("select count(*) from caja_banco where origen_tipo='PAGO' and origen_id in (select id from cxp where compra_id=?)",(i,)).fetchone()[0]
 if pagos: flash('No se puede anular: primero debe revertir los pagos vinculados.'); c.close(); return redirect('/compras')
 antes=snapshot(r)
 for it in c.execute('select * from compra_items where compra_id=?',(i,)).fetchall():
  c.execute('update productos set stock=stock-? where id=?',(it['cantidad'],it['producto_id']))
  c.execute('insert into stock_mov(fecha,producto_id,tipo,cantidad,costo_pyg,origen_tipo,origen_id) values(?,?,?,?,?,?,?)',(now()[:10],it['producto_id'],'REVERSIÓN COMPRA',-it['cantidad'],it['total_pyg']/it['cantidad'] if it['cantidad'] else 0,'ANULACION_COMPRA',i))
 c.execute("update cxp set saldo=0,estado='ANULADO' where compra_id=?",(i,)); c.execute("update compras set estado='ANULADA' where id=?",(i,)); reverse_asientos(c,'COMPRA',i,now()[:10],motivo); audit_change(c,'ANULAR','COMPRAS',i,antes,{'estado':'ANULADA'},motivo); c.commit(); c.close(); flash('Compra anulada y movimientos relacionados revertidos.'); return redirect('/compras')

@app.post('/anular-venta/<int:i>')
def anular_venta(i):
 c=db(); r=c.execute('select * from ventas where id=?',(i,)).fetchone(); motivo=request.form.get('motivo','Corrección de registro')
 if not r or r['estado']=='ANULADA': c.close(); return redirect('/ventas')
 cobros=c.execute("select count(*) from caja_banco where origen_tipo='COBRO' and origen_id in (select id from cxc where venta_id=?)",(i,)).fetchone()[0]
 if cobros: flash('No se puede anular: primero debe revertir los cobros vinculados.'); c.close(); return redirect('/ventas')
 antes=snapshot(r)
 for it in c.execute('select * from venta_items where venta_id=?',(i,)).fetchall():
  c.execute('update productos set stock=stock+? where id=?',(it['cantidad'],it['producto_id']))
  c.execute('insert into stock_mov(fecha,producto_id,tipo,cantidad,costo_pyg,origen_tipo,origen_id) values(?,?,?,?,?,?,?)',(now()[:10],it['producto_id'],'REVERSIÓN VENTA',it['cantidad'],it['costo_pyg']/it['cantidad'] if it['cantidad'] else 0,'ANULACION_VENTA',i))
 c.execute("update cxc set saldo=0,estado='ANULADO' where venta_id=?",(i,)); c.execute("update ventas set estado='ANULADA' where id=?",(i,)); reverse_asientos(c,'VENTA',i,now()[:10],motivo); audit_change(c,'ANULAR','VENTAS',i,antes,{'estado':'ANULADA'},motivo); c.commit(); c.close(); flash('Venta anulada y movimientos relacionados revertidos.'); return redirect('/ventas')

@app.route('/editar-paciente/<int:i>',methods=['GET','POST'])
def editar_paciente(i):
 c=db(); r=c.execute('select * from pacientes where id=?',(i,)).fetchone()
 if request.method=='POST':
  antes=snapshot(r); vals=(request.form['documento'],request.form['nombre'],request.form.get('fecha_nacimiento'),request.form.get('telefono'),request.form.get('direccion'),i); c.execute('update pacientes set documento=?,nombre=?,fecha_nacimiento=?,telefono=?,direccion=? where id=?',vals); c.execute('update terceros set ruc=?,nombre=?,telefono=? where id=?',(request.form['documento'],request.form['nombre'],request.form.get('telefono'),r['tercero_id'])); despues=snapshot(c.execute('select * from pacientes where id=?',(i,)).fetchone()); audit_change(c,'MODIFICAR','PACIENTES',i,antes,despues,request.form.get('motivo','Corrección')); c.commit(); c.close(); return redirect('/pacientes')
 c.close(); return render_template('edit_patient.html',r=r)

@app.post('/eliminar-paciente/<int:i>')
def eliminar_paciente(i):
 c=db(); r=c.execute('select * from pacientes where id=?',(i,)).fetchone(); n=c.execute('select count(*) from admisiones where paciente_id=?',(i,)).fetchone()[0]
 if n: flash('No se puede eliminar: el paciente tiene admisiones. Edite sus datos en su lugar.'); c.close(); return redirect('/pacientes')
 if r: audit_change(c,'ELIMINAR','PACIENTES',i,snapshot(r),{},request.form.get('motivo','Registro erróneo')); c.execute('delete from pacientes where id=?',(i,)); c.execute('delete from terceros where id=?',(r['tercero_id'],)); c.commit()
 c.close(); return redirect('/pacientes')

@app.route('/auditoria-detallada')
def auditoria_detallada():
 c=db(); rows=c.execute('select * from auditoria order by id desc limit 1000').fetchall(); c.close(); return render_template('audit.html',rows=rows)

# ===== V10.1: Consultorio, liquidaciones e informes (corregido) =====
def init_consultorio():
 c=db(); c.executescript('''
 CREATE TABLE IF NOT EXISTS especialidades(id INTEGER PRIMARY KEY,nombre TEXT UNIQUE,precio_consulta REAL DEFAULT 0,honorario_medico REAL DEFAULT 0,activo INT DEFAULT 1);
 CREATE TABLE IF NOT EXISTS consultas(id INTEGER PRIMARY KEY,fecha TEXT,hora TEXT,paciente_id INT,medico_id INT,especialidad_id INT,aseguradora_id INT,admision_id INT,moneda TEXT,tipo_cambio REAL,precio REAL,honorario_medico REAL,precio_pyg REAL,honorario_pyg REAL,observacion TEXT,estado TEXT DEFAULT 'REALIZADA',liquidacion_id INT);
 CREATE TABLE IF NOT EXISTS liquidaciones_medicas(id INTEGER PRIMARY KEY,fecha TEXT,medico_id INT,total_consultas INT,total_facturado_pyg REAL,total_honorario_pyg REAL,estado TEXT DEFAULT 'CERRADA',cxp_id INT,creado_en TEXT);
 ''')
 # agrega columnas nuevas sin perder bases existentes
 cols=[r['name'] for r in c.execute('pragma table_info(especialidades)').fetchall()]
 if 'precio_consulta' not in cols:c.execute('alter table especialidades add column precio_consulta REAL DEFAULT 0')
 if 'honorario_medico' not in cols:c.execute('alter table especialidades add column honorario_medico REAL DEFAULT 0')
 mcols=[r['name'] for r in c.execute('pragma table_info(medicos)').fetchall()]
 if 'precio_consulta' not in mcols:c.execute('alter table medicos add column precio_consulta REAL DEFAULT 0')
 if 'honorario_consulta' not in mcols:c.execute('alter table medicos add column honorario_consulta REAL DEFAULT 0')
 c.execute("INSERT OR IGNORE INTO plan_cuentas(codigo,nombre,tipo) VALUES('5.3.01','Honorarios Médicos','EGRESO')")
 c.execute("INSERT OR IGNORE INTO plan_cuentas(codigo,nombre,tipo) VALUES('2.1.03','Honorarios Médicos a Pagar','PASIVO')")
 for r in c.execute("select distinct trim(especialidad) e from medicos where trim(coalesce(especialidad,''))<>''").fetchall(): c.execute('insert or ignore into especialidades(nombre) values(?)',(r['e'],))
 c.commit(); c.close()

@app.route('/consultas',methods=['GET','POST'])
def consultas_medicas():
 c=db()
 if request.method=='POST':
  try:
   fecha=request.form['fecha']; mon=request.form.get('moneda','PYG'); tc=tc_fecha(c,fecha,mon,request.form.get('tipo_cambio')); precio=float(request.form['precio']); hon=float(request.form['honorario_medico'])
   if precio<0 or hon<0: raise ValueError('Los importes no pueden ser negativos.')
   pid=int(request.form['paciente_id']); mid=int(request.form['medico_id']); eid=int(request.form['especialidad_id']); aseg=int(request.form['aseguradora_id']) if request.form.get('aseguradora_id') else None
   # crea una admisión de consultorio para vincular cuenta del paciente
   cur=c.execute("insert into admisiones(fecha,paciente_id,tipo,medico_id,aseguradora_id,moneda,tipo_cambio,estado) values(?,?,?,?,?,?,?,'ABIERTA')",(fecha,pid,'CONSULTORIO',mid,aseg,mon,tc)); aid=cur.lastrowid
   cur=c.execute('insert into consultas(fecha,hora,paciente_id,medico_id,especialidad_id,aseguradora_id,admision_id,moneda,tipo_cambio,precio,honorario_medico,precio_pyg,honorario_pyg,observacion) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(fecha,request.form.get('hora'),pid,mid,eid,aseg,aid,mon,tc,precio,hon,precio*tc,hon*tc,request.form.get('observacion'))); qid=cur.lastrowid
   esp=c.execute('select nombre from especialidades where id=?',(eid,)).fetchone()['nombre']
   c.execute('insert into cargos_paciente(fecha,admision_id,tipo,referencia_id,descripcion,cantidad,precio,moneda,tipo_cambio,total,total_pyg) values(?,?,?,?,?,?,?,?,?,?,?)',(fecha,aid,'CONSULTA',qid,'Consulta médica - '+esp,1,precio,mon,tc,precio,precio*tc))
   c.commit(); audit('CONSULTA_MEDICA',str(qid)); flash('Consulta registrada correctamente y cargada a la cuenta del paciente.')
  except Exception as e: c.rollback(); flash('No se pudo registrar la consulta: '+str(e))
  finally: c.close()
  return redirect('/consultas')
 rows=c.execute('''select q.*,p.nombre paciente,m.nombre medico,e.nombre especialidad from consultas q join pacientes p on p.id=q.paciente_id join medicos m on m.id=q.medico_id join especialidades e on e.id=q.especialidad_id order by q.fecha desc,q.id desc limit 300''').fetchall()
 pats=c.execute('select * from pacientes order by nombre').fetchall(); meds=c.execute('select * from medicos order by nombre').fetchall(); esps=c.execute('select * from especialidades where activo=1 order by nombre').fetchall(); asegs=c.execute('select * from aseguradoras order by nombre').fetchall(); mons=c.execute('select * from monedas where activa=1').fetchall(); c.close()
 return render_template('consultations.html',rows=rows,pats=pats,meds=meds,esps=esps,asegs=asegs,mons=mons)

@app.route('/liquidaciones-medicas')
def liquidaciones_medicas():
 c=db(); fecha=request.args.get('fecha',datetime.date.today().isoformat()); meds=c.execute('select * from medicos order by nombre').fetchall(); rows=c.execute('''select l.*,m.nombre medico,m.especialidad from liquidaciones_medicas l join medicos m on m.id=l.medico_id order by l.fecha desc,l.id desc''').fetchall(); c.close(); return render_template('doctor_settlements.html',rows=rows,meds=meds,fecha=fecha)

@app.post('/liquidar-medico')
def liquidar_medico():
 c=db()
 try:
  fecha=request.form['fecha']; mid=int(request.form['medico_id']); qs=c.execute("select * from consultas where fecha=? and medico_id=? and estado='REALIZADA' and liquidacion_id is null",(fecha,mid)).fetchall()
  if not qs: raise ValueError('No existen consultas pendientes de liquidación para ese médico y fecha.')
  totalf=sum(x['precio_pyg'] for x in qs); totalh=sum(x['honorario_pyg'] for x in qs)
  med=c.execute('select * from medicos where id=?',(mid,)).fetchone()
  # La liquidación de honorarios es un documento ADMINISTRATIVO INTERNO.
  # No genera CxP, asiento contable, IVA ni movimientos de caja/banco.
  cur=c.execute("insert into liquidaciones_medicas(fecha,medico_id,total_consultas,total_facturado_pyg,total_honorario_pyg,estado,cxp_id,creado_en) values(?,?,?,?,?,'GENERADA',NULL,?)",(fecha,mid,len(qs),totalf,totalh,now())); lid=cur.lastrowid
  c.execute('update consultas set liquidacion_id=? where fecha=? and medico_id=? and liquidacion_id is null',(lid,fecha,mid))
  c.commit(); audit('LIQUIDACION_MEDICA_INTERNA',str(lid)); flash('Liquidación interna de honorarios generada correctamente. No afecta Contabilidad ni Cuentas por Pagar.')
 except Exception as e: c.rollback(); flash(str(e))
 finally: c.close()
 return redirect('/liquidaciones-medicas')

def _filtros_consultas(c):
 hoy=datetime.date.today(); desde=request.args.get('desde') or hoy.replace(day=1).isoformat(); hasta=request.args.get('hasta') or hoy.isoformat()
 sql='''select q.*,p.nombre paciente,m.nombre medico,e.nombre especialidad,(q.precio_pyg-q.honorario_pyg) margen_pyg from consultas q join pacientes p on p.id=q.paciente_id join medicos m on m.id=q.medico_id join especialidades e on e.id=q.especialidad_id where q.fecha between ? and ? and q.estado<>'ANULADA' order by q.fecha,q.id'''
 rows=c.execute(sql,(desde,hasta)).fetchall(); resumen=c.execute('''select e.nombre especialidad,count(*) cantidad,sum(q.precio_pyg) facturado,sum(q.honorario_pyg) honorarios,sum(q.precio_pyg-q.honorario_pyg) margen from consultas q join especialidades e on e.id=q.especialidad_id where q.fecha between ? and ? and q.estado<>'ANULADA' group by e.id,e.nombre order by cantidad desc,e.nombre''',(desde,hasta)).fetchall(); return desde,hasta,rows,resumen

@app.get('/informes-consultas')
def informes_consultas():
 c=db(); desde,hasta,rows,resumen=_filtros_consultas(c); c.close(); return render_template('consultation_reports.html',desde=desde,hasta=hasta,rows=rows,resumen=resumen)

@app.get('/exportar-consultas.xlsx')
def exportar_consultas_xlsx():
 from openpyxl import Workbook
 from openpyxl.styles import Font
 from flask import send_file
 from io import BytesIO
 c=db(); desde,hasta,rows,resumen=_filtros_consultas(c); c.close(); wb=Workbook(); ws=wb.active; ws.title='Consultas'; headers=['Fecha','Paciente','Médico','Especialidad','Precio Gs.','Honorario Gs.','Margen Gs.']; ws.append(headers)
 for cell in ws[1]: cell.font=Font(bold=True)
 for r in rows: ws.append([r['fecha'],r['paciente'],r['medico'],r['especialidad'],r['precio_pyg'],r['honorario_pyg'],r['margen_pyg']])
 rs=wb.create_sheet('Resumen'); rs.append(['Especialidad','Consultas','Facturado Gs.','Honorarios Gs.','Margen Gs.'])
 for cell in rs[1]: cell.font=Font(bold=True)
 for r in resumen: rs.append([r['especialidad'],r['cantidad'],r['facturado'],r['honorarios'],r['margen']])
 out=BytesIO(); wb.save(out); out.seek(0); return send_file(out,as_attachment=True,download_name=f'consultas_{desde}_{hasta}.xlsx',mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.get('/exportar-consultas.pdf')
def exportar_consultas_pdf():
 from reportlab.lib.pagesizes import A4,landscape
 from reportlab.platypus import SimpleDocTemplate,Table,TableStyle,Paragraph,Spacer
 from reportlab.lib import colors
 from reportlab.lib.styles import getSampleStyleSheet
 from flask import send_file
 from io import BytesIO
 c=db(); desde,hasta,rows,resumen=_filtros_consultas(c); c.close(); out=BytesIO(); doc=SimpleDocTemplate(out,pagesize=landscape(A4),leftMargin=24,rightMargin=24,topMargin=24,bottomMargin=24); st=getSampleStyleSheet(); story=([pdf_logo()] if pdf_logo() else [])+[Paragraph('Centro Médico Santa Clara - Informe de Consultas',st['Title']),Paragraph(f'Período: {desde} al {hasta}',st['Normal']),Spacer(1,10)]
 data=[['Fecha','Paciente','Médico','Especialidad','Precio Gs.','Honorario Gs.','Margen Gs.']]+[[r['fecha'],r['paciente'],r['medico'],r['especialidad'],f"{r['precio_pyg']:,.0f}",f"{r['honorario_pyg']:,.0f}",f"{r['margen_pyg']:,.0f}"] for r in rows]; t=Table(data,repeatRows=1); t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.lightgrey),('GRID',(0,0),(-1,-1),.25,colors.grey),('FONTSIZE',(0,0),(-1,-1),8),('VALIGN',(0,0),(-1,-1),'TOP')])); story.append(t); doc.build(story); out.seek(0); return send_file(out,as_attachment=True,download_name=f'consultas_{desde}_{hasta}.pdf',mimetype='application/pdf')

@app.get('/liquidacion-medica/<int:i>.pdf')
def liquidacion_medica_pdf(i):
 from reportlab.lib.pagesizes import A4
 from reportlab.platypus import SimpleDocTemplate,Table,TableStyle,Paragraph,Spacer
 from reportlab.lib import colors
 from reportlab.lib.styles import getSampleStyleSheet
 from flask import send_file
 from io import BytesIO
 c=db(); l=c.execute('''select l.*,m.nombre medico,m.especialidad from liquidaciones_medicas l join medicos m on m.id=l.medico_id where l.id=?''',(i,)).fetchone(); qs=c.execute('''select q.*,p.nombre paciente,e.nombre especialidad from consultas q join pacientes p on p.id=q.paciente_id join especialidades e on e.id=q.especialidad_id where q.liquidacion_id=? order by q.hora,q.id''',(i,)).fetchall(); c.close()
 if not l: return 'Liquidación no encontrada',404
 out=BytesIO(); doc=SimpleDocTemplate(out,pagesize=A4); st=getSampleStyleSheet(); story=([pdf_logo()] if pdf_logo() else [])+[Paragraph('Centro Médico Santa Clara - Liquidación Médica',st['Title']),Paragraph(f"Médico: {l['medico']} | Fecha: {l['fecha']}",st['Normal']),Spacer(1,10)]; data=[['Paciente','Especialidad','Precio Gs.','Honorario Gs.']]+[[q['paciente'],q['especialidad'],f"{q['precio_pyg']:,.0f}",f"{q['honorario_pyg']:,.0f}"] for q in qs]+[['','','TOTAL',f"{l['total_honorario_pyg']:,.0f}"]]; t=Table(data,repeatRows=1); t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.lightgrey),('GRID',(0,0),(-1,-1),.3,colors.grey),('ALIGN',(2,1),(-1,-1),'RIGHT')])); story.append(t); doc.build(story); out.seek(0); return send_file(out,as_attachment=True,download_name=f'liquidacion_medica_{i}.pdf',mimetype='application/pdf')


# ===== V11: arquitectura modular, roles y farmacia interna =====
MODULES = {
 'PACIENTES':'Pacientes','CONSULTORIO':'Consultorio','URGENCIAS':'Urgencias','ADMISION':'Admisión / Internación',
 'QUIROFANO':'Quirófano','ENFERMERIA':'Enfermería','FARMACIA':'Farmacia interna','FACTURACION':'Facturación',
 'STOCK':'Productos y Stock','COMPRAS':'Compras','VENTAS':'Ventas','FINANZAS':'CxC/CxP/Caja/Bancos',
 'CONTABILIDAD':'Contabilidad','INFORMES':'Informes','CONFIG_SANATORIO':'Configuración Sanatorial','USUARIOS':'Usuarios y Roles'
}
ACTIONS=['VER','CREAR','EDITAR','ANULAR','FACTURAR','ALTA','TRASLADAR','SOLICITAR','AUTORIZAR','ENTREGAR','ADMINISTRAR']

def init_modular():
 c=db();c.executescript('''
 CREATE TABLE IF NOT EXISTS roles(id INTEGER PRIMARY KEY,nombre TEXT UNIQUE,descripcion TEXT,activo INT DEFAULT 1);
 CREATE TABLE IF NOT EXISTS usuario_roles(usuario_id INT,rol_id INT,PRIMARY KEY(usuario_id,rol_id));
 CREATE TABLE IF NOT EXISTS permisos_rol(rol_id INT,modulo TEXT,accion TEXT,permitido INT DEFAULT 1,PRIMARY KEY(rol_id,modulo,accion));
 CREATE TABLE IF NOT EXISTS solicitudes_farmacia(id INTEGER PRIMARY KEY,fecha TEXT,admision_id INT,solicitante TEXT,estado TEXT DEFAULT 'PENDIENTE',observacion TEXT,autorizado_por TEXT,autorizado_en TEXT);
 CREATE TABLE IF NOT EXISTS solicitud_farmacia_items(id INTEGER PRIMARY KEY,solicitud_id INT,producto_id INT,cantidad_solicitada REAL,cantidad_autorizada REAL DEFAULT 0,cantidad_entregada REAL DEFAULT 0,estado TEXT DEFAULT 'PENDIENTE');
 ''')
 defaults={
 'ADMINISTRADOR':list(MODULES),
 'RECEPCION':['PACIENTES','CONSULTORIO','URGENCIAS','FACTURACION'],
 'ADMISION':['PACIENTES','CONSULTORIO','URGENCIAS','ADMISION','QUIROFANO','FACTURACION'],
 'ENFERMERIA':['URGENCIAS','ADMISION','QUIROFANO','ENFERMERIA'],
 'FARMACIA':['FARMACIA','STOCK']}
 for role,mods in defaults.items():
  existente=c.execute('select id from roles where nombre=?',(role,)).fetchone()
  if existente:
   rid=existente[0]
   continue
  rid=c.execute('insert into roles(nombre,descripcion) values(?,?)',(role,'Rol estándar Santa Clara')).lastrowid
  for m in mods:
   acts=['VER']
   if role=='ADMINISTRADOR': acts=ACTIONS
   elif role=='RECEPCION': acts=['VER','CREAR','FACTURAR']
   elif role=='ADMISION': acts=['VER','CREAR','EDITAR','FACTURAR','ALTA','TRASLADAR']
   elif role=='ENFERMERIA': acts=['VER','CREAR','SOLICITAR']
   elif role=='FARMACIA': acts=['VER','AUTORIZAR','ENTREGAR']
   for a in acts:c.execute('insert into permisos_rol(rol_id,modulo,accion,permitido) values(?,?,?,1)',(rid,m,a))
 admin=c.execute("select id from usuarios where usuario='admin'").fetchone()
 rid=c.execute("select id from roles where nombre='ADMINISTRADOR'").fetchone()
 if admin and rid:c.execute('insert or ignore into usuario_roles(usuario_id,rol_id) values(?,?)',(admin[0],rid[0]))
 c.commit();c.close()

def user_has(modulo,accion='VER'):
 if not session.get('user'): return False
 c=db();r=c.execute('''select 1 from usuarios u join usuario_roles ur on ur.usuario_id=u.id join permisos_rol p on p.rol_id=ur.rol_id
 where u.usuario=? and u.activo=1 and p.modulo=? and p.accion=? and p.permitido=1 limit 1''',(session['user'],modulo,accion)).fetchone();c.close();return bool(r)

@app.context_processor
def inject_permissions(): return dict(has_perm=user_has,modulos_sistema=MODULES)

ROUTE_MODULE={
 'pacientes':'PACIENTES','hospital_admisiones':'ADMISION','cuenta_paciente':'ADMISION','facturar_admision':'FACTURACION','alta':'ADMISION','hospital_enfermeria':'ENFERMERIA',
 'consultas':'CONSULTORIO','liquidaciones_medicas':'FINANZAS','informes_consultas':'INFORMES','config_sanatorio':'CONFIG_SANATORIO',
 'productos':'STOCK','compras':'COMPRAS','ventas':'VENTAS','finanzas':'FINANZAS','contabilidad':'CONTABILIDAD','libros':'CONTABILIDAD'
}
@app.before_request
def modular_guard():
 # Rutas públicas / autenticación.
 publicos={None,'login','logout','static','agenda_web_publica','agenda_web_reservar','agenda_web_confirmacion'}
 if request.endpoint in publicos:return
 if not session.get('user'):return redirect('/login')

 # Administración de usuarios/roles: permiso explícito y exclusivo.
 if request.endpoint and request.endpoint.startswith('admin_'):
  if not user_has('USUARIOS','ADMINISTRAR'):return ('Acceso no autorizado',403)
  return

 # Permiso exacto por operación. Nunca basta VER para crear/editar/anular.
 reglas={
  'tipos_cambio':('FINANZAS','EDITAR' if request.method=='POST' else 'VER'),
  'terceros':('FINANZAS','CREAR' if request.method=='POST' else 'VER'),
  'tercero_editar':('FINANZAS','EDITAR'),'tercero_eliminar':('FINANZAS','ANULAR'),
  'productos':('STOCK','CREAR' if request.method=='POST' else 'VER'),
  'producto_editar':('STOCK','EDITAR'),'producto_eliminar':('STOCK','ANULAR'),
  'api_productos_buscar':('STOCK','VER'),
  'compras':('COMPRAS','CREAR' if request.method=='POST' else 'VER'),
  'compra_ver':('COMPRAS','VER'),'compra_editar':('COMPRAS','EDITAR'),
  'compra_eliminar':('COMPRAS','ANULAR'),'compra_cuotas':('COMPRAS','EDITAR'),
  'anular_compra':('COMPRAS','ANULAR'),
  'ventas_unificado':('VENTAS','VER'),'ventas':('VENTAS','CREAR' if request.method=='POST' else 'VER'),
  'recepcion_caja_unificada':('VENTAS','VER'),'cobrar_venta_credito':('FINANZAS','EDITAR'),
  'venta_cuotas':('VENTAS','EDITAR'),'anular_venta':('VENTAS','ANULAR'),
  'factura_venta':('VENTAS','VER'),'factura_venta_pdf':('VENTAS','VER'),
  'administrar_cajas':('FINANZAS','EDITAR' if request.method=='POST' else 'VER'),
  'historial_cierres_caja':('FINANZAS','VER'),
  'cobrar':('FINANZAS','EDITAR'),'pagar':('FINANZAS','EDITAR'),'finanzas':('FINANZAS','VER'),
  'recibo_pago':('FINANZAS','VER'),'recibo_pdf':('FINANZAS','VER'),'recibos_lista':('FINANZAS','VER'),
  'cuentas_bancarias':('FINANZAS','EDITAR' if request.method=='POST' else 'VER'),
  'terminales_pos':('FINANZAS','EDITAR' if request.method=='POST' else 'VER'),
  'conciliacion_bancaria':('FINANZAS','CREAR' if request.method=='POST' else 'VER'),
  'conciliacion_bancaria_detalle':('FINANZAS','EDITAR' if request.method=='POST' else 'VER'),
  'contabilidad':('CONTABILIDAD','VER'),'libros':('CONTABILIDAD','VER'),
  'plan_contable':('CONTABILIDAD','EDITAR' if request.method=='POST' else 'VER'),
  'plan_contable_desactivar':('CONTABILIDAD','ANULAR'),
  'contabilidad_informes':('CONTABILIDAD','VER'),'contabilidad_informe':('CONTABILIDAD','VER'),
  'contabilidad_excel':('CONTABILIDAD','VER'),'contabilidad_pdf':('CONTABILIDAD','VER'),
  'pacientes':('PACIENTES','CREAR' if request.method=='POST' else 'VER'),
  'editar_paciente':('PACIENTES','EDITAR'),'eliminar_paciente':('PACIENTES','ANULAR'),
  'paciente_eliminar':('PACIENTES','ANULAR'),'api_paciente_nuevo':('PACIENTES','CREAR'),
  'hospital_admisiones':('ADMISION','CREAR' if request.method=='POST' else 'VER'),
  'cuenta_paciente':('ADMISION','VER'),'facturar_admision':('FACTURACION','FACTURAR'),
  'alta':('ADMISION','ALTA'),'trasladar_internacion':('ADMISION','TRASLADAR'),
  'hospital_enfermeria':('ENFERMERIA','VER'),'enfermeria_solicitar_farmacia':('ENFERMERIA','SOLICITAR'),
  'farmacia_solicitudes':('FARMACIA','VER'),'farmacia_autorizar':('FARMACIA','AUTORIZAR'),
  'farmacia_entregar':('FARMACIA','ENTREGAR'),
  'consultas_medicas':('CONSULTORIO','CREAR' if request.method=='POST' else 'VER'),
  'mis_pacientes':('CONSULTORIO','VER'),'llamar_paciente':('CONSULTORIO','LLAMAR'),
  'historia_clinica_v12':('HISTORIA','HISTORIA' if request.method=='POST' else 'VER'),
  'liquidaciones_medicas':('FINANZAS','VER'),'liquidar_medico':('FINANZAS','EDITAR'),
  'agendamiento_inicio':('AGENDA','VER'),'agenda_turnos':('AGENDA','VER'),
  'agendamiento_v12':('AGENDA','CREAR' if request.method=='POST' else 'VER'),
  'agenda_estado':('AGENDA','EDITAR'),'horarios_medicos':('AGENDA','EDITAR' if request.method=='POST' else 'VER'),
  'imprimir_agendamiento':('AGENDA','VER'),'cobrar_agenda':('CAJA','COBRAR'),
  'recepcion_v12':('RECEPCION','VER'),'caja_recepcion':('CAJA','EDITAR' if request.method=='POST' else 'VER'),
  'config_medicos_usuarios':('CONFIG_SANATORIO','EDITAR' if request.method=='POST' else 'VER'),
  'config_sanatorio':('CONFIG_SANATORIO','EDITAR' if request.method=='POST' else 'VER'),
  'configuracion_empresa':('CONFIG_SANATORIO','EDITAR' if request.method=='POST' else 'VER'),
  'seguros_facturar':('FACTURACION','FACTURAR' if request.method=='POST' else 'VER'),
  'informes_consultas':('INFORMES','VER'),'exportar_consultas_xlsx':('INFORMES','VER'),
  'exportar_consultas_pdf':('INFORMES','VER'),'liquidacion_medica_pdf':('INFORMES','VER'),
  'informes_centro':('INFORMES','VER'),'informe_especifico':('INFORMES','VER'),'informe_pdf':('INFORMES','VER'),
  'auditoria_detallada':('USUARIOS','ADMINISTRAR'),
  'transaccion_anular':('CONTABILIDAD','ANULAR')
 }
 regla=reglas.get(request.endpoint)
 if regla and not user_has(regla[0],regla[1]):return ('Acceso no autorizado para esta operación',403)

 # Para cualquier ruta interna mapeada, exigir al menos VER.
 m=ROUTE_MODULE.get(request.endpoint)
 if m and not user_has(m,'VER'):return ('Acceso no autorizado para este módulo',403)

@app.route('/admin/usuarios-roles',methods=['GET','POST'])
def admin_usuarios_roles():
 c=db()
 if request.method=='POST':
  kind=request.form['kind']
  if kind=='usuario':
   uid=c.execute('insert into usuarios(nombre,usuario,clave,rol,activo,tipo_usuario,persona_tipo,persona_id) values(?,?,?,?,?,?,?,?)',(
    request.form['nombre'],request.form['usuario'],h(request.form['clave']),'MODULAR',1,request.form.get('tipo_usuario','EMPLEADO'),request.form.get('persona_tipo') or None,int(request.form['persona_id']) if request.form.get('persona_id') else None)).lastrowid
   rid=request.form.get('rol_id')
   if rid:c.execute('insert or ignore into usuario_roles(usuario_id,rol_id) values(?,?)',(uid,int(rid)))
  elif kind=='rol':c.execute('insert into roles(nombre,descripcion,activo) values(?,?,1)',(request.form['nombre'].upper(),request.form.get('descripcion','')))
  elif kind=='permisos':
   rid=int(request.form['rol_id']);c.execute('delete from permisos_rol where rol_id=?',(rid,))
   for key in request.form.getlist('perm'):
    mod,act=key.split('|',1);c.execute('insert into permisos_rol(rol_id,modulo,accion,permitido) values(?,?,?,1)',(rid,mod,act))
  elif kind=='asignar':
   uid=int(request.form['usuario_id']);c.execute('delete from usuario_roles where usuario_id=?',(uid,))
   rid=request.form.get('rol_id')
   if rid:c.execute('insert into usuario_roles(usuario_id,rol_id) values(?,?)',(uid,int(rid)))
  c.commit();audit_change(c,'CONFIGURAR','SEGURIDAD',0,despues={'tipo':kind});c.commit();c.close();return redirect('/admin/usuarios-roles')
 users=c.execute('select * from usuarios order by nombre').fetchall();roles=c.execute('select * from roles where activo=1 order by nombre').fetchall()
 selected_role=int(request.args.get('rol_id') or (roles[0]['id'] if roles else 0))
 perms=c.execute('select * from permisos_rol where rol_id=?',(selected_role,)).fetchall() if selected_role else []
 urs=c.execute('select * from usuario_roles').fetchall();medicos=c.execute('select id,nombre from medicos order by nombre').fetchall()
 empleados=[]
 try: empleados=c.execute('select id,nombre from empleados order by nombre').fetchall()
 except sqlite3.OperationalError: pass
 c.close()
 checked={(x['modulo'],x['accion']) for x in perms}; user_role={x['usuario_id']:x['rol_id'] for x in urs}
 return render_template('admin_roles.html',users=users,roles=roles,selected_role=selected_role,checked=checked,user_role=user_role,medicos=medicos,empleados=empleados,modules=MODULES,actions=ACTIONS)

@app.post('/enfermeria/solicitar-farmacia')
def enfermeria_solicitar_farmacia():
 c=db();aid=int(request.form['admision_id']);pid=int(request.form['producto_id']);qty=float(request.form['cantidad'])
 a=c.execute("select * from admisiones where id=? and estado='ABIERTA'",(aid,)).fetchone()
 if not a or a['tipo'] not in ('URGENCIA','INTERNACION','QUIROFANO'):
  c.close();flash('La solicitud solo puede realizarse para Urgencias, Internación o Quirófano activos.');return redirect('/enfermeria')
 sid=c.execute('insert into solicitudes_farmacia(fecha,admision_id,solicitante,observacion) values(?,?,?,?)',(now(),aid,session['user'],request.form.get('observacion',''))).lastrowid
 c.execute('insert into solicitud_farmacia_items(solicitud_id,producto_id,cantidad_solicitada) values(?,?,?)',(sid,pid,qty));audit_change(c,'SOLICITAR','FARMACIA',sid,despues={'admision':aid,'producto':pid,'cantidad':qty});c.commit();c.close();return redirect('/enfermeria')

@app.route('/farmacia-solicitudes')
def farmacia_solicitudes():
 c=db();rows=c.execute('''select s.*,p.nombre paciente,a.tipo,pr.nombre producto,pr.stock,i.id item_id,i.cantidad_solicitada,i.cantidad_autorizada,i.cantidad_entregada,i.estado item_estado
 from solicitudes_farmacia s join admisiones a on a.id=s.admision_id join pacientes p on p.id=a.paciente_id join solicitud_farmacia_items i on i.solicitud_id=s.id join productos pr on pr.id=i.producto_id order by s.id desc''').fetchall();c.close();return render_template('pharmacy_requests.html',rows=rows)

@app.post('/farmacia/autorizar/<int:item_id>')
def farmacia_autorizar(item_id):
 c=db();i=c.execute('''select i.*,p.stock from solicitud_farmacia_items i join productos p on p.id=i.producto_id where i.id=?''',(item_id,)).fetchone();qty=float(request.form['cantidad_autorizada'])
 if not i or qty<0 or qty>i['cantidad_solicitada'] or qty>i['stock']: c.close();flash('Cantidad inválida o stock insuficiente.');return redirect('/farmacia-solicitudes')
 estado='AUTORIZADA' if qty>0 else 'RECHAZADA';c.execute('update solicitud_farmacia_items set cantidad_autorizada=?,estado=? where id=?',(qty,estado,item_id));c.execute("update solicitudes_farmacia set estado=?,autorizado_por=?,autorizado_en=? where id=?",(estado,session['user'],now(),i['solicitud_id']));audit_change(c,'AUTORIZAR','FARMACIA',item_id,despues={'cantidad':qty});c.commit();c.close();return redirect('/farmacia-solicitudes')

@app.post('/farmacia/entregar/<int:item_id>')
def farmacia_entregar(item_id):
 c=db();i=c.execute('''select i.*,s.admision_id,p.nombre,p.stock,p.precio_pyg,p.costo_pyg,p.iva_pct from solicitud_farmacia_items i join solicitudes_farmacia s on s.id=i.solicitud_id join productos p on p.id=i.producto_id where i.id=?''',(item_id,)).fetchone()
 if not i or i['estado']!='AUTORIZADA':c.close();flash('El ítem debe estar autorizado antes de entregarse.');return redirect('/farmacia-solicitudes')
 qty=float(request.form.get('cantidad_entregada') or i['cantidad_autorizada']);pend=i['cantidad_autorizada']-i['cantidad_entregada']
 if qty<=0 or qty>pend or qty>i['stock']:c.close();flash('Cantidad de entrega inválida o stock insuficiente.');return redirect('/farmacia-solicitudes')
 a=c.execute('select moneda,tipo_cambio from admisiones where id=?',(i['admision_id'],)).fetchone();tc=float(a['tipo_cambio'] or 1);price=i['precio_pyg']/tc;total=qty*price
 c.execute('update productos set stock=stock-? where id=?',(qty,i['producto_id']));c.execute('insert into stock_mov(fecha,producto_id,tipo,cantidad,costo_pyg,origen_tipo,origen_id) values(?,?,?,?,?,?,?)',(now()[:10],i['producto_id'],'SALIDA',-qty,i['costo_pyg'],'FARMACIA_PACIENTE',i['admision_id']))
 c.execute('insert into cargos_paciente(fecha,admision_id,tipo,referencia_id,descripcion,cantidad,precio,moneda,tipo_cambio,total,total_pyg,iva_pct) values(?,?,?,?,?,?,?,?,?,?,?,?)',(now()[:10],i['admision_id'],'PRODUCTO',i['producto_id'],i['nombre'],qty,price,a['moneda'],tc,total,total*tc,float(i['iva_pct'] or 0)))
 newent=i['cantidad_entregada']+qty;estado='ENTREGADA' if newent>=i['cantidad_autorizada'] else 'PARCIAL';c.execute('update solicitud_farmacia_items set cantidad_entregada=?,estado=? where id=?',(newent,estado,item_id));c.execute('update solicitudes_farmacia set estado=? where id=?',(estado,i['solicitud_id']));audit_change(c,'ENTREGAR','FARMACIA',item_id,despues={'cantidad':qty,'admision':i['admision_id']});c.commit();c.close();return redirect('/farmacia-solicitudes')

@app.post('/trasladar-internacion/<int:aid>')
def trasladar_internacion(aid):
 if not user_has('ADMISION','TRASLADAR'):return ('Acceso no autorizado',403)
 c=db();a=c.execute('select * from admisiones where id=?',(aid,)).fetchone();cama=int(request.form['cama_id']) if request.form.get('cama_id') else None
 if not a or a['estado']!='ABIERTA':c.close();flash('Admisión no disponible.');return redirect('/admisiones')
 c.execute("update admisiones set tipo='INTERNACION',cama_id=? where id=?",(cama,aid));
 if cama:c.execute("update camas set estado='OCUPADA' where id=?",(cama,));audit_change(c,'TRASLADAR','ADMISION',aid,antes={'tipo':a['tipo']},despues={'tipo':'INTERNACION','cama':cama});c.commit();c.close();return redirect('/admisiones')


# ===== V12: Recepción, Caja, Agenda y Consultorio Médico =====
def init_v12():
 c=db()
 c.executescript('''
 CREATE TABLE IF NOT EXISTS formas_cobro(id INTEGER PRIMARY KEY,nombre TEXT UNIQUE,activo INT DEFAULT 1);
 CREATE TABLE IF NOT EXISTS cajas(id INTEGER PRIMARY KEY,nombre TEXT UNIQUE,activo INT DEFAULT 1);
 CREATE TABLE IF NOT EXISTS aperturas_caja(id INTEGER PRIMARY KEY,caja_id INT,usuario TEXT,fecha_apertura TEXT,saldo_inicial REAL DEFAULT 0,fecha_cierre TEXT,total_sistema REAL DEFAULT 0,total_declarado REAL DEFAULT 0,diferencia REAL DEFAULT 0,estado TEXT DEFAULT 'ABIERTA');
 CREATE TABLE IF NOT EXISTS movimientos_caja(id INTEGER PRIMARY KEY,apertura_id INT,fecha TEXT,tipo TEXT,forma_cobro_id INT,concepto TEXT,importe_pyg REAL,origen_tipo TEXT,origen_id INT,usuario TEXT);
 CREATE TABLE IF NOT EXISTS agenda(id INTEGER PRIMARY KEY,fecha TEXT,hora TEXT,paciente_id INT,medico_id INT,especialidad_id INT,aseguradora_id INT,motivo TEXT,estado TEXT DEFAULT 'AGENDADO',precio_pyg REAL DEFAULT 0,cobrado INT DEFAULT 0,consulta_id INT,creado_por TEXT,creado_en TEXT);
 CREATE TABLE IF NOT EXISTS historia_clinica(id INTEGER PRIMARY KEY,paciente_id INT,fecha TEXT,medico_id INT,agenda_id INT,motivo TEXT,anamnesis TEXT,diagnostico TEXT,indicaciones TEXT,observaciones TEXT,creado_por TEXT,creado_en TEXT);
 CREATE TABLE IF NOT EXISTS llamados_pacientes(id INTEGER PRIMARY KEY,agenda_id INT,fecha_hora TEXT,medico_id INT,texto TEXT,usuario TEXT);
 ''')
 for x in ('Efectivo','Banco','Transferencia','POS','Tarjeta de débito','Tarjeta de crédito','QR','Cheque'):
  c.execute('insert or ignore into formas_cobro(nombre) values(?)',(x,))
 c.execute("insert or ignore into cajas(nombre) values('Caja Recepción')")
 # médico vinculado a usuario
 cols=[r['name'] for r in c.execute('pragma table_info(medicos)').fetchall()]
 if 'usuario_id' not in cols:c.execute('alter table medicos add column usuario_id INT')
 # V13.4.6: toda consulta creada por Recepción queda facturada en el mismo acto.
 acols=[r['name'] for r in c.execute('pragma table_info(agenda)').fetchall()]
 for col,defn in [('venta_id','INT'),('factura_numero','TEXT'),('condicion_venta',"TEXT DEFAULT 'CONTADO'"),('forma_cobro','TEXT'),('facturada','INT DEFAULT 0')]:
  if col not in acols:c.execute(f'alter table agenda add column {col} {defn}')
 # módulos/acciones V12
 global MODULES,ACTIONS
 MODULES.update({'RECEPCION':'Recepción','AGENDA':'Agendamiento','CAJA':'Caja de Recepción','HISTORIA':'Historia Clínica'})
 for a in ('COBRAR','ABRIR_CAJA','CERRAR_CAJA','LLAMAR','HISTORIA'):
  if a not in ACTIONS:ACTIONS.append(a)
 # roles y permisos incrementales
 defs={
  'ADMINISTRADOR':[(m,a) for m in MODULES for a in ACTIONS],
  'RECEPCION':[('RECEPCION',a) for a in ('VER','CREAR','EDITAR','FACTURAR')]+[('AGENDA',a) for a in ('VER','CREAR','EDITAR','COBRAR')]+[('CAJA',a) for a in ('VER','ABRIR_CAJA','CERRAR_CAJA','COBRAR')],
  'ADMISION':[('RECEPCION','VER'),('AGENDA','VER'),('AGENDA','CREAR'),('CAJA','VER'),('CAJA','COBRAR')],
  'MEDICO':[('AGENDA','VER'),('CONSULTORIO','VER'),('CONSULTORIO','CREAR'),('CONSULTORIO','LLAMAR'),('HISTORIA','VER'),('HISTORIA','HISTORIA')]
 }
 for role,perms in defs.items():
  existente=c.execute('select id from roles where nombre=?',(role,)).fetchone()
  if existente:
   continue
  rid=c.execute('insert into roles(nombre,descripcion) values(?,?)',(role,'Rol estándar Santa Clara V12')).lastrowid
  for m,a in perms:c.execute('insert into permisos_rol(rol_id,modulo,accion,permitido) values(?,?,?,1)',(rid,m,a))
 c.commit();c.close()

def caja_abierta(c,usuario=None):
 usuario=usuario or session.get('user')
 return c.execute("select a.*,c.nombre caja from aperturas_caja a join cajas c on c.id=a.caja_id where a.usuario=? and a.estado='ABIERTA' order by a.id desc limit 1",(usuario,)).fetchone()

@app.route('/recepcion')
def recepcion_v12():
 c=db();ap=caja_abierta(c); hoy=datetime.date.today().isoformat()
 rows=c.execute('''select g.*,p.nombre paciente,p.documento,p.telefono,m.nombre medico,e.nombre especialidad from agenda g join pacientes p on p.id=g.paciente_id join medicos m on m.id=g.medico_id left join especialidades e on e.id=g.especialidad_id where g.fecha=? order by g.hora,g.id''',(hoy,)).fetchall();c.close()
 return render_template('reception_v12.html',rows=rows,ap=ap,hoy=hoy)

@app.route('/caja-recepcion',methods=['GET','POST'])
def caja_recepcion():
 c=db();ap=caja_abierta(c)
 if request.method=='POST':
  op=request.form['op']
  if op=='abrir':
   if ap:flash('Ya tiene una caja abierta.')
   else:
    c.execute('insert into aperturas_caja(caja_id,usuario,fecha_apertura,saldo_inicial) values(?,?,?,?)',(int(request.form['caja_id']),session['user'],now(),float(request.form.get('saldo_inicial') or 0)));c.commit();flash('Caja abierta correctamente.')
  elif op=='cerrar':
   if not ap:flash('No existe una caja abierta.')
   else:
    mov=c.execute("select coalesce(sum(case when tipo='INGRESO' then importe_pyg else -importe_pyg end),0) from movimientos_caja where apertura_id=?",(ap['id'],)).fetchone()[0];sistema=float(ap['saldo_inicial'])+float(mov);decl=float(request.form.get('total_declarado') or 0)
    c.execute("update aperturas_caja set fecha_cierre=?,total_sistema=?,total_declarado=?,diferencia=?,estado='CERRADA' where id=?",(now(),sistema,decl,decl-sistema,ap['id']));c.commit();flash('Caja cerrada. Diferencia: Gs. {:,.0f}'.format(decl-sistema))
  c.close();return redirect('/caja-recepcion')
 cajas=c.execute('select * from cajas where activo=1').fetchall();formas=c.execute('select * from formas_cobro where activo=1').fetchall();hist=c.execute('select * from aperturas_caja where usuario=? order by id desc limit 20',(session['user'],)).fetchall();mov=[]
 if ap:mov=c.execute('''select m.*,f.nombre forma from movimientos_caja m left join formas_cobro f on f.id=m.forma_cobro_id where m.apertura_id=? order by m.id desc''',(ap['id'],)).fetchall()
 c.close();return render_template('cash_v12.html',ap=ap,cajas=cajas,formas=formas,hist=hist,mov=mov)

@app.post('/api/paciente-nuevo')
def api_paciente_nuevo():
 if not (user_has('AGENDA','CREAR') or user_has('RECEPCION','CREAR')):return jsonify(ok=False,error='Sin permiso'),403
 d=request.get_json(force=True);c=db()
 try:
  nombre=(d.get('nombre') or '').strip();doc=(d.get('documento') or '').strip()
  if not nombre:raise ValueError('El nombre es obligatorio')
  ex=c.execute('select * from pacientes where documento=? and documento<>\'\'',(doc,)).fetchone() if doc else None
  if ex:return jsonify(ok=True,id=ex['id'],nombre=ex['nombre'])
  tid=c.execute("insert into terceros(tipo,ruc,nombre,telefono,email,moneda) values('CLIENTE',?,?,?,?,'PYG')",(doc,nombre,d.get('telefono'),d.get('email'))).lastrowid
  pid=c.execute('insert into pacientes(documento,nombre,fecha_nacimiento,telefono,direccion,tercero_id) values(?,?,?,?,?,?)',(doc,nombre,d.get('fecha_nacimiento'),d.get('telefono'),d.get('direccion'),tid)).lastrowid;c.commit();return jsonify(ok=True,id=pid,nombre=nombre)
 except Exception as e:c.rollback();return jsonify(ok=False,error=str(e)),400
 finally:c.close()


@app.get('/agendamiento')
def agendamiento_inicio():
 return redirect('/agendamiento/turnos?'+request.query_string.decode())

@app.route('/agendamiento/nueva',methods=['GET','POST'])
def agendamiento_v12():
 c=db()
 if request.method=='POST':
  try:
   pid=int(request.form['paciente_id']);mid=int(request.form['medico_id']);fecha=request.form['fecha'];hora=request.form['hora']
   m=c.execute('select * from medicos where id=?',(mid,)).fetchone();e=c.execute('select * from especialidades where nombre=?',(m['especialidad'],)).fetchone() if m else None;eid=e['id'] if e else None
   precio=float((m['precio_consulta'] if m and m['precio_consulta'] else (e['precio_consulta'] if e else 0)) or 0)
   honorario=float((m['honorario_consulta'] if m and m['honorario_consulta'] else (e['honorario_medico'] if e else 0)) or 0)
   condicion=(request.form.get('condicion_venta') or 'CONTADO').upper();medio=(request.form.get('forma_cobro') or '').strip();ref=(request.form.get('referencia_cobro') or '').strip()
   cuenta_id=int(request.form.get('cuenta_bancaria_id') or 0) or None
   pos_id=int(request.form.get('terminal_pos_id') or 0) or None
   if condicion not in ('CONTADO','CREDITO'):raise ValueError('Seleccione CONTADO o CRÉDITO')
   if condicion=='CONTADO' and medio not in ('Efectivo','Banco','Transferencia','POS'):raise ValueError('Seleccione la forma de cobro: Efectivo, Banco, Transferencia o POS')
   if condicion in ('CONTADO','CUOTAS') and (condicion=='CONTADO' or entrega>0) and medio=='Efectivo' and not caja_abierta(c):raise ValueError('Debe abrir Recepción y Caja antes de cobrar una consulta en efectivo')
   if condicion in ('CONTADO','CUOTAS') and (condicion=='CONTADO' or entrega>0) and medio in ('Banco','Transferencia','POS') and not cuenta_id:raise ValueError('Seleccione la cuenta bancaria receptora')
   if condicion in ('CONTADO','CUOTAS') and (condicion=='CONTADO' or entrega>0) and medio=='POS' and not pos_id:raise ValueError('Seleccione la terminal POS')
   pte=c.execute('select * from pacientes where id=?',(pid,)).fetchone()
   if not pte or not pte['tercero_id']:raise ValueError('El paciente debe estar vinculado a un cliente para poder facturar')
   tercero_id=int(pte['tercero_id']);aseg=request.form.get('aseguradora_id') or None
   # Seguro: registrar atención y dejarla pendiente, sin factura inmediata.
   if aseg:
    aseg=int(aseg);cura=c.execute("insert into agenda(fecha,hora,paciente_id,medico_id,especialidad_id,aseguradora_id,motivo,precio_pyg,cobrado,creado_por,creado_en,facturada,condicion_venta) values(?,?,?,?,?,?,?,?,?,?,?,?,?)",(fecha,hora,pid,mid,eid,aseg,request.form.get('motivo'),precio,0,session['user'],now(),0,'SEGURO'));gid=cura.lastrowid
    qid=c.execute('insert into consultas(fecha,hora,paciente_id,medico_id,especialidad_id,aseguradora_id,admision_id,moneda,tipo_cambio,precio,honorario_medico,precio_pyg,honorario_pyg,observacion,estado) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(fecha,hora,pid,mid,eid,aseg,None,'PYG',1,precio,honorario,precio,honorario,request.form.get('motivo'),'REALIZADA')).lastrowid
    c.execute('update agenda set consulta_id=? where id=?',(qid,gid));c.execute("insert into seguro_pendientes(fecha,aseguradora_id,paciente_id,origen_tipo,origen_id,categoria,descripcion,importe_pyg,iva_pct,estado) values(?,?,?,?,?,?,?,?,?,'PENDIENTE')",(fecha,aseg,pid,'CONSULTA',qid,'SERVICIOS SANATORIALES','Consulta - '+(e['nombre'] if e else 'Consulta médica'),precio,10));c.commit();audit('CONSULTA_SEGURO_PENDIENTE',f'Agenda {gid} / Consulta {qid}');flash('Consulta registrada y PENDIENTE DE FACTURACIÓN AL SEGURO.');return redirect('/agendamiento?imprimir='+str(gid))
   siguiente=c.execute('select coalesce(max(id),0)+1 from ventas').fetchone()[0];numero='CONS-'+fecha.replace('-','')+'-'+str(siguiente).zfill(6)
   iva_pct=10.0;base,iva=desglosar_iva_incluido(precio,iva_pct)
   curv=c.execute('''insert into ventas(fecha,cliente_id,numero,moneda,tipo_cambio,gravado,iva,exento,total,total_pyg,gravado_10,iva_10,gravado_5,iva_5,exento_iva,condicion_venta,forma_cobro,referencia_cobro)
                    values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(fecha,tercero_id,numero,'PYG',1,base,iva,0,precio,precio,base,iva,0,0,0,condicion,medio or None,ref or None));vid=curv.lastrowid
   c.execute('update ventas set cuenta_bancaria_id=?,terminal_pos_id=? where id=?',(cuenta_id,pos_id,vid))
   c.execute('insert into venta_items(venta_id,producto_id,cantidad,precio,total,total_pyg,costo_pyg,iva_pct) values(?,?,?,?,?,?,?,?)',(vid,None,1,precio,base,base,0,iva_pct))
   saldo=0 if condicion=='CONTADO' else precio;estado_cxc='PAGADO' if condicion=='CONTADO' else 'PENDIENTE'
   c.execute('insert into cxc(venta_id,tercero_id,moneda,tipo_cambio_origen,importe,saldo,importe_pyg,estado) values(?,?,?,?,?,?,?,?)',(vid,tercero_id,'PYG',1,precio,saldo,precio,estado_cxc))
   if condicion=='CONTADO':
    c.execute('insert into caja_banco(fecha,tipo,medio,moneda,tipo_cambio,importe,importe_pyg,concepto,origen_tipo,origen_id,cuenta_bancaria_id,terminal_pos_id) values(?,?,?,?,?,?,?,?,?,?,?,?)',(fecha,'INGRESO',medio,'PYG',1,precio,precio,'Cobro consulta en Recepción','VENTA_CONSULTA',vid,cuenta_id,pos_id))
    if medio=='Efectivo':
     ap=caja_abierta(c);fid=c.execute("select id from formas_cobro where nombre='Efectivo'").fetchone();c.execute("insert into movimientos_caja(apertura_id,fecha,tipo,forma_cobro_id,concepto,importe_pyg,origen_tipo,origen_id,usuario) values(?,?,'INGRESO',?,?,?,?,?,?)",(ap['id'],now(),fid['id'] if fid else None,'Cobro consulta '+numero,precio,'VENTA_CONSULTA',vid,session.get('user')))
   cuenta_debe='1.1.01' if condicion=='CONTADO' else '1.1.02'
   asiento(c,fecha,'Consulta facturada '+numero,'VENTA_CONSULTA',vid,'PYG',1,[(cuenta_debe,precio,0,precio,'Consulta '+condicion.lower()),('4.1.03',0,base,base,'Ingreso por consulta'),('2.1.02',0,iva,iva,'IVA débito')])
   cura=c.execute('''insert into agenda(fecha,hora,paciente_id,medico_id,especialidad_id,aseguradora_id,motivo,precio_pyg,cobrado,creado_por,creado_en,venta_id,factura_numero,condicion_venta,forma_cobro,facturada)
                     values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1)''',(fecha,hora,pid,mid,eid,aseg,request.form.get('motivo'),precio,1 if condicion=='CONTADO' else 0,session['user'],now(),vid,numero,condicion,medio or None));gid=cura.lastrowid
   curq=c.execute('insert into consultas(fecha,hora,paciente_id,medico_id,especialidad_id,aseguradora_id,admision_id,moneda,tipo_cambio,precio,honorario_medico,precio_pyg,honorario_pyg,observacion,estado) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(fecha,hora,pid,mid,eid,aseg,None,'PYG',1,precio,honorario,precio,honorario,request.form.get('motivo'),'REALIZADA'));qid=curq.lastrowid
   c.execute('update agenda set consulta_id=? where id=?',(qid,gid));c.commit();audit('CONSULTA_FACTURADA_RECEPCION',f'Agenda {gid} / Venta {vid} / {numero}');flash('Consulta registrada y facturada correctamente: '+numero);c.close();return redirect('/agendamiento?imprimir='+str(gid))
  except Exception as ex:
   c.rollback();flash('No se pudo registrar/facturar la consulta: '+str(ex))
  finally:c.close()
  return redirect('/agendamiento')
 pats=c.execute('select * from pacientes order by nombre').fetchall();meds=c.execute('select * from medicos order by nombre').fetchall();asegs=c.execute('select * from aseguradoras order by nombre').fetchall();formas=c.execute('select * from formas_cobro where activo=1 order by id').fetchall();cuentas=c.execute('select * from cuentas_bancarias where activo=1 order by banco,alias').fetchall();poses=c.execute('select * from terminales_pos where activo=1 order by nombre').fetchall();rows=c.execute('''select g.*,p.nombre paciente,p.documento,p.telefono,p.fecha_nacimiento,p.direccion,m.nombre medico,e.nombre especialidad,a.nombre aseguradora from agenda g join pacientes p on p.id=g.paciente_id join medicos m on m.id=g.medico_id left join especialidades e on e.id=g.especialidad_id left join aseguradoras a on a.id=g.aseguradora_id order by g.fecha desc,g.hora desc limit 300''').fetchall();c.close();return render_template('agenda_v12.html',pats=pats,meds=meds,asegs=asegs,formas=formas,cuentas=cuentas,poses=poses,rows=rows,pref_fecha=request.args.get('fecha',''),pref_hora=request.args.get('hora',''),pref_medico=request.args.get('medico_id',type=int))


@app.route('/agenda/<int:gid>/imprimir')
def imprimir_agendamiento(gid):
 c=db()
 x=c.execute("""select g.*,p.nombre paciente,p.documento,p.telefono,p.direccion,
                       m.nombre medico,e.nombre especialidad,a.nombre aseguradora
                from agenda g
                join pacientes p on p.id=g.paciente_id
                join medicos m on m.id=g.medico_id
                left join especialidades e on e.id=g.especialidad_id
                left join aseguradoras a on a.id=g.aseguradora_id
                where g.id=?""",(gid,)).fetchone()
 if not x:
  c.close();return ('Agendamiento no encontrado',404)
 responsable=x['creado_por'] or 'Agendamiento Web'
 try:
  c.execute("""create table if not exists impresiones_agenda(
      id integer primary key autoincrement, agenda_id integer not null,
      fecha_hora text not null, usuario text, tipo text default 'TICKET_TERMICO')""")
  c.execute("insert into impresiones_agenda(agenda_id,fecha_hora,usuario,tipo) values(?,?,?,'TICKET_TERMICO')",
            (gid,now(),session.get('user') or responsable))
  c.commit()
 except Exception:
  c.rollback()
 c.close()
 audit('REIMPRESION_AGENDA',f'Agenda {gid} / responsable {responsable}')
 return render_template('agenda_ticket_termico.html',x=x,responsable=responsable,autoprint=request.args.get('auto')=='1')

@app.post('/agenda/<int:gid>/cobrar')
def cobrar_agenda(gid):
 if not user_has('CAJA','COBRAR'):return ('Acceso no autorizado',403)
 c=db();ap=caja_abierta(c)
 if not ap:c.close();flash('Debe abrir su caja antes de cobrar.');return redirect('/agendamiento')
 g=c.execute('select * from agenda where id=?',(gid,)).fetchone()
 if not g or g['cobrado']:c.close();flash('La agenda no existe o ya fue cobrada.');return redirect('/agendamiento')
 forma=int(request.form['forma_cobro_id']);imp=float(g['precio_pyg'] or 0);c.execute("insert into movimientos_caja(apertura_id,fecha,tipo,forma_cobro_id,concepto,importe_pyg,origen_tipo,origen_id,usuario) values(?,?,'INGRESO',?,?,?,?,?,?)",(ap['id'],now(),forma,'Cobro de consulta',imp,'AGENDA',gid,session['user']));c.execute('update agenda set cobrado=1 where id=?',(gid,));c.commit();c.close();flash('Cobro registrado en caja.');return redirect('/agendamiento')

@app.route('/mis-pacientes')
def mis_pacientes():
 c=db();u=c.execute('select id from usuarios where usuario=?',(session['user'],)).fetchone();m=c.execute('select * from medicos where usuario_id=?',(u['id'],)).fetchone() if u else None
 if not m:c.close();return render_template('doctor_patients_v12.html',medico=None,rows=[])
 hoy=request.args.get('fecha') or datetime.date.today().isoformat();rows=c.execute('''select g.*,p.nombre paciente,p.documento,p.telefono,e.nombre especialidad from agenda g join pacientes p on p.id=g.paciente_id left join especialidades e on e.id=g.especialidad_id where g.medico_id=? and g.fecha=? order by g.hora,g.id''',(m['id'],hoy)).fetchall();c.close();return render_template('doctor_patients_v12.html',medico=m,rows=rows,hoy=hoy)

@app.post('/llamar-paciente/<int:gid>')
def llamar_paciente(gid):
 if not (user_has('AGENDA','LLAMAR') or user_has('CONSULTORIO','LLAMAR')):return jsonify(ok=False,error='Sin permiso para llamar pacientes'),403
 c=db();r=c.execute('''select g.*,p.nombre paciente,m.nombre medico from agenda g join pacientes p on p.id=g.paciente_id join medicos m on m.id=g.medico_id where g.id=?''',(gid,)).fetchone()
 if not r:c.close();return jsonify(ok=False,error='Agenda no encontrada'),404
 texto=f"Paciente {r['paciente']}, favor pasar al consultorio del doctor {r['medico']}";c.execute('insert into llamados_pacientes(agenda_id,fecha_hora,medico_id,texto,usuario) values(?,?,?,?,?)',(gid,now(),r['medico_id'],texto,session['user']));c.execute("update agenda set estado='LLAMADO' where id=?",(gid,));c.commit();c.close();return jsonify(ok=True,texto=texto)

@app.route('/historia-clinica/<int:pid>',methods=['GET','POST'])
def historia_clinica_v12(pid):
 if not (user_has('HISTORIA','VER') or user_has('HISTORIA','HISTORIA')):return ('Acceso no autorizado',403)
 c=db();p=c.execute('select * from pacientes where id=?',(pid,)).fetchone();u=c.execute('select id from usuarios where usuario=?',(session['user'],)).fetchone();m=c.execute('select * from medicos where usuario_id=?',(u['id'],)).fetchone() if u else None
 if request.method=='POST':
  if not m:c.close();return ('Debe vincular este usuario a un médico en Configuración Sanatorial.',400)
  c.execute('insert into historia_clinica(paciente_id,fecha,medico_id,agenda_id,motivo,anamnesis,diagnostico,indicaciones,observaciones,creado_por,creado_en) values(?,?,?,?,?,?,?,?,?,?,?)',(pid,request.form.get('fecha') or datetime.date.today().isoformat(),m['id'],request.form.get('agenda_id') or None,request.form.get('motivo'),request.form.get('anamnesis'),request.form.get('diagnostico'),request.form.get('indicaciones'),request.form.get('observaciones'),session['user'],now()));c.commit();flash('Historia clínica actualizada.')
 rows=c.execute('''select h.*,m.nombre medico from historia_clinica h left join medicos m on m.id=h.medico_id where h.paciente_id=? order by h.fecha desc,h.id desc''',(pid,)).fetchall();c.close();return render_template('clinical_history_v12.html',p=p,rows=rows)

@app.route('/config-medicos-usuarios',methods=['GET','POST'])
def config_medicos_usuarios():
 if not user_has('CONFIG_SANATORIO','VER'):return ('Acceso no autorizado',403)
 c=db()
 if request.method=='POST':
  mid=int(request.form['medico_id']);uid=int(request.form['usuario_id']) if request.form.get('usuario_id') else None
  if uid:c.execute('update medicos set usuario_id=null where usuario_id=?',(uid,))
  c.execute('update medicos set usuario_id=? where id=?',(uid,mid));c.commit();flash('Usuario médico vinculado correctamente.');c.close();return redirect('/config-medicos-usuarios')
 rows=c.execute('''select m.*,u.nombre usuario_nombre,u.usuario from medicos m left join usuarios u on u.id=m.usuario_id order by m.nombre''').fetchall();users=c.execute('select * from usuarios where activo=1 order by nombre').fetchall();c.close();return render_template('doctor_user_config_v12.html',rows=rows,users=users)


# Guardas V12
ROUTE_MODULE.update({'agendamiento_inicio':'AGENDA','recepcion_v12':'RECEPCION','caja_recepcion':'CAJA','agendamiento_v12':'AGENDA','cobrar_agenda':'CAJA','mis_pacientes':'CONSULTORIO','llamar_paciente':'AGENDA','historia_clinica_v12':'HISTORIA','config_medicos_usuarios':'CONFIG_SANATORIO'})

def preparar_actualizacion_segura():
 # La base de datos es persistente: nunca se elimina ni se reemplaza durante una actualización.
 if not os.path.exists(DB): return
 c=sqlite3.connect(DB)
 try:
  c.execute("CREATE TABLE IF NOT EXISTS schema_migrations(version TEXT PRIMARY KEY, aplicado_en TEXT)")
  ya=c.execute("SELECT 1 FROM schema_migrations WHERE version=?",('V13.3',)).fetchone()
  if not ya:
   carpeta=os.path.join(os.path.dirname(DB),'backups')
   os.makedirs(carpeta,exist_ok=True)
   destino=os.path.join(carpeta,'santa_clara_antes_V13_3_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'.db')
   c.commit(); shutil.copy2(DB,destino)
   c.execute("INSERT INTO schema_migrations(version,aplicado_en) VALUES(?,?)",('V13.3',now()));c.commit()
 finally:c.close()

backup_inicio()
preparar_actualizacion_segura()
init()
init_v1357_codigo_barras()
init_consultorio()
init_modular()
init_v12()
# V13.4.5: Ventas contado/crédito, recibos y Recepción+Caja unificados. Migración incremental, sin borrar datos.
c=db()
for tabla,col,defn in [
 ('ventas','condicion_venta',"TEXT DEFAULT 'CREDITO'"),('ventas','forma_cobro',"TEXT"),('ventas','referencia_cobro',"TEXT")]:
 cols=[r['name'] for r in c.execute(f'pragma table_info({tabla})').fetchall()]
 if col not in cols:c.execute(f'alter table {tabla} add column {col} {defn}')
c.executescript("""
CREATE TABLE IF NOT EXISTS recibos_pago(
 id INTEGER PRIMARY KEY, numero TEXT UNIQUE, fecha TEXT, cxc_id INT, venta_id INT, tercero_id INT,
 moneda TEXT, tipo_cambio REAL, importe REAL, importe_pyg REAL, saldo_anterior REAL, saldo_restante REAL,
 medio TEXT, referencia TEXT, usuario TEXT, estado TEXT DEFAULT 'EMITIDO'
);
CREATE TABLE IF NOT EXISTS cuentas_bancarias(
 id INTEGER PRIMARY KEY, banco TEXT NOT NULL, numero_cuenta TEXT, tipo_cuenta TEXT, moneda TEXT DEFAULT 'PYG',
 titular TEXT, alias TEXT, acepta_transferencia INT DEFAULT 1, acepta_pos INT DEFAULT 1, activo INT DEFAULT 1
);
CREATE TABLE IF NOT EXISTS terminales_pos(
 id INTEGER PRIMARY KEY, nombre TEXT NOT NULL, cuenta_bancaria_id INT, activo INT DEFAULT 1
);
""")
for tabla,col,defn in [
 ('recibos_pago','cuenta_bancaria_id','INTEGER'),('recibos_pago','terminal_pos_id','INTEGER'),
 ('caja_banco','cuenta_bancaria_id','INTEGER'),('caja_banco','terminal_pos_id','INTEGER'),
 ('ventas','cuenta_bancaria_id','INTEGER'),('ventas','terminal_pos_id','INTEGER')]:
 cols=[r['name'] for r in c.execute(f'pragma table_info({tabla})').fetchall()]
 if col not in cols:c.execute(f'alter table {tabla} add column {col} {defn}')
for x in ('Efectivo','Banco','Transferencia','POS'):
 c.execute('insert or ignore into formas_cobro(nombre) values(?)',(x,))
c.commit();c.close()
# Migración incremental de usuarios simplificados. No borra registros existentes.
c=db()
cols=[r['name'] for r in c.execute('pragma table_info(usuarios)').fetchall()]
for col,defn in [('tipo_usuario',"TEXT DEFAULT 'EMPLEADO'"),('persona_tipo','TEXT'),('persona_id','INTEGER')]:
 if col not in cols:c.execute(f'alter table usuarios add column {col} {defn}')
c.commit();c.close()
# El arranque de Flask debe quedar al FINAL del archivo para registrar todas las rutas.

# ===== V13.1 OPERATIVA: CRUD, BUSQUEDA Y CREACION DIRECTA =====
def _safe_delete_master(table, rid, dependencies):
    c=db()
    for tab,col in dependencies:
        if c.execute(f'SELECT 1 FROM {tab} WHERE {col}=? LIMIT 1',(rid,)).fetchone():
            c.close(); return False, 'No se puede eliminar: el registro tiene movimientos relacionados. Puede editarlo o desactivarlo.'
    c.execute(f'DELETE FROM {table} WHERE id=?',(rid,)); c.commit(); c.close(); return True, 'Registro eliminado.'

@app.route('/producto/<int:rid>/editar',methods=['GET','POST'])
def producto_editar(rid):
    c=db(); r=c.execute('select * from productos where id=?',(rid,)).fetchone()
    if request.method=='POST':
        cb=(request.form.get('codigo_barras') or '').strip() or None
        if cb and c.execute('select 1 from productos where codigo_barras=? and id<>?',(cb,rid)).fetchone():flash('Código de barras ya registrado en otro producto.');c.close();return redirect(f'/producto/{rid}/editar')
        c.execute('update productos set codigo=?,codigo_barras=?,nombre=?,categoria=?,costo_pyg=?,precio_pyg=?,stock_min=?,iva_pct=? where id=?',(request.form['codigo'],cb,request.form['nombre'],request.form.get('categoria'),float(request.form.get('costo_pyg') or 0),float(request.form.get('precio_pyg') or 0),float(request.form.get('stock_min') or 0),float(request.form.get('iva_pct') or 0),rid));c.commit();c.close();audit('EDITAR_PRODUCTO',str(rid));return redirect('/productos')
    c.close();return render_template('edit_master.html',title='Modificar producto',record=r,kind='producto')
@app.post('/producto/<int:rid>/eliminar')
def producto_eliminar(rid):
    ok,msg=_safe_delete_master('productos',rid,[('compra_items','producto_id'),('venta_items','producto_id'),('stock_mov','producto_id'),('cargos_paciente','referencia_id')]);flash(msg);audit('ELIMINAR_PRODUCTO' if ok else 'BLOQUEO_ELIMINAR_PRODUCTO',str(rid));return redirect('/productos')

@app.route('/tercero/<int:rid>/editar',methods=['GET','POST'])
def tercero_editar(rid):
    c=db();r=c.execute('select * from terceros where id=?',(rid,)).fetchone();mons=c.execute('select * from monedas').fetchall()
    if request.method=='POST':
        c.execute('update terceros set tipo=?,ruc=?,nombre=?,telefono=?,email=?,moneda=? where id=?',(request.form['tipo'],request.form.get('ruc'),request.form['nombre'],request.form.get('telefono'),request.form.get('email'),request.form['moneda'],rid));c.commit();c.close();audit('EDITAR_TERCERO',str(rid));return redirect('/terceros')
    c.close();return render_template('edit_master.html',title='Modificar cliente/proveedor',record=r,kind='tercero',mons=mons)
@app.post('/tercero/<int:rid>/eliminar')
def tercero_eliminar(rid):
    ok,msg=_safe_delete_master('terceros',rid,[('compras','proveedor_id'),('ventas','cliente_id'),('cxc','tercero_id'),('cxp','tercero_id'),('pacientes','tercero_id'),('aseguradoras','tercero_id'),('medicos','tercero_id')]);flash(msg);audit('ELIMINAR_TERCERO' if ok else 'BLOQUEO_ELIMINAR_TERCERO',str(rid));return redirect('/terceros')

@app.route('/paciente/<int:rid>/eliminar',methods=['POST'])
def paciente_eliminar(rid):
    c=db();p=c.execute('select * from pacientes where id=?',(rid,)).fetchone()
    if c.execute('select 1 from admisiones where paciente_id=? limit 1',(rid,)).fetchone():flash('No se puede eliminar un paciente con admisiones o historia relacionada.');c.close();return redirect('/pacientes')
    if p:c.execute('delete from pacientes where id=?',(rid,));c.execute('delete from terceros where id=?',(p['tercero_id'],));c.commit();audit('ELIMINAR_PACIENTE',str(rid))
    c.close();return redirect('/pacientes')

@app.post('/transaccion/<string:kind>/<int:rid>/anular')
def transaccion_anular(kind,rid):
    if kind not in ('compra','venta'):return redirect('/')
    c=db();tabla='compras' if kind=='compra' else 'ventas';r=c.execute(f'select * from {tabla} where id=?',(rid,)).fetchone()
    if not r or r['estado']=='ANULADA':c.close();return redirect('/'+('compras' if kind=='compra' else 'ventas'))
    if kind=='compra':
        items=c.execute('select * from compra_items where compra_id=?',(rid,)).fetchall()
        for i in items:c.execute('update productos set stock=stock-? where id=?',(i['cantidad'],i['producto_id']));c.execute('insert into stock_mov(fecha,producto_id,tipo,cantidad,costo_pyg,origen_tipo,origen_id) values(?,?,?,?,?,?,?)',(now()[:10],i['producto_id'],'REVERSA_COMPRA',-i['cantidad'],0,'ANULACION_COMPRA',rid))
        c.execute("update cxp set saldo=0,estado='ANULADA' where compra_id=?",(rid,))
    else:
        items=c.execute('select * from venta_items where venta_id=?',(rid,)).fetchall()
        for i in items:c.execute('update productos set stock=stock+? where id=?',(i['cantidad'],i['producto_id']));c.execute('insert into stock_mov(fecha,producto_id,tipo,cantidad,costo_pyg,origen_tipo,origen_id) values(?,?,?,?,?,?,?)',(now()[:10],i['producto_id'],'REVERSA_VENTA',i['cantidad'],i['costo_pyg'],'ANULACION_VENTA',rid))
        c.execute("update cxc set saldo=0,estado='ANULADA' where venta_id=?",(rid,))
    c.execute(f"update {tabla} set estado='ANULADA' where id=?",(rid,));c.execute("update asientos set estado='ANULADO' where origen_tipo=? and origen_id=?",(kind.upper(),rid));c.commit();c.close();audit('ANULAR_'+kind.upper(),str(rid));flash(kind.title()+' anulada y movimientos relacionados revertidos.');return redirect('/'+('compras' if kind=='compra' else 'ventas'))

@app.get('/api/buscar/<string:tipo>')
def api_buscar(tipo):
    q='%'+(request.args.get('q') or '')+'%';c=db()
    if tipo=='productos':rows=c.execute('select id,codigo,nombre,precio_pyg,stock,iva_pct from productos where codigo like ? or nombre like ? order by nombre limit 30',(q,q)).fetchall()
    elif tipo=='pacientes':rows=c.execute('select id,documento,nombre,telefono from pacientes where documento like ? or nombre like ? order by nombre limit 30',(q,q)).fetchall()
    elif tipo=='terceros':rows=c.execute('select id,ruc,nombre,tipo from terceros where ruc like ? or nombre like ? order by nombre limit 30',(q,q)).fetchall()
    elif tipo=='medicos':rows=c.execute('select id,nombre,registro,especialidad from medicos where nombre like ? or registro like ? order by nombre limit 30',(q,q)).fetchall()
    else:rows=[]
    out=[dict(x) for x in rows];c.close();return jsonify(out)


@app.get('/recibos/<int:rid>/pdf')
def recibo_pdf(rid):
 from reportlab.lib.pagesizes import A4
 from reportlab.lib import colors
 from reportlab.lib.styles import getSampleStyleSheet
 from reportlab.lib.units import mm
 from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle
 c=db(); r=c.execute("select rp.*,v.numero factura,t.nombre cliente,t.ruc,cb.banco,cb.numero_cuenta,cb.alias cuenta_alias,tp.nombre terminal_pos from recibos_pago rp join ventas v on v.id=rp.venta_id join terceros t on t.id=rp.tercero_id left join cuentas_bancarias cb on cb.id=rp.cuenta_bancaria_id left join terminales_pos tp on tp.id=rp.terminal_pos_id where rp.id=?",(rid,)).fetchone(); inst=c.execute('select * from institucion_config where id=1').fetchone(); c.close()
 if not r:return 'Recibo no encontrado',404
 bio=io.BytesIO(); doc=SimpleDocTemplate(bio,pagesize=A4,leftMargin=10*mm,rightMargin=10*mm,topMargin=8*mm,bottomMargin=8*mm); st=getSampleStyleSheet(); story=[]; logo=pdf_logo(105,72)
 if logo:story.append(logo)
 story += [Paragraph('<b>'+str(inst['nombre'] or 'CENTRO MEDICO SANTA CLARA')+'</b>',st['Heading2']),Paragraph('R.U.C.: '+str(inst['ruc'] or 'Configurar')+' &nbsp;&nbsp; Timbrado: '+str(inst['timbrado'] or 'Configurar'),st['Normal']),Paragraph(str(inst['direccion'] or '')+' '+str(inst['telefono'] or '')+' '+str(inst['email'] or ''),st['Normal']),Spacer(1,3*mm),Paragraph('<b>RECIBO DE DINERO</b><br/><b>'+str(r['numero'])+'</b>',st['Title']),Spacer(1,3*mm)]
 datos=[['Fecha de Emisión: '+str(r['fecha']),'R.U.C./C.I.: '+str(r['ruc'] or '')],['Moneda: '+str(r['moneda'])+'   Tipo de Cambio: '+str(r['tipo_cambio'] or ''),'Razón Social: '+str(r['cliente'])]]; t=Table(datos,colWidths=[90*mm,90*mm]); t.setStyle(TableStyle([('BOX',(0,0),(-1,-1),.5,colors.grey),('INNERGRID',(0,0),(-1,-1),.25,colors.lightgrey),('FONTSIZE',(0,0),(-1,-1),8),('VALIGN',(0,0),(-1,-1),'TOP'),('PADDING',(0,0),(-1,-1),5)])); story += [t,Spacer(1,2*mm)]
 comp=[['Comprobante','Concepto','Importe Pagado'],[r['factura'],'Venta / Consulta',f"{r['importe']:,.0f}"],['','TOTAL COBRADO',f"{r['importe']:,.0f}"]]; t=Table(comp,colWidths=[55*mm,80*mm,45*mm]); t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.lightgrey),('GRID',(0,0),(-1,-1),.5,colors.grey),('ALIGN',(-1,1),(-1,-1),'RIGHT'),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),8)])); story += [t,Paragraph('Son: '+monto_letras(r['importe']),st['Normal']),Spacer(1,2*mm)]
 entidad=' '.join(x for x in [r['banco'] or '',r['cuenta_alias'] or r['numero_cuenta'] or '',r['terminal_pos'] or ''] if x); cob=[['Método','Entidad / Cuenta','Referencia','Moneda','Importe'],[r['medio'],entidad,r['referencia'] or '',r['moneda'],f"{r['importe']:,.0f}"]]; t=Table(cob,colWidths=[32*mm,62*mm,35*mm,22*mm,29*mm]); t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.lightgrey),('GRID',(0,0),(-1,-1),.5,colors.grey),('FONTSIZE',(0,0),(-1,-1),7.5),('ALIGN',(-1,1),(-1,-1),'RIGHT')])); story += [Paragraph('<b>Composición del Cobro</b>',st['Heading3']),t,Spacer(1,16*mm),Table([['_______________________________','_______________________________'],['Entregué conforme','Recibí conforme']],colWidths=[90*mm,90*mm],style=[('ALIGN',(0,0),(-1,-1),'CENTER'),('FONTSIZE',(0,0),(-1,-1),8)])]; doc.build(story); bio.seek(0); return send_file(bio,mimetype='application/pdf',as_attachment=False,download_name=str(r['numero'])+'.pdf')

# ===== V13.4.7: recibos históricos, cuentas receptoras y PDF de informes =====
@app.route('/bancos/cuentas',methods=['GET','POST'])
def cuentas_bancarias():
 c=db()
 if request.method=='POST':
  op=request.form.get('op','nuevo')
  if op=='nuevo':
   c.execute('insert into cuentas_bancarias(banco,numero_cuenta,tipo_cuenta,moneda,titular,alias,acepta_transferencia,acepta_pos,activo) values(?,?,?,?,?,?,?,?,1)',(request.form['banco'],request.form.get('numero_cuenta'),request.form.get('tipo_cuenta'),request.form.get('moneda','PYG'),request.form.get('titular'),request.form.get('alias'),1 if request.form.get('acepta_transferencia') else 0,1 if request.form.get('acepta_pos') else 0))
  elif op=='estado':c.execute('update cuentas_bancarias set activo=case when activo=1 then 0 else 1 end where id=?',(int(request.form['id']),))
  c.commit();c.close();audit('CUENTA_BANCARIA',op);return redirect('/bancos/cuentas')
 rows=c.execute('select * from cuentas_bancarias order by activo desc,banco,alias').fetchall();c.close();return render_template('bank_accounts.html',rows=rows)

@app.route('/bancos/pos',methods=['GET','POST'])
def terminales_pos():
 c=db()
 if request.method=='POST':
  c.execute('insert into terminales_pos(nombre,cuenta_bancaria_id,activo) values(?,?,1)',(request.form['nombre'],int(request.form['cuenta_bancaria_id'])));c.commit();c.close();audit('TERMINAL_POS',request.form['nombre']);return redirect('/bancos/pos')
 rows=c.execute('select p.*,b.banco,b.alias from terminales_pos p left join cuentas_bancarias b on b.id=p.cuenta_bancaria_id order by p.nombre').fetchall();cuentas=c.execute('select * from cuentas_bancarias where activo=1 and acepta_pos=1 order by banco').fetchall();c.close();return render_template('pos_terminals.html',rows=rows,cuentas=cuentas)

@app.get('/recibos')
def recibos_lista():
 q=(request.args.get('q') or '').strip();desde=request.args.get('desde') or '';hasta=request.args.get('hasta') or '';c=db();sql="select rp.*,v.numero factura,t.nombre cliente,cb.banco,cb.alias cuenta_alias,tp.nombre terminal_pos from recibos_pago rp join ventas v on v.id=rp.venta_id join terceros t on t.id=rp.tercero_id left join cuentas_bancarias cb on cb.id=rp.cuenta_bancaria_id left join terminales_pos tp on tp.id=rp.terminal_pos_id where 1=1";ps=[]
 if q:sql+=' and (rp.numero like ? or v.numero like ? or t.nombre like ? or rp.medio like ?)';ps += ['%'+q+'%']*4
 if desde:sql+=' and substr(rp.fecha,1,10)>=?';ps.append(desde)
 if hasta:sql+=' and substr(rp.fecha,1,10)<=?';ps.append(hasta)
 sql+=' order by rp.id desc';rows=c.execute(sql,ps).fetchall();c.close();return render_template('receipts_list.html',rows=rows,q=q,desde=desde,hasta=hasta)

@app.get('/informes/<tipo>/pdf')
def informe_pdf(tipo):
 valid={x[0] for x in REPORT_GROUPS}
 if tipo not in valid:return ('Informe no encontrado',404)
 hoy=datetime.date.today();desde=request.args.get('desde') or hoy.replace(day=1).isoformat();hasta=request.args.get('hasta') or hoy.isoformat();c=db();titulo,headers,rows=_report_data(c,tipo,desde,hasta);c.close()
 from reportlab.lib import colors
 from reportlab.lib.pagesizes import A4,landscape
 from reportlab.lib.styles import getSampleStyleSheet
 from reportlab.lib.units import mm
 from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle
 buf=io.BytesIO();doc=SimpleDocTemplate(buf,pagesize=landscape(A4),rightMargin=10*mm,leftMargin=10*mm,topMargin=10*mm,bottomMargin=10*mm);styles=getSampleStyleSheet();story=([pdf_logo()] if pdf_logo() else [])+[Paragraph('CENTRO MÉDICO SANTA CLARA',styles['Title']),Paragraph(titulo,styles['Heading2']),Paragraph(f'Período: {desde} al {hasta} · Generado: {now().replace("T"," ")}',styles['Normal']),Spacer(1,5*mm)]
 data=[headers]+[[str(v if v is not None else '') for v in r] for r in rows];tbl=Table(data,repeatRows=1);tbl.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.lightgrey),('GRID',(0,0),(-1,-1),0.35,colors.grey),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),7),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),3),('RIGHTPADDING',(0,0),(-1,-1),3)]));story.append(tbl);story.append(Spacer(1,4*mm));story.append(Paragraph(f'Total de registros: {len(rows)}',styles['Normal']));doc.build(story);buf.seek(0);return send_file(buf,mimetype='application/pdf',as_attachment=True,download_name=f'{tipo}_{desde}_{hasta}.pdf')

# ===== V13.9.2: búsqueda bajo demanda de productos =====
@app.get('/api/productos/buscar')
def api_productos_buscar():
 q=(request.args.get('q') or '').strip()
 if not q: return jsonify([])
 c=db(); like='%'+q+'%'
 rows=c.execute("""select id,codigo,nombre,coalesce(codigo_barras,'') codigo_barras,
                         coalesce(iva_pct,0) iva_pct,coalesce(precio_pyg,0) precio_pyg,
                         coalesce(costo_pyg,0) costo_pyg,coalesce(stock,0) stock
                  from productos
                  where coalesce(activo,1)=1 and (codigo=? or codigo_barras=? or nombre like ? or codigo like ?)
                  order by case when codigo=? or codigo_barras=? then 0 else 1 end,nombre limit 20""",
                (q,q,like,like,q,q)).fetchall();c.close()
 return jsonify([dict(r) for r in rows])

# ===== V13.4: Centro de Informes Específicos =====
REPORT_GROUPS = [
 ('compras','Compras','Compras por período, proveedor, comprobante, estado e importes'),
 ('ventas','Ventas y Facturación','Ventas/facturas por período, cliente, comprobante, estado e importes'),
 ('consultas','Consultas','Consultas por paciente, médico, especialidad, estado, honorarios y margen'),
 ('cirugias','Cirugías','Actividad de quirófano por paciente, médico, estado y cuenta hospitalaria'),
 ('urgencias','Urgencias','Atenciones de urgencia por paciente, médico, estado y cuenta hospitalaria'),
 ('internaciones','Internaciones','Ingresos, egresos/estado, cama, médico y cuentas de internación'),
 ('farmacia','Farmacia y Stock','Movimientos de productos, entradas, salidas y existencias'),
 ('seguros','Seguros Médicos','Cuentas/admisiones vinculadas a aseguradoras y estado de facturación'),
 ('caja','Caja y Cobranzas','Movimientos de caja por fecha, tipo, medio, concepto e importe'),
 ('cxc','Cuentas por Cobrar','Saldos de clientes, pacientes y aseguradoras'),
 ('cxp','Cuentas por Pagar','Saldos de proveedores y obligaciones'),
 ('medicos','Médicos','Producción y honorarios de consultas por médico'),
 ('auditoria','Auditoría','Actividad registrada por fecha, usuario, acción y detalle')
]

@app.get('/informes')
def informes_centro():
 return render_template('report_center.html',groups=REPORT_GROUPS)

def _report_data(c, tipo, desde, hasta):
 params=(desde,hasta)
 if tipo=='compras':
  return ('Informes de Compras',['Fecha','Proveedor','Comprobante','Moneda','Total PYG','Estado'], c.execute("select co.fecha,coalesce(t.nombre,'-'),co.numero,co.moneda,co.total_pyg,co.estado from compras co left join terceros t on t.id=co.proveedor_id where co.fecha between ? and ? order by co.fecha desc,co.id desc",params).fetchall())
 if tipo=='ventas':
  return ('Informes de Ventas y Facturación',['Fecha','Cliente','Comprobante','Moneda','Total PYG','Estado'], c.execute("select v.fecha,coalesce(t.nombre,'-'),v.numero,v.moneda,v.total_pyg,v.estado from ventas v left join terceros t on t.id=v.cliente_id where v.fecha between ? and ? order by v.fecha desc,v.id desc",params).fetchall())
 if tipo=='consultas':
  return ('Informes de Consultas',['Fecha','Paciente','Médico','Especialidad','Estado','Facturado PYG','Honorario PYG','Margen PYG'], c.execute("select q.fecha,p.nombre,m.nombre,e.nombre,q.estado,q.precio_pyg,q.honorario_pyg,(q.precio_pyg-q.honorario_pyg) from consultas q join pacientes p on p.id=q.paciente_id join medicos m on m.id=q.medico_id join especialidades e on e.id=q.especialidad_id where q.fecha between ? and ? order by q.fecha desc,q.id desc",params).fetchall())
 if tipo in ('cirugias','urgencias','internaciones'):
  filtro={'cirugias':'QUIROFANO','urgencias':'URGENCIA','internaciones':'INTERNACION'}[tipo]
  titulo={'cirugias':'Informes de Cirugías / Quirófano','urgencias':'Informes de Urgencias','internaciones':'Informes de Internación'}[tipo]
  rows=c.execute("select a.fecha,p.nombre,coalesce(m.nombre,'-'),a.tipo,a.estado,coalesce(cam.codigo,'-'),coalesce(sum(cp.total_pyg),0) from admisiones a join pacientes p on p.id=a.paciente_id left join medicos m on m.id=a.medico_id left join camas cam on cam.id=a.cama_id left join cargos_paciente cp on cp.admision_id=a.id where a.fecha between ? and ? and upper(a.tipo) like ? group by a.id order by a.fecha desc,a.id desc",(desde,hasta,'%'+filtro+'%')).fetchall()
  return (titulo,['Fecha','Paciente','Médico','Tipo','Estado','Cama','Cuenta PYG'],rows)
 if tipo=='farmacia':
  return ('Informes de Farmacia y Stock',['Fecha','Producto','Tipo','Cantidad','Costo PYG','Origen'], c.execute("select s.fecha,p.nombre,s.tipo,s.cantidad,s.costo_pyg,coalesce(s.origen_tipo,'-') from stock_mov s join productos p on p.id=s.producto_id where s.fecha between ? and ? order by s.fecha desc,s.id desc",params).fetchall())
 if tipo=='seguros':
  return ('Informes de Seguros Médicos',['Fecha','Paciente','Seguro','Tipo atención','Estado','Cuenta PYG'], c.execute("select a.fecha,p.nombre,coalesce(ase.nombre,'-'),a.tipo,a.estado,coalesce(sum(cp.total_pyg),0) from admisiones a join pacientes p on p.id=a.paciente_id join aseguradoras ase on ase.id=a.aseguradora_id left join cargos_paciente cp on cp.admision_id=a.id where a.fecha between ? and ? group by a.id order by a.fecha desc,a.id desc",params).fetchall())
 if tipo=='caja':
  return ('Informes de Caja y Cobranzas',['Fecha','Tipo','Medio','Moneda','Importe','Importe PYG','Concepto'], c.execute("select fecha,tipo,medio,moneda,importe,importe_pyg,concepto from caja_banco where fecha between ? and ? order by fecha desc,id desc",params).fetchall())
 if tipo=='cxc':
  return ('Informes de Cuentas por Cobrar',['Cliente','Moneda','Importe','Saldo','Importe PYG','Estado'], c.execute("select coalesce(t.nombre,'-'),x.moneda,x.importe,x.saldo,x.importe_pyg,x.estado from cxc x left join terceros t on t.id=x.tercero_id order by x.id desc").fetchall())
 if tipo=='cxp':
  return ('Informes de Cuentas por Pagar',['Proveedor/Profesional','Moneda','Importe','Saldo','Importe PYG','Estado'], c.execute("select coalesce(t.nombre,'-'),x.moneda,x.importe,x.saldo,x.importe_pyg,x.estado from cxp x left join terceros t on t.id=x.tercero_id order by x.id desc").fetchall())
 if tipo=='medicos':
  return ('Informes de Médicos',['Médico','Consultas','Facturado PYG','Honorarios PYG','Margen PYG'], c.execute("select m.nombre,count(q.id),coalesce(sum(q.precio_pyg),0),coalesce(sum(q.honorario_pyg),0),coalesce(sum(q.precio_pyg-q.honorario_pyg),0) from medicos m left join consultas q on q.medico_id=m.id and q.fecha between ? and ? group by m.id,m.nombre order by m.nombre",params).fetchall())
 if tipo=='auditoria':
  return ('Informes de Auditoría',['Fecha','Usuario','Acción','Detalle'], c.execute("select fecha,usuario,accion,detalle from auditoria where substr(fecha,1,10) between ? and ? order by id desc",params).fetchall())
 return ('Informe',['Información'],[])

@app.get('/informes/<tipo>')
def informe_especifico(tipo):
 valid={x[0] for x in REPORT_GROUPS}
 if tipo not in valid: return ('Informe no encontrado',404)
 hoy=datetime.date.today(); desde=request.args.get('desde') or hoy.replace(day=1).isoformat(); hasta=request.args.get('hasta') or hoy.isoformat()
 buscado=request.args.get('buscar')=='1'
 c=db()
 if buscado: titulo,headers,rows=_report_data(c,tipo,desde,hasta)
 else:
  titulo,headers,_=_report_data(c,tipo,'0001-01-01','0001-01-01'); rows=[]
 c.close()
 return render_template('specific_report.html',tipo=tipo,titulo=titulo,headers=headers,rows=rows,desde=desde,hasta=hasta,buscado=buscado)


# ===== V13.4.8 CONTABILIDAD PARAGUAY - INFORMES / PDF / EXCEL / IMPRESION =====
ACCOUNTING_REPORTS=[
 ('diario','Libro Diario'),('mayor','Libro Mayor'),('balance_sumas','Balance de Sumas y Saldos'),
 ('situacion','Estado de Situación Patrimonial'),('resultados','Estado de Resultados'),
 ('flujo','Estado de Flujo de Efectivo'),('patrimonio','Estado de Cambios del Patrimonio Neto'),
 ('compras_iva','Libro Compras / IVA Crédito'),('ventas_iva','Libro Ventas / IVA Débito'),
 ('movimientos','Movimientos por Cuenta')]

def _accounting_report(c,tipo,desde,hasta,cuenta=None):
 p=(desde,hasta)
 if tipo=='diario':
  rows=c.execute("select a.fecha,a.numero,a.concepto,d.cuenta,coalesce(pc.nombre,''),d.debe_pyg,d.haber_pyg,a.moneda,a.tipo_cambio from asientos a join asiento_det d on d.asiento_id=a.id left join plan_cuentas pc on pc.codigo=d.cuenta where a.fecha between ? and ? and a.estado='CONFIRMADO' order by a.fecha,a.id,d.id",p).fetchall()
  return 'Libro Diario',['Fecha','Asiento','Concepto','Cuenta','Nombre','Debe Gs.','Haber Gs.','Moneda','TC'],rows
 if tipo in ('mayor','movimientos'):
  sql="select d.cuenta,coalesce(pc.nombre,''),a.fecha,a.numero,a.concepto,d.debe_pyg,d.haber_pyg,(d.debe_pyg-d.haber_pyg) from asientos a join asiento_det d on d.asiento_id=a.id left join plan_cuentas pc on pc.codigo=d.cuenta where a.fecha between ? and ? and a.estado='CONFIRMADO'"
  args=[desde,hasta]
  if cuenta: sql+=' and d.cuenta=?';args.append(cuenta)
  sql+=' order by d.cuenta,a.fecha,a.id,d.id'
  return ('Libro Mayor' if tipo=='mayor' else 'Movimientos por Cuenta'),['Cuenta','Nombre','Fecha','Asiento','Concepto','Debe Gs.','Haber Gs.','Movimiento'],c.execute(sql,args).fetchall()
 if tipo=='balance_sumas':
  rows=c.execute("select p.codigo,p.nombre,p.tipo,coalesce(sum(case when a.fecha between ? and ? and a.estado='CONFIRMADO' then d.debe_pyg else 0 end),0),coalesce(sum(case when a.fecha between ? and ? and a.estado='CONFIRMADO' then d.haber_pyg else 0 end),0),coalesce(sum(case when a.fecha between ? and ? and a.estado='CONFIRMADO' then d.debe_pyg-d.haber_pyg else 0 end),0) from plan_cuentas p left join asiento_det d on d.cuenta=p.codigo left join asientos a on a.id=d.asiento_id group by p.codigo,p.nombre,p.tipo order by p.codigo",(desde,hasta,desde,hasta,desde,hasta)).fetchall()
  return 'Balance de Sumas y Saldos',['Cuenta','Nombre','Tipo','Debe Gs.','Haber Gs.','Saldo Gs.'],rows
 if tipo=='situacion':
  rows=c.execute("select p.tipo,p.codigo,p.nombre,coalesce(sum(case when a.fecha<=? and a.estado='CONFIRMADO' then d.debe_pyg-d.haber_pyg else 0 end),0) saldo from plan_cuentas p left join asiento_det d on d.cuenta=p.codigo left join asientos a on a.id=d.asiento_id where p.tipo in ('ACTIVO','PASIVO','PATRIMONIO') group by p.codigo,p.nombre,p.tipo order by p.codigo",(hasta,)).fetchall()
  return 'Estado de Situación Patrimonial',['Grupo','Cuenta','Nombre','Saldo Gs.'],rows
 if tipo=='resultados':
  rows=c.execute("select p.tipo,p.codigo,p.nombre,coalesce(sum(case when a.fecha between ? and ? and a.estado='CONFIRMADO' then case when p.tipo='INGRESO' then d.haber_pyg-d.debe_pyg else d.debe_pyg-d.haber_pyg end else 0 end),0) saldo from plan_cuentas p left join asiento_det d on d.cuenta=p.codigo left join asientos a on a.id=d.asiento_id where p.tipo in ('INGRESO','EGRESO') group by p.codigo,p.nombre,p.tipo order by p.tipo,p.codigo",p).fetchall()
  return 'Estado de Resultados',['Grupo','Cuenta','Nombre','Importe Gs.'],rows
 if tipo=='flujo':
  rows=c.execute("select a.fecha,a.numero,a.concepto,d.cuenta,coalesce(pc.nombre,''),d.debe_pyg,d.haber_pyg from asientos a join asiento_det d on d.asiento_id=a.id left join plan_cuentas pc on pc.codigo=d.cuenta where a.fecha between ? and ? and a.estado='CONFIRMADO' and (d.cuenta like '1.1.01%' or lower(coalesce(pc.nombre,'')) like '%banco%' or lower(coalesce(pc.nombre,'')) like '%caja%') order by a.fecha,a.id",p).fetchall()
  return 'Estado / Movimientos de Flujo de Efectivo',['Fecha','Asiento','Concepto','Cuenta','Cuenta Efectivo','Entrada Gs.','Salida Gs.'],rows
 if tipo=='patrimonio':
  rows=c.execute("select p.codigo,p.nombre,coalesce(sum(case when a.fecha<=? and a.estado='CONFIRMADO' then d.haber_pyg-d.debe_pyg else 0 end),0) saldo from plan_cuentas p left join asiento_det d on d.cuenta=p.codigo left join asientos a on a.id=d.asiento_id where p.tipo='PATRIMONIO' group by p.codigo,p.nombre order by p.codigo",(hasta,)).fetchall()
  return 'Estado de Cambios del Patrimonio Neto',['Cuenta','Nombre','Saldo al cierre Gs.'],rows
 if tipo=='compras_iva':
  rows=c.execute("select co.fecha,co.numero,coalesce(t.ruc,''),coalesce(t.nombre,''),co.total_pyg,co.gravado_10,co.iva_10,co.gravado_5,co.iva_5,co.exento_iva,co.estado from compras co left join terceros t on t.id=co.proveedor_id where co.fecha between ? and ? order by co.fecha,co.id",p).fetchall()
  return 'Libro Compras / IVA Crédito',['Fecha','Comprobante','RUC','Proveedor','Total Gs.','Gravado 10%','IVA 10%','Gravado 5%','IVA 5%','Exento','Estado'],rows
 if tipo=='ventas_iva':
  rows=c.execute("select v.fecha,v.numero,coalesce(t.ruc,''),coalesce(t.nombre,''),v.total_pyg,v.gravado_10,v.iva_10,v.gravado_5,v.iva_5,v.exento_iva,v.estado from ventas v left join terceros t on t.id=v.cliente_id where v.fecha between ? and ? order by v.fecha,v.id",p).fetchall()
  return 'Libro Ventas / IVA Débito',['Fecha','Comprobante','RUC/CI','Cliente','Total Gs.','Gravado 10%','IVA 10%','Gravado 5%','IVA 5%','Exento','Estado'],rows
 return 'Informe Contable',['Información'],[]

@app.route('/contabilidad/plan',methods=['GET','POST'])
def plan_contable():
 c=db()
 if request.method=='POST':
  codigo=request.form['codigo'].strip(); nombre=request.form['nombre'].strip(); tipo=request.form['tipo']; moneda=request.form.get('moneda') or 'PYG'; imputable=1 if request.form.get('imputable') else 0
  padre=(request.form.get('cuenta_padre') or '').strip() or None; naturaleza=request.form.get('naturaleza') or ('DEUDORA' if tipo in ('ACTIVO','EGRESO') else 'ACREEDORA'); activa=1 if request.form.get('activa') else 0
  original=(request.form.get('codigo_original') or '').strip()
  try:
   if original and original!=codigo:
    mov=c.execute('select count(*) from asiento_det where cuenta=?',(original,)).fetchone()[0]
    hijos=c.execute('select count(*) from plan_cuentas where cuenta_padre=?',(original,)).fetchone()[0]
    if mov or hijos:
     flash('El código no puede cambiarse porque la cuenta tiene movimientos o cuentas dependientes. Puede modificar su nombre y demás parámetros.')
     c.close();return redirect('/contabilidad/plan?editar='+original)
    if c.execute('select 1 from plan_cuentas where codigo=?',(codigo,)).fetchone():
     flash('Ya existe otra cuenta con ese código.');c.close();return redirect('/contabilidad/plan?editar='+original)
    c.execute('update plan_cuentas set codigo=? where codigo=?',(codigo,original))
   c.execute('''insert into plan_cuentas(codigo,nombre,tipo,moneda,imputable,cuenta_padre,naturaleza,activa) values(?,?,?,?,?,?,?,?)
                on conflict(codigo) do update set nombre=excluded.nombre,tipo=excluded.tipo,moneda=excluded.moneda,imputable=excluded.imputable,cuenta_padre=excluded.cuenta_padre,naturaleza=excluded.naturaleza,activa=excluded.activa''',(codigo,nombre,tipo,moneda,imputable,padre,naturaleza,activa))
   c.commit();audit('PLAN_CUENTAS_MODIFICAR' if original else 'PLAN_CUENTAS_NUEVA',codigo);flash('Cuenta guardada correctamente.')
  except Exception as e:
   c.rollback();flash('No se pudo guardar la cuenta: '+str(e))
  c.close();return redirect('/contabilidad/plan?editar='+codigo)
 editar=(request.args.get('editar') or '').strip(); q=(request.args.get('q') or '').strip()
 sql='select * from plan_cuentas'; pars=[]
 if q: sql+=' where codigo like ? or nombre like ?';pars=['%'+q+'%','%'+q+'%']
 sql+=' order by codigo'
 rows=c.execute(sql,pars).fetchall(); selected=c.execute('select * from plan_cuentas where codigo=?',(editar,)).fetchone() if editar else None
 mons=c.execute('select * from monedas where activa=1 order by codigo').fetchall(); padres=c.execute('select codigo,nombre from plan_cuentas where activa=1 order by codigo').fetchall();c.close()
 return render_template('accounting_plan.html',rows=rows,mons=mons,padres=padres,selected=selected,q=q)

@app.post('/contabilidad/plan/<path:codigo>/desactivar')
def plan_contable_desactivar(codigo):
 c=db();r=c.execute('select activa from plan_cuentas where codigo=?',(codigo,)).fetchone()
 if r:
  nuevo=0 if r['activa'] else 1;c.execute('update plan_cuentas set activa=? where codigo=?',(nuevo,codigo));c.commit();audit('PLAN_CUENTAS_ESTADO',f'{codigo} -> {nuevo}')
 c.close();return redirect('/contabilidad/plan?editar='+codigo)

@app.get('/contabilidad/informes')
def contabilidad_informes():
 return render_template('accounting_reports_center.html',reports=ACCOUNTING_REPORTS)

@app.get('/contabilidad/informe/<tipo>')
def contabilidad_informe(tipo):
 if tipo not in {x[0] for x in ACCOUNTING_REPORTS}: return 'Informe contable no encontrado',404
 hoy=datetime.date.today();desde=request.args.get('desde') or hoy.replace(month=1,day=1).isoformat();hasta=request.args.get('hasta') or hoy.isoformat();cuenta=request.args.get('cuenta') or ''
 buscado=request.args.get('buscar')=='1'; c=db()
 if buscado: titulo,headers,rows=_accounting_report(c,tipo,desde,hasta,cuenta or None)
 else:
  titulo,headers,_=_accounting_report(c,tipo,'0001-01-01','0001-01-01',cuenta or None); rows=[]
 cuentas=c.execute('select codigo,nombre from plan_cuentas order by codigo').fetchall();c.close()
 return render_template('accounting_report.html',tipo=tipo,titulo=titulo,headers=headers,rows=rows,desde=desde,hasta=hasta,cuenta=cuenta,cuentas=cuentas,buscado=buscado)

def _safe(v): return '' if v is None else str(v)

@app.get('/contabilidad/informe/<tipo>/excel')
def contabilidad_excel(tipo):
 from openpyxl import Workbook
 from openpyxl.styles import Font,Alignment
 desde=request.args.get('desde') or '1900-01-01';hasta=request.args.get('hasta') or datetime.date.today().isoformat();cuenta=request.args.get('cuenta') or None
 c=db();titulo,headers,rows=_accounting_report(c,tipo,desde,hasta,cuenta);c.close();wb=Workbook();ws=wb.active;ws.title='Informe'
 ws.append(['CENTRO MEDICO SANTA CLARA']);ws.append([titulo]);ws.append([f'Periodo: {desde} al {hasta}']);ws.append([]);ws.append(headers)
 for cell in ws[5]:cell.font=Font(bold=True);cell.alignment=Alignment(horizontal='center')
 for r in rows:ws.append([v for v in r])
 for col in ws.columns:
  letter=col[0].column_letter;ws.column_dimensions[letter].width=min(45,max(12,max(len(_safe(x.value)) for x in col)+2))
 bio=io.BytesIO();wb.save(bio);bio.seek(0);return send_file(bio,as_attachment=True,download_name=f'{tipo}_{desde}_{hasta}.xlsx',mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

@app.get('/contabilidad/informe/<tipo>/pdf')
def contabilidad_pdf(tipo):
 from reportlab.lib import colors
 from reportlab.lib.pagesizes import A4,landscape
 from reportlab.lib.styles import getSampleStyleSheet
 from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle
 desde=request.args.get('desde') or '1900-01-01';hasta=request.args.get('hasta') or datetime.date.today().isoformat();cuenta=request.args.get('cuenta') or None
 c=db();titulo,headers,rows=_accounting_report(c,tipo,desde,hasta,cuenta);c.close();bio=io.BytesIO();doc=SimpleDocTemplate(bio,pagesize=landscape(A4),leftMargin=20,rightMargin=20,topMargin=24,bottomMargin=24);styles=getSampleStyleSheet();story=([pdf_logo()] if pdf_logo() else [])+[Paragraph('CENTRO MEDICO SANTA CLARA',styles['Title']),Paragraph(titulo,styles['Heading2']),Paragraph(f'Periodo: {desde} al {hasta} · Emitido: {datetime.datetime.now():%d/%m/%Y %H:%M}',styles['Normal']),Spacer(1,10)]
 data=[headers]+[[_safe(v) for v in r] for r in rows];tbl=Table(data,repeatRows=1);tbl.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.lightgrey),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),7),('GRID',(0,0),(-1,-1),0.25,colors.grey),('VALIGN',(0,0),(-1,-1),'TOP'),('ALIGN',(0,0),(-1,0),'CENTER')]));story.append(tbl);story.append(Spacer(1,8));story.append(Paragraph(f'Total de registros: {len(rows)}',styles['Normal']));doc.build(story);bio.seek(0);return send_file(bio,as_attachment=False,download_name=f'{tipo}_{desde}_{hasta}.pdf',mimetype='application/pdf')


# ===== V13.5.3: Agenda por turnos médicos + llamador administrativo =====
def init_v1353_turnos():
 c=db()
 c.executescript('''
 CREATE TABLE IF NOT EXISTS horarios_medicos(id INTEGER PRIMARY KEY, medico_id INTEGER NOT NULL, dia_semana INTEGER NOT NULL, hora_inicio TEXT NOT NULL, hora_fin TEXT NOT NULL, minutos_consulta INTEGER NOT NULL DEFAULT 15, consultorio TEXT, activo INTEGER NOT NULL DEFAULT 1, UNIQUE(medico_id,dia_semana,hora_inicio,hora_fin));
 CREATE TABLE IF NOT EXISTS agenda_excepciones(id INTEGER PRIMARY KEY, medico_id INTEGER NOT NULL, fecha TEXT NOT NULL, hora_inicio TEXT, hora_fin TEXT, motivo TEXT, activo INTEGER DEFAULT 1);
 ''')
 # Los permisos existentes son administrados exclusivamente desde Roles y Permisos.
 c.commit();c.close()

def _slot_times(inicio,fin,minutos):
 try:
  a=datetime.datetime.strptime(inicio,'%H:%M');b=datetime.datetime.strptime(fin,'%H:%M');delta=datetime.timedelta(minutes=max(5,int(minutos or 15)));out=[]
  while a<b:out.append(a.strftime('%H:%M'));a+=delta
  return out
 except Exception:return []

@app.route('/agendamiento/turnos')
def agenda_turnos():
 fecha=request.args.get('fecha') or datetime.date.today().isoformat();medico_id=request.args.get('medico_id',type=int);especialidad=(request.args.get('especialidad') or '').strip();c=db()
 meds=c.execute('select * from medicos order by nombre').fetchall();especialidades=c.execute("select distinct especialidad from medicos where coalesce(especialidad,'')<>'' order by especialidad").fetchall()
 pars=[fecha];sql='''select g.*,p.nombre paciente,p.telefono,m.nombre medico,e.nombre especialidad from agenda g join pacientes p on p.id=g.paciente_id join medicos m on m.id=g.medico_id left join especialidades e on e.id=g.especialidad_id where g.fecha=?'''
 if medico_id:sql+=' and g.medico_id=?';pars.append(medico_id)
 if especialidad:sql+=' and m.especialidad=?';pars.append(especialidad)
 ag=c.execute(sql+' order by m.nombre,g.hora',pars).fetchall();booked={(x['medico_id'],x['hora'][:5]):x for x in ag};day=datetime.date.fromisoformat(fecha).weekday()
 q='''select h.*,m.nombre medico,m.especialidad from horarios_medicos h join medicos m on m.id=h.medico_id where h.activo=1 and h.dia_semana=?''';qp=[day]
 if medico_id:q+=' and h.medico_id=?';qp.append(medico_id)
 if especialidad:q+=' and m.especialidad=?';qp.append(especialidad)
 horarios=c.execute(q+' order by m.nombre,h.hora_inicio',qp).fetchall();slots=[]
 for hr in horarios:
  for hora in _slot_times(hr['hora_inicio'],hr['hora_fin'],hr['minutos_consulta']):
   ex=c.execute('''select 1 from agenda_excepciones where activo=1 and medico_id=? and fecha=? and (hora_inicio is null or ?>=hora_inicio) and (hora_fin is null or ?<hora_fin) limit 1''',(hr['medico_id'],fecha,hora,hora)).fetchone()
   if not ex:slots.append({'hora':hora,'medico_id':hr['medico_id'],'medico':hr['medico'],'especialidad':hr['especialidad'],'consultorio':hr['consultorio'] or '','minutos':hr['minutos_consulta'],'agenda':booked.get((hr['medico_id'],hora))})
 c.close();return render_template('agenda_turnos.html',fecha=fecha,medico_id=medico_id,especialidad=especialidad,meds=meds,especialidades=especialidades,slots=slots,puede_llamar=(user_has('AGENDA','LLAMAR') or user_has('CONSULTORIO','LLAMAR')))

@app.route('/agendamiento/horarios',methods=['GET','POST'])
def horarios_medicos():
 if not (user_has('AGENDA','EDITAR') or user_has('USUARIOS','ADMINISTRAR')):return ('Acceso no autorizado',403)
 c=db()
 if request.method=='POST':
  if request.form.get('op')=='eliminar':c.execute('delete from horarios_medicos where id=?',(int(request.form['id']),));flash('Horario eliminado.')
  else:
   mid=int(request.form['medico_id']);dia=int(request.form['dia_semana']);ini=request.form['hora_inicio'];fin=request.form['hora_fin'];mins=int(request.form.get('minutos_consulta') or 15);cons=(request.form.get('consultorio') or '').strip()
   if mins<5 or mins>240:c.close();flash('El tiempo de consulta debe estar entre 5 y 240 minutos.');return redirect('/agendamiento/horarios')
   if ini>=fin:c.close();flash('La hora final debe ser posterior a la inicial.');return redirect('/agendamiento/horarios')
   c.execute('insert or replace into horarios_medicos(id,medico_id,dia_semana,hora_inicio,hora_fin,minutos_consulta,consultorio,activo) values(?,?,?,?,?,?,?,1)',(request.form.get('id') or None,mid,dia,ini,fin,mins,cons));flash('Horario médico guardado.')
  c.commit();c.close();return redirect('/agendamiento/horarios')
 rows=c.execute('''select h.*,m.nombre medico from horarios_medicos h join medicos m on m.id=h.medico_id order by m.nombre,h.dia_semana,h.hora_inicio''').fetchall();meds=c.execute('select id,nombre from medicos order by nombre').fetchall();c.close();return render_template('doctor_schedules.html',rows=rows,meds=meds)

@app.post('/agendamiento/turno/<int:gid>/estado')
def agenda_estado(gid):
 if not (user_has('AGENDA','EDITAR') or user_has('RECEPCION','EDITAR')):return ('Acceso no autorizado',403)
 estado=(request.form.get('estado') or 'AGENDADO').upper();permitidos={'AGENDADO','EN ESPERA','LLAMADO','EN CONSULTA','ATENDIDO','CANCELADO','AUSENTE'}
 if estado not in permitidos:return ('Estado inválido',400)
 c=db();c.execute('update agenda set estado=? where id=?',(estado,gid));c.commit();c.close();return redirect(request.referrer or '/agendamiento/turnos')

ROUTE_MODULE.update({'agenda_turnos':'AGENDA','horarios_medicos':'AGENDA','agenda_estado':'AGENDA'})

init_v1353_turnos()

def init_v1354():
 c=db()
 # No se reponen permisos al arrancar: se respeta exactamente la configuración del rol.
 c.commit();c.close()

@app.route('/ventas/cajas',methods=['GET','POST'])
def administrar_cajas():
 if not (user_has('CAJA','ABRIR_CAJA') or user_has('USUARIOS','ADMINISTRAR')):return ('Acceso no autorizado',403)
 c=db()
 if request.method=='POST':
  try:
   op=request.form.get('op','guardar')
   if op=='guardar':
    nombre=(request.form.get('nombre') or '').strip(); cid=request.form.get('id')
    if not nombre:raise ValueError('El nombre de la caja es obligatorio')
    if cid:c.execute('update cajas set nombre=?,activo=? where id=?',(nombre,1 if request.form.get('activo','1')=='1' else 0,int(cid)))
    else:c.execute('insert into cajas(nombre,activo) values(?,1)',(nombre,))
    flash('Caja guardada correctamente.')
   elif op=='desactivar':
    cid=int(request.form['id'])
    if c.execute("select 1 from aperturas_caja where caja_id=? and estado='ABIERTA' limit 1",(cid,)).fetchone():raise ValueError('No puede desactivar una caja con apertura activa')
    c.execute('update cajas set activo=0 where id=?',(cid,));flash('Caja desactivada.')
   c.commit()
  except Exception as e:c.rollback();flash(str(e))
  c.close();return redirect('/ventas/cajas')
 rows=c.execute('select * from cajas order by activo desc,nombre').fetchall();c.close();return render_template('cash_registers.html',rows=rows)

@app.get('/ventas/cierres-caja')
def historial_cierres_caja():
 if not (user_has('CAJA','VER') or user_has('USUARIOS','ADMINISTRAR')):return ('Acceso no autorizado',403)
 c=db();rows=c.execute("select a.*,c.nombre caja from aperturas_caja a join cajas c on c.id=a.caja_id where a.estado='CERRADA' order by a.id desc limit 300").fetchall();c.close();return render_template('cash_closings.html',rows=rows)

ROUTE_MODULE.update({'administrar_cajas':'CAJA','historial_cierres_caja':'CAJA'})
init_v1354()

# ===== V13.5.6: facturación consolidada a Seguros Médicos =====
def init_v1356_seguros():
 c=db()
 c.executescript("""
 CREATE TABLE IF NOT EXISTS seguro_pendientes(id INTEGER PRIMARY KEY,fecha TEXT NOT NULL,aseguradora_id INTEGER NOT NULL,paciente_id INTEGER,origen_tipo TEXT NOT NULL,origen_id INTEGER NOT NULL,categoria TEXT NOT NULL,descripcion TEXT,importe_pyg REAL NOT NULL DEFAULT 0,iva_pct REAL NOT NULL DEFAULT 10,estado TEXT NOT NULL DEFAULT 'PENDIENTE',factura_seguro_id INTEGER,UNIQUE(origen_tipo,origen_id));
 CREATE TABLE IF NOT EXISTS facturas_seguro(id INTEGER PRIMARY KEY,fecha TEXT NOT NULL,aseguradora_id INTEGER NOT NULL,numero TEXT NOT NULL UNIQUE,medicamentos_pyg REAL DEFAULT 0,descartables_pyg REAL DEFAULT 0,servicios_pyg REAL DEFAULT 0,total_pyg REAL DEFAULT 0,venta_id INTEGER,estado TEXT DEFAULT 'EMITIDA',creado_por TEXT,creado_en TEXT);
 CREATE TABLE IF NOT EXISTS factura_seguro_det(id INTEGER PRIMARY KEY,factura_seguro_id INTEGER NOT NULL,pendiente_id INTEGER,origen_tipo TEXT,origen_id INTEGER,paciente_id INTEGER,categoria TEXT,descripcion TEXT,importe_pyg REAL DEFAULT 0,iva_pct REAL DEFAULT 10);
 """)
 c.commit();c.close()

def clasificar_cargo_seguro(c,row):
 if row['tipo']=='PRODUCTO':
  pr=c.execute('select categoria from productos where id=?',(row['referencia_id'],)).fetchone();cat=((pr['categoria'] if pr else '') or '').upper()
  if 'MEDIC' in cat or 'FARMAC' in cat:return 'MEDICAMENTOS',5.0
  return 'DESCARTABLES',10.0
 return 'SERVICIOS SANATORIALES',10.0

def sincronizar_pendientes_seguro(c):
 # V13.6.3: solo las cuentas aseguradas YA CERRADAS pasan a pendientes de facturación.
 for r in c.execute("select cp.*,a.aseguradora_id,a.paciente_id from cargos_paciente cp join admisiones a on a.id=cp.admision_id where cp.facturado=0 and a.aseguradora_id is not null and a.tipo in ('URGENCIA','INTERNACION','QUIROFANO') and a.estado in ('PENDIENTE_FACTURACION','ALTA')").fetchall():
  cat,iva=clasificar_cargo_seguro(c,r)
  c.execute("insert or ignore into seguro_pendientes(fecha,aseguradora_id,paciente_id,origen_tipo,origen_id,categoria,descripcion,importe_pyg,iva_pct,estado) values(?,?,?,?,?,?,?,?,?,'PENDIENTE')",(r['fecha'],r['aseguradora_id'],r['paciente_id'],'CARGO',r['id'],cat,r['descripcion'],r['total_pyg'],iva))

@app.route('/seguros/facturar',methods=['GET','POST'])
def seguros_facturar():
 c=db();sincronizar_pendientes_seguro(c)
 if request.method=='POST':
  try:
   aseg=int(request.form['aseguradora_id']);ids=[int(x) for x in request.form.getlist('item_id')]
   if not ids:raise ValueError('Seleccione al menos un ítem pendiente para facturar.')
   marks=','.join('?'*len(ids));rows=c.execute(f"select sp.* from seguro_pendientes sp where sp.id in ({marks}) and sp.aseguradora_id=? and sp.estado='PENDIENTE'",ids+[aseg]).fetchall()
   if not rows:raise ValueError('Los ítems seleccionados ya no están pendientes.')
   fecha=request.form.get('fecha') or datetime.date.today().isoformat();num=(request.form.get('numero') or '').strip()
   if not num:raise ValueError('Ingrese el número de factura.')
   meds=sum(float(r['importe_pyg']) for r in rows if r['categoria']=='MEDICAMENTOS');desc=sum(float(r['importe_pyg']) for r in rows if r['categoria']=='DESCARTABLES');serv=sum(float(r['importe_pyg']) for r in rows if r['categoria']=='SERVICIOS SANATORIALES');total=meds+desc+serv
   b5,i5=desglosar_iva_incluido(meds,5);b10,i10=desglosar_iva_incluido(desc+serv,10);ase=c.execute('select * from aseguradoras where id=?',(aseg,)).fetchone()
   if not ase or not ase['tercero_id']:raise ValueError('El seguro debe estar vinculado a un tercero/cliente para facturar.')
   ter=ase['tercero_id'];v=c.execute("insert into ventas(fecha,cliente_id,numero,moneda,tipo_cambio,gravado,iva,exento,total,total_pyg,gravado_10,iva_10,gravado_5,iva_5,exento_iva,condicion_venta) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(fecha,ter,num,'PYG',1,b10+b5,i10+i5,0,total,total,b10,i10,b5,i5,0,'CREDITO'));vid=v.lastrowid
   for nombre,importe,iva_pct in [('MEDICAMENTOS',meds,5),('DESCARTABLES',desc,10),('SERVICIOS SANATORIALES',serv,10)]:
    if importe>0:
     base,iv=desglosar_iva_incluido(importe,iva_pct);c.execute('insert into venta_items(venta_id,producto_id,cantidad,precio,total,total_pyg,costo_pyg,iva_pct) values(?,?,?,?,?,?,?,?)',(vid,None,1,importe,base,base,0,iva_pct))
   fid=c.execute('insert into facturas_seguro(fecha,aseguradora_id,numero,medicamentos_pyg,descartables_pyg,servicios_pyg,total_pyg,venta_id,creado_por,creado_en) values(?,?,?,?,?,?,?,?,?,?)',(fecha,aseg,num,meds,desc,serv,total,vid,session.get('user'),now())).lastrowid
   for r in rows:
    c.execute('insert into factura_seguro_det(factura_seguro_id,pendiente_id,origen_tipo,origen_id,paciente_id,categoria,descripcion,importe_pyg,iva_pct) values(?,?,?,?,?,?,?,?,?)',(fid,r['id'],r['origen_tipo'],r['origen_id'],r['paciente_id'],r['categoria'],r['descripcion'],r['importe_pyg'],r['iva_pct']));c.execute("update seguro_pendientes set estado='FACTURADO',factura_seguro_id=? where id=?",(fid,r['id']))
    if r['origen_tipo']=='CARGO':c.execute('update cargos_paciente set facturado=1 where id=?',(r['origen_id'],))
   c.execute("insert into cxc(venta_id,tercero_id,moneda,tipo_cambio_origen,importe,saldo,importe_pyg,estado) values(?,?,?,?,?,?,?,'PENDIENTE')",(vid,ter,'PYG',1,total,total,total));asiento(c,fecha,'Factura consolidada seguro '+num,'FACTURA_SEGURO',fid,'PYG',1,[('1.1.02',total,0,total,'Cuenta a cobrar seguro'),('4.1.02',0,b10+b5,b10+b5,'Prestaciones/insumos seguro'),('2.1.02',0,i10+i5,i10+i5,'IVA débito')]);c.commit();audit('FACTURA_SEGURO',f'{fid} / {num} / {len(rows)} items');flash('Factura al seguro generada correctamente.')
  except Exception as e:c.rollback();flash('No se pudo facturar al seguro: '+str(e))
  c.close();return redirect('/seguros/facturar')
 aseg_id=request.args.get('aseguradora_id',type=int);desde=request.args.get('desde','');hasta=request.args.get('hasta','');wh=["sp.estado='PENDIENTE'"];pa=[]
 if aseg_id:wh.append('sp.aseguradora_id=?');pa.append(aseg_id)
 if desde:wh.append('sp.fecha>=?');pa.append(desde)
 if hasta:wh.append('sp.fecha<=?');pa.append(hasta)
 rows=c.execute("select sp.*,p.nombre paciente,a.nombre seguro from seguro_pendientes sp left join pacientes p on p.id=sp.paciente_id join aseguradoras a on a.id=sp.aseguradora_id where "+' and '.join(wh)+' order by a.nombre,sp.fecha,sp.id',pa).fetchall();asegs=c.execute('select * from aseguradoras order by nombre').fetchall();c.commit();c.close();return render_template('insurance_billing.html',rows=rows,asegs=asegs,aseg_id=aseg_id,desde=desde,hasta=hasta)

ROUTE_MODULE.update({'seguros_facturar':'FACTURACION'})
init_v1356_seguros()

# ===== V13.6.3: cierre de cuentas aseguradas pendiente de facturación =====
def init_v1363_cierre_seguro():
 c=db()
 cols={r['name'] for r in c.execute('pragma table_info(admisiones)').fetchall()}
 if 'fecha_cierre' not in cols:c.execute('alter table admisiones add column fecha_cierre TEXT')
 if 'cerrado_por' not in cols:c.execute('alter table admisiones add column cerrado_por TEXT')
 c.execute("CREATE TABLE IF NOT EXISTS schema_migrations(version TEXT PRIMARY KEY, aplicado_en TEXT)")
 c.execute("INSERT OR IGNORE INTO schema_migrations(version,aplicado_en) VALUES('13.6.3-cierre-seguros',?)",(now(),))
 c.commit();c.close()
init_v1363_cierre_seguro()

# ===== V13.6.1: códigos internos automáticos para movimientos =====
def init_v1361_codigos_internos():
    """Agrega un identificador interno automático, único y persistente."""
    c=db()
    specs={
      'compras':'COM','ventas':'VEN','stock_mov':'STK','cxc':'CXC','cxp':'CXP',
      'asientos':'ASI','caja_banco':'BAN','admisiones':'ADM','facturas_sanatorio':'FAC',
      'solicitudes_farmacia':'FAR','movimientos_caja':'CAJ','aperturas_caja':'APE',
      'recibos_pago':'REC','liquidaciones_medicas':'LIQ','facturas_seguro':'SEG'
    }
    existentes={r['name'] for r in c.execute("select name from sqlite_master where type='table'").fetchall()}
    for tabla,prefijo in specs.items():
        if tabla not in existentes:
            continue
        cols={r['name'] for r in c.execute(f'pragma table_info({tabla})').fetchall()}
        if 'codigo_interno' not in cols:
            c.execute(f'alter table {tabla} add column codigo_interno TEXT')
        c.execute(f"update {tabla} set codigo_interno=? || printf('%06d',id) where codigo_interno is null or trim(codigo_interno)=''",(prefijo+'-',))
        c.execute(f"create unique index if not exists ux_{tabla}_codigo_interno on {tabla}(codigo_interno) where codigo_interno is not null")
        trg=f'trg_{tabla}_codigo_interno'
        sql=("CREATE TRIGGER IF NOT EXISTS "+trg+" AFTER INSERT ON "+tabla+
             " FOR EACH ROW WHEN NEW.codigo_interno IS NULL OR trim(NEW.codigo_interno)='' BEGIN "+
             "UPDATE "+tabla+" SET codigo_interno='"+prefijo+"-' || printf('%06d',NEW.id) WHERE id=NEW.id; END")
        c.execute(sql)
    c.execute("CREATE TABLE IF NOT EXISTS schema_migrations(version TEXT PRIMARY KEY, aplicado_en TEXT)")
    c.execute("INSERT OR IGNORE INTO schema_migrations(version,aplicado_en) VALUES('13.6.1-codigos-internos',?)",(now(),))
    c.commit();c.close()

init_v1361_codigos_internos()



# ===== V13.6.4: Factura imprimible/PDF y preparación SIFEN =====
def init_v1364_factura_electronica():
    c=db()
    cols={r['name'] for r in c.execute('pragma table_info(ventas)').fetchall()}
    for col,defn in [('cdc','TEXT'),('estado_sifen',"TEXT DEFAULT 'NO_ENVIADO'"),('protocolo_sifen','TEXT'),('fecha_aprobacion_sifen','TEXT')]:
        if col not in cols:
            c.execute(f'alter table ventas add column {col} {defn}')
    c.execute("CREATE TABLE IF NOT EXISTS schema_migrations(version TEXT PRIMARY KEY, aplicado_en TEXT)")
    c.execute("INSERT OR IGNORE INTO schema_migrations(version,aplicado_en) VALUES('13.6.4-factura-pdf',?)",(now(),))
    c.commit();c.close()
init_v1364_factura_electronica()

def _factura_venta_data(venta_id):
    c=db()
    v=c.execute('''select v.*,t.nombre cliente,t.ruc,cb.banco,cb.numero_cuenta,cb.alias cuenta_alias,tp.nombre terminal_pos
                   from ventas v left join terceros t on t.id=v.cliente_id
                   left join cuentas_bancarias cb on cb.id=v.cuenta_bancaria_id
                   left join terminales_pos tp on tp.id=v.terminal_pos_id where v.id=?''',(venta_id,)).fetchone()
    items=c.execute('''select vi.*,p.codigo,p.nombre from venta_items vi left join productos p on p.id=vi.producto_id where vi.venta_id=? order by vi.id''',(venta_id,)).fetchall()
    inst=c.execute('select * from institucion_config where id=1').fetchone()
    c.close();return v,items,inst

@app.get('/ventas/<int:venta_id>/factura')
def factura_venta(venta_id):
    v,items,inst=_factura_venta_data(venta_id)
    if not v: flash('Factura no encontrada.'); return redirect('/ventas/carga')
    return render_template('invoice_sale.html',v=v,items=items,inst=inst)

@app.get('/ventas/<int:venta_id>/factura/pdf')
def factura_venta_pdf(venta_id):
    from io import BytesIO
    from flask import send_file
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,Image
    v,items,inst=_factura_venta_data(venta_id)
    if not v: flash('Factura no encontrada.'); return redirect('/ventas/carga')
    b=BytesIO();doc=SimpleDocTemplate(b,pagesize=A4,rightMargin=12*mm,leftMargin=12*mm,topMargin=10*mm,bottomMargin=10*mm)
    st=getSampleStyleSheet(); story=[]
    logo=os.path.join(app.root_path,'static','logo_santa_clara_cropped.png')
    head=[]
    if os.path.exists(logo): head.append(Image(logo,width=42*mm,height=20*mm))
    else: head.append(Paragraph('<b>CENTRO MÉDICO SANTA CLARA</b>',st['Heading2']))
    datos=f"<b>{(inst['razon_social'] if inst and 'razon_social' in inst.keys() else 'Centro Médico Santa Clara') or 'Centro Médico Santa Clara'}</b><br/>RUC: {(inst['ruc'] if inst and 'ruc' in inst.keys() else '') or '-'}<br/>{(inst['direccion'] if inst and 'direccion' in inst.keys() else '') or ''}"
    head.append(Paragraph(datos,st['Normal']))
    box=Table([[Paragraph('<b>FACTURA</b>',st['Heading2'])],[f"N.º {v['numero'] or v['id']}"],[f"Fecha: {v['fecha']}"],[f"Condición: {v['condicion_venta'] or '-'}"]],colWidths=[52*mm])
    box.setStyle(TableStyle([('BOX',(0,0),(-1,-1),.8,colors.black),('ALIGN',(0,0),(-1,-1),'CENTER'),('FONTSIZE',(0,0),(-1,-1),9)]))
    h=Table([[head[0],head[1],box]],colWidths=[45*mm,82*mm,52*mm]);h.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP')]));story += [h,Spacer(1,4*mm)]
    story += [Paragraph(f"<b>Cliente/Paciente:</b> {v['cliente'] or '-'} &nbsp;&nbsp; <b>RUC/CI:</b> {v['ruc'] or '-'}",st['Normal']),Paragraph(f"<b>Moneda:</b> {v['moneda']} &nbsp;&nbsp; <b>Tipo de cambio:</b> {v['tipo_cambio'] or 1}",st['Normal']),Spacer(1,3*mm)]
    data=[['Código','Descripción','Cant.','Precio IVA incl.','IVA','Total']]
    for x in items:data.append([x['codigo'] or '',x['nombre'] or '',f"{x['cantidad']:,.2f}",f"{x['precio']:,.0f}",('Exento' if not x['iva_pct'] else f"{x['iva_pct']:g}%"),f"{x['total']:,.0f}"])
    t=Table(data,colWidths=[25*mm,67*mm,18*mm,28*mm,18*mm,28*mm],repeatRows=1);t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.lightgrey),('GRID',(0,0),(-1,-1),.35,colors.grey),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),8),('ALIGN',(2,1),(-1,-1),'RIGHT')]));story += [t,Spacer(1,3*mm)]
    totals=[['Gravado 10%',f"{v['gravado_10'] or 0:,.0f}"],['IVA 10%',f"{v['iva_10'] or 0:,.0f}"],['Gravado 5%',f"{v['gravado_5'] or 0:,.0f}"],['IVA 5%',f"{v['iva_5'] or 0:,.0f}"],['Exento',f"{v['exento_iva'] or 0:,.0f}"],['TOTAL',f"{v['total'] or 0:,.0f} {v['moneda']}"]]
    tt=Table(totals,colWidths=[38*mm,38*mm],hAlign='RIGHT');tt.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.35,colors.grey),('ALIGN',(1,0),(1,-1),'RIGHT'),('FONTNAME',(0,-1),(-1,-1),'Helvetica-Bold')]));story.append(tt)
    pago=(v['forma_cobro'] or '-') + ((' / Ref. '+v['referencia_cobro']) if v['referencia_cobro'] else '')
    story += [Spacer(1,3*mm),Paragraph(f"<b>Forma de pago:</b> {pago}",st['Normal'])]
    if v['cdc']:
        story += [Paragraph(f"<b>CDC:</b> {v['cdc']} &nbsp; <b>Estado SIFEN:</b> {v['estado_sifen'] or '-'}",st['Normal'])]
    else:
        story += [Paragraph('<font size=7>Representación generada por el sistema. No se identifica como DTE aprobado por SIFEN mientras no exista CDC/aprobación.</font>',st['Normal'])]
    doc.build(story);b.seek(0)
    return send_file(b,mimetype='application/pdf',as_attachment=False,download_name=f"Factura_{v['numero'] or venta_id}.pdf")


# ===== V13.6.5: Configuración institucional centralizada =====
def init_v1365_empresa_config():
    c=db()
    cols={r['name'] for r in c.execute('pragma table_info(institucion_config)').fetchall()}
    nuevos=[
      ('razon_social','TEXT'),('nombre_fantasia','TEXT'),('dv','TEXT'),('ciudad','TEXT'),('departamento','TEXT'),
      ('whatsapp','TEXT'),('web','TEXT'),('establecimiento','TEXT'),('punto_expedicion','TEXT'),
      ('timbrado_desde','TEXT'),('timbrado_hasta','TEXT'),('proximo_numero_factura','INTEGER DEFAULT 1'),
      ('prefijo_factura',"TEXT DEFAULT '001-001'"),('proximo_numero_recibo','INTEGER DEFAULT 1'),
      ('prefijo_recibo',"TEXT DEFAULT 'REC'"),('pie_documento','TEXT'),('ambiente_sifen',"TEXT DEFAULT 'SIN_INTEGRACION'"),
      ('logo_archivo',"TEXT DEFAULT 'logo_santa_clara_cropped.png'")
    ]
    for col,defn in nuevos:
        if col not in cols: c.execute(f'alter table institucion_config add column {col} {defn}')
    c.execute("update institucion_config set razon_social=coalesce(nullif(razon_social,''),nombre), nombre_fantasia=coalesce(nullif(nombre_fantasia,''),nombre) where id=1")
    c.execute("CREATE TABLE IF NOT EXISTS schema_migrations(version TEXT PRIMARY KEY, aplicado_en TEXT)")
    c.execute("INSERT OR IGNORE INTO schema_migrations(version,aplicado_en) VALUES('13.6.5-config-empresa',?)",(now(),))
    c.commit();c.close()
init_v1365_empresa_config()

@app.route('/configuracion-empresa',methods=['GET','POST'])
def configuracion_empresa():
    if not (user_has('USUARIOS','ADMINISTRAR') or user_has('CONFIG_SANATORIO','EDITAR')):
        flash('No tiene permiso para modificar la configuración de la empresa.'); return redirect('/')
    c=db()
    if request.method=='POST':
        campos=['razon_social','nombre_fantasia','ruc','dv','direccion','ciudad','departamento','telefono','whatsapp','email','web','timbrado','establecimiento','punto_expedicion','timbrado_desde','timbrado_hasta','prefijo_factura','proximo_numero_factura','prefijo_recibo','proximo_numero_recibo','pie_documento','ambiente_sifen']
        vals=[]
        for x in campos:
            v=request.form.get(x,'').strip()
            if x in ('proximo_numero_factura','proximo_numero_recibo'):
                try:v=max(1,int(v or 1))
                except:v=1
            vals.append(v)
        c.execute('update institucion_config set '+','.join(f'{x}=?' for x in campos)+' where id=1',vals)
        logo=request.files.get('logo')
        if logo and logo.filename:
            ext=Path(logo.filename).suffix.lower()
            if ext in ('.png','.jpg','.jpeg','.webp'):
                nombre='logo_empresa'+ext
                logo.save(os.path.join(app.root_path,'static',nombre))
                c.execute('update institucion_config set logo_archivo=? where id=1',(nombre,))
            else: flash('Logo no actualizado: use PNG, JPG, JPEG o WEBP.')
        c.commit();audit('CONFIG_EMPRESA','Actualización de datos institucionales y documentos');flash('Configuración de la empresa guardada correctamente.')
        c.close();return redirect('/configuracion-empresa')
    inst=c.execute('select * from institucion_config where id=1').fetchone();c.close()
    return render_template('company_config.html',inst=inst)

ROUTE_MODULE.update({'configuracion_empresa':'CONFIG_SANATORIO'})

# V13.9.6: Seguridad modular estricta.
# Los permisos configurados por el administrador son persistentes y NO se reponen al reiniciar.
# GET/POST y acciones sensibles se validan en servidor por módulo + acción.

# Arranque al final: garantiza que Informes y futuras rutas queden registradas.

# === V13.7.0 MIGRACION HISTORICA SANTA CLARA 2026 ===
def migrate_legacy_2026():
 import csv
 c=db()
 try:
  # Ampliaciones no destructivas del maestro de productos
  cols={r[1] for r in c.execute('pragma table_info(productos)').fetchall()}
  extras={'resumido':'TEXT','moneda':'TEXT DEFAULT \'PYG\'','tipo_producto':'TEXT','presentacion':'TEXT','generico':'TEXT','laboratorio':'TEXT','distribuidora':'TEXT','droga':'TEXT','indicacion':'TEXT','posologia':'TEXT','tipo_controlado':'TEXT','especialidad':'TEXT','clasif_general':'TEXT','clasif_parcial':'TEXT','descripcion':'TEXT','vencimiento_control':'INTEGER DEFAULT 0','lote_control':'INTEGER DEFAULT 0','permitir_salida':'INTEGER DEFAULT 1','activo':'INTEGER DEFAULT 1'}
  for k,t in extras.items():
   if k not in cols:c.execute(f'alter table productos add column {k} {t}')
  c.execute('create table if not exists producto_stock_deposito(id integer primary key,producto_id int,deposito text,stock real default 0,stock_min real default 0,unique(producto_id,deposito))')
  c.execute('create table if not exists legacy_import_map(tipo text,legacy_id text,new_id integer,primary key(tipo,legacy_id))')
  c.execute('create table if not exists legacy_import_log(id integer primary key,fecha text,fuente text,detalle text)')
  root=os.path.join(os.path.dirname(__file__),'import_data')
  def rows(name):
   p=os.path.join(root,name)
   if not os.path.exists(p):return []
   return csv.DictReader(open(p,encoding='utf-8-sig'))
  # Plan de cuentas oficial provisto por el usuario: 657 registros.
  plan=list(rows('plan_cuentas.csv')); legacy_to_account={}
  for r in plan:
   code=r['numero_cuenta']; legacy_to_account[r['codigo_legacy']]=code
   top=code[:2]; tipo={'01':'ACTIVO','02':'PASIVO','03':'PATRIMONIO','04':'INGRESO','05':'EGRESO'}.get(top,'OTRO')
   c.execute('insert or ignore into plan_cuentas(codigo,nombre,tipo,moneda,imputable) values(?,?,?,?,?)',(code,r['nombre'],tipo,'PYG',1 if r['imputable']=='S' else 0))
  # Productos + existencias por depósito. No se reemplazan productos ya existentes.
  prodrows=list(rows('stock_productos.csv')); agg={}
  for r in prodrows:
   a=agg.setdefault(r['codigo'],dict(r,stock_total=0.0));a['stock_total']+=float(r['stock'] or 0)
  for code,a in agg.items():
   p=c.execute('select id from productos where codigo=?',(code,)).fetchone()
   if p: pid=p[0]
   else:
    c.execute('insert into productos(codigo,codigo_barras,nombre,categoria,costo_pyg,precio_pyg,stock,stock_min,iva_pct,moneda,activo) values(?,?,?,?,?,?,?,?,?,?,1)',(code,a['codigo_barras'] or None,a['nombre'],'MIGRADO NEXTSYS',0,float(a['precio'] or 0),a['stock_total'],float(a['stock_min'] or 0),float(a['iva'] or 0),'PYG'));pid=c.execute('select last_insert_rowid()').fetchone()[0]
   for r in (x for x in prodrows if x['codigo']==code):
    c.execute('insert into producto_stock_deposito(producto_id,deposito,stock,stock_min) values(?,?,?,?) on conflict(producto_id,deposito) do update set stock=excluded.stock,stock_min=excluded.stock_min',(pid,r['deposito'],float(r['stock'] or 0),float(r['stock_min'] or 0)))
  # Compras/Ventas históricas: se registran a nivel comprobante según los libros entregados.
  from datetime import datetime as _dt
  def iso(s):
   try:return _dt.strptime(s,'%d/%m/%y').strftime('%Y-%m-%d')
   except:return s
  def tercero(tipo,nombre,ruc):
   x=c.execute('select id from terceros where ruc=? and tipo=?',(ruc,tipo)).fetchone()
   if x:return x[0]
   c.execute('insert into terceros(tipo,ruc,nombre,moneda) values(?,?,?,?)',(tipo,ruc,nombre,'PYG'));return c.execute('select last_insert_rowid()').fetchone()[0]
  for kind,fn,table,fk,tipo in [('VENTA','ventas_2026.csv','ventas','cliente_id','CLIENTE'),('COMPRA','compras_2026.csv','compras','proveedor_id','PROVEEDOR')]:
   for r in rows(fn):
    key=r['legacy_id']
    if c.execute('select 1 from legacy_import_map where tipo=? and legacy_id=?',(kind,key)).fetchone():continue
    tid=tercero(tipo,r['nombre'],r['ruc']); g=float(r['gravado5'])+float(r['gravado10']); iva=float(r['iva5'])+float(r['iva10']); ex=float(r['exento']); total=float(r['total'])
    c.execute(f'insert into {table}(fecha,{fk},numero,moneda,tipo_cambio,gravado,iva,exento,total,total_pyg,estado) values(?,?,?,?,?,?,?,?,?,?,?)',(iso(r['fecha']),tid,r['numero'],'PYG',1,g,iva,ex,total,total,'MIGRADA'))
    nid=c.execute('select last_insert_rowid()').fetchone()[0];c.execute('insert into legacy_import_map(tipo,legacy_id,new_id) values(?,?,?)',(kind,key,nid))
  # Diario histórico: conserva asiento, fecha, cuenta, debe/haber. Evita duplicación por mapa.
  for r in rows('diario_2026.csv'):
   aid=r['asiento']; key='DIARIO:'+aid
   m=c.execute('select new_id from legacy_import_map where tipo=? and legacy_id=?',('ASIENTO',aid)).fetchone()
   if m:new_aid=m[0]
   else:
    numero='LEG-'+aid
    old=c.execute('select id from asientos where numero=?',(numero,)).fetchone()
    if old:new_aid=old[0]
    else:
     c.execute('insert into asientos(fecha,numero,concepto,origen_tipo,origen_id,moneda,tipo_cambio,estado) values(?,?,?,?,?,?,?,?)',(iso(r['fecha']),numero,'Asiento histórico migrado NextSys','MIGRACION',int(r['enlace'] or 0),'PYG',1,'CONFIRMADO'));new_aid=c.execute('select last_insert_rowid()').fetchone()[0]
    c.execute('insert or ignore into legacy_import_map(tipo,legacy_id,new_id) values(?,?,?)',('ASIENTO',aid,new_aid))
   cuenta=legacy_to_account.get(r['codigo_legacy'],r['codigo_legacy'])
   sig=(new_aid,cuenta,float(r['debe'] or 0),float(r['haber'] or 0),float(r['debe'] or 0)-float(r['haber'] or 0),'PYG',1,r['cuenta_nombre'])
   # evitar repetir líneas en reinicios: sólo cargar detalle si asiento aún no tiene detalles migrados
   if not c.execute("select 1 from asiento_det where asiento_id=? and detalle like 'MIGRADO:%' limit 1",(new_aid,)).fetchone():
    pass
  # segunda pasada agrupada para insertar detalles exactamente una vez
  by={}
  for r in rows('diario_2026.csv'):by.setdefault(r['asiento'],[]).append(r)
  for aid,rr in by.items():
   m=c.execute('select new_id from legacy_import_map where tipo=? and legacy_id=?',('ASIENTO',aid)).fetchone()
   if not m:continue
   new_aid=m[0]
   if c.execute("select 1 from asiento_det where asiento_id=? and detalle like 'MIGRADO:%' limit 1",(new_aid,)).fetchone():continue
   for r in rr:
    cuenta=legacy_to_account.get(r['codigo_legacy'],r['codigo_legacy'])
    c.execute('insert into asiento_det(asiento_id,cuenta,debe_pyg,haber_pyg,importe_moneda,moneda,tipo_cambio,detalle) values(?,?,?,?,?,?,?,?)',(new_aid,cuenta,float(r['debe'] or 0),float(r['haber'] or 0),float(r['debe'] or 0)-float(r['haber'] or 0),'PYG',1,'MIGRADO: '+r['cuenta_nombre']))
  c.execute("insert into legacy_import_log(fecha,fuente,detalle) select datetime('now'),'Reportes NextSys 2026','Plan de cuentas, stock, compras, ventas y diario importados' where not exists(select 1 from legacy_import_log where fuente='Reportes NextSys 2026')")
  c.commit()
 except Exception as e:
  c.rollback();print('[Santa Clara] Migración histórica pendiente/error:',e)
 finally:c.close()

# Ejecutar importación incremental al iniciar. No borra registros existentes.
try:migrate_legacy_2026()
except Exception as _e:print('[Santa Clara] No se pudo ejecutar migración histórica:',_e)

# === V13.9.1: Conciliación bancaria + Portal público de agendamiento web ===
def init_v1391():
 c=db();c.executescript("""
 CREATE TABLE IF NOT EXISTS conciliaciones_bancarias(id INTEGER PRIMARY KEY, cuenta_bancaria_id INTEGER NOT NULL, fecha_desde TEXT NOT NULL, fecha_hasta TEXT NOT NULL, saldo_extracto REAL DEFAULT 0, saldo_sistema REAL DEFAULT 0, diferencia REAL DEFAULT 0, estado TEXT DEFAULT 'ABIERTA', observaciones TEXT, creado_por TEXT, creado_en TEXT, cerrado_en TEXT);
 CREATE TABLE IF NOT EXISTS conciliacion_extracto(id INTEGER PRIMARY KEY, conciliacion_id INTEGER NOT NULL, fecha TEXT NOT NULL, referencia TEXT, descripcion TEXT, debito REAL DEFAULT 0, credito REAL DEFAULT 0, importe_neto REAL DEFAULT 0, movimiento_sistema_id INTEGER, estado TEXT DEFAULT 'PENDIENTE');
 CREATE TABLE IF NOT EXISTS agenda_web_solicitudes(id INTEGER PRIMARY KEY, agenda_id INTEGER, fecha TEXT, hora TEXT, medico_id INTEGER, especialidad TEXT, documento TEXT, paciente TEXT, telefono TEXT, email TEXT, motivo TEXT, estado TEXT DEFAULT 'CONFIRMADO', creado_en TEXT, ip_origen TEXT);
 """);c.commit();c.close()

@app.route('/bancos/conciliacion',methods=['GET','POST'])
def conciliacion_bancaria():
 c=db()
 if request.method=='POST':
  cuenta=int(request.form['cuenta_bancaria_id']);desde=request.form['fecha_desde'];hasta=request.form['fecha_hasta'];saldo=float(request.form.get('saldo_extracto') or 0)
  sist=c.execute("select coalesce(sum(case when tipo='INGRESO' then importe_pyg else -importe_pyg end),0) from caja_banco where cuenta_bancaria_id=? and fecha between ? and ?",(cuenta,desde,hasta)).fetchone()[0]
  cur=c.execute("insert into conciliaciones_bancarias(cuenta_bancaria_id,fecha_desde,fecha_hasta,saldo_extracto,saldo_sistema,diferencia,creado_por,creado_en) values(?,?,?,?,?,?,?,?)",(cuenta,desde,hasta,saldo,sist,saldo-sist,session['user'],now()));cid=cur.lastrowid;c.commit();c.close();audit('CONCILIACION_BANCARIA_NUEVA',f'Conciliación {cid}');return redirect(f'/bancos/conciliacion/{cid}')
 cuentas=c.execute('select * from cuentas_bancarias where activo=1 order by banco,alias').fetchall();rows=c.execute('select x.*,b.banco,b.alias,b.numero_cuenta from conciliaciones_bancarias x join cuentas_bancarias b on b.id=x.cuenta_bancaria_id order by x.id desc').fetchall();c.close();return render_template('bank_reconciliation.html',cuentas=cuentas,rows=rows)

@app.route('/bancos/conciliacion/<int:cid>',methods=['GET','POST'])
def conciliacion_bancaria_detalle(cid):
 c=db();r=c.execute('select x.*,b.banco,b.alias,b.numero_cuenta from conciliaciones_bancarias x join cuentas_bancarias b on b.id=x.cuenta_bancaria_id where x.id=?',(cid,)).fetchone()
 if not r:c.close();return ('Conciliación no encontrada',404)
 if request.method=='POST':
  op=request.form.get('op')
  if r['estado']=='CERRADA':c.close();flash('La conciliación está cerrada.');return redirect(f'/bancos/conciliacion/{cid}')
  if op=='extracto':
   deb=float(request.form.get('debito') or 0);cred=float(request.form.get('credito') or 0);c.execute('insert into conciliacion_extracto(conciliacion_id,fecha,referencia,descripcion,debito,credito,importe_neto) values(?,?,?,?,?,?,?)',(cid,request.form['fecha'],request.form.get('referencia'),request.form.get('descripcion'),deb,cred,cred-deb))
  elif op=='conciliar':c.execute("update conciliacion_extracto set movimiento_sistema_id=?,estado='CONCILIADO' where id=? and conciliacion_id=?",(int(request.form['movimiento_id']),int(request.form['extracto_id']),cid))
  elif op=='desconciliar':c.execute("update conciliacion_extracto set movimiento_sistema_id=null,estado='PENDIENTE' where id=? and conciliacion_id=?",(int(request.form['extracto_id']),cid))
  elif op=='cerrar':
   pend=c.execute("select count(*) from conciliacion_extracto where conciliacion_id=? and estado<>'CONCILIADO'",(cid,)).fetchone()[0]
   if pend:c.close();flash('No puede cerrar: existen movimientos del extracto pendientes.');return redirect(f'/bancos/conciliacion/{cid}')
   c.execute("update conciliaciones_bancarias set estado='CERRADA',cerrado_en=? where id=?",(now(),cid))
  c.commit();c.close();audit('CONCILIACION_BANCARIA',f'{op} / {cid}');return redirect(f'/bancos/conciliacion/{cid}')
 ext=c.execute('select * from conciliacion_extracto where conciliacion_id=? order by fecha,id',(cid,)).fetchall();mov=c.execute('select * from caja_banco where cuenta_bancaria_id=? and fecha between ? and ? and id not in (select coalesce(movimiento_sistema_id,0) from conciliacion_extracto where movimiento_sistema_id is not null) order by fecha,id',(r['cuenta_bancaria_id'],r['fecha_desde'],r['fecha_hasta'])).fetchall();c.close();return render_template('bank_reconciliation_detail.html',r=r,ext=ext,mov=mov)

@app.get('/turnos-web')
def agenda_web_publica():
 fecha=request.args.get('fecha') or datetime.date.today().isoformat();especialidad=(request.args.get('especialidad') or '').strip();c=db();day=datetime.date.fromisoformat(fecha).weekday();especialidades=c.execute("select distinct especialidad from medicos where coalesce(especialidad,'')<>'' order by especialidad").fetchall();pars=[day];q='select h.*,m.nombre medico,m.especialidad from horarios_medicos h join medicos m on m.id=h.medico_id where h.activo=1 and h.dia_semana=?'
 if especialidad:q+=' and m.especialidad=?';pars.append(especialidad)
 hrs=c.execute(q+' order by m.nombre,h.hora_inicio',pars).fetchall();slots=[]
 for hr in hrs:
  for hora in _slot_times(hr['hora_inicio'],hr['hora_fin'],hr['minutos_consulta']):
   busy=c.execute("select 1 from agenda where medico_id=? and fecha=? and substr(hora,1,5)=? and estado<>'CANCELADO' limit 1",(hr['medico_id'],fecha,hora)).fetchone();ex=c.execute('select 1 from agenda_excepciones where activo=1 and medico_id=? and fecha=? and (hora_inicio is null or ?>=hora_inicio) and (hora_fin is null or ?<hora_fin) limit 1',(hr['medico_id'],fecha,hora,hora)).fetchone()
   if not busy and not ex:slots.append({'medico_id':hr['medico_id'],'medico':hr['medico'],'especialidad':hr['especialidad'],'hora':hora,'consultorio':hr['consultorio'] or ''})
 c.close();return render_template('public_booking.html',fecha=fecha,especialidad=especialidad,especialidades=especialidades,slots=slots)

@app.post('/turnos-web/reservar')
def agenda_web_reservar():
 fecha=request.form['fecha'];hora=request.form['hora'];mid=int(request.form['medico_id']);doc=(request.form.get('documento') or '').strip();nombre=(request.form.get('paciente') or '').strip();tel=(request.form.get('telefono') or '').strip();email=(request.form.get('email') or '').strip();motivo=(request.form.get('motivo') or '').strip()
 if not nombre or not tel:return ('Nombre y teléfono son obligatorios',400)
 c=db();c.execute('BEGIN IMMEDIATE')
 if c.execute("select 1 from agenda where medico_id=? and fecha=? and substr(hora,1,5)=? and estado<>'CANCELADO' limit 1",(mid,fecha,hora)).fetchone():c.rollback();c.close();flash('Ese horario acaba de ser reservado. Elija otro.');return redirect('/turnos-web?fecha='+fecha)
 p=c.execute('select * from pacientes where documento=?',(doc,)).fetchone() if doc else None
 if p:pid=p['id'];c.execute('update pacientes set nombre=?,telefono=? where id=?',(nombre,tel,pid))
 else:pid=c.execute('insert into pacientes(documento,nombre,telefono) values(?,?,?)',(doc,nombre,tel)).lastrowid
 m=c.execute('select * from medicos where id=?',(mid,)).fetchone();esp=(m['especialidad'] if m else '') or '';eidrow=c.execute('select id from especialidades where nombre=?',(esp,)).fetchone();eid=eidrow['id'] if eidrow else None
 gid=c.execute("insert into agenda(fecha,hora,paciente_id,medico_id,especialidad_id,motivo,estado,precio_pyg,cobrado,creado_por,creado_en) values(?,?,?,?,?,?,'AGENDADO',0,0,'WEB',?)",(fecha,hora,pid,mid,eid,motivo,now())).lastrowid;c.execute('insert into agenda_web_solicitudes(agenda_id,fecha,hora,medico_id,especialidad,documento,paciente,telefono,email,motivo,creado_en,ip_origen) values(?,?,?,?,?,?,?,?,?,?,?,?)',(gid,fecha,hora,mid,esp,doc,nombre,tel,email,motivo,now(),request.remote_addr));c.commit();c.close();return redirect('/turnos-web/confirmacion?id='+str(gid))

@app.get('/turnos-web/confirmacion')
def agenda_web_confirmacion():
 gid=request.args.get('id',type=int);c=db();r=c.execute("select g.fecha,g.hora,p.nombre paciente,m.nombre medico,m.especialidad from agenda g join pacientes p on p.id=g.paciente_id join medicos m on m.id=g.medico_id where g.id=? and g.creado_por='WEB'",(gid,)).fetchone();c.close();return render_template('public_booking_success.html',r=r)

ROUTE_MODULE.update({'conciliacion_bancaria':'FINANZAS','conciliacion_bancaria_detalle':'FINANZAS'})
init_v1391()

if __name__=='__main__':
    app.run(host='0.0.0.0',port=5000,debug=False)
