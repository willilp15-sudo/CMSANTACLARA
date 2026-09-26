from flask import Flask,render_template,request,redirect,session,flash,jsonify,send_file
import sqlite3,os,hashlib,datetime,shutil,io,threading,time,secrets
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from pathlib import Path
app=Flask(__name__)

# ===== V13.9.37: formato monetario Paraguay + totales universales =====
def _num_local(value, decimals=0):
    try:
        n=float(value or 0)
        txt=f"{n:,.{int(decimals)}f}"
        return txt.replace(',', '#').replace('.', ',').replace('#', '.')
    except Exception:
        return str(value if value is not None else '')

def _money_local(value, currency='PYG'):
    cur=(currency or 'PYG').upper()
    return _num_local(value, 0 if cur in ('PYG','GS','G$','GUARANI','GUARANIES') else 2)

def _is_money_header(header):
    h=(header or '').lower()
    keys=('total','importe','saldo','debe','haber','facturado','honorario','margen','cuenta pyg','costo','precio','iva','gravado','exento','entrada','salida','movimiento','gs.','pyg')
    return any(k in h for k in keys) and not any(k in h for k in ('fecha','cantidad','consultas','registros'))

def _report_totals(headers, rows):
    out=[]
    for i,h in enumerate(headers):
        if not _is_money_header(h): continue
        total=0.0; found=False
        for r in rows:
            try:
                v=r[i]
                if isinstance(v,(int,float)):
                    total += float(v or 0); found=True
            except Exception: pass
        if found: out.append((h,total))
    return out

def _report_value(value, header=''):
    if isinstance(value,(int,float)):
        if _is_money_header(header): return _money_local(value,'PYG')
        return _num_local(value, 2 if isinstance(value,float) and not float(value).is_integer() else 0)
    return '' if value is None else str(value)
@app.template_filter('pyg')
def _jinja_pyg(v): return _money_local(v,'PYG')
@app.template_filter('num_local')
def _jinja_num_local(v): return _num_local(v,2)
@app.template_filter('money_local')
def _jinja_money_local(v): return _money_local(v,'PYG')



app.secret_key=os.environ.get('SECRET_KEY') or secrets.token_hex(32)
app.config.update(SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Lax',SESSION_COOKIE_SECURE=bool(os.environ.get('RENDER')),PERMANENT_SESSION_LIFETIME=datetime.timedelta(hours=8),MAX_CONTENT_LENGTH=16*1024*1024)

# V13.5.9 - Base de datos persistente fuera de la carpeta de cada versión.
# En Windows se guarda en %LOCALAPPDATA%\SantaClaraERP\data. De esta forma,
# reemplazar/descomprimir una nueva versión del programa no reemplaza los datos.
def _directorio_datos_persistente():
 base=os.environ.get('SANTA_CLARA_DATA_DIR')
 if not base and os.environ.get('RENDER'): base='/var/data'
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
 # V13.9.32: desactivado. Los backups se crean únicamente de forma manual.
 return

preparar_base_persistente()

def db():
 c=sqlite3.connect(DB);c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON');return c
def h(s):return hashlib.sha256(s.encode()).hexdigest()
def password_hash(s):return generate_password_hash(s,method='scrypt')
def password_ok(stored,plain):
 try:
  if stored and (stored.startswith('scrypt:') or stored.startswith('pbkdf2:')): return check_password_hash(stored,plain)
 except Exception: pass
 return secrets.compare_digest(stored or '',h(plain))
def now():return datetime.datetime.now().isoformat(timespec='seconds')
DEFAULT_LOGO='santa_clara_logo_documentos.jpg'
BRANDING_DIR=os.path.join(DATA_DIR,'branding')
os.makedirs(BRANDING_DIR,exist_ok=True)

def _logo_archivo_configurado():
 try:
  c=db(); r=c.execute('select logo_archivo from institucion_config where id=1').fetchone(); c.close()
  return (r['logo_archivo'] if r and r['logo_archivo'] else DEFAULT_LOGO)
 except Exception:
  return DEFAULT_LOGO

def logo_path_actual():
 nombre=os.path.basename(_logo_archivo_configurado())
 persistente=os.path.join(BRANDING_DIR,nombre)
 if os.path.isfile(persistente): return persistente
 candidato=os.path.join(app.root_path,'static',nombre)
 if os.path.isfile(candidato): return candidato
 return os.path.join(app.root_path,'static',DEFAULT_LOGO)

def pdf_logo(width=120,height=82):
 from reportlab.platypus import Image
 ruta=logo_path_actual()
 if os.path.exists(ruta):
  im=Image(ruta,width=width,height=height); im.hAlign='LEFT'; return im
 return None

@app.get('/branding/logo')
def branding_logo():
 ruta=logo_path_actual()
 if os.path.isfile(ruta): return send_file(ruta,max_age=300)
 return ('',404)

@app.context_processor
def identidad_visual_global():
 return {'logo_url':'/branding/logo'}
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
 if not c.execute('select 1 from usuarios').fetchone():c.execute('insert into usuarios(nombre,usuario,clave,rol) values(?,?,?,?)',('Administrador','admin',password_hash(os.environ.get('ADMIN_PASSWORD','SantaClara2026!')),'ADMIN'))
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
 if tc<=0:tc=tc_dnit(c,fecha,moneda,'VENTA')
 return tc

@app.before_request
def auth():
 if request.endpoint not in ('login','static','agenda_web_publica','agenda_web_reservar','agenda_web_confirmacion','llamador_api_pendientes','llamador_api_confirmar','llamador_api_ping') and 'user' not in session:return redirect('/login')
@app.route('/login',methods=['GET','POST'])
def login():
 if request.method=='POST':
  c=db();u=c.execute('select * from usuarios where usuario=? and activo=1',(request.form['usuario'],)).fetchone()
  if u and password_ok(u['clave'],request.form['clave']):
   if not (u['clave'] or '').startswith(('scrypt:','pbkdf2:')):
    c.execute('update usuarios set clave=? where id=?',(password_hash(request.form['clave']),u['id']));c.commit()
   c.close();session.permanent=True;session['user']=u['usuario'];session['name']=u['nombre'];return redirect('/')
  c.close()
  flash('Usuario o contraseña incorrectos')
 return render_template('login.html')
@app.get('/logout')
def logout():session.clear();return redirect('/login')
@app.route('/')
def home():
 return render_template('dashboard.html')
@app.route('/tipos-cambio',methods=['GET','POST'])
def tipos_cambio():
 c=db()
 if request.method=='POST':c.execute('insert into tipos_cambio(fecha,moneda,tipo,fuente) values(?,?,?,?) on conflict(fecha,moneda) do update set tipo=excluded.tipo,fuente=excluded.fuente',(request.form['fecha'],request.form['moneda'],float(request.form['tipo']),request.form.get('fuente','Manual')));c.commit();audit('TIPO_CAMBIO',request.form['moneda']);return redirect('/tipos-cambio')
 rows=c.execute('select * from tipos_cambio order by fecha desc,moneda').fetchall();mons=c.execute("select * from monedas where codigo<>'PYG'").fetchall();c.close();return render_template('exchange.html',rows=rows,mons=mons)
@app.route('/proveedores',methods=['GET','POST'])
def proveedores():
 c=db()
 if request.method=='POST':
  vals=('PROVEEDOR',request.form.get('ruc'),request.form['nombre'],request.form.get('telefono'),request.form.get('email'),request.form.get('moneda') or 'PYG')
  c.execute('insert into terceros(tipo,ruc,nombre,telefono,email,moneda) values(?,?,?,?,?,?)',vals);c.commit();c.close();flash('Proveedor registrado correctamente.');return redirect('/proveedores')
 rows=c.execute("select * from terceros where upper(coalesce(tipo,''))='PROVEEDOR' order by nombre").fetchall();mons=c.execute('select * from monedas').fetchall();c.close();return render_template('providers.html',rows=rows,mons=mons)

@app.route('/terceros',methods=['GET','POST'])
def terceros():
 # Compatibilidad con enlaces antiguos: el maestro Terceros deja de exponerse al usuario.
 return redirect('/proveedores')

@app.route('/clientes',methods=['GET','POST'])
def clientes():
 # CLIENTES es el único maestro visible de pacientes/clientes. La tabla pacientes se conserva
 # internamente para historia clínica, admisiones y compatibilidad de relaciones existentes.
 return pacientes()

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

def init_v13991_maestros_sifen():
 c=db()
 try:
  # Datos fiscales/receptor SIFEN. Migración aditiva: no elimina ni transforma datos existentes.
  tcols={r['name'] for r in c.execute('pragma table_info(terceros)').fetchall()}
  for col,typ in [
   ('sifen_naturaleza',"TEXT DEFAULT '1'"),('sifen_tipo_operacion',"TEXT DEFAULT '1'"),
   ('sifen_tipo_contribuyente',"TEXT DEFAULT '2'"),('sifen_tipo_documento',"TEXT DEFAULT '1'"),
   ('sifen_numero_documento','TEXT'),('sifen_pais',"TEXT DEFAULT 'PRY'"),('sifen_pais_desc',"TEXT DEFAULT 'Paraguay'"),
   ('sifen_direccion','TEXT'),('sifen_numero_casa',"TEXT DEFAULT '0'"),
   ('sifen_departamento_codigo','TEXT'),('sifen_departamento_desc','TEXT'),
   ('sifen_distrito_codigo','TEXT'),('sifen_distrito_desc','TEXT'),
   ('sifen_ciudad_codigo','TEXT'),('sifen_ciudad_desc','TEXT')]:
   if col not in tcols:c.execute('alter table terceros add column '+col+' '+typ)
  pcols={r['name'] for r in c.execute('pragma table_info(productos)').fetchall()}
  for col,typ in [('sifen_unidad_codigo',"TEXT DEFAULT '77'"),('sifen_unidad_desc',"TEXT DEFAULT 'UNI'"),('sifen_descripcion','TEXT')]:
   if col not in pcols:c.execute('alter table productos add column '+col+' '+typ)
  c.execute("update terceros set sifen_numero_documento=coalesce(nullif(trim(sifen_numero_documento),''),ruc) where upper(coalesce(tipo,'')) in ('CLIENTE','AMBOS')")
  c.execute("update productos set sifen_descripcion=coalesce(nullif(trim(sifen_descripcion),''),nullif(trim(nombre),''),'Servicio medico')")
  c.execute("insert or ignore into schema_migrations(version,aplicado_en) values('13.9.91-maestros-sifen',?)",(now(),))
  c.commit()
 finally:c.close()
@app.route('/productos',methods=['GET','POST'])
def productos():
 c=db()
 if request.method=='POST':
  try:
   cb=(request.form.get('codigo_barras') or '').strip() or None
   if cb and c.execute('select 1 from productos where codigo_barras=?',(cb,)).fetchone():raise ValueError('Código de barras ya registrado en otro producto.')
   c.execute('insert into productos(codigo,codigo_barras,nombre,categoria,costo_pyg,precio_pyg,stock,stock_min,iva_pct,resumido,moneda,tipo_producto,presentacion,generico,laboratorio,distribuidora,droga,indicacion,posologia,tipo_controlado,especialidad,clasif_general,clasif_parcial,descripcion,vencimiento_control,lote_control,permitir_salida,activo,sifen_descripcion,sifen_unidad_codigo,sifen_unidad_desc) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(request.form['codigo'],cb,request.form['nombre'],request.form.get('categoria',''),float(request.form.get('costo_pyg') or 0),float(request.form.get('precio_pyg') or 0),float(request.form.get('stock') or 0),float(request.form.get('stock_min') or 0),float(request.form.get('iva_pct') or 0),request.form.get('resumido',''),request.form.get('moneda','PYG'),request.form.get('tipo_producto',''),request.form.get('presentacion',''),request.form.get('generico',''),request.form.get('laboratorio',''),request.form.get('distribuidora',''),request.form.get('droga',''),request.form.get('indicacion',''),request.form.get('posologia',''),request.form.get('tipo_controlado',''),request.form.get('especialidad',''),request.form.get('clasif_general',''),request.form.get('clasif_parcial',''),request.form.get('descripcion',''),1 if request.form.get('vencimiento_control') else 0,1 if request.form.get('lote_control') else 0,1 if request.form.get('permitir_salida') else 0,1,request.form.get('sifen_descripcion') or request.form['nombre'],request.form.get('sifen_unidad_codigo') or '77',request.form.get('sifen_unidad_desc') or 'UNI'));c.commit();flash('Producto registrado correctamente.')
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
 ters=c.execute("select * from terceros where tipo in ('PROVEEDOR','AMBOS')").fetchall();prods=c.execute("select id,codigo,coalesce(codigo_barras,'') codigo_barras,nombre,coalesce(iva_pct,0) iva_pct,coalesce(precio_pyg,0) precio_pyg,coalesce(costo_pyg,0) costo_pyg,coalesce(stock,0) stock from productos where coalesce(activo,1)=1 order by nombre").fetchall();mons=c.execute('select * from monedas').fetchall();c.close();return render_template('transaction.html',kind='Compra',rows=rows,ters=ters,prods=prods,mons=mons,buscado=buscado,q=q)



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
    items=c.execute('select ci.*,p.codigo,p.nombre from compra_items ci left join productos p on p.id=ci.producto_id where ci.compra_id=? order by ci.id',(compra_id,)).fetchall();cuotas=c.execute('select * from compra_cuotas where compra_id=? order by numero,id',(compra_id,)).fetchall();ncs=c.execute('select * from notas_credito_compras where compra_id=? order by id desc',(compra_id,)).fetchall();cxp=c.execute("select * from cxp where compra_id=? and coalesce(estado,'') not in ('ANULADA','ANULADO') order by id limit 1",(compra_id,)).fetchone();c.close()
    return render_template('purchase_detail.html',comp=comp,items=items,cuotas=cuotas,ncs=ncs,cxp=cxp)

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


# ===== V13.9.44: múltiples establecimientos/puntos de expedición y correlatividad independiente =====
def init_v13944_puntos_expedicion():
    c=db()
    c.execute("""CREATE TABLE IF NOT EXISTS sifen_puntos_expedicion(
      id INTEGER PRIMARY KEY,
      establecimiento TEXT NOT NULL,
      punto_expedicion TEXT NOT NULL,
      descripcion TEXT,
      timbrado TEXT,
      factura_electronica INTEGER NOT NULL DEFAULT 1,
      nota_credito_electronica INTEGER NOT NULL DEFAULT 0,
      nota_debito_electronica INTEGER NOT NULL DEFAULT 0,
      autorizado_dnit INTEGER NOT NULL DEFAULT 1,
      activo INTEGER NOT NULL DEFAULT 1,
      predeterminado INTEGER NOT NULL DEFAULT 0,
      proximo_numero_factura INTEGER NOT NULL DEFAULT 1,
      creado_en TEXT, actualizado_en TEXT,
      UNIQUE(establecimiento,punto_expedicion)
    )""")
    vcols={r['name'] for r in c.execute('pragma table_info(ventas)').fetchall()}
    for col,defn in [('sifen_punto_id','INTEGER'),('establecimiento','TEXT'),('punto_expedicion','TEXT')]:
        if col not in vcols:c.execute(f'alter table ventas add column {col} {defn}')
    # Migra la configuración anterior como punto inicial sin borrar ningún dato.
    n=c.execute('select count(*) from sifen_puntos_expedicion').fetchone()[0]
    if not n:
        cfg=c.execute('select * from sifen_config where id=1').fetchone()
        ic=c.execute('select * from institucion_config where id=1').fetchone()
        est=((cfg['establecimiento'] if cfg else None) or '001').strip().zfill(3)
        pex=((cfg['punto_expedicion'] if cfg else None) or '001').strip().zfill(3)
        tim=((cfg['timbrado'] if cfg else None) or '').strip()
        prox=max(1,int((ic['proximo_numero_factura'] if ic else 1) or 1))
        c.execute('insert or ignore into sifen_puntos_expedicion(establecimiento,punto_expedicion,descripcion,timbrado,autorizado_dnit,activo,predeterminado,proximo_numero_factura,creado_en,actualizado_en) values(?,?,?,?,1,1,1,?,?,?)',(est,pex,'Punto migrado de la configuración anterior',tim,prox,now(),now()))
    c.execute("INSERT OR IGNORE INTO schema_migrations(version,aplicado_en) VALUES('13.9.44-multipunto-expedicion',?)",(now(),))
    c.commit();c.close()

def _flag_activo(v):
    # Compatibilidad con bases históricas: algunos flags pudieron quedar como
    # texto ("1", "SI", "ON") en versiones anteriores.
    if isinstance(v, bool): return v
    if isinstance(v, (int, float)): return int(v) == 1
    return str(v or '').strip().upper() in ('1','SI','SÍ','TRUE','ON','YES')

def _punto_facturacion(c,punto_id=None):
    """Devuelve EXACTAMENTE el punto elegido y valida sus tres flags FE.
    No sustituye silenciosamente el punto por Recepción/predeterminado.
    """
    if punto_id not in (None, '', 0, '0'):
        try: pid=int(str(punto_id).strip())
        except Exception: raise ValueError('El punto de expedición seleccionado no es válido.')
        p=c.execute("select * from sifen_puntos_expedicion where id=?",(pid,)).fetchone()
        if not p: raise ValueError('El punto de expedición seleccionado ya no existe. Actualice la pantalla y vuelva a elegirlo.')
        faltan=[]
        if not _flag_activo(p['activo']): faltan.append('Activo')
        if not _flag_activo(p['autorizado_dnit']): faltan.append('Autorizado DNIT')
        if not _flag_activo(p['factura_electronica']): faltan.append('Factura Electrónica')
        if faltan:
            codigo=f"{str(p['establecimiento'] or '').zfill(3)}-{str(p['punto_expedicion'] or '').zfill(3)}"
            raise ValueError('El punto '+codigo+' no puede emitir FE. Revise: '+', '.join(faltan)+'.')
        return p
    # Solo cuando el proceso no permite elegir punto se usa el predeterminado.
    candidatos=c.execute("select * from sifen_puntos_expedicion order by predeterminado desc,id").fetchall()
    for p in candidatos:
        if _flag_activo(p['activo']) and _flag_activo(p['autorizado_dnit']) and _flag_activo(p['factura_electronica']):
            return p
    raise ValueError('Configure al menos un punto de expedición DNIT activo y autorizado para Factura Electrónica.')

def _siguiente_numero_factura(c,punto_id=None):
    """Reserva el correlativo del punto dentro de la misma transacción de la venta."""
    p=_punto_facturacion(c,punto_id)
    est=str(p['establecimiento']).zfill(3);pex=str(p['punto_expedicion']).zfill(3)
    n=max(1,int(p['proximo_numero_factura'] or 1))
    while c.execute('select 1 from ventas where numero=? limit 1',(f'{est}-{pex}-{n:07d}',)).fetchone(): n+=1
    numero=f'{est}-{pex}-{n:07d}'
    c.execute('update sifen_puntos_expedicion set proximo_numero_factura=?,actualizado_en=? where id=?',(n+1,now(),p['id']))
    return numero,p

def _proximo_numero_factura_preview(c,punto_id=None):
    p=_punto_facturacion(c,punto_id)
    est=str(p['establecimiento']).zfill(3);pex=str(p['punto_expedicion']).zfill(3);n=max(1,int(p['proximo_numero_factura'] or 1))
    while c.execute('select 1 from ventas where numero=? limit 1',(f'{est}-{pex}-{n:07d}',)).fetchone(): n+=1
    return f'{est}-{pex}-{n:07d}'

# ===== V13.9.61: servicios sin control de stock =====
def _producto_es_servicio(p):
    vals=[p['tipo_producto'] if 'tipo_producto' in p.keys() else '',p['clasif_general'] if 'clasif_general' in p.keys() else '',p['categoria'] if 'categoria' in p.keys() else '']
    return any('SERVICIO' in str(v or '').strip().upper() for v in vals)

def _producto_controla_stock(p):
    return not _producto_es_servicio(p)

@app.route('/ventas/carga',methods=['GET','POST'])
def ventas():
 c=db()
 if request.method=='POST':
  success_vid=None
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
    if _producto_controla_stock(p):
     acumulado_stock[pid]=acumulado_stock.get(pid,0)+qty
     if float(p['stock'] or 0)<acumulado_stock[pid]:raise ValueError('Stock insuficiente para '+p['nombre'])
    iva_pct=float(p['iva_pct'] or 0);line_total=qty*price;base,line_iva=desglosar_iva_incluido(line_total,iva_pct)
    total+=line_total;iva+=line_iva;cost_line=(qty*float(p['costo_pyg'] or 0)) if _producto_controla_stock(p) else 0.0;costg+=cost_line
    if iva_pct==10:g10+=base;i10+=line_iva;grav+=base
    elif iva_pct==5:g5+=base;i5+=line_iva;grav+=base
    else:exento+=line_total
    detalle.append((p,pid,qty,price,line_total,base,line_iva,iva_pct,cost_line))
   tid=int(request.form['proveedor_id']);totg=total*tc;ivag=iva*tc
   # V13.9.109: respetar exactamente el punto elegido por el usuario en la factura.
   # Antes se ignoraba sifen_punto_id del formulario y se forzaba el punto asociado
   # a Caja/Recepción; si ese punto estaba inactivo aparecía el mensaje de
   # 'no está activo/autorizado' aunque el usuario hubiera elegido otro válido.
   punto_id_seleccionado=int(request.form.get('sifen_punto_id') or 0)
   if not punto_id_seleccionado:
    raise ValueError('Seleccione un punto de expedición habilitado para Factura Electrónica.')
   numero_factura,punto_factura=_siguiente_numero_factura(c,punto_id_seleccionado)
   if condicion=='CUOTAS' and entrega>total:raise ValueError('La entrega inicial no puede superar el total de la venta')
   cuotas_venta=[]
   if condicion=='CUOTAS':
    cuotas_venta=json.loads(request.form.get('venta_cuotas_json') or '[]');saldo_fin=round(total-entrega,2)
    if saldo_fin>0 and not cuotas_venta:raise ValueError('Debe cargar al menos una cuota para el saldo financiado')
    suma=round(sum(float(x.get('importe') or 0) for x in cuotas_venta),2)
    if abs(suma-saldo_fin)>0.01:raise ValueError(f'La suma de cuotas ({suma:,.2f}) debe ser igual al saldo financiado ({saldo_fin:,.2f})')
   cur=c.execute('insert into ventas(fecha,cliente_id,numero,moneda,tipo_cambio,gravado,iva,exento,total,total_pyg,gravado_10,iva_10,gravado_5,iva_5,exento_iva,condicion_venta,forma_cobro,referencia_cobro,entrega_inicial,fecha_vencimiento) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(fecha,tid,numero_factura,mon,tc,grav,iva,exento,total,totg,g10,i10,g5,i5,exento,condicion,medio or None,ref or None,entrega,venc));vid=cur.lastrowid
   ap_fact=caja_abierta(c);c.execute('update ventas set sifen_punto_id=?,establecimiento=?,punto_expedicion=?,caja_id=?,origen_area=? where id=?',(punto_factura['id'],punto_factura['establecimiento'],punto_factura['punto_expedicion'],ap_fact['caja_id'] if ap_fact else None,'RECEPCION',vid))
   c.execute('update ventas set cuenta_bancaria_id=?,terminal_pos_id=? where id=?',(cuenta_id,pos_id,vid))
   for p,pid,qty,price,line_total,base,line_iva,iva_pct,cost_line in detalle:
    c.execute('insert into venta_items(venta_id,producto_id,cantidad,precio,total,total_pyg,costo_pyg,iva_pct) values(?,?,?,?,?,?,?,?)',(vid,pid,qty,price,line_total,line_total*tc,cost_line,iva_pct))
    if _producto_controla_stock(p):
     c.execute('update productos set stock=stock-? where id=?',(qty,pid));c.execute('insert into stock_mov(fecha,producto_id,tipo,cantidad,costo_pyg,origen_tipo,origen_id) values(?,?,?,?,?,?,?)',(fecha,pid,'SALIDA',-qty,p['costo_pyg'],'VENTA',vid))
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
   asiento(c,fecha,'Venta '+numero_factura,'VENTA',vid,mon,tc,lineas)
   # V13.9.107: la emisión fiscal es un único proceso. Primero se confirma la
   # venta y luego el motor SIFEN genera CDC/QR/XML/firma/XSD y, en PRODUCCIÓN,
   # transmite automáticamente. No hay botones manuales de CDC/QR/envío.
   c.commit();success_vid=vid;audit('VENTA',str(vid));flash('Venta registrada correctamente con '+str(len(detalle))+' ítem(s). Procesando Factura Electrónica automáticamente...')
  except Exception as e:c.rollback();flash(str(e))
  finally:c.close()
  if success_vid:
   # Procesar SIFEN después del COMMIT para que el documento y sus ítems sean
   # visibles para el motor fiscal. Siempre termina en el KuDE/PDF imprimible.
   try:
    _sifen_emitir_factura_automatico(success_vid)
   except Exception as sx:
    _sifen_log('FE_EMISION_AUTOMATICA','ERROR',f'Factura {success_vid}: {sx}')
    flash('La venta fue registrada, pero el proceso SIFEN automático informó: '+str(sx))
   return redirect(f'/ventas/{success_vid}/factura/pdf')
  return redirect('/ventas/carga')
 q=(request.args.get('q') or '').strip(); buscado=bool(q); rows=[]
 if buscado:
  like='%'+q+'%'
  rows=c.execute("select x.*,t.nombre tercero from ventas x join terceros t on t.id=x.cliente_id where x.numero like ? or t.nombre like ? or coalesce(x.estado,'') like ? or x.fecha like ? order by x.id desc limit 200",(like,like,like,like)).fetchall()
 ters=c.execute("select * from terceros where tipo in ('CLIENTE','AMBOS')").fetchall();prods=c.execute("select id,codigo,coalesce(codigo_barras,'') codigo_barras,nombre,coalesce(iva_pct,0) iva_pct,coalesce(precio_pyg,0) precio_pyg,coalesce(costo_pyg,0) costo_pyg,coalesce(stock,0) stock from productos where coalesce(activo,1)=1 order by nombre").fetchall();mons=c.execute('select * from monedas').fetchall();cuentas=c.execute('select * from cuentas_bancarias where activo=1 order by banco,alias').fetchall();poses=c.execute('select * from terminales_pos where activo=1 order by nombre').fetchall();puntos=[p for p in c.execute("select * from sifen_puntos_expedicion order by predeterminado desc,establecimiento,punto_expedicion").fetchall() if _flag_activo(p['activo']) and _flag_activo(p['autorizado_dnit']) and _flag_activo(p['factura_electronica'])];proximo_numero=_proximo_numero_factura_preview(c) if puntos else 'Configure un punto DNIT';c.close();return render_template('transaction.html',kind='Venta',rows=rows,ters=ters,prods=prods,mons=mons,cuentas=cuentas,poses=poses,puntos=puntos,buscado=buscado,q=q,proximo_numero=proximo_numero)

@app.route('/ventas/recepcion-caja',methods=['GET','POST'])
def recepcion_caja_unificada():
 c=db();ap=caja_abierta(c);hoy=datetime.date.today().isoformat();es_admin=usuario_es_admin_cajas(c)
 if request.method=='POST':
  op=request.form.get('op')
  try:
   if op=='abrir':
    caja_id=int(request.form['caja_id'])
    if not caja_autorizada(c,caja_id): raise ValueError('No tiene autorización para abrir esta caja.')
    ocupada=c.execute("select a.*,u.nombre operador from aperturas_caja a left join usuarios u on u.usuario=a.usuario where a.caja_id=? and a.estado='ABIERTA' order by a.id desc limit 1",(caja_id,)).fetchone()
    if ocupada: raise ValueError('Esta caja ya está abierta por '+str(ocupada['operador'] or ocupada['usuario'])+'.')
    if ap: raise ValueError('Ya tiene una caja abierta. Ciérrela antes de abrir otra.')
    c.execute('insert into aperturas_caja(caja_id,usuario,fecha_apertura,saldo_inicial) values(?,?,?,?)',(caja_id,session['user'],now(),float(request.form.get('saldo_inicial') or 0)))
    c.commit();audit('ABRIR_CAJA',f'Caja {caja_id} por {session.get("user")}');flash('Caja abierta correctamente.')
   elif op in ('cerrar','cerrar_admin'):
    objetivo=ap
    if op=='cerrar_admin':
     if not es_admin: raise ValueError('Solo ADMIN puede cerrar cajas de otros usuarios.')
     objetivo=c.execute("select a.*,ca.nombre caja from aperturas_caja a join cajas ca on ca.id=a.caja_id where a.id=? and a.estado='ABIERTA'",(int(request.form['apertura_id']),)).fetchone()
    if not objetivo: raise ValueError('No existe una caja abierta para cerrar.')
    if not es_admin and objetivo['usuario']!=session.get('user'): raise ValueError('No tiene autorización para cerrar esta caja.')
    movsum=c.execute("select coalesce(sum(case when tipo='INGRESO' then importe_pyg else -importe_pyg end),0) from movimientos_caja where apertura_id=?",(objetivo['id'],)).fetchone()[0]
    sistema=float(objetivo['saldo_inicial'])+float(movsum);decl=float(request.form.get('total_declarado') or sistema)
    c.execute("update aperturas_caja set fecha_cierre=?,total_sistema=?,total_declarado=?,diferencia=?,estado='CERRADA' where id=?",(now(),sistema,decl,decl-sistema,objetivo['id']))
    c.commit();audit('CERRAR_CAJA',f'Apertura {objetivo["id"]}; operador original {objetivo["usuario"]}; cerrado por {session.get("user")}');flash('Caja cerrada. Diferencia: Gs. {:,.0f}'.format(decl-sistema))
  except Exception as e:
   c.rollback();flash(str(e))
  c.close();return redirect('/ventas/recepcion-caja')
 rows=c.execute('''select g.*,p.nombre paciente,p.documento,p.telefono,m.nombre medico,e.nombre especialidad from agenda g join pacientes p on p.id=g.paciente_id join medicos m on m.id=g.medico_id left join especialidades e on e.id=g.especialidad_id where g.fecha=? order by g.hora,g.id''',(hoy,)).fetchall()
 cajas=cajas_autorizadas_usuario(c)
 hist=c.execute('select a.*,ca.nombre caja from aperturas_caja a join cajas ca on ca.id=a.caja_id where a.usuario=? order by a.id desc limit 10',(session['user'],)).fetchall();mov=[]
 if ap:mov=c.execute('''select m.*,f.nombre forma from movimientos_caja m left join formas_cobro f on f.id=m.forma_cobro_id where m.apertura_id=? order by m.id desc''',(ap['id'],)).fetchall()
 abiertas_admin=c.execute("select a.*,ca.nombre caja,u.nombre operador from aperturas_caja a join cajas ca on ca.id=a.caja_id left join usuarios u on u.usuario=a.usuario where a.estado='ABIERTA' order by ca.nombre,a.id").fetchall() if es_admin else []
 c.close();return render_template('reception_cash_unified.html',rows=rows,ap=ap,hoy=hoy,cajas=cajas,hist=hist,mov=mov,es_admin=es_admin,abiertas_admin=abiertas_admin)

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
   cta_fin,_=_cuenta_financiera(c,medio,cuenta_id)
   asiento(c,fecha,'Cobro '+n,'COBRO_VENTA',cur.lastrowid,r['moneda'],tc,[(cta_fin,pyg,0,imp,'Cobro'),('1.1.02',0,imp*r['tipo_cambio_origen'],imp,'Cancela cliente')]);c.commit();audit('RECIBO_PAGO',n);rid=cur.lastrowid;c.close();return redirect('/recibos/'+str(rid))
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

def init_v13917_pagos_proveedores():
 c=db()
 c.execute("""CREATE TABLE IF NOT EXISTS pagos_proveedores(
  id INTEGER PRIMARY KEY,fecha TEXT NOT NULL,cxp_id INTEGER NOT NULL,proveedor_id INTEGER NOT NULL,
  compra_id INTEGER,documento TEXT,medio TEXT,moneda TEXT,importe REAL,tipo_cambio REAL,importe_pyg REAL,
  cuenta_debe TEXT,cuenta_haber TEXT,asiento_id INTEGER,creado_por TEXT,creado_en TEXT)""")
 c.commit();c.close()
init_v13917_pagos_proveedores()

@app.route('/compras/cuentas-proveedores')
def cuentas_pendientes_proveedores():
 c=db();q=(request.args.get('q') or '').strip();estado=request.args.get('estado','PENDIENTE')
 sql="""select x.*,t.nombre proveedor,t.ruc,c.numero factura,c.fecha fecha_compra,c.fecha_vencimiento
 from cxp x join terceros t on t.id=x.tercero_id left join compras c on c.id=x.compra_id where 1=1"""
 par=[]
 if estado=='PENDIENTE':sql+=" and x.saldo>0.0001"
 elif estado=='PAGADO':sql+=" and x.saldo<=0.0001"
 if q:
  sql+=" and (t.nombre like ? collate nocase or t.ruc like ? or c.numero like ?)"
  like='%'+q+'%';par += [like,like,like]
 sql+=" order by t.nombre,c.fecha,x.id"
 rows=c.execute(sql,par).fetchall()
 resumen=c.execute("""select t.id,t.nombre,t.ruc,count(x.id) documentos,sum(x.saldo) saldo
 from cxp x join terceros t on t.id=x.tercero_id where x.saldo>0.0001 group by t.id,t.nombre,t.ruc order by t.nombre""").fetchall()
 c.close();return render_template('supplier_pending.html',rows=rows,resumen=resumen,q=q,estado=estado)

@app.route('/compras/pagos-proveedores',methods=['GET','POST'])
def pagos_proveedores():
 c=db()
 # V13.9.69: un pago puede aplicarse a varias facturas del mismo proveedor y moneda.
 c.execute("""CREATE TABLE IF NOT EXISTS pagos_proveedores_lotes(id INTEGER PRIMARY KEY,fecha TEXT,proveedor_id INTEGER,documento TEXT,medio TEXT,moneda TEXT,tipo_cambio REAL,importe REAL,importe_pyg REAL,cuenta_bancaria_id INTEGER,cuenta_debe TEXT,cuenta_haber TEXT,asiento_id INTEGER,creado_por TEXT,creado_en TEXT)""")
 c.execute("""CREATE TABLE IF NOT EXISTS pagos_proveedores_det(id INTEGER PRIMARY KEY,lote_id INTEGER,cxp_id INTEGER,compra_id INTEGER,factura TEXT,importe_aplicado REAL,saldo_anterior REAL,saldo_restante REAL)""")
 c.commit()
 if request.method=='POST':
  try:
   proveedor_id=int(request.form['proveedor_id']); ids=[int(x) for x in request.form.getlist('cxp_ids')]
   if not ids: raise ValueError('Seleccione al menos una factura pendiente.')
   qs=','.join('?'*len(ids)); rows=c.execute(f"select x.*,coalesce(cp.numero,'-') factura,t.nombre proveedor from cxp x join terceros t on t.id=x.tercero_id left join compras cp on cp.id=x.compra_id where x.id in ({qs}) and x.tercero_id=? and x.saldo>0.0001",ids+[proveedor_id]).fetchall()
   if len(rows)!=len(ids): raise ValueError('Una o más cuentas no pertenecen al proveedor seleccionado o ya no tienen saldo.')
   monedas={r['moneda'] or 'PYG' for r in rows}
   if len(monedas)!=1: raise ValueError('Para un mismo pago seleccione facturas de una sola moneda.')
   mon=next(iter(monedas)); aplicaciones=[]
   for r in rows:
    imp=float(request.form.get('aplica_'+str(r['id'])) or 0)
    if imp<0 or imp>float(r['saldo'])+0.0001: raise ValueError('Aplicación inválida para factura '+str(r['factura']))
    if imp>0: aplicaciones.append((r,imp))
   if not aplicaciones: raise ValueError('Indique un importe a aplicar en al menos una factura.')
   total=sum(x[1] for x in aplicaciones); fecha=request.form['fecha']; lado=request.form.get('lado_cotizacion','VENTA'); tc=1.0 if mon=='PYG' else tc_dnit(c,fecha,mon,lado); pyg=round(total*tc,2)
   medio=request.form['medio']; cuenta_id=int(request.form.get('cuenta_bancaria_id') or 0) or None
   if medio!='EFECTIVO' and not cuenta_id: raise ValueError('Seleccione la cuenta bancaria de donde sale el dinero.')
   haber,_=_cuenta_financiera(c,medio,cuenta_id); debe=request.form.get('cuenta_debe') or '2.1.01'
   if debe==haber: raise ValueError('Cuenta Debe y Cuenta Haber deben ser diferentes.')
   orig=sum(imp*float(r['tipo_cambio_origen'] or 1) for r,imp in aplicaciones)
   lines=[(debe,orig,0,total,'Cancelación de '+str(len(aplicaciones))+' factura(s) proveedor'),(haber,0,pyg,total,'Pago a proveedor')]
   dif=pyg-orig
   if abs(dif)>0.01: lines.append(('5.2.01',dif,0,0,'Pérdida por diferencia de cambio') if dif>0 else ('4.2.01',0,-dif,0,'Ganancia por diferencia de cambio'))
   cur=c.execute("insert into pagos_proveedores_lotes(fecha,proveedor_id,documento,medio,moneda,tipo_cambio,importe,importe_pyg,cuenta_bancaria_id,cuenta_debe,cuenta_haber,creado_por,creado_en) values(?,?,?,?,?,?,?,?,?,?,?,?,?)",(fecha,proveedor_id,request.form.get('documento',''),medio,mon,tc,total,pyg,cuenta_id,debe,haber,session.get('user'),now())); lote=cur.lastrowid
   aid=asiento(c,fecha,'Pago múltiple a proveedor','PAGO_PROVEEDOR_MULTIPLE',lote,mon,tc,lines);c.execute('update pagos_proveedores_lotes set asiento_id=? where id=?',(aid,lote))
   for r,imp in aplicaciones:
    ant=float(r['saldo']);rest=max(0,ant-imp);c.execute("update cxp set saldo=?,estado=? where id=?",(rest,'PAGADO' if rest<=0.0001 else 'PENDIENTE',r['id']));c.execute("insert into pagos_proveedores_det(lote_id,cxp_id,compra_id,factura,importe_aplicado,saldo_anterior,saldo_restante) values(?,?,?,?,?,?,?)",(lote,r['id'],r['compra_id'],r['factura'],imp,ant,rest))
   c.execute("insert into caja_banco(fecha,tipo,medio,moneda,tipo_cambio,importe,importe_pyg,concepto,origen_tipo,origen_id,cuenta_bancaria_id) values(?,'EGRESO',?,?,?,?,?,'Pago múltiple a proveedor','PAGO_PROVEEDOR_MULTIPLE',?,?)",(fecha,medio,mon,tc,total,pyg,lote,cuenta_id));c.commit();audit('PAGO_PROVEEDOR_MULTIPLE',f'Lote {lote} / {len(aplicaciones)} facturas / {total} {mon}');flash(f'Pago registrado y aplicado a {len(aplicaciones)} factura(s).')
  except Exception as ex: c.rollback();flash(str(ex))
  c.close();return redirect('/compras/pagos-proveedores?proveedor_id='+request.form.get('proveedor_id',''))
 proveedor_id=int(request.args.get('proveedor_id') or 0); proveedores=c.execute("select distinct t.id,t.nombre,t.ruc from cxp x join terceros t on t.id=x.tercero_id where x.saldo>0.0001 order by t.nombre").fetchall(); pendientes=[]
 if proveedor_id: pendientes=c.execute("select x.*,coalesce(cp.numero,'-') factura,cp.fecha fecha_compra,t.nombre proveedor from cxp x join terceros t on t.id=x.tercero_id left join compras cp on cp.id=x.compra_id where x.tercero_id=? and x.saldo>0.0001 order by cp.fecha,x.id",(proveedor_id,)).fetchall()
 cuentas=c.execute('select * from plan_cuentas where imputable=1 order by codigo').fetchall();bancos=c.execute('select * from cuentas_bancarias where activo=1 order by banco,alias').fetchall();hist=c.execute("select l.*,t.nombre proveedor,(select count(*) from pagos_proveedores_det d where d.lote_id=l.id) documentos from pagos_proveedores_lotes l join terceros t on t.id=l.proveedor_id order by l.id desc limit 100").fetchall();c.close();return render_template('supplier_payments.html',pendientes=pendientes,proveedores=proveedores,proveedor_id=proveedor_id,cuentas=cuentas,bancos=bancos,pagos=hist)

@app.route('/ventas/cobros-clientes',methods=['GET','POST'])
def cobros_clientes_multiples():
 c=db();c.execute("""CREATE TABLE IF NOT EXISTS cobros_clientes_lotes(id INTEGER PRIMARY KEY,fecha TEXT,cliente_id INTEGER,referencia TEXT,medio TEXT,moneda TEXT,tipo_cambio REAL,importe REAL,importe_pyg REAL,cuenta_bancaria_id INTEGER,terminal_pos_id INTEGER,asiento_id INTEGER,creado_por TEXT,creado_en TEXT)""");c.execute("""CREATE TABLE IF NOT EXISTS cobros_clientes_det(id INTEGER PRIMARY KEY,lote_id INTEGER,cxc_id INTEGER,venta_id INTEGER,factura TEXT,importe_aplicado REAL,saldo_anterior REAL,saldo_restante REAL)""");c.commit()
 if request.method=='POST':
  try:
   cliente_id=int(request.form['cliente_id']);ids=[int(x) for x in request.form.getlist('cxc_ids')]
   if not ids: raise ValueError('Seleccione al menos una factura pendiente.')
   qs=','.join('?'*len(ids));rows=c.execute(f"select x.*,coalesce(v.numero,'-') factura,t.nombre cliente from cxc x join terceros t on t.id=x.tercero_id left join ventas v on v.id=x.venta_id where x.id in ({qs}) and x.tercero_id=? and x.saldo>0.0001",ids+[cliente_id]).fetchall()
   if len(rows)!=len(ids): raise ValueError('Una o más cuentas no pertenecen al cliente seleccionado o ya no tienen saldo.')
   monedas={r['moneda'] or 'PYG' for r in rows}
   if len(monedas)!=1: raise ValueError('Para un mismo cobro seleccione facturas de una sola moneda.')
   mon=next(iter(monedas)); aplicaciones=[]
   for r in rows:
    imp=float(request.form.get('aplica_'+str(r['id'])) or 0)
    if imp<0 or imp>float(r['saldo'])+0.0001: raise ValueError('Aplicación inválida para factura '+str(r['factura']))
    if imp>0: aplicaciones.append((r,imp))
   if not aplicaciones: raise ValueError('Indique un importe a aplicar en al menos una factura.')
   total=sum(x[1] for x in aplicaciones);fecha=request.form['fecha'];tc=tc_fecha(c,fecha,mon,request.form.get('tipo_cambio'));pyg=round(total*tc,2);medio=request.form['medio'];cuenta_id=int(request.form.get('cuenta_bancaria_id') or 0) or None;pos_id=int(request.form.get('terminal_pos_id') or 0) or None
   if medio in ('Banco','Transferencia','POS') and not cuenta_id: raise ValueError('Seleccione la cuenta bancaria receptora.')
   if medio=='POS' and not pos_id: raise ValueError('Seleccione la terminal POS.')
   if medio=='Efectivo' and not caja_abierta(c): raise ValueError('Debe abrir Recepción y Caja para cobrar en efectivo.')
   cta_fin,_=_cuenta_financiera(c,medio,cuenta_id);orig=sum(imp*float(r['tipo_cambio_origen'] or 1) for r,imp in aplicaciones);lines=[(cta_fin,pyg,0,total,'Cobro de '+str(len(aplicaciones))+' factura(s)'),('1.1.02',0,orig,total,'Cancela clientes')];dif=pyg-orig
   if abs(dif)>0.01: lines.append(('4.2.01',0,dif,0,'Ganancia cambio') if dif>0 else ('5.2.01',-dif,0,0,'Pérdida cambio'))
   cur=c.execute("insert into cobros_clientes_lotes(fecha,cliente_id,referencia,medio,moneda,tipo_cambio,importe,importe_pyg,cuenta_bancaria_id,terminal_pos_id,creado_por,creado_en) values(?,?,?,?,?,?,?,?,?,?,?,?)",(fecha,cliente_id,request.form.get('referencia',''),medio,mon,tc,total,pyg,cuenta_id,pos_id,session.get('user'),now()));lote=cur.lastrowid;aid=asiento(c,fecha,'Cobro múltiple de cliente','COBRO_CLIENTE_MULTIPLE',lote,mon,tc,lines);c.execute('update cobros_clientes_lotes set asiento_id=? where id=?',(aid,lote))
   for r,imp in aplicaciones:
    ant=float(r['saldo']);rest=max(0,ant-imp);c.execute("update cxc set saldo=?,estado=? where id=?",(rest,'PAGADO' if rest<=0.0001 else 'PENDIENTE',r['id']));c.execute("insert into cobros_clientes_det(lote_id,cxc_id,venta_id,factura,importe_aplicado,saldo_anterior,saldo_restante) values(?,?,?,?,?,?,?)",(lote,r['id'],r['venta_id'],r['factura'],imp,ant,rest))
   c.execute("insert into caja_banco(fecha,tipo,medio,moneda,tipo_cambio,importe,importe_pyg,concepto,origen_tipo,origen_id,cuenta_bancaria_id,terminal_pos_id) values(?,'INGRESO',?,?,?,?,?,'Cobro múltiple de cliente','COBRO_CLIENTE_MULTIPLE',?,?,?)",(fecha,medio,mon,tc,total,pyg,lote,cuenta_id,pos_id))
   if medio=='Efectivo':
    ap=caja_abierta(c);fid=c.execute("select id from formas_cobro where nombre='Efectivo'").fetchone();c.execute("insert into movimientos_caja(apertura_id,fecha,tipo,forma_cobro_id,concepto,importe_pyg,origen_tipo,origen_id,usuario) values(?,?,'INGRESO',?,?,?,?,?,?)",(ap['id'],now(),fid['id'] if fid else None,'Cobro múltiple de cliente',pyg,'COBRO_CLIENTE_MULTIPLE',lote,session.get('user')))
   c.commit();audit('COBRO_CLIENTE_MULTIPLE',f'Lote {lote} / {len(aplicaciones)} facturas / {total} {mon}');flash(f'Cobro registrado y aplicado a {len(aplicaciones)} factura(s).')
  except Exception as ex:c.rollback();flash(str(ex))
  c.close();return redirect('/ventas/cobros-clientes?cliente_id='+request.form.get('cliente_id',''))
 cliente_id=int(request.args.get('cliente_id') or 0);clientes=c.execute("select distinct t.id,t.nombre,t.ruc from cxc x join terceros t on t.id=x.tercero_id where x.saldo>0.0001 order by t.nombre").fetchall();pendientes=[]
 if cliente_id: pendientes=c.execute("select x.*,coalesce(v.numero,'-') factura,v.fecha fecha_venta,t.nombre cliente from cxc x join terceros t on t.id=x.tercero_id left join ventas v on v.id=x.venta_id where x.tercero_id=? and x.saldo>0.0001 order by v.fecha,x.id",(cliente_id,)).fetchall()
 bancos=c.execute('select * from cuentas_bancarias where activo=1 order by banco,alias').fetchall();poses=c.execute('select * from terminales_pos where activo=1 order by nombre').fetchall();hist=c.execute("select l.*,t.nombre cliente,(select count(*) from cobros_clientes_det d where d.lote_id=l.id) documentos from cobros_clientes_lotes l join terceros t on t.id=l.cliente_id order by l.id desc limit 100").fetchall();c.close();return render_template('customer_collections.html',pendientes=pendientes,clientes=clientes,cliente_id=cliente_id,bancos=bancos,poses=poses,cobros=hist)

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
 c=db(); sincronizar_clientes_pacientes(c)
 if request.method=='POST':
  doc=(request.form.get('documento') or '').strip(); nombre=(request.form.get('nombre') or '').strip()
  nat=(request.form.get('sifen_naturaleza') or '1').strip(); tiop=(request.form.get('sifen_tipo_operacion') or ('1' if nat=='1' else '2')).strip()
  vals=(doc,nombre,request.form.get('telefono'),request.form.get('email'),request.form.get('moneda') or 'PYG',nat,tiop,request.form.get('sifen_tipo_contribuyente') or '2',request.form.get('sifen_tipo_documento') or '1',request.form.get('sifen_numero_documento') or doc,request.form.get('sifen_pais') or 'PRY',request.form.get('sifen_pais_desc') or 'Paraguay',request.form.get('direccion'),request.form.get('sifen_numero_casa') or '0',request.form.get('sifen_departamento_codigo'),request.form.get('sifen_departamento_desc'),request.form.get('sifen_distrito_codigo'),request.form.get('sifen_distrito_desc'),request.form.get('sifen_ciudad_codigo'),request.form.get('sifen_ciudad_desc'))
  cur=c.execute("""insert into terceros(tipo,ruc,nombre,telefono,email,moneda,sifen_naturaleza,sifen_tipo_operacion,sifen_tipo_contribuyente,sifen_tipo_documento,sifen_numero_documento,sifen_pais,sifen_pais_desc,sifen_direccion,sifen_numero_casa,sifen_departamento_codigo,sifen_departamento_desc,sifen_distrito_codigo,sifen_distrito_desc,sifen_ciudad_codigo,sifen_ciudad_desc) values('CLIENTE',?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",vals)
  tid=cur.lastrowid
  c.execute('insert into pacientes(documento,nombre,fecha_nacimiento,telefono,direccion,tercero_id) values(?,?,?,?,?,?)',(doc,nombre,request.form.get('fecha_nacimiento'),request.form.get('telefono'),request.form.get('direccion'),tid));c.commit();c.close();flash('Cliente registrado y preparado para facturación electrónica.');return redirect('/clientes')
 rows=c.execute("""select p.*,t.ruc,t.email,t.moneda,t.sifen_naturaleza,t.sifen_tipo_operacion,t.sifen_tipo_contribuyente,t.sifen_tipo_documento,t.sifen_numero_documento,t.sifen_pais,t.sifen_pais_desc,t.sifen_direccion,t.sifen_numero_casa,t.sifen_departamento_codigo,t.sifen_departamento_desc,t.sifen_distrito_codigo,t.sifen_distrito_desc,t.sifen_ciudad_codigo,t.sifen_ciudad_desc from pacientes p left join terceros t on t.id=p.tercero_id order by p.id desc""").fetchall();c.close();return render_template('hospital_patients.html',rows=rows)
@app.route('/config-sanatorio',methods=['GET','POST'])
def config_sanatorio():
 c=db()
 # Migración compatible para instalaciones existentes
 cols=[r['name'] for r in c.execute('pragma table_info(medicos)').fetchall()]
 if 'precio_consulta' not in cols:c.execute('alter table medicos add column precio_consulta REAL DEFAULT 0')
 if 'honorario_consulta' not in cols:c.execute('alter table medicos add column honorario_consulta REAL DEFAULT 0')
 if 'consultorio_numero' not in cols:c.execute('alter table medicos add column consultorio_numero TEXT')
 for col,ddl in [('documento','TEXT'),('ruc','TEXT'),('telefono','TEXT'),('email','TEXT'),('direccion','TEXT'),('activo','INTEGER DEFAULT 1')]:
  if col not in cols:c.execute(f'alter table medicos add column {col} {ddl}')
 c.execute('CREATE TABLE IF NOT EXISTS especialidades(id INTEGER PRIMARY KEY,nombre TEXT UNIQUE,precio_consulta REAL DEFAULT 0,honorario_medico REAL DEFAULT 0,activo INT DEFAULT 1)')
 ecols=[r['name'] for r in c.execute('pragma table_info(especialidades)').fetchall()]
 if 'minutos_consulta' not in ecols:c.execute('alter table especialidades add column minutos_consulta INT DEFAULT 15')
 # V13.9.60: aseguradoras y camas editables, preservando IDs y relaciones históricas
 acols=[r['name'] for r in c.execute('pragma table_info(aseguradoras)').fetchall()]
 for col,ddl in [('nombre_comercial','TEXT'),('telefono','TEXT'),('email','TEXT'),('direccion','TEXT'),('contacto','TEXT'),('datos_facturacion','TEXT'),('convenio','TEXT'),('observaciones','TEXT'),('activo','INTEGER DEFAULT 1')]:
  if col not in acols:c.execute(f'alter table aseguradoras add column {col} {ddl}')
 ccols=[r['name'] for r in c.execute('pragma table_info(camas)').fetchall()]
 for col,ddl in [('tipo','TEXT DEFAULT \'Internación\''),('descripcion','TEXT'),('tarifa_diaria','REAL DEFAULT 0'),('activo','INTEGER DEFAULT 1'),('observaciones','TEXT')]:
  if col not in ccols:c.execute(f'alter table camas add column {col} {ddl}')
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
   c.execute('insert into medicos(nombre,registro,especialidad,precio_consulta,honorario_consulta,consultorio_numero,documento,ruc,telefono,email,direccion,activo) values(?,?,?,?,?,?,?,?,?,?,?,1)',(request.form['nombre'].strip(),request.form.get('registro','').strip(),esp,precio,hon,request.form.get('consultorio_numero','').strip(),request.form.get('documento','').strip(),request.form.get('ruc','').strip(),request.form.get('telefono','').strip(),request.form.get('email','').strip(),request.form.get('direccion','').strip()))
  elif k=='actualizar_medico':
   c.execute('update medicos set nombre=?,registro=?,especialidad=?,precio_consulta=?,honorario_consulta=?,consultorio_numero=?,documento=?,ruc=?,telefono=?,email=?,direccion=?,activo=? where id=?',(request.form['nombre'].strip(),request.form.get('registro','').strip(),request.form['especialidad'],float(request.form.get('precio_consulta') or 0),float(request.form.get('honorario_consulta') or 0),request.form.get('consultorio_numero','').strip(),request.form.get('documento','').strip(),request.form.get('ruc','').strip(),request.form.get('telefono','').strip(),request.form.get('email','').strip(),request.form.get('direccion','').strip(),1 if request.form.get('activo')=='1' else 0,int(request.form['medico_id'])))
   audit('EDITAR_MEDICO',request.form['medico_id'])
  elif k=='aseguradora':
   cur=c.execute("insert into terceros(tipo,ruc,nombre,telefono,moneda) values('CLIENTE',?,?,?,?)",(request.form['ruc'],request.form['nombre'],request.form.get('telefono'),request.form['moneda']))
   aid=c.execute('insert into aseguradoras(nombre,ruc,tercero_id,moneda,nombre_comercial,telefono,email,direccion,contacto,datos_facturacion,convenio,observaciones,activo) values(?,?,?,?,?,?,?,?,?,?,?,?,1)',(request.form['nombre'],request.form['ruc'],cur.lastrowid,request.form['moneda'],request.form.get('nombre_comercial'),request.form.get('telefono'),request.form.get('email'),request.form.get('direccion'),request.form.get('contacto'),request.form.get('datos_facturacion'),request.form.get('convenio'),request.form.get('observaciones'))).lastrowid
   audit_change(c,'CREAR','ASEGURADORAS',aid,{},dict(request.form))
  elif k=='actualizar_aseguradora':
   aid=int(request.form['aseguradora_id']); old=c.execute('select * from aseguradoras where id=?',(aid,)).fetchone()
   if old:
    vals=(request.form['nombre'].strip(),request.form.get('nombre_comercial','').strip(),request.form.get('ruc','').strip(),request.form.get('telefono','').strip(),request.form.get('email','').strip(),request.form.get('direccion','').strip(),request.form.get('contacto','').strip(),request.form.get('datos_facturacion','').strip(),request.form.get('convenio','').strip(),request.form.get('observaciones','').strip(),request.form.get('moneda') or 'PYG',1 if request.form.get('activo')=='1' else 0,aid)
    c.execute('update aseguradoras set nombre=?,nombre_comercial=?,ruc=?,telefono=?,email=?,direccion=?,contacto=?,datos_facturacion=?,convenio=?,observaciones=?,moneda=?,activo=? where id=?',vals)
    if old['tercero_id']:c.execute('update terceros set nombre=?,ruc=?,telefono=?,moneda=? where id=?',(vals[0],vals[2],vals[3],vals[10],old['tercero_id']))
    audit_change(c,'EDITAR','ASEGURADORAS',aid,snapshot(old),{'nombre':vals[0],'ruc':vals[2],'activo':vals[11]})
  elif k=='cama':
   hid=c.execute('select id from habitaciones where nombre=?',(request.form['habitacion'],)).fetchone()
   if not hid:hid=c.execute('insert into habitaciones(nombre,tipo) values(?,?)',(request.form['habitacion'],request.form.get('tipo','Internación'))).lastrowid
   else:hid=hid['id']
   cid=c.execute('insert into camas(habitacion_id,codigo,tipo,descripcion,tarifa_diaria,activo,observaciones) values(?,?,?,?,?,1,?)',(hid,request.form['codigo'],request.form.get('tipo','Internación'),request.form.get('descripcion'),float(request.form.get('tarifa_diaria') or 0),request.form.get('observaciones'))).lastrowid
   audit_change(c,'CREAR','CAMAS',cid,{},dict(request.form))
  elif k=='actualizar_cama':
   cid=int(request.form['cama_id']); old=c.execute('select * from camas where id=?',(cid,)).fetchone()
   if old:
    ocupada=c.execute("select count(*) n from admisiones where cama_id=? and estado='ABIERTA'",(cid,)).fetchone()['n']>0
    if ocupada and request.form.get('activo')!='1':
     flash('No se puede inactivar una cama con una internación/admisión abierta.');c.close();return redirect('/config-sanatorio')
    hab=request.form.get('habitacion','').strip(); hr=c.execute('select id from habitaciones where nombre=?',(hab,)).fetchone()
    if not hr:hid=c.execute('insert into habitaciones(nombre,tipo) values(?,?)',(hab,request.form.get('tipo','Internación'))).lastrowid
    else:hid=hr['id']
    c.execute('update camas set habitacion_id=?,codigo=?,tipo=?,descripcion=?,tarifa_diaria=?,activo=?,observaciones=? where id=?',(hid,request.form['codigo'].strip(),request.form.get('tipo','Internación'),request.form.get('descripcion','').strip(),float(request.form.get('tarifa_diaria') or 0),1 if request.form.get('activo')=='1' else 0,request.form.get('observaciones','').strip(),cid))
    audit_change(c,'EDITAR','CAMAS',cid,snapshot(old),{'habitacion':hab,'codigo':request.form['codigo'],'activo':1 if request.form.get('activo')=='1' else 0})
  c.commit();return redirect('/config-sanatorio')
 data={x:c.execute('select * from '+x+' order by id desc').fetchall() for x in ['servicios','medicos','aseguradoras']};data['especialidades']=c.execute('select * from especialidades order by activo desc,nombre').fetchall();data['camas']=c.execute("select c.*,h.nombre habitacion,exists(select 1 from admisiones a where a.cama_id=c.id and a.estado='ABIERTA') ocupada_actual from camas c join habitaciones h on h.id=c.habitacion_id order by c.id desc").fetchall();mons=c.execute('select * from monedas').fetchall();c.close();return render_template('hospital_config.html',data=data,mons=mons)
@app.route('/admisiones',methods=['GET','POST'])
def hospital_admisiones():
 c=db()
 if request.method=='POST':
  fecha=request.form['fecha'];mon=request.form['moneda'];tc=tc_fecha(c,fecha,mon,request.form.get('tipo_cambio'));cama=int(request.form['cama_id']) if request.form.get('cama_id') else None
  aseg_id=int(request.form['aseguradora_id']) if request.form.get('aseguradora_id') else None
  if aseg_id and not all((request.form.get(k) or '').strip() for k in ('numero_visacion','fecha_visacion','hora_visacion')):
   c.close();flash('Atención por seguro: complete número, fecha y hora de visación.');return redirect('/admisiones')
  if aseg_id and not (request.form.get('medico_visacion_id') or request.form.get('medico_id')):
   c.close();flash('Atención por seguro: seleccione el médico que realiza la atención.');return redirect('/admisiones')
  cur=c.execute('insert into admisiones(fecha,paciente_id,tipo,medico_id,aseguradora_id,moneda,tipo_cambio,cama_id) values(?,?,?,?,?,?,?,?)',(fecha,int(request.form['paciente_id']),request.form['tipo'],request.form.get('medico_id') or None,aseg_id,mon,tc,cama)); aid=cur.lastrowid
  if aseg_id:_registrar_visacion(c,aseg_id,int(request.form['paciente_id']),request.form['tipo'],aid,request.form.get('medico_id') or None)
  if cama:c.execute("update camas set estado='OCUPADA' where id=?",(cama,))
  c.commit();audit('ADMISION',str(cur.lastrowid));return redirect('/admisiones')
 rows=c.execute('select a.*,p.nombre paciente,m.nombre medico,ca.codigo cama from admisiones a join pacientes p on p.id=a.paciente_id left join medicos m on m.id=a.medico_id left join camas ca on ca.id=a.cama_id order by a.id desc').fetchall();pats=c.execute('select * from pacientes').fetchall();med=c.execute('select * from medicos').fetchall();aseg=c.execute('select * from aseguradoras').fetchall();camas=c.execute("select * from camas where estado='LIBRE' and coalesce(activo,1)=1").fetchall();mons=c.execute('select * from monedas').fetchall();c.close();return render_template('hospital_admissions.html',rows=rows,pats=pats,med=med,aseg=aseg,camas=camas,mons=mons)
@app.route('/admisiones/<int:aid>/editar',methods=['GET','POST'])
def editar_admision(aid):
 c=db();a=c.execute('select * from admisiones where id=?',(aid,)).fetchone()
 if not a:
  c.close();flash('Admisión no encontrada.');return redirect('/admisiones')
 if request.method=='POST':
  antes=snapshot(a);fecha=request.form.get('fecha') or a['fecha'];pid=int(request.form.get('paciente_id') or a['paciente_id']);tipo=(request.form.get('tipo') or a['tipo']).strip().upper();mid=int(request.form['medico_id']) if request.form.get('medico_id') else None;aseg=int(request.form['aseguradora_id']) if request.form.get('aseguradora_id') else None;mon=(request.form.get('moneda') or a['moneda'] or 'PYG').upper();tc=tc_fecha(c,fecha,mon,request.form.get('tipo_cambio'));nueva_cama=int(request.form['cama_id']) if request.form.get('cama_id') else None
  if aseg and not all((request.form.get(k) or '').strip() for k in ('numero_visacion','fecha_visacion','hora_visacion')):
   c.close();flash('Atención por seguro: complete número, fecha y hora de visación.');return redirect(request.path)
  if aseg and not (request.form.get('medico_visacion_id') or mid):
   c.close();flash('Atención por seguro: seleccione el médico que realiza la atención.');return redirect(request.path)
  if nueva_cama and nueva_cama!=a['cama_id']:
   oc=c.execute("select 1 from admisiones where cama_id=? and estado='ABIERTA' and id<>? limit 1",(nueva_cama,aid)).fetchone()
   if oc:c.close();flash('La cama seleccionada está ocupada por otra admisión.');return redirect(request.path)
  c.execute('update admisiones set fecha=?,paciente_id=?,tipo=?,medico_id=?,aseguradora_id=?,moneda=?,tipo_cambio=?,cama_id=? where id=?',(fecha,pid,tipo,mid,aseg,mon,tc,nueva_cama,aid))
  if a['cama_id'] and a['cama_id']!=nueva_cama:c.execute("update camas set estado='LIBRE' where id=?",(a['cama_id'],))
  if nueva_cama:c.execute("update camas set estado='OCUPADA' where id=?",(nueva_cama,))
  if aseg:
   v=c.execute("select * from seguro_visaciones where origen_id=? and origen_tipo in ('CONSULTA','URGENCIA','INTERNACION','QUIROFANO') order by id desc limit 1",(aid,)).fetchone()
   if v:
    orig,guard,ft=(v['archivo_nombre'],v['archivo_guardado'],v['archivo_tipo'])
    if request.files.get('archivo_visacion') and request.files['archivo_visacion'].filename:orig,guard,ft=_guardar_archivo_visacion(request.files['archivo_visacion'])
    c.execute('update seguro_visaciones set fecha=?,hora=?,numero_visacion=?,aseguradora_id=?,paciente_id=?,medico_id=?,origen_tipo=?,archivo_nombre=?,archivo_guardado=?,archivo_tipo=?,observacion=? where id=?',(request.form['fecha_visacion'],request.form['hora_visacion'],request.form['numero_visacion'].strip(),aseg,pid,int(request.form.get('medico_visacion_id') or mid),tipo,orig,guard,ft,request.form.get('observacion_visacion'),v['id']))
   else:_registrar_visacion(c,aseg,pid,tipo,aid,mid)
  audit_change(c,'EDITAR','ADMISION',aid,antes,snapshot(c.execute('select * from admisiones where id=?',(aid,)).fetchone()))
  c.commit();c.close();flash('Admisión modificada correctamente.');return redirect('/admisiones')
 pats=c.execute('select * from pacientes order by nombre').fetchall();med=c.execute('select * from medicos order by nombre').fetchall();asegs=c.execute('select * from aseguradoras where coalesce(activo,1)=1 or id=? order by nombre',(a['aseguradora_id'] or -1,)).fetchall();camas=c.execute("select c.* from camas c where coalesce(c.activo,1)=1 and (c.id=? or not exists(select 1 from admisiones x where x.cama_id=c.id and x.estado='ABIERTA' and x.id<>?)) order by c.codigo",(a['cama_id'] or -1,aid)).fetchall();mons=c.execute('select * from monedas').fetchall();v=c.execute("select * from seguro_visaciones where origen_id=? and origen_tipo in ('CONSULTA','URGENCIA','INTERNACION','QUIROFANO') order by id desc limit 1",(aid,)).fetchone();c.close();return render_template('hospital_admission_edit.html',a=a,pats=pats,med=med,aseg=asegs,camas=camas,mons=mons,v=v)

@app.post('/admisiones/<int:aid>/eliminar')
def eliminar_admision(aid):
 c=db();a=c.execute('select * from admisiones where id=?',(aid,)).fetchone()
 if not a:c.close();flash('Admisión no encontrada.');return redirect('/admisiones')
 refs=[('cargos_paciente','admision_id'),('enfermeria','admision_id'),('facturas_sanatorio','admision_id')]
 for tab,col in refs:
  try:n=c.execute(f'select count(*) from {tab} where {col}=?',(aid,)).fetchone()[0]
  except Exception:n=0
  if n:c.close();flash('No se puede eliminar: la admisión tiene movimientos relacionados. Puede anularla si corresponde.');return redirect('/admisiones')
 if a['cama_id']:c.execute("update camas set estado='LIBRE' where id=?",(a['cama_id'],))
 c.execute('delete from admisiones where id=?',(aid,));audit_change(c,'ELIMINAR','ADMISION',aid,snapshot(a),{});c.commit();c.close();flash('Admisión eliminada.');return redirect('/admisiones')

@app.post('/admisiones/<int:aid>/anular')
def anular_admision(aid):
 c=db();a=c.execute('select * from admisiones where id=?',(aid,)).fetchone();motivo=(request.form.get('motivo') or '').strip()
 if not a:c.close();flash('Admisión no encontrada.');return redirect('/admisiones')
 if not motivo:c.close();flash('Debe indicar el motivo de anulación.');return redirect('/admisiones')
 fac=c.execute('select 1 from facturas_sanatorio where admision_id=? limit 1',(aid,)).fetchone()
 if fac:c.close();flash('No se puede anular una admisión ya facturada. Debe realizar la corrección mediante el documento fiscal correspondiente.');return redirect('/admisiones')
 c.execute("update admisiones set estado='ANULADA' where id=?",(aid,))
 if a['cama_id']:c.execute("update camas set estado='LIBRE' where id=?",(a['cama_id'],))
 audit_change(c,'ANULAR','ADMISION',aid,snapshot(a),{'estado':'ANULADA'},motivo);c.commit();c.close();flash('Admisión anulada correctamente.');return redirect('/admisiones')

@app.route('/cuenta-paciente/<int:aid>',methods=['GET','POST'])
def cuenta_paciente(aid):
 c=db();a=c.execute('select a.*,p.nombre paciente,p.tercero_id paciente_tercero,sg.tercero_id seguro_tercero from admisiones a join pacientes p on p.id=a.paciente_id left join aseguradoras sg on sg.id=a.aseguradora_id where a.id=?',(aid,)).fetchone()
 if not a:
  c.close();flash('La cuenta o admisión solicitada no existe. Puede localizar la cuenta desde Caja Central.');return redirect('/ventas/caja-central')
 if request.method=='POST':
  fecha=request.form['fecha'];mon=request.form['moneda'];tc=tc_fecha(c,fecha,mon,request.form.get('tipo_cambio'));tipo=request.form['tipo'];ref=int(request.form['referencia_id']);qty=float(request.form['cantidad'])
  if a['aseguradora_id'] and tipo=='SERVICIO':
   if not all((request.form.get(k) or '').strip() for k in ('numero_visacion','fecha_visacion','hora_visacion')):
    c.close();flash('Servicio por seguro: complete número, fecha y hora de visación.');return redirect(f'/cuenta-paciente/{aid}')
   if not (request.form.get('medico_visacion_id') or a['medico_id']):
    c.close();flash('Servicio por seguro: seleccione el médico que realiza la atención.');return redirect(f'/cuenta-paciente/{aid}')
  if tipo=='PRODUCTO':
   if not user_has('FARMACIA','ENTREGAR'):
    flash('Los productos y medicamentos deben solicitarse desde Enfermería y ser autorizados/entregados por Farmacia Interna.');c.close();return redirect(f'/cuenta-paciente/{aid}')
   x=c.execute('select * from productos where id=?',(ref,)).fetchone()
   if x['stock']<qty:flash('Stock insuficiente');c.close();return redirect(f'/cuenta-paciente/{aid}')
   price=x['precio_pyg']/tc;desc=x['nombre'];c.execute('update productos set stock=stock-? where id=?',(qty,ref));c.execute('insert into stock_mov(fecha,producto_id,tipo,cantidad,costo_pyg,origen_tipo,origen_id) values(?,?,?,?,?,?,?)',(fecha,ref,'SALIDA',-qty,x['costo_pyg'],'PACIENTE',aid))
  else:
   x=c.execute('select * from servicios where id=?',(ref,)).fetchone();price=x['precio_pyg']/tc;desc=x['nombre']
  iva_pct=float(x['iva_pct'] or 0);total=qty*price;cargo_id=c.execute('insert into cargos_paciente(fecha,admision_id,tipo,referencia_id,descripcion,cantidad,precio,moneda,tipo_cambio,total,total_pyg,iva_pct) values(?,?,?,?,?,?,?,?,?,?,?,?)',(fecha,aid,tipo,ref,desc,qty,price,mon,tc,total,total*tc,iva_pct)).lastrowid
  if a['aseguradora_id'] and tipo=='SERVICIO':_registrar_visacion(c,a['aseguradora_id'],a['paciente_id'],'CARGO_SERVICIO',cargo_id,request.form.get('medico_id') or a['medico_id'])
  c.commit();return redirect(f'/cuenta-paciente/{aid}')
 cargos=c.execute('select * from cargos_paciente where admision_id=? order by id',(aid,)).fetchall();prods=c.execute('select * from productos').fetchall();serv=c.execute('select * from servicios').fetchall();mons=c.execute('select * from monedas').fetchall();meds=c.execute('select * from medicos where activo=1 order by nombre').fetchall();visaciones=c.execute("select v.*,m.nombre medico from seguro_visaciones v left join medicos m on m.id=v.medico_id where (v.origen_tipo=? and v.origen_id=?) or (v.origen_tipo='CARGO_SERVICIO' and v.origen_id in (select id from cargos_paciente where admision_id=?)) order by v.id desc",(a['tipo'],aid,aid)).fetchall();total=sum(x['total_pyg'] for x in cargos if not x['facturado']);c.close();return render_template('hospital_account.html',a=a,cargos=cargos,prods=prods,serv=serv,mons=mons,meds=meds,visaciones=visaciones,total=total)
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
 subtotal=subtotal_pyg/tc;iva=iva_pyg/tc;total=totg/tc;ter=a['seguro_tercero'] or a['paciente_tercero'];punto_id_operativo=_punto_id_caja_actual(c,a['tipo']);num,punto_factura=_siguiente_numero_factura(c,punto_id_operativo);cur=c.execute('insert into facturas_sanatorio(fecha,admision_id,tercero_id,numero,moneda,tipo_cambio,subtotal,iva,total,total_pyg,gravado_10,iva_10,gravado_5,iva_5,exento_iva) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(fecha,aid,ter,num,mon,tc,subtotal,iva,total,totg,base10_pyg/tc,iva10_pyg/tc,base5_pyg/tc,iva5_pyg/tc,exento_pyg/tc));fid=cur.lastrowid;c.execute('update cargos_paciente set facturado=1 where admision_id=? and facturado=0',(aid,));c.execute('insert into ventas(fecha,cliente_id,numero,moneda,tipo_cambio,gravado,iva,exento,total,total_pyg,gravado_10,iva_10,gravado_5,iva_5,exento_iva) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(fecha,ter,num,mon,tc,(base10_pyg+base5_pyg)/tc,iva,exento_pyg/tc,total,totg,base10_pyg/tc,iva10_pyg/tc,base5_pyg/tc,iva5_pyg/tc,exento_pyg/tc));vid=c.execute('select last_insert_rowid()').fetchone()[0];ap_fact=caja_abierta(c);c.execute('update ventas set sifen_punto_id=?,establecimiento=?,punto_expedicion=?,caja_id=?,origen_area=? where id=?',(punto_factura['id'],punto_factura['establecimiento'],punto_factura['punto_expedicion'],ap_fact['caja_id'] if ap_fact else None,a['tipo'],vid));c.execute('update facturas_sanatorio set sifen_punto_id=?,establecimiento=?,punto_expedicion=?,caja_id=?,origen_area=? where id=?',(punto_factura['id'],punto_factura['establecimiento'],punto_factura['punto_expedicion'],ap_fact['caja_id'] if ap_fact else None,a['tipo'],fid));c.execute('insert into cxc(venta_id,tercero_id,moneda,tipo_cambio_origen,importe,saldo,importe_pyg) values(?,?,?,?,?,?,?)',(vid,ter,mon,tc,total,total,totg));asiento(c,fecha,'Factura sanatorial '+num,'FACTURA_SANATORIO',fid,mon,tc,[('1.1.02',totg,0,total,'Paciente/Seguro'),('4.1.02',0,subtotal_pyg,subtotal,'Servicios sanatoriales'),('2.1.02',0,iva_pyg,iva,'IVA débito')]);c.commit();audit('FACTURA_SANATORIO',str(fid));return redirect(f'/cuenta-paciente/{aid}')
# ===== V13.9.66: liquidación de cobertura por seguro ítem por ítem =====
def init_v13966_cobertura_seguro():
 c=db()
 c.executescript("""
 CREATE TABLE IF NOT EXISTS seguro_coberturas(
   id INTEGER PRIMARY KEY, admision_id INTEGER NOT NULL, cargo_id INTEGER NOT NULL UNIQUE,
   total_pyg REAL NOT NULL DEFAULT 0, cubierto_seguro_pyg REAL NOT NULL DEFAULT 0,
   diferencia_paciente_pyg REAL NOT NULL DEFAULT 0, categoria TEXT, iva_pct REAL DEFAULT 10,
   venta_paciente_id INTEGER, seguro_pendiente_id INTEGER, creado_por TEXT, creado_en TEXT
 );
 """)
 c.execute("CREATE TABLE IF NOT EXISTS schema_migrations(version TEXT PRIMARY KEY, aplicado_en TEXT)")
 c.execute("INSERT OR IGNORE INTO schema_migrations(version,aplicado_en) VALUES('13.9.66-cobertura-seguro',?)",(now(),))
 c.commit();c.close()
init_v13966_cobertura_seguro()

@app.route('/alta/<int:aid>',methods=['GET','POST'])
def alta(aid):
 c=db();a=c.execute('''select a.*,p.nombre paciente,p.tercero_id paciente_tercero,
 sg.nombre aseguradora,sg.tercero_id seguro_tercero from admisiones a
 join pacientes p on p.id=a.paciente_id left join aseguradoras sg on sg.id=a.aseguradora_id where a.id=?''',(aid,)).fetchone()
 if not a:
  c.close();flash('Admisión no encontrada.');return redirect('/admisiones')
 asegurado=bool(a['aseguradora_id']) and a['tipo'] in ('URGENCIA','INTERNACION','QUIROFANO')
 if request.method=='GET':
  if not asegurado:
   c.close();flash('Esta admisión no corresponde a una cuenta de seguro.');return redirect(f'/cuenta-paciente/{aid}')
  if a['estado']!='ABIERTA':
   c.close();flash('La cuenta ya fue cerrada o procesada.');return redirect(f'/cuenta-paciente/{aid}')
  items=c.execute('select * from cargos_paciente where admision_id=? and coalesce(facturado,0)=0 order by id',(aid,)).fetchall()
  puntos=[p for p in c.execute("select * from sifen_puntos_expedicion order by predeterminado desc,establecimiento,punto_expedicion").fetchall() if _flag_activo(p['activo']) and _flag_activo(p['autorizado_dnit']) and _flag_activo(p['factura_electronica'])]
  c.close();return render_template('insurance_coverage_close.html',a=a,items=items,puntos=puntos)
 if a['estado']!='ABIERTA':
  c.close();flash('La cuenta ya fue cerrada o procesada.');return redirect(f'/cuenta-paciente/{aid}')
 if not asegurado:
  c.execute("update admisiones set estado='ALTA',fecha_cierre=?,cerrado_por=? where id=?",(now(),session.get('user'),aid))
  if a['cama_id']:c.execute("update camas set estado='LIBRE' where id=?",(a['cama_id'],))
  c.commit();c.close();audit('ALTA',str(aid));flash('Alta registrada correctamente.');return redirect('/admisiones')
 try:
  items=c.execute('select * from cargos_paciente where admision_id=? and coalesce(facturado,0)=0 order by id',(aid,)).fetchall()
  if not items:raise ValueError('No hay cargos pendientes para liquidar.')
  fecha=request.form.get('fecha') or datetime.date.today().isoformat();liquid=[];total_seg=0.0;total_pac=0.0
  for r in items:
   total=float(r['total_pyg'] or 0);raw=(request.form.get(f'cubierto_{r["id"]}') or '0').strip().replace('.','').replace(',','.')
   cub=float(raw or 0)
   if cub < -0.0001 or cub-total > 0.01:raise ValueError(f'Cobertura inválida para {r["descripcion"]}: debe estar entre 0 y {total:,.0f} Gs.')
   cub=max(0.0,min(total,cub));dif=round(total-cub,2);cat,iva=clasificar_cargo_seguro(c,r);liquid.append((r,cub,dif,cat,iva));total_seg+=cub;total_pac+=dif
  vid_pac=None;fid_pac=None;numero_pac=None
  if total_pac>0.005:
   numero_pac,punto=_siguiente_numero_factura(c,request.form.get('sifen_punto_id'))
   tot10=sum(dif for r,cub,dif,cat,iva in liquid if iva==10);tot5=sum(dif for r,cub,dif,cat,iva in liquid if iva==5);exento=sum(dif for r,cub,dif,cat,iva in liquid if iva==0)
   b10,i10=desglosar_iva_incluido(tot10,10);b5,i5=desglosar_iva_incluido(tot5,5);subtotal=b10+b5+exento;iva=i10+i5
   v=c.execute('''insert into ventas(fecha,cliente_id,numero,moneda,tipo_cambio,gravado,iva,exento,total,total_pyg,gravado_10,iva_10,gravado_5,iva_5,exento_iva,condicion_venta)
    values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(fecha,a['paciente_tercero'],numero_pac,'PYG',1,b10+b5,iva,exento,total_pac,total_pac,b10,i10,b5,i5,exento,'CREDITO'));vid_pac=v.lastrowid
   c.execute('update ventas set sifen_punto_id=?,establecimiento=?,punto_expedicion=? where id=?',(punto['id'],punto['establecimiento'],punto['punto_expedicion'],vid_pac))
   for r,cub,dif,cat,ivap in liquid:
    if dif<=0.005:continue
    base,_iv=desglosar_iva_incluido(dif,ivap) if ivap else (dif,0)
    c.execute('''insert into venta_items(venta_id,producto_id,cantidad,precio,total,total_pyg,costo_pyg,iva_pct,descripcion) values(?,?,?,?,?,?,?,?,?)''',(vid_pac,None,1,dif,base,dif,0,ivap,(r['descripcion'] or 'Ítem')+' - diferencia no cubierta por seguro'))
   fid_pac=c.execute('''insert into facturas_sanatorio(fecha,admision_id,tercero_id,numero,moneda,tipo_cambio,subtotal,iva,total,total_pyg,gravado_10,iva_10,gravado_5,iva_5,exento_iva) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(fecha,aid,a['paciente_tercero'],numero_pac,'PYG',1,subtotal,iva,total_pac,total_pac,b10,i10,b5,i5,exento)).lastrowid
   c.execute("insert into cxc(venta_id,tercero_id,moneda,tipo_cambio_origen,importe,saldo,importe_pyg,estado) values(?,?,?,?,?,?,?,'PENDIENTE')",(vid_pac,a['paciente_tercero'],'PYG',1,total_pac,total_pac,total_pac))
   asiento(c,fecha,'Diferencia no cubierta por seguro '+numero_pac,'FACTURA_SANATORIO',fid_pac,'PYG',1,[('1.1.02',total_pac,0,total_pac,'Cuenta a cobrar paciente'),('4.1.02',0,subtotal,subtotal,'Prestaciones no cubiertas'),('2.1.02',0,iva,iva,'IVA débito')]);_generar_cdc_test_venta(c,vid_pac,fecha,numero_pac)
  for r,cub,dif,cat,ivap in liquid:
   spid=None
   if cub>0.005:
    c.execute("insert or ignore into seguro_pendientes(fecha,aseguradora_id,paciente_id,origen_tipo,origen_id,categoria,descripcion,importe_pyg,iva_pct,estado) values(?,?,?,?,?,?,?,?,?,'PENDIENTE')",(r['fecha'],a['aseguradora_id'],a['paciente_id'],'CARGO',r['id'],cat,r['descripcion'],cub,ivap))
    sp=c.execute("select id from seguro_pendientes where origen_tipo='CARGO' and origen_id=?",(r['id'],)).fetchone();spid=sp['id'] if sp else None
   c.execute('''insert or replace into seguro_coberturas(admision_id,cargo_id,total_pyg,cubierto_seguro_pyg,diferencia_paciente_pyg,categoria,iva_pct,venta_paciente_id,seguro_pendiente_id,creado_por,creado_en) values(?,?,?,?,?,?,?,?,?,?,?)''',(aid,r['id'],r['total_pyg'],cub,dif,cat,ivap,vid_pac,spid,session.get('user'),now()))
   c.execute('update cargos_paciente set facturado=1 where id=?',(r['id'],))
  c.execute("update admisiones set estado='PENDIENTE_FACTURACION',fecha_cierre=?,cerrado_por=? where id=?",(now(),session.get('user'),aid))
  if a['cama_id']:c.execute("update camas set estado='LIBRE' where id=?",(a['cama_id'],))
  c.commit();c.close();audit('CIERRE_CUENTA_SEGURO_COBERTURA',f'{aid}: seguro={total_seg:.0f}; paciente={total_pac:.0f}; venta_paciente={vid_pac or 0}')
  msg=f'Cuenta cerrada. Seguro: Gs. {total_seg:,.0f}. Diferencia paciente: Gs. {total_pac:,.0f}.'
  if numero_pac:msg+=f' Factura del paciente: {numero_pac}.'
  flash(msg);return redirect('/admisiones')
 except Exception as e:
  c.rollback();c.close();flash('No se pudo cerrar/liquidar la cuenta: '+str(e));return redirect(f'/alta/{aid}')

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
 c=db(); r=c.execute("""select p.*,t.email,t.moneda,t.sifen_naturaleza,t.sifen_tipo_operacion,t.sifen_tipo_contribuyente,t.sifen_tipo_documento,t.sifen_numero_documento,t.sifen_pais,t.sifen_pais_desc,t.sifen_direccion,t.sifen_numero_casa,t.sifen_departamento_codigo,t.sifen_departamento_desc,t.sifen_distrito_codigo,t.sifen_distrito_desc,t.sifen_ciudad_codigo,t.sifen_ciudad_desc from pacientes p left join terceros t on t.id=p.tercero_id where p.id=?""",(i,)).fetchone()
 if not r:c.close();flash('Cliente no encontrado.');return redirect('/clientes')
 if request.method=='POST':
  antes=snapshot(r);doc=(request.form.get('documento') or '').strip();nombre=(request.form.get('nombre') or '').strip();nat=request.form.get('sifen_naturaleza') or '1';tiop=request.form.get('sifen_tipo_operacion') or ('1' if nat=='1' else '2')
  c.execute('update pacientes set documento=?,nombre=?,fecha_nacimiento=?,telefono=?,direccion=? where id=?',(doc,nombre,request.form.get('fecha_nacimiento'),request.form.get('telefono'),request.form.get('direccion'),i))
  c.execute("""update terceros set tipo='CLIENTE',ruc=?,nombre=?,telefono=?,email=?,moneda=?,sifen_naturaleza=?,sifen_tipo_operacion=?,sifen_tipo_contribuyente=?,sifen_tipo_documento=?,sifen_numero_documento=?,sifen_pais=?,sifen_pais_desc=?,sifen_direccion=?,sifen_numero_casa=?,sifen_departamento_codigo=?,sifen_departamento_desc=?,sifen_distrito_codigo=?,sifen_distrito_desc=?,sifen_ciudad_codigo=?,sifen_ciudad_desc=? where id=?""",(doc,nombre,request.form.get('telefono'),request.form.get('email'),request.form.get('moneda') or 'PYG',nat,tiop,request.form.get('sifen_tipo_contribuyente') or '2',request.form.get('sifen_tipo_documento') or '1',request.form.get('sifen_numero_documento') or doc,request.form.get('sifen_pais') or 'PRY',request.form.get('sifen_pais_desc') or 'Paraguay',request.form.get('direccion'),request.form.get('sifen_numero_casa') or '0',request.form.get('sifen_departamento_codigo'),request.form.get('sifen_departamento_desc'),request.form.get('sifen_distrito_codigo'),request.form.get('sifen_distrito_desc'),request.form.get('sifen_ciudad_codigo'),request.form.get('sifen_ciudad_desc'),r['tercero_id']))
  despues=snapshot(c.execute('select * from pacientes where id=?',(i,)).fetchone());audit_change(c,'MODIFICAR','CLIENTES',i,antes,despues,request.form.get('motivo','Actualización'));c.commit();c.close();flash('Cliente actualizado.');return redirect('/clientes')
 c.close();return render_template('edit_patient.html',r=r)

@app.post('/eliminar-paciente/<int:i>')
def eliminar_paciente(i):
 c=db(); r=c.execute('select * from pacientes where id=?',(i,)).fetchone(); n=c.execute('select count(*) from admisiones where paciente_id=?',(i,)).fetchone()[0]
 if n: flash('No se puede eliminar: el paciente tiene admisiones. Edite sus datos en su lugar.'); c.close(); return redirect('/clientes')
 if r: audit_change(c,'ELIMINAR','PACIENTES',i,snapshot(r),{},request.form.get('motivo','Registro erróneo')); c.execute('delete from pacientes where id=?',(i,)); c.execute('delete from terceros where id=?',(r['tercero_id'],)); c.commit()
 c.close(); return redirect('/clientes')

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
   if aseg:_registrar_visacion(c,aseg,pid,'CONSULTA',qid,mid)
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
  fecha=request.form['fecha'];mid=int(request.form['medico_id']);qs=c.execute("select * from consultas where fecha=? and medico_id=? and estado='REALIZADA' and liquidacion_id is null order by hora,id",(fecha,mid)).fetchall()
  if not qs:raise ValueError('No existen consultas o procedimientos pendientes de cierre.')
  totalf=sum(float(x['precio_pyg'] or 0) for x in qs);totalh=sum(float(x['honorario_pyg'] or 0) for x in qs);nc=sum(1 for x in qs if (x['tipo_prestacion'] or 'CONSULTA')=='CONSULTA');np=sum(1 for x in qs if x['tipo_prestacion']=='PROCEDIMIENTO');npart=sum(1 for x in qs if not x['aseguradora_id']);nseg=len(qs)-npart
  lid=c.execute("insert into liquidaciones_medicas(fecha,medico_id,total_consultas,total_facturado_pyg,total_honorario_pyg,estado,cxp_id,creado_en,total_procedimientos,particulares,seguros) values(?,?,?,?,?,'GENERADA',NULL,?,?,?,?)",(fecha,mid,nc,totalf,totalh,now(),np,npart,nseg)).lastrowid
  for q in qs:c.execute('insert into liquidacion_medica_items(liquidacion_id,consulta_id,tipo_prestacion,paciente_id,aseguradora_id,importe_pyg,honorario_pyg,origen_facturacion,facturada) values(?,?,?,?,?,?,?,?,?)',(lid,q['id'],q['tipo_prestacion'] or 'CONSULTA',q['paciente_id'],q['aseguradora_id'],q['precio_pyg'],q['honorario_pyg'],q['origen_facturacion'] or ('SEGURO' if q['aseguradora_id'] else 'PARTICULAR'),q['facturada'] or 0))
  c.execute("update consultas set liquidacion_id=? where fecha=? and medico_id=? and estado='REALIZADA' and liquidacion_id is null",(lid,fecha,mid));c.commit();audit('CIERRE_CONSULTORIO_MEDICO',str(lid));flash('Cierre generado con consultas y procedimientos, particulares y seguros.')
 except Exception as e:c.rollback();flash(str(e))
 finally:c.close()
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
 data=[['Fecha','Paciente','Médico','Especialidad','Precio Gs.','Honorario Gs.','Margen Gs.']]+[[r['fecha'],r['paciente'],r['medico'],r['especialidad'],_money_local(r['precio_pyg'],'PYG'),_money_local(r['honorario_pyg'],'PYG'),_money_local(r['margen_pyg'],'PYG')] for r in rows]; t=Table(data,repeatRows=1); t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.lightgrey),('GRID',(0,0),(-1,-1),.25,colors.grey),('FONTSIZE',(0,0),(-1,-1),8),('VALIGN',(0,0),(-1,-1),'TOP')])); story.append(t); doc.build(story); out.seek(0); return send_file(out,as_attachment=True,download_name=f'consultas_{desde}_{hasta}.pdf',mimetype='application/pdf')

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
 out=BytesIO(); doc=SimpleDocTemplate(out,pagesize=A4); st=getSampleStyleSheet(); story=([pdf_logo()] if pdf_logo() else [])+[Paragraph('Centro Médico Santa Clara - Liquidación Médica',st['Title']),Paragraph(f"Médico: {l['medico']} | Fecha: {l['fecha']}",st['Normal']),Spacer(1,10)]; data=[['Paciente','Especialidad','Precio Gs.','Honorario Gs.']]+[[q['paciente'],q['especialidad'],_money_local(q['precio_pyg'],'PYG'),_money_local(q['honorario_pyg'],'PYG')] for q in qs]+[['','','TOTAL',_money_local(l['total_honorario_pyg'],'PYG')]]; t=Table(data,repeatRows=1); t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.lightgrey),('GRID',(0,0),(-1,-1),.3,colors.grey),('ALIGN',(2,1),(-1,-1),'RIGHT')])); story.append(t); doc.build(story); out.seek(0); return send_file(out,as_attachment=True,download_name=f'liquidacion_medica_{i}.pdf',mimetype='application/pdf')


# ===== V11: arquitectura modular, roles y farmacia interna =====
MODULES = {
 'PACIENTES':'Pacientes','CONSULTORIO':'Consultorio','URGENCIAS':'Urgencias','ADMISION':'Admisión / Internación',
 'QUIROFANO':'Quirófano','ENFERMERIA':'Enfermería','FARMACIA':'Farmacia interna','FACTURACION':'Facturación',
 'STOCK':'Productos y Stock','COMPRAS':'Compras','VENTAS':'Ventas','FINANZAS':'CxC/CxP/Caja/Bancos',
 'CONTABILIDAD':'Contabilidad','INFORMES':'Informes','LABORATORIO':'Laboratorio','CONFIG_SANATORIO':'Configuración Sanatorial','USUARIOS':'Usuarios y Roles'
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
 # V13.9.74: el usuario técnico principal 'admin' es SUPERADMIN.
 # Si está activo, tiene acceso total a todas las rutas, módulos y acciones,
 # incluso módulos nuevos que todavía no tengan una fila en permisos_rol.
 c=db()
 u=c.execute('select id,usuario,activo from usuarios where usuario=? limit 1',(session['user'],)).fetchone()
 if u and u['activo'] and str(u['usuario']).strip().lower()=='admin':
  c.close();return True
 r=c.execute('''select 1 from usuarios u join usuario_roles ur on ur.usuario_id=u.id join permisos_rol p on p.rol_id=ur.rol_id
 where u.usuario=? and u.activo=1 and p.modulo=? and p.accion=? and p.permitido=1 limit 1''',(session['user'],modulo,accion)).fetchone();c.close();return bool(r)

@app.context_processor
def inject_permissions(): return dict(has_perm=user_has,modulos_sistema=MODULES)

ROUTE_MODULE={
 'pacientes':'PACIENTES','hospital_admisiones':'ADMISION','cuenta_paciente':'ADMISION','facturar_admision':'FACTURACION','alta':'ADMISION','hospital_enfermeria':'ENFERMERIA',
 'consultas':'CONSULTORIO','liquidaciones_medicas':'FINANZAS','informes_consultas':'INFORMES','config_sanatorio':'CONFIG_SANATORIO',
 'productos':'STOCK','compras':'COMPRAS','ventas':'VENTAS','finanzas':'FINANZAS','contabilidad':'CONTABILIDAD','libros':'CONTABILIDAD'
}
ROUTE_MODULE.update({'cuentas_pendientes_proveedores':'COMPRAS','pagos_proveedores':'COMPRAS'})
ROUTE_MODULE.update({'editar_admision':'ADMISION','eliminar_admision':'ADMISION','anular_admision':'ADMISION'})
@app.before_request
def modular_guard():
 # Rutas públicas / autenticación.
 publicos={None,'login','logout','static','branding_logo','agenda_web_publica','agenda_web_reservar','agenda_web_confirmacion','llamador_api_pendientes','llamador_api_confirmar','llamador_api_ping'}
 if request.endpoint in publicos:return
 if not session.get('user'):return redirect('/login')
 if request.endpoint=='cambiar_mi_clave':return
 if request.endpoint in ('api_buscar_pacientes','api_buscar_proveedores'):return
 # La búsqueda de productos es una operación auxiliar necesaria tanto para Ventas como Compras.
 # El control de acceso se hace aquí para no exigir permiso STOCK a cajeros/compradores.
 if request.endpoint=='api_productos_buscar':
  # Endpoint auxiliar: cualquier usuario autenticado puede consultar el catálogo.
  # La autorización de crear ventas/compras sigue controlada por la ruta principal.
  return

 # Administración de usuarios/roles: permiso explícito y exclusivo.
 if request.endpoint and request.endpoint.startswith('admin_'):
  if not user_has('USUARIOS','ADMINISTRAR'):return ('Acceso no autorizado',403)
  return

 # Permiso exacto por operación. Nunca basta VER para crear/editar/anular.
 reglas={
  'tipos_cambio':('FINANZAS','EDITAR' if request.method=='POST' else 'VER'),
  'cotizaciones_dnit':('FINANZAS','EDITAR' if request.method=='POST' else 'VER'),'movimientos_financieros_manuales':('FINANZAS','CREAR' if request.method=='POST' else 'VER'),'diferencia_cambio':('CONTABILIDAD','CREAR' if request.method=='POST' else 'VER'),
  'terceros':('COMPRAS','VER'),'proveedores':('COMPRAS','CREAR' if request.method=='POST' else 'VER'),'clientes':('PACIENTES','CREAR' if request.method=='POST' else 'VER'),
  'tercero_editar':('FINANZAS','EDITAR'),'tercero_eliminar':('FINANZAS','ANULAR'),
  'productos':('STOCK','CREAR' if request.method=='POST' else 'VER'),
  'producto_editar':('STOCK','EDITAR'),'producto_eliminar':('STOCK','ANULAR'),
  'compras':('COMPRAS','CREAR' if request.method=='POST' else 'VER'),
  'cuentas_pendientes_proveedores':('COMPRAS','VER'),'pagos_proveedores':('COMPRAS','CREAR' if request.method=='POST' else 'VER'),
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
  'paciente_eliminar':('PACIENTES','ANULAR'),'api_paciente_nuevo':('PACIENTES','CREAR'),'api_buscar_pacientes':('PACIENTES','VER'),'api_buscar_proveedores':('COMPRAS','VER'),
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
  'agendamiento_inicio':('AGENDA','VER'),'agenda_turnos':('AGENDA','VER'),'agenda_pendientes_facturacion':('FACTURACION','VER'),'agenda_facturar':('FACTURACION','FACTURAR'),'agenda_facturar_seleccion':('FACTURACION','FACTURAR'),'agenda_preparar_venta':('FACTURACION','FACTURAR'),'agenda_generar_ventas':('FACTURACION','FACTURAR'),'consultorio_prestaciones':('CONSULTORIO','CREAR' if request.method=='POST' else 'VER'),'cierre_consultorio':('CONSULTORIO','VER'),
  'laboratorio':('LABORATORIO','CREAR' if request.method=='POST' else 'VER'),
  'laboratorio_facturar_particular':('LABORATORIO','FACTURAR'),
  'laboratorio_pendientes_seguro':('LABORATORIO','VER'),
  'laboratorio_ventas_contado':('LABORATORIO','VER'),
  'laboratorio_liquidaciones':('LABORATORIO','EDITAR' if request.method=='POST' else 'VER'),
  'laboratorio_liquidacion_detalle':('LABORATORIO','VER'),'laboratorio_liquidacion_pdf':('LABORATORIO','VER'),
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

@app.route('/mi-cuenta/cambiar-clave',methods=['GET','POST'])
def cambiar_mi_clave():
 if request.method=='POST':
  actual=request.form.get('clave_actual','');nueva=request.form.get('clave_nueva','');confirmar=request.form.get('confirmar_clave','')
  if len(nueva)<6:
   flash('La nueva contraseña debe tener al menos 6 caracteres.');return redirect('/mi-cuenta/cambiar-clave')
  if nueva!=confirmar:
   flash('La confirmación de la nueva contraseña no coincide.');return redirect('/mi-cuenta/cambiar-clave')
  c=db();u=c.execute('select * from usuarios where usuario=? and activo=1',(session['user'],)).fetchone()
  if not u or not password_ok(u['clave'],actual):
   c.close();flash('La contraseña actual es incorrecta.');return redirect('/mi-cuenta/cambiar-clave')
  if password_ok(u['clave'],nueva):
   c.close();flash('La nueva contraseña debe ser diferente de la contraseña actual.');return redirect('/mi-cuenta/cambiar-clave')
  c.execute('update usuarios set clave=? where id=?',(password_hash(nueva),u['id']))
  audit_change(c,'CAMBIAR_CLAVE','USUARIO',u['id'],antes={'usuario':u['usuario']},despues={'usuario':u['usuario'],'clave':'ACTUALIZADA'})
  c.commit();c.close()
  flash('Contraseña actualizada correctamente.')
  return redirect('/mi-cuenta/cambiar-clave')
 return render_template('change_password.html')

@app.route('/admin/usuarios-roles',methods=['GET','POST'])
def admin_usuarios_roles():
 c=db()
 if request.method=='POST':
  kind=request.form['kind']
  if kind=='usuario':
   uid=c.execute('insert into usuarios(nombre,usuario,clave,rol,activo,tipo_usuario,persona_tipo,persona_id) values(?,?,?,?,?,?,?,?)',(
    request.form['nombre'],request.form['usuario'],password_hash(request.form['clave']),'MODULAR',1,request.form.get('tipo_usuario','EMPLEADO'),request.form.get('persona_tipo') or None,int(request.form['persona_id']) if request.form.get('persona_id') else None)).lastrowid
   for rid in request.form.getlist('rol_ids'):
    if rid:c.execute('insert or ignore into usuario_roles(usuario_id,rol_id) values(?,?)',(uid,int(rid)))
  elif kind=='rol':c.execute('insert into roles(nombre,descripcion,activo) values(?,?,1)',(request.form['nombre'].upper(),request.form.get('descripcion','')))
  elif kind=='permisos':
   rid=int(request.form['rol_id']);c.execute('delete from permisos_rol where rol_id=?',(rid,))
   for key in request.form.getlist('perm'):
    mod,act=key.split('|',1);c.execute('insert into permisos_rol(rol_id,modulo,accion,permitido) values(?,?,?,1)',(rid,mod,act))
  elif kind=='asignar':
   uid=int(request.form['usuario_id']);c.execute('delete from usuario_roles where usuario_id=?',(uid,))
   for rid in request.form.getlist('rol_ids'):
    if rid:c.execute('insert or ignore into usuario_roles(usuario_id,rol_id) values(?,?)',(uid,int(rid)))
  elif kind=='cajas':
   uid=int(request.form['usuario_id']);c.execute('delete from usuario_cajas where usuario_id=?',(uid,))
   for cid in request.form.getlist('caja_ids'):
    if cid:c.execute('insert or ignore into usuario_cajas(usuario_id,caja_id,activo) values(?,?,1)',(uid,int(cid)))
  c.commit();audit_change(c,'CONFIGURAR','SEGURIDAD',0,despues={'tipo':kind});c.commit();c.close();return redirect('/admin/usuarios-roles')
 users=c.execute('select * from usuarios order by nombre').fetchall();roles=c.execute('select * from roles where activo=1 order by nombre').fetchall()
 selected_role=int(request.args.get('rol_id') or (roles[0]['id'] if roles else 0))
 perms=c.execute('select * from permisos_rol where rol_id=?',(selected_role,)).fetchall() if selected_role else []
 urs=c.execute('select * from usuario_roles').fetchall();ucs=c.execute('select * from usuario_cajas where activo=1').fetchall();cajas_usuario=c.execute('select * from cajas where activo=1 order by nombre').fetchall();medicos=c.execute('select id,nombre from medicos order by nombre').fetchall()
 empleados=[]
 try: empleados=c.execute('select id,nombre from empleados order by nombre').fetchall()
 except sqlite3.OperationalError: pass
 c.close()
 checked={(x['modulo'],x['accion']) for x in perms}
 user_roles={}
 for x in urs: user_roles.setdefault(x['usuario_id'],set()).add(x['rol_id'])
 user_cajas={}
 for x in ucs:user_cajas.setdefault(x['usuario_id'],set()).add(x['caja_id'])
 return render_template('admin_roles.html',users=users,roles=roles,selected_role=selected_role,checked=checked,user_roles=user_roles,user_cajas=user_cajas,cajas_usuario=cajas_usuario,medicos=medicos,empleados=empleados,modules=MODULES,actions=ACTIONS)

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



@app.get('/api/buscar-pacientes')
def api_buscar_pacientes():
 if not (user_has('AGENDA','VER') or user_has('PACIENTES','VER') or user_has('ADMISION','VER') or user_has('LABORATORIO','VER') or user_has('CONSULTORIO','VER')):return jsonify(ok=False,error='Sin permiso'),403
 q=(request.args.get('q') or '').strip();c=db();sincronizar_clientes_pacientes(c)
 if len(q)<1:rows=[]
 else:
  like='%'+q+'%'
  rows=c.execute("""select id,nombre,documento,telefono from pacientes
                    where nombre like ? collate nocase or documento like ?
                    order by case when documento=? then 0 when nombre like ? collate nocase then 1 else 2 end,nombre limit 20""",(like,like,q,q+'%')).fetchall()
 out=[{'id':x['id'],'nombre':x['nombre'],'documento':x['documento'] or '','telefono':x['telefono'] or ''} for x in rows];c.close()
 return jsonify(ok=True,items=out)

@app.get('/api/buscar-proveedores')
def api_buscar_proveedores():
 if not (user_has('COMPRAS','VER') or user_has('FINANZAS','VER')):return jsonify(ok=False,error='Sin permiso'),403
 q=(request.args.get('q') or '').strip();c=db()
 if len(q)<1:rows=[]
 else:
  like='%'+q+'%'
  rows=c.execute("""select id,nombre,ruc,telefono from terceros where upper(coalesce(tipo,''))='PROVEEDOR'
                    and (nombre like ? collate nocase or ruc like ?)
                    order by case when ruc=? then 0 when nombre like ? collate nocase then 1 else 2 end,nombre limit 20""",(like,like,q,q+'%')).fetchall()
 out=[{'id':x['id'],'nombre':x['nombre'],'ruc':x['ruc'] or '','telefono':x['telefono'] or ''} for x in rows];c.close()
 return jsonify(ok=True,items=out)

@app.get('/agendamiento')
def agendamiento_inicio():
 return redirect('/agendamiento/turnos?'+request.query_string.decode())

@app.route('/agendamiento/nueva',methods=['GET','POST'])
def agendamiento_v12():
 c=db()
 if request.method=='POST':
  try:
   pid=int(request.form['paciente_id']);mid=int(request.form['medico_id']);fecha=request.form['fecha'];hora=request.form['hora']
   m=c.execute('select * from medicos where id=?',(mid,)).fetchone()
   if not m:raise ValueError('Médico no encontrado.')
   e=c.execute('select * from especialidades where nombre=?',(m['especialidad'],)).fetchone();eid=e['id'] if e else None
   precio=float((m['precio_consulta'] if m['precio_consulta'] else (e['precio_consulta'] if e else 0)) or 0)
   aseg=int(request.form['aseguradora_id']) if request.form.get('aseguradora_id') else None
   origen='SEGURO' if aseg else 'PARTICULAR'
   gid=c.execute("insert into agenda(fecha,hora,paciente_id,medico_id,especialidad_id,aseguradora_id,motivo,precio_pyg,cobrado,creado_por,creado_en,facturada,condicion_venta) values(?,?,?,?,?,?,?,?,0,?,?,0,?)",(fecha,hora,pid,mid,eid,aseg,request.form.get('motivo'),precio,session['user'],now(),origen)).lastrowid
   c.commit();audit('AGENDAMIENTO_REGISTRADO',f'Agenda {gid} / {origen}');flash('Turno registrado. Queda pendiente de facturación.')
   return redirect('/agendamiento?imprimir='+str(gid))
  except Exception as ex:
   c.rollback();flash('No se pudo registrar el turno: '+str(ex))
  finally:c.close()
  return redirect('/agendamiento')
 sincronizar_clientes_pacientes(c)
 pats=c.execute('select * from pacientes order by nombre').fetchall();meds=c.execute('select * from medicos order by nombre').fetchall();asegs=c.execute('select * from aseguradoras order by nombre').fetchall();formas=c.execute('select * from formas_cobro where activo=1 order by id').fetchall();cuentas=c.execute('select * from cuentas_bancarias where activo=1 order by banco,alias').fetchall();poses=c.execute('select * from terminales_pos where activo=1 order by nombre').fetchall();rows=c.execute('''select g.*,p.nombre paciente,p.documento,p.telefono,p.fecha_nacimiento,p.direccion,m.nombre medico,e.nombre especialidad,a.nombre aseguradora from agenda g join pacientes p on p.id=g.paciente_id join medicos m on m.id=g.medico_id left join especialidades e on e.id=g.especialidad_id left join aseguradoras a on a.id=g.aseguradora_id order by g.fecha desc,g.hora desc limit 300''').fetchall();c.close();return render_template('agenda_v12.html',pats=pats,meds=meds,asegs=asegs,formas=formas,cuentas=cuentas,poses=poses,rows=rows,pref_fecha=request.args.get('fecha',''),pref_hora=request.args.get('hora',''),pref_medico=request.args.get('medico_id',type=int))



def init_v1398_flujo_consultorio():
 c=db()
 q={r['name'] for r in c.execute('pragma table_info(consultas)').fetchall()}
 for col,typ in [('agenda_id','INT'),('tipo_prestacion',"TEXT DEFAULT 'CONSULTA'"),('servicio_id','INT'),('origen_facturacion','TEXT'),('facturada','INT DEFAULT 0'),('venta_id','INT')]:
  if col not in q:c.execute('alter table consultas add column '+col+' '+typ)
 l={r['name'] for r in c.execute('pragma table_info(liquidaciones_medicas)').fetchall()}
 for col,typ in [('total_procedimientos','INT DEFAULT 0'),('particulares','INT DEFAULT 0'),('seguros','INT DEFAULT 0')]:
  if col not in l:c.execute('alter table liquidaciones_medicas add column '+col+' '+typ)
 c.execute('create table if not exists liquidacion_medica_items(id integer primary key,liquidacion_id int,consulta_id int unique,tipo_prestacion text,paciente_id int,aseguradora_id int,importe_pyg real,honorario_pyg real,origen_facturacion text,facturada int default 0)')
 c.commit();c.close()
init_v1398_flujo_consultorio()

def init_v13933_caja_consultorio():
 c=db()
 try:
  c.execute("CREATE TABLE IF NOT EXISTS caja_pendientes_consultorio(id INTEGER PRIMARY KEY,consulta_id INTEGER UNIQUE,agenda_id INTEGER,paciente_id INTEGER NOT NULL,fecha TEXT NOT NULL,descripcion TEXT,importe_pyg REAL NOT NULL DEFAULT 0,estado TEXT NOT NULL DEFAULT 'PENDIENTE',venta_id INTEGER,creado_en TEXT,procesado_en TEXT)")
  c.execute("insert or ignore into schema_migrations(version,aplicado_en) values('13.9.33-consultorio-a-caja',?)",(now(),));c.commit()
 finally:c.close()
init_v13933_caja_consultorio()

@app.route('/agenda/pendientes-facturacion')
def agenda_pendientes_facturacion():
 c=db();rows=c.execute("""select g.*,p.nombre paciente,p.documento,m.nombre medico,e.nombre especialidad,a.nombre aseguradora
 from agenda g join pacientes p on p.id=g.paciente_id join medicos m on m.id=g.medico_id
 left join especialidades e on e.id=g.especialidad_id left join aseguradoras a on a.id=g.aseguradora_id
 where coalesce(g.facturada,0)=0 and coalesce(g.estado,'AGENDADO')<>'CANCELADO' order by g.fecha,g.hora""").fetchall()
 c.close();return render_template('agenda_pending_billing.html',rows=rows)

@app.post('/agenda/<int:gid>/facturar')
def agenda_facturar(gid):
 c=db()
 try:
  g=c.execute("""select g.*,p.tercero_id,m.nombre medico,e.nombre especialidad from agenda g join pacientes p on p.id=g.paciente_id join medicos m on m.id=g.medico_id left join especialidades e on e.id=g.especialidad_id where g.id=?""",(gid,)).fetchone()
  if not g:raise ValueError('Turno no encontrado.')
  if g['facturada']:raise ValueError('El turno ya fue procesado para facturación.')
  med=c.execute('select * from medicos where id=?',(g['medico_id'],)).fetchone();hon=float((med['honorario_consulta'] if med else 0) or 0);precio=float(g['precio_pyg'] or 0)
  qid=c.execute("""insert into consultas(fecha,hora,paciente_id,medico_id,especialidad_id,aseguradora_id,moneda,tipo_cambio,precio,honorario_medico,precio_pyg,honorario_pyg,observacion,estado,agenda_id,tipo_prestacion,origen_facturacion,facturada)
  values(?,?,?,?,?,?,'PYG',1,?,?,?,?,?,'REALIZADA',?,'CONSULTA',?,0)""",(g['fecha'],g['hora'],g['paciente_id'],g['medico_id'],g['especialidad_id'],g['aseguradora_id'],precio,hon,precio,hon,g['motivo'],gid,'SEGURO' if g['aseguradora_id'] else 'PARTICULAR')).lastrowid
  c.execute('update agenda set consulta_id=? where id=?',(qid,gid))
  if g['aseguradora_id']:
   c.execute("""insert or ignore into seguro_pendientes(fecha,aseguradora_id,paciente_id,origen_tipo,origen_id,categoria,descripcion,importe_pyg,iva_pct,estado)
   values(?,?,?,?,?,?,?,?,?,'PENDIENTE')""",(g['fecha'],g['aseguradora_id'],g['paciente_id'],'CONSULTA',qid,'SERVICIOS SANATORIALES','Consulta - '+(g['especialidad'] or 'Consulta médica'),precio,10))
   c.execute("update agenda set facturada=1,condicion_venta='SEGURO' where id=?",(gid,));flash('Consulta enviada a pendientes de facturación del seguro.')
  else:
   desc='Consulta - '+(g['especialidad'] or 'Consulta médica')
   c.execute("insert or ignore into caja_pendientes_consultorio(consulta_id,agenda_id,paciente_id,fecha,descripcion,importe_pyg,estado,creado_en) values(?,?,?,?,?,?,'PENDIENTE',?)",(qid,gid,g['paciente_id'],g['fecha'],desc,precio,now()))
   c.execute("update agenda set facturada=1,condicion_venta='PENDIENTE_CAJA' where id=?",(gid,));flash('Prestación registrada y enviada a Caja Central para facturación y cobro.')
  c.commit();audit('CONSULTA_REALIZADA_PENDIENTE_FACTURACION',str(gid))
 except Exception as ex:c.rollback();flash(str(ex))
 finally:c.close()
 return redirect('/agenda/pendientes-facturacion')

@app.route('/consultorio/prestaciones',methods=['GET','POST'])
def consultorio_prestaciones():
 c=db()
 if request.method=='POST':
  try:
   sid=int(request.form['servicio_id']);s=c.execute('select * from servicios where id=?',(sid,)).fetchone()
   if not s:raise ValueError('Servicio no encontrado.')
   mid=int(request.form['medico_id']);med=c.execute('select * from medicos where id=?',(mid,)).fetchone();esp=c.execute('select id from especialidades where nombre=?',(med['especialidad'],)).fetchone() if med else None
   aseg=int(request.form['aseguradora_id']) if request.form.get('aseguradora_id') else None;precio=float(request.form.get('precio') or s['precio_pyg'] or 0);hon=float(request.form.get('honorario_medico') or 0)
   qid=c.execute("""insert into consultas(fecha,hora,paciente_id,medico_id,especialidad_id,aseguradora_id,moneda,tipo_cambio,precio,honorario_medico,precio_pyg,honorario_pyg,observacion,estado,tipo_prestacion,servicio_id,origen_facturacion,facturada)
   values(?,?,?,?,?,?,'PYG',1,?,?,?,?,?,'REALIZADA','PROCEDIMIENTO',?,?,0)""",(request.form['fecha'],request.form.get('hora'),int(request.form['paciente_id']),mid,esp['id'] if esp else None,aseg,precio,hon,precio,hon,request.form.get('observacion'),sid,'SEGURO' if aseg else 'PARTICULAR')).lastrowid
   if aseg:_registrar_visacion(c,aseg,int(request.form['paciente_id']),'PROCEDIMIENTO',qid,mid)
   c.commit();audit('PROCEDIMIENTO_CONSULTORIO',str(qid));flash('Procedimiento registrado para el cierre del consultorio.')
  except Exception as ex:c.rollback();flash(str(ex))
  finally:c.close()
  return redirect('/consultorio/prestaciones')
 pats=c.execute('select * from pacientes order by nombre').fetchall();meds=c.execute('select * from medicos order by nombre').fetchall();servs=c.execute('select * from servicios order by nombre').fetchall();asegs=c.execute('select * from aseguradoras order by nombre').fetchall()
 rows=c.execute("""select q.*,p.nombre paciente,m.nombre medico,s.nombre servicio,a.nombre aseguradora from consultas q join pacientes p on p.id=q.paciente_id join medicos m on m.id=q.medico_id left join servicios s on s.id=q.servicio_id left join aseguradoras a on a.id=q.aseguradora_id where q.tipo_prestacion='PROCEDIMIENTO' order by q.fecha desc,q.id desc limit 200""").fetchall();c.close()
 return render_template('office_procedures.html',pats=pats,meds=meds,servs=servs,asegs=asegs,rows=rows)

@app.route('/consultorio/cierre')
def cierre_consultorio():
 c=db();fecha=request.args.get('fecha') or datetime.date.today().isoformat();mid=request.args.get('medico_id',type=int);meds=c.execute('select * from medicos order by nombre').fetchall();rows=[];res=None
 if mid:
  rows=c.execute("""select q.*,p.nombre paciente,s.nombre servicio,a.nombre aseguradora from consultas q join pacientes p on p.id=q.paciente_id left join servicios s on s.id=q.servicio_id left join aseguradoras a on a.id=q.aseguradora_id where q.fecha=? and q.medico_id=? and q.estado='REALIZADA' and q.liquidacion_id is null order by q.hora,q.id""",(fecha,mid)).fetchall()
  res={'cantidad':len(rows),'consultas':sum(1 for x in rows if (x['tipo_prestacion'] or 'CONSULTA')=='CONSULTA'),'procedimientos':sum(1 for x in rows if x['tipo_prestacion']=='PROCEDIMIENTO'),'particulares':sum(1 for x in rows if not x['aseguradora_id']),'seguros':sum(1 for x in rows if x['aseguradora_id']),'facturado':sum(float(x['precio_pyg'] or 0) for x in rows),'honorarios':sum(float(x['honorario_pyg'] or 0) for x in rows)}
 c.close();return render_template('office_closure.html',fecha=fecha,meds=meds,mid=mid,rows=rows,res=res)



# ===== V13.9.9: Laboratorio LACED =====
def init_v1399_laboratorio():
 c=db()
 # Migración puntual: el módulo es nuevo. Solo ADMINISTRADOR recibe acceso inicial completo.
 # No se reponen ni modifican permisos de los demás roles.
 admin=c.execute("select id from roles where nombre='ADMINISTRADOR'").fetchone()
 if admin:
  for act in ACTIONS:
   c.execute("insert or ignore into permisos_rol(rol_id,modulo,accion,permitido) values(?,?,?,1)",(admin['id'],'LABORATORIO',act))
 c.executescript("""
 CREATE TABLE IF NOT EXISTS laboratorio_prestaciones(
  id INTEGER PRIMARY KEY,fecha TEXT NOT NULL,paciente_id INTEGER,aseguradora_id INTEGER,
  tipo TEXT NOT NULL DEFAULT 'ANALISIS',descripcion TEXT NOT NULL,importe_pyg REAL NOT NULL DEFAULT 0,
  origen TEXT NOT NULL DEFAULT 'PARTICULAR',estado_facturacion TEXT NOT NULL DEFAULT 'PENDIENTE',
  venta_id INTEGER,seguro_pendiente_id INTEGER,creado_por TEXT,creado_en TEXT,
  liquidacion_id INTEGER,estudio_admisional INTEGER DEFAULT 0);
 CREATE TABLE IF NOT EXISTS laboratorio_liquidaciones(
  id INTEGER PRIMARY KEY,fecha_desde TEXT,fecha_hasta TEXT,total_bruto_pyg REAL DEFAULT 0,
  total_laced_pyg REAL DEFAULT 0,total_santa_clara_pyg REAL DEFAULT 0,
  total_normal_pyg REAL DEFAULT 0,total_admisional_pyg REAL DEFAULT 0,
  estado TEXT DEFAULT 'GENERADA',creado_por TEXT,creado_en TEXT);
 CREATE TABLE IF NOT EXISTS laboratorio_liquidacion_items(
  id INTEGER PRIMARY KEY,liquidacion_id INTEGER NOT NULL,prestacion_id INTEGER NOT NULL UNIQUE,
  importe_pyg REAL DEFAULT 0,porcentaje_laced REAL DEFAULT 0,importe_laced_pyg REAL DEFAULT 0,
  porcentaje_santa_clara REAL DEFAULT 0,importe_santa_clara_pyg REAL DEFAULT 0);
 """)
 c.commit();c.close()
init_v1399_laboratorio()
ROUTE_MODULE.update({'laboratorio':'LABORATORIO','laboratorio_facturar_particular':'LABORATORIO','laboratorio_pendientes_seguro':'LABORATORIO','laboratorio_ventas_contado':'LABORATORIO','laboratorio_liquidaciones':'LABORATORIO','laboratorio_liquidacion_detalle':'LABORATORIO','laboratorio_liquidacion_pdf':'LABORATORIO'})

@app.route('/laboratorio',methods=['GET','POST'])
def laboratorio():
 c=db()
 if request.method=='POST':
  try:
   fecha=request.form['fecha'];pid=int(request.form['paciente_id']);desc=(request.form.get('descripcion') or '').strip()
   if not desc:raise ValueError('Ingrese el análisis o estudio realizado.')
   importe=float(request.form.get('importe_pyg') or 0)
   if importe<0:raise ValueError('Importe inválido.')
   aseg=int(request.form['aseguradora_id']) if request.form.get('aseguradora_id') else None
   adm=1 if request.form.get('estudio_admisional')=='1' else 0
   origen='SEGURO' if aseg else 'PARTICULAR'
   estado='PENDIENTE_SEGURO' if aseg else 'PENDIENTE_PARTICULAR'
   lid=c.execute("""insert into laboratorio_prestaciones(fecha,paciente_id,aseguradora_id,tipo,descripcion,importe_pyg,origen,estado_facturacion,creado_por,creado_en,estudio_admisional)
                    values(?,?,?,'ANALISIS',?,?,?,?,?,?,?)""",(fecha,pid,aseg,desc,importe,origen,estado,session.get('user'),now(),adm)).lastrowid
   if aseg:
    _registrar_visacion(c,aseg,pid,'LABORATORIO',lid,request.form.get('medico_id') or None)
    spid=c.execute("""insert into seguro_pendientes(fecha,aseguradora_id,paciente_id,origen_tipo,origen_id,categoria,descripcion,importe_pyg,iva_pct,estado)
                      values(?,?,?,?,?,'SERVICIOS SANATORIALES',?,?,10,'PENDIENTE')""",(fecha,aseg,pid,'LABORATORIO',lid,'Laboratorio - '+desc,importe)).lastrowid
    c.execute('update laboratorio_prestaciones set seguro_pendiente_id=? where id=?',(spid,lid))
   c.commit();audit('LABORATORIO_REGISTRO',f'{lid}/{origen}');flash('Análisis de laboratorio registrado.')
  except Exception as ex:c.rollback();flash('No se pudo registrar: '+str(ex))
  c.close();return redirect('/laboratorio')
 pats=c.execute('select * from pacientes order by nombre').fetchall();asegs=c.execute('select * from aseguradoras order by nombre').fetchall();meds=c.execute('select * from medicos where activo=1 order by nombre').fetchall()
 rows=c.execute("""select l.*,p.nombre paciente,a.nombre aseguradora from laboratorio_prestaciones l
 left join pacientes p on p.id=l.paciente_id left join aseguradoras a on a.id=l.aseguradora_id
 order by l.fecha desc,l.id desc limit 300""").fetchall()
 c.close();return render_template('laboratory.html',pats=pats,asegs=asegs,meds=meds,rows=rows)

@app.post('/laboratorio/<int:lid>/facturar-particular')
def laboratorio_facturar_particular(lid):
 c=db()
 try:
  l=c.execute('select l.*,p.tercero_id from laboratorio_prestaciones l join pacientes p on p.id=l.paciente_id where l.id=?',(lid,)).fetchone()
  if not l or l['origen']!='PARTICULAR':raise ValueError('Prestación particular no encontrada.')
  if l['estado_facturacion']=='FACTURADO':raise ValueError('Esta prestación ya fue facturada.')
  if not l['tercero_id']:raise ValueError('El paciente debe estar vinculado a un cliente.')
  if not caja_abierta(c):raise ValueError('Debe abrir la caja para registrar una venta al contado.')
  numero=(request.form.get('numero') or '').strip()
  if not numero:raise ValueError('Ingrese el número de factura.')
  total=float(l['importe_pyg'] or 0);base,iva=desglosar_iva_incluido(total,10)
  vid=c.execute("""insert into ventas(fecha,cliente_id,numero,moneda,tipo_cambio,gravado,iva,exento,total,total_pyg,gravado_10,iva_10,gravado_5,iva_5,exento_iva,condicion_venta,forma_cobro)
                   values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(l['fecha'],l['tercero_id'],numero,'PYG',1,base,iva,0,total,total,base,iva,0,0,0,'CONTADO','Efectivo')).lastrowid
  c.execute("insert into cxc(venta_id,tercero_id,moneda,tipo_cambio_origen,importe,saldo,importe_pyg,estado) values(?,?,?,?,?,?,?,'PAGADO')",(vid,l['tercero_id'],'PYG',1,total,0,total))
  ap=caja_abierta(c);fid=c.execute("select id from formas_cobro where nombre='Efectivo'").fetchone()
  c.execute("insert into movimientos_caja(apertura_id,fecha,tipo,forma_cobro_id,concepto,importe_pyg,origen_tipo,origen_id,usuario) values(?,?,'INGRESO',?,?,?,?,?,?)",(ap['id'],now(),fid['id'] if fid else None,'Laboratorio '+numero,total,'LABORATORIO',lid,session.get('user')))
  c.execute("update laboratorio_prestaciones set estado_facturacion='FACTURADO',venta_id=? where id=?",(vid,lid))
  c.commit();audit('LABORATORIO_FACTURA_CONTADO',f'{lid}/{numero}');flash('Factura de laboratorio al contado registrada.')
 except Exception as ex:c.rollback();flash(str(ex))
 finally:c.close()
 return redirect('/laboratorio')

@app.route('/laboratorio/pendientes-seguro')
def laboratorio_pendientes_seguro():
 c=db();rows=c.execute("""select l.*,p.nombre paciente,a.nombre aseguradora,sp.estado estado_seguro
 from laboratorio_prestaciones l left join pacientes p on p.id=l.paciente_id left join aseguradoras a on a.id=l.aseguradora_id
 left join seguro_pendientes sp on sp.id=l.seguro_pendiente_id where l.origen='SEGURO'
 order by l.fecha desc,l.id desc""").fetchall();c.close()
 return render_template('laboratory_insurance_pending.html',rows=rows)

@app.route('/laboratorio/ventas-contado')
def laboratorio_ventas_contado():
 c=db();rows=c.execute("""select l.*,p.nombre paciente,v.numero factura from laboratorio_prestaciones l
 left join pacientes p on p.id=l.paciente_id left join ventas v on v.id=l.venta_id
 where l.origen='PARTICULAR' order by l.fecha desc,l.id desc""").fetchall();c.close()
 return render_template('laboratory_cash_sales.html',rows=rows)

@app.route('/laboratorio/liquidaciones',methods=['GET','POST'])
def laboratorio_liquidaciones():
 c=db()
 if request.method=='POST':
  try:
   desde=request.form['desde'];hasta=request.form['hasta']
   items=c.execute("""select * from laboratorio_prestaciones where fecha between ? and ? and liquidacion_id is null
                      order by fecha,id""",(desde,hasta)).fetchall()
   if not items:raise ValueError('No existen prestaciones pendientes de liquidación en el período.')
   bruto=sum(float(x['importe_pyg'] or 0) for x in items)
   normal=sum(float(x['importe_pyg'] or 0) for x in items if not x['estudio_admisional'])
   adm=sum(float(x['importe_pyg'] or 0) for x in items if x['estudio_admisional'])
   laced=normal*.80+adm*.85;santa=normal*.20+adm*.15
   q=c.execute("""insert into laboratorio_liquidaciones(fecha_desde,fecha_hasta,total_bruto_pyg,total_laced_pyg,total_santa_clara_pyg,total_normal_pyg,total_admisional_pyg,creado_por,creado_en)
                  values(?,?,?,?,?,?,?,?,?)""",(desde,hasta,bruto,laced,santa,normal,adm,session.get('user'),now()))
   liq=q.lastrowid
   for x in items:
    pl=85.0 if x['estudio_admisional'] else 80.0;ps=15.0 if x['estudio_admisional'] else 20.0;imp=float(x['importe_pyg'] or 0)
    c.execute("""insert into laboratorio_liquidacion_items(liquidacion_id,prestacion_id,importe_pyg,porcentaje_laced,importe_laced_pyg,porcentaje_santa_clara,importe_santa_clara_pyg)
                 values(?,?,?,?,?,?,?)""",(liq,x['id'],imp,pl,imp*pl/100,ps,imp*ps/100))
    c.execute('update laboratorio_prestaciones set liquidacion_id=? where id=?',(liq,x['id']))
   c.commit();audit('LIQUIDACION_LABORATORIO',str(liq));flash('Liquidación de Laboratorio LACED generada.')
  except Exception as ex:c.rollback();flash(str(ex))
  c.close();return redirect('/laboratorio/liquidaciones')
 rows=c.execute('select * from laboratorio_liquidaciones order by id desc limit 100').fetchall();c.close()
 return render_template('laboratory_settlements.html',rows=rows)

@app.route('/laboratorio/liquidaciones/<int:lid>')
def laboratorio_liquidacion_detalle(lid):
 c=db();liq=c.execute('select * from laboratorio_liquidaciones where id=?',(lid,)).fetchone()
 items=c.execute("""select i.*,l.fecha,l.descripcion,l.origen,l.estudio_admisional,p.nombre paciente,a.nombre aseguradora
 from laboratorio_liquidacion_items i join laboratorio_prestaciones l on l.id=i.prestacion_id
 left join pacientes p on p.id=l.paciente_id left join aseguradoras a on a.id=l.aseguradora_id
 where i.liquidacion_id=? order by l.fecha,l.id""",(lid,)).fetchall();c.close()
 if not liq:return ('Liquidación no encontrada',404)
 return render_template('laboratory_settlement_detail.html',liq=liq,items=items)


@app.route('/laboratorio/liquidaciones/<int:lid>/pdf')
def laboratorio_liquidacion_pdf(lid):
 from reportlab.lib.pagesizes import A4
 from reportlab.platypus import SimpleDocTemplate,Table,TableStyle,Paragraph,Spacer
 from reportlab.lib import colors
 from reportlab.lib.styles import getSampleStyleSheet
 from flask import send_file
 from io import BytesIO
 c=db()
 liq=c.execute('select * from laboratorio_liquidaciones where id=?',(lid,)).fetchone()
 items=c.execute("""select i.*,l.fecha,l.descripcion,l.origen,l.estudio_admisional,p.nombre paciente,a.nombre aseguradora
 from laboratorio_liquidacion_items i join laboratorio_prestaciones l on l.id=i.prestacion_id
 left join pacientes p on p.id=l.paciente_id left join aseguradoras a on a.id=l.aseguradora_id
 where i.liquidacion_id=? order by l.fecha,l.id""",(lid,)).fetchall()
 c.close()
 if not liq:return ('Liquidación no encontrada',404)
 out=BytesIO();doc=SimpleDocTemplate(out,pagesize=A4,rightMargin=24,leftMargin=24,topMargin=24,bottomMargin=24)
 st=getSampleStyleSheet();story=[]
 logo=pdf_logo()
 if logo:story.append(logo)
 story += [Paragraph('CENTRO MÉDICO SANTA CLARA',st['Title']),
           Paragraph('Liquidación a Pagar - Laboratorio LACED',st['Heading2']),
           Paragraph(f"N.º {liq['id']} | Período: {liq['fecha_desde']} al {liq['fecha_hasta']}",st['Normal']),Spacer(1,10)]
 data=[['Fecha','Paciente','Prestación','Origen','Bruto','% LACED','LACED','Santa Clara']]
 for x in items:
  origen=x['aseguradora'] or ('Particular' if x['origen']=='PARTICULAR' else x['origen'])
  if x['estudio_admisional']:origen+=' / Admisional'
  data.append([x['fecha'],x['paciente'] or '-',x['descripcion'],origen,f"{float(x['importe_pyg'] or 0):,.0f}",f"{float(x['porcentaje_laced'] or 0):.0f}%",f"{float(x['importe_laced_pyg'] or 0):,.0f}",f"{float(x['importe_santa_clara_pyg'] or 0):,.0f}"])
 t=Table(data,repeatRows=1,colWidths=[48,78,115,82,58,48,62,65])
 t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.lightgrey),('GRID',(0,0),(-1,-1),.3,colors.grey),('FONTSIZE',(0,0),(-1,-1),7),('VALIGN',(0,0),(-1,-1),'TOP'),('ALIGN',(4,1),(-1,-1),'RIGHT')]))
 story += [t,Spacer(1,12),
           Paragraph(f"Total bruto: Gs. {float(liq['total_bruto_pyg'] or 0):,.0f}",st['Normal']),
           Paragraph(f"A pagar a Laboratorio LACED: Gs. {float(liq['total_laced_pyg'] or 0):,.0f}",st['Heading3']),
           Paragraph(f"Participación Centro Médico Santa Clara: Gs. {float(liq['total_santa_clara_pyg'] or 0):,.0f}",st['Normal']),
           Spacer(1,8),Paragraph('Servicios normales: 80% LACED / 20% Santa Clara. Estudios admisionales: 85% LACED / 15% Santa Clara.',st['Normal'])]
 doc.build(story);out.seek(0)
 audit('PDF_LIQUIDACION_LABORATORIO',str(lid))
 return send_file(out,as_attachment=True,download_name=f'liquidacion_laboratorio_LACED_{lid}.pdf',mimetype='application/pdf')



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
 c=db();r=c.execute('''select g.*,p.nombre paciente,m.consultorio_numero from agenda g join pacientes p on p.id=g.paciente_id join medicos m on m.id=g.medico_id where g.id=?''',(gid,)).fetchone()
 if not r:c.close();return jsonify(ok=False,error='Agenda no encontrada'),404
 numero=(r['consultorio_numero'] or '').strip()
 if not numero:c.close();return jsonify(ok=False,error='Este médico no tiene número de consultorio configurado.'),400
 texto=f"Paciente {r['paciente']}, favor pasar al consultorio número {numero}"
 # V13.9.70: la PC del médico solo encola; el dispositivo independiente reproduce la llamada.
 c.execute("insert into llamados_pacientes(agenda_id,fecha_hora,medico_id,texto,usuario,estado,dispositivo,reproducido_en) values(?,?,?,?,?,'PENDIENTE',NULL,NULL)",(gid,now(),r['medico_id'],texto,session['user']))
 c.execute("update agenda set estado='LLAMADO' where id=?",(gid,));c.commit();c.close();return jsonify(ok=True,mensaje='Llamada enviada al dispositivo llamador.')

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

# Seguridad web y respaldo automático V13.9.20-R1
_login_attempts={}
_login_lock=threading.Lock()

@app.before_request
def seguridad_basica():
 if request.endpoint=='login' and request.method=='POST':
  ip=request.headers.get('X-Forwarded-For',request.remote_addr or '').split(',')[0].strip()
  ahora=time.time()
  with _login_lock:
   intentos=[t for t in _login_attempts.get(ip,[]) if ahora-t<300]
   if len(intentos)>=8:return ('Demasiados intentos de acceso. Intente nuevamente en unos minutos.',429)
   intentos.append(ahora);_login_attempts[ip]=intentos
 if request.method in ('POST','PUT','PATCH','DELETE'):
  origin=request.headers.get('Origin')
  if origin and origin.rstrip('/') != request.host_url.rstrip('/'):
   return ('Solicitud rechazada por seguridad.',403)

@app.after_request
def cabeceras_seguridad(resp):
 resp.headers['X-Content-Type-Options']='nosniff'
 resp.headers['X-Frame-Options']='SAMEORIGIN'
 resp.headers['Referrer-Policy']='strict-origin-when-cross-origin'
 resp.headers['Permissions-Policy']='camera=(), microphone=(), geolocation=()'
 resp.headers['Content-Security-Policy']="default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; script-src 'self' 'unsafe-inline'; font-src 'self' data:; frame-ancestors 'self'"
 if os.environ.get('RENDER'):resp.headers['Strict-Transport-Security']='max-age=31536000; includeSubDomains'
 return resp

@app.get('/health')
def health():
 try:
  c=db();c.execute('select 1').fetchone();c.close();return jsonify(status='ok',database='ok'),200
 except Exception as e:return jsonify(status='error'),503

# V13.9.29 - Backups con control de espacio. Evita llenar el disco persistente.
BACKUP_5MIN_DIR=os.path.join(DATA_DIR,'backups','5min')
BACKUP_MIN_FREE_BYTES=200*1024*1024       # reserva mínima de 200 MB para SQLite/ERP
BACKUP_MAX_DISK_FRACTION=0.35             # backups <= 35% del disco
BACKUP_5MIN_KEEP=24                       # 2 horas: 24 copias cada 5 minutos
BACKUP_DAILY_KEEP=7                       # 7 copias diarias locales; externo recomendado

def _archivos_db(carpeta):
 try:
  return sorted([os.path.join(carpeta,x) for x in os.listdir(carpeta) if x.endswith('.db') and os.path.isfile(os.path.join(carpeta,x))],key=os.path.getmtime,reverse=True)
 except OSError:return []

def _borrar_seguro(ruta):
 try:os.remove(ruta);return True
 except OSError:return False

def limpiar_backups_emergencia():
 os.makedirs(BACKUP_5MIN_DIR,exist_ok=True)
 raiz=os.path.join(DATA_DIR,'backups')
 # Primero limita por antigüedad/cantidad.
 for viejo in _archivos_db(BACKUP_5MIN_DIR)[BACKUP_5MIN_KEEP:]:_borrar_seguro(viejo)
 diarios=[x for x in _archivos_db(raiz) if 'antes_V' not in os.path.basename(x)]
 for viejo in diarios[BACKUP_DAILY_KEEP:]:_borrar_seguro(viejo)
 # Después libera espacio de forma adaptativa. Nunca toca DB principal ni branding.
 try:
  total,used,free=shutil.disk_usage(DATA_DIR)
  limite=int(total*BACKUP_MAX_DISK_FRACTION)
  candidatos=_archivos_db(BACKUP_5MIN_DIR)+diarios
  candidatos=sorted(set(candidatos),key=lambda x:os.path.getmtime(x)) # más viejos primero
  def tam_backups():
   n=0
   for f in _archivos_db(BACKUP_5MIN_DIR)+_archivos_db(raiz):
    try:n+=os.path.getsize(f)
    except OSError:pass
   return n
  usados=tam_backups()
  while candidatos and (free<BACKUP_MIN_FREE_BYTES or usados>limite):
   f=candidatos.pop(0)
   # Conserva siempre al menos la copia de 5 min más reciente si existe.
   recientes=_archivos_db(BACKUP_5MIN_DIR)
   if f in recientes and len(recientes)<=1:continue
   try:sz=os.path.getsize(f)
   except OSError:sz=0
   if _borrar_seguro(f):
    usados=max(0,usados-sz)
    total,used,free=shutil.disk_usage(DATA_DIR)
  print('[Santa Clara] Espacio disco libre:',round(free/1024/1024,1),'MB')
 except Exception as e:print('[Santa Clara] Limpieza backups:',e)

def hay_espacio_para_backup():
 try:
  total,used,free=shutil.disk_usage(DATA_DIR)
  dbsize=os.path.getsize(DB) if os.path.exists(DB) else 0
  # Para crear una copia completa se exige DB + margen operativo.
  return free >= dbsize + BACKUP_MIN_FREE_BYTES
 except OSError:return False

def backup_sqlite_5min():
 os.makedirs(BACKUP_5MIN_DIR,exist_ok=True)
 while True:
  try:
   limpiar_backups_emergencia()
   if os.path.exists(DB) and hay_espacio_para_backup():
    destino=os.path.join(BACKUP_5MIN_DIR,'santa_clara_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'.db')
    src=sqlite3.connect(DB);dst=sqlite3.connect(destino)
    try:src.backup(dst)
    finally:dst.close();src.close()
    limpiar_backups_emergencia()
   else:
    print('[Santa Clara] Backup 5 min omitido temporalmente: espacio insuficiente; la base activa no se toca.')
  except Exception as e:print('[Santa Clara] Backup 5 min:',e)
  time.sleep(300)

def iniciar_backup_automatico():
 t=threading.Thread(target=backup_sqlite_5min,name='backup-santa-clara',daemon=True);t.start()

def init_v13992_internacion_geografia():
 c=db()
 try:
  c.execute("CREATE TABLE IF NOT EXISTS internacion_traslados(id INTEGER PRIMARY KEY,admision_id INTEGER NOT NULL,cama_origen_id INTEGER,cama_destino_id INTEGER NOT NULL,fecha TEXT NOT NULL,usuario TEXT,motivo TEXT)")
  c.execute("CREATE TABLE IF NOT EXISTS geo_ubicaciones(id INTEGER PRIMARY KEY,departamento_codigo TEXT NOT NULL,departamento TEXT NOT NULL,distrito_codigo TEXT,distrito TEXT,ciudad_codigo TEXT,ciudad TEXT,barrio_codigo TEXT,barrio TEXT,activo INTEGER DEFAULT 1,actualizado_en TEXT,UNIQUE(departamento_codigo,distrito_codigo,ciudad_codigo,barrio_codigo))")
  tcols={r['name'] for r in c.execute('pragma table_info(terceros)').fetchall()}
  for col,typ in [('sifen_barrio_codigo','TEXT'),('sifen_barrio_desc','TEXT')]:
   if col not in tcols:c.execute('alter table terceros add column '+col+' '+typ)
  dup=c.execute("select cama_id,count(*) n from admisiones where estado='ABIERTA' and cama_id is not null group by cama_id having count(*)>1 limit 1").fetchone()
  if not dup:c.execute("create unique index if not exists ux_admision_cama_abierta on admisiones(cama_id) where estado='ABIERTA' and cama_id is not null")
  c.execute("insert or ignore into schema_migrations(version,aplicado_en) values('13.9.92-internacion-geografia',?)",(now(),));c.commit()
 finally:c.close()

# IMPORTANTE: liberar backups antiguos ANTES de cualquier copia o migración.
limpiar_backups_emergencia()
preparar_actualizacion_segura()
init()
init_v13991_maestros_sifen()
init_v13992_internacion_geografia()

def sincronizar_clientes_pacientes(c):
 # En Santa Clara, CLIENTE y PACIENTE representan a la misma persona.
 # Conserva las dos tablas por compatibilidad contable, pero asegura vínculo 1 a 1.
 clientes=c.execute("select id,ruc,nombre,telefono from terceros where upper(coalesce(tipo,''))='CLIENTE' order by id").fetchall()
 for t in clientes:
  vinc=c.execute('select id from pacientes where tercero_id=?',(t['id'],)).fetchone()
  if vinc:continue
  por_doc=c.execute("select id,tercero_id from pacientes where documento=? and coalesce(documento,'')<>'' limit 1",(t['ruc'] or '',)).fetchone() if t['ruc'] else None
  if por_doc:
   if not por_doc['tercero_id']:c.execute('update pacientes set tercero_id=? where id=?',(t['id'],por_doc['id']))
   continue
  c.execute('insert into pacientes(documento,nombre,telefono,tercero_id) values(?,?,?,?)',(t['ruc'] or '',t['nombre'],t['telefono'],t['id']))
 c.commit()

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
        c.execute('update productos set codigo=?,codigo_barras=?,nombre=?,categoria=?,costo_pyg=?,precio_pyg=?,stock_min=?,iva_pct=?,tipo_producto=?,clasif_general=?,sifen_descripcion=?,sifen_unidad_codigo=?,sifen_unidad_desc=? where id=?',(request.form['codigo'],cb,request.form['nombre'],request.form.get('categoria'),float(request.form.get('costo_pyg') or 0),float(request.form.get('precio_pyg') or 0),float(request.form.get('stock_min') or 0),float(request.form.get('iva_pct') or 0),request.form.get('tipo_producto') or '',request.form.get('clasif_general') or '',request.form.get('sifen_descripcion') or request.form['nombre'],request.form.get('sifen_unidad_codigo') or '77',request.form.get('sifen_unidad_desc') or 'UNI',rid));c.commit();c.close();audit('EDITAR_PRODUCTO',str(rid));return redirect('/productos')
    c.close();return render_template('edit_master.html',title='Modificar producto',record=r,kind='producto')
@app.post('/producto/<int:rid>/eliminar')
def producto_eliminar(rid):
    ok,msg=_safe_delete_master('productos',rid,[('compra_items','producto_id'),('venta_items','producto_id'),('stock_mov','producto_id'),('cargos_paciente','referencia_id')]);flash(msg);audit('ELIMINAR_PRODUCTO' if ok else 'BLOQUEO_ELIMINAR_PRODUCTO',str(rid));return redirect('/productos')

@app.route('/tercero/<int:rid>/editar',methods=['GET','POST'])
def tercero_editar(rid):
    c=db();r=c.execute('select * from terceros where id=?',(rid,)).fetchone();mons=c.execute('select * from monedas').fetchall()
    if request.method=='POST':
        c.execute('''update terceros set tipo=?,ruc=?,nombre=?,telefono=?,email=?,moneda=?,sifen_naturaleza=?,sifen_tipo_operacion=?,sifen_tipo_contribuyente=?,sifen_tipo_documento=?,sifen_numero_documento=?,sifen_pais=?,sifen_pais_desc=?,sifen_direccion=?,sifen_numero_casa=?,sifen_departamento_codigo=?,sifen_departamento_desc=?,sifen_distrito_codigo=?,sifen_distrito_desc=?,sifen_ciudad_codigo=?,sifen_ciudad_desc=? where id=?''',('PROVEEDOR',request.form.get('ruc'),request.form['nombre'],request.form.get('telefono'),request.form.get('email'),request.form['moneda'],request.form.get('sifen_naturaleza','1'),request.form.get('sifen_tipo_operacion','1'),request.form.get('sifen_tipo_contribuyente','2'),request.form.get('sifen_tipo_documento','1'),request.form.get('sifen_numero_documento') or request.form.get('ruc'),request.form.get('sifen_pais','PRY'),request.form.get('sifen_pais_desc','Paraguay'),request.form.get('sifen_direccion'),request.form.get('sifen_numero_casa','0'),request.form.get('sifen_departamento_codigo'),request.form.get('sifen_departamento_desc'),request.form.get('sifen_distrito_codigo'),request.form.get('sifen_distrito_desc'),request.form.get('sifen_ciudad_codigo'),request.form.get('sifen_ciudad_desc'),rid));c.commit();c.close();audit('EDITAR_TERCERO',str(rid));return redirect('/proveedores')
    c.close();return render_template('edit_master.html',title='Modificar proveedor',record=r,kind='tercero',mons=mons)
@app.post('/tercero/<int:rid>/eliminar')
def tercero_eliminar(rid):
    ok,msg=_safe_delete_master('terceros',rid,[('compras','proveedor_id'),('ventas','cliente_id'),('cxc','tercero_id'),('cxp','tercero_id'),('pacientes','tercero_id'),('aseguradoras','tercero_id'),('medicos','tercero_id')]);flash(msg);audit('ELIMINAR_TERCERO' if ok else 'BLOQUEO_ELIMINAR_TERCERO',str(rid));return redirect('/proveedores')

@app.route('/paciente/<int:rid>/eliminar',methods=['POST'])
def paciente_eliminar(rid):
    c=db();p=c.execute('select * from pacientes where id=?',(rid,)).fetchone()
    if c.execute('select 1 from admisiones where paciente_id=? limit 1',(rid,)).fetchone():flash('No se puede eliminar un paciente con admisiones o historia relacionada.');c.close();return redirect('/clientes')
    if p:c.execute('delete from pacientes where id=?',(rid,));c.execute('delete from terceros where id=?',(p['tercero_id'],));c.commit();audit('ELIMINAR_PACIENTE',str(rid))
    c.close();return redirect('/clientes')

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
 bio=io.BytesIO();doc=SimpleDocTemplate(bio,pagesize=A4,leftMargin=10*mm,rightMargin=10*mm,topMargin=8*mm,bottomMargin=8*mm);st=getSampleStyleSheet();story=[]
 _kude_header(story,inst,'RECIBO DE DINERO',r['numero'],'Comprobante de Recibo')
 datos=[[Paragraph('<b>Nombre o Razón Social:</b> '+str(r['cliente']),st['Normal']),Paragraph('<b>RUC/Documento:</b> '+str(r['ruc'] or '-'),st['Normal'])],[Paragraph('<b>Fecha y hora:</b> '+str(r['fecha']),st['Normal']),Paragraph('<b>Moneda:</b> '+str(r['moneda']),st['Normal'])],[Paragraph('<b>Factura relacionada:</b> '+str(r['factura']),st['Normal']),Paragraph('<b>Medio de cobro:</b> '+str(r['medio']),st['Normal'])]]
 t=Table(datos,colWidths=[95*mm,91*mm]);t.setStyle(TableStyle([('BOX',(0,0),(-1,-1),1,colors.black),('INNERGRID',(0,0),(-1,-1),.3,colors.grey),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),6),('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]));story += [t,Spacer(1,2*mm)]
 entidad=' '.join(x for x in [r['banco'] or '',r['cuenta_alias'] or r['numero_cuenta'] or '',r['terminal_pos'] or ''] if x)
 comp=[['Comprobante','Concepto','Entidad / Cuenta','Referencia','Importe'],[r['factura'],'Cobro de factura',entidad,r['referencia'] or '',f"{float(r['importe'] or 0):,.0f}"],['','','','TOTAL COBRADO',f"{float(r['importe'] or 0):,.0f}"]]
 t=Table(comp,colWidths=[34*mm,46*mm,45*mm,31*mm,30*mm],rowHeights=[8*mm,18*mm,9*mm]);t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e9eef3')),('GRID',(0,0),(-1,-1),.45,colors.black),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTNAME',(-2,-1),(-1,-1),'Helvetica-Bold'),('ALIGN',(-1,1),(-1,-1),'RIGHT'),('FONTSIZE',(0,0),(-1,-1),7.5),('VALIGN',(0,0),(-1,-1),'TOP')]));story += [t,Spacer(1,2*mm),Paragraph('<b>Son:</b> '+monto_letras(r['importe']),st['Normal'])]
 _kude_footer(story,inst,None,None,False)
 doc.build(story);bio.seek(0);return send_file(bio,mimetype='application/pdf',as_attachment=False,download_name=str(r['numero'])+'.pdf')


# ===== V13.4.7: recibos históricos, cuentas receptoras y PDF de informes =====
@app.route('/bancos/cuentas',methods=['GET','POST'])
def cuentas_bancarias():
 c=db()
 if request.method=='POST':
  op=request.form.get('op','nuevo')
  if op=='nuevo':
   c.execute('insert into cuentas_bancarias(banco,numero_cuenta,tipo_cuenta,moneda,titular,alias,acepta_transferencia,acepta_pos,activo,cuenta_contable) values(?,?,?,?,?,?,?,?,1,?)',(request.form['banco'],request.form.get('numero_cuenta'),request.form.get('tipo_cuenta'),request.form.get('moneda','PYG'),request.form.get('titular'),request.form.get('alias'),1 if request.form.get('acepta_transferencia') else 0,1 if request.form.get('acepta_pos') else 0,request.form.get('cuenta_contable')))
  elif op=='estado':c.execute('update cuentas_bancarias set activo=case when activo=1 then 0 else 1 end where id=?',(int(request.form['id']),))
  c.commit();c.close();audit('CUENTA_BANCARIA',op);return redirect('/bancos/cuentas')
 rows=c.execute('select * from cuentas_bancarias order by activo desc,banco,alias').fetchall();pc=c.execute('select codigo,nombre from plan_cuentas where imputable=1 order by codigo').fetchall();c.close();return render_template('bank_accounts.html',rows=rows,pc=pc)

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
 data=[headers]+[[_report_value(v,headers[i]) for i,v in enumerate(r)] for r in rows];tbl=Table(data,repeatRows=1);tbl.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.lightgrey),('GRID',(0,0),(-1,-1),0.35,colors.grey),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),7),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),3),('RIGHTPADDING',(0,0),(-1,-1),3)]));story.append(tbl);story.append(Spacer(1,4*mm));story.append(Paragraph(f'Total de registros: {len(rows)}',styles['Normal']));
 for h,v in _report_totals(headers,rows): story.append(Paragraph(f'<b>{h}:</b> Gs. {_money_local(v,"PYG")}',styles['Normal']))
 doc.build(story);buf.seek(0);return send_file(buf,mimetype='application/pdf',as_attachment=True,download_name=f'{tipo}_{desde}_{hasta}.pdf')

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
 totales=_report_totals(headers,rows) if buscado else []
 return render_template('specific_report.html',tipo=tipo,titulo=titulo,headers=headers,rows=rows,desde=desde,hasta=hasta,buscado=buscado,totales=totales,report_value=_report_value)


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
 cuentas=c.execute('select codigo,nombre from plan_cuentas order by codigo').fetchall();config=c.execute('select * from institucion_config where id=1').fetchone();c.close()
 totales=_report_totals(headers,rows) if buscado else []
 modo='rubricado' if request.args.get('modo')=='rubricado' else 'normal'
 return render_template('accounting_report.html',tipo=tipo,titulo=titulo,headers=headers,rows=rows,desde=desde,hasta=hasta,cuenta=cuenta,cuentas=cuentas,buscado=buscado,totales=totales,report_value=_report_value,modo=modo,config=config)

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
 from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
 from reportlab.lib.enums import TA_CENTER,TA_LEFT,TA_RIGHT
 from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,KeepTogether
 desde=request.args.get('desde') or '1900-01-01';hasta=request.args.get('hasta') or datetime.date.today().isoformat();cuenta=request.args.get('cuenta') or None
 modo='rubricado' if request.args.get('modo')=='rubricado' else 'normal'
 c=db();titulo,headers,rows=_accounting_report(c,tipo,desde,hasta,cuenta);inst=c.execute('select * from institucion_config where id=1').fetchone();c.close()
 empresa=(inst['razon_social'] if inst and 'razon_social' in inst.keys() and inst['razon_social'] else (inst['nombre'] if inst else 'CENTRO MEDICO SANTA CLARA'))
 ruc=(inst['ruc'] if inst and inst['ruc'] else '')
 if inst and 'dv' in inst.keys() and inst['dv'] and ruc and '-' not in ruc:ruc=f"{ruc}-{inst['dv']}"
 direccion=(inst['direccion'] if inst and 'direccion' in inst.keys() and inst['direccion'] else '')
 bio=io.BytesIO();styles=getSampleStyleSheet()
 # V13.9.57: el Libro Diario rubricado replica el formato tradicional mostrado por el usuario:
 # encabezado institucional, asiento/cuenta/debe/haber, glosa, fecha separadora y folio por página.
 if modo=='rubricado' and tipo=='diario':
  from collections import OrderedDict
  doc=SimpleDocTemplate(bio,pagesize=A4,leftMargin=22,rightMargin=22,topMargin=68,bottomMargin=28)
  normal=ParagraphStyle('rdn',parent=styles['Normal'],fontName='Helvetica',fontSize=7.2,leading=9)
  small=ParagraphStyle('rds',parent=normal,fontSize=6.6,leading=8)
  money=ParagraphStyle('rdm',parent=normal,alignment=TA_RIGHT)
  story=[];grupos=OrderedDict()
  for r in rows:
   # Fecha, Asiento, Concepto, Cuenta, Nombre, Debe, Haber, Moneda, TC
   key=(r[0],r[1],r[2]);grupos.setdefault(key,[]).append(r)
  for (fecha,num,concepto),det in grupos.items():
   data=[];td=th=0
   for r in det:
    debe=float(r[5] or 0);haber=float(r[6] or 0);td+=debe;th+=haber
    nombre=(r[4] or '').strip();cuenta=(r[3] or '').strip()
    etiqueta=(('a ' if haber and not debe else '') + nombre).strip()
    if cuenta: etiqueta=(cuenta+'  '+etiqueta).strip()
    data.append([Paragraph(str(num),small),Paragraph(etiqueta,normal),Paragraph(_money_local(debe,'PYG') if debe else '0',money),Paragraph(_money_local(haber,'PYG') if haber else '0',money)])
   data.append(['','',Paragraph(_money_local(td,'PYG'),money),Paragraph(_money_local(th,'PYG'),money)])
   t=Table(data,colWidths=[52,330,82,82],hAlign='LEFT')
   t.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),2),('RIGHTPADDING',(0,0),(-1,-1),2),('TOPPADDING',(0,0),(-1,-1),2),('BOTTOMPADDING',(0,0),(-1,-2),2),('LINEABOVE',(2,-1),(-1,-1),0.55,colors.black),('LINEBELOW',(2,-1),(-1,-1),0.55,colors.black)]))
   try: ftxt=datetime.datetime.strptime(str(fecha)[:10],'%Y-%m-%d').strftime('%d-%m-%y')
   except: ftxt=str(fecha)
   glosa=Paragraph(str(concepto or ''),small)
   sep=Table([[glosa,Paragraph(ftxt,ParagraphStyle('date',parent=small,alignment=TA_CENTER)),'']],colWidths=[265,90,191])
   sep.setStyle(TableStyle([('LINEBELOW',(0,0),(0,0),0.7,colors.black),('LINEBELOW',(2,0),(2,0),0.7,colors.black),('VALIGN',(0,0),(-1,-1),'BOTTOM'),('LEFTPADDING',(0,0),(-1,-1),0),('RIGHTPADDING',(0,0),(-1,-1),0),('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),2)]))
   story.append(KeepTogether([t,sep,Spacer(1,3)]))
  def _cab(canvas,doc):
   canvas.saveState();w,h=A4
   canvas.setStrokeColor(colors.HexColor('#1f3f9a'));canvas.setLineWidth(1.2);canvas.line(0,h-2,w,h-2)
   canvas.setFont('Helvetica-Bold',8);canvas.drawString(22,h-20,empresa.upper())
   canvas.setFont('Helvetica',7);canvas.drawString(22,h-32,(direccion or '').upper())
   canvas.setFont('Helvetica-Bold',8);canvas.drawCentredString(w/2,h-20,titulo)
   canvas.setFont('Helvetica',7);canvas.drawRightString(w-22,h-20,f'Pág.: {doc.page}')
   canvas.drawRightString(w-22,h-32,f'R.U.C.: {ruc or "-"}')
   y=h-49
   canvas.setLineWidth(.45);canvas.rect(22,y-10,w-44,11,stroke=1,fill=0)
   canvas.setFont('Helvetica-Bold',6.6);canvas.drawString(28,y-7,'Asiento');canvas.drawString(83,y-7,'Cuenta');canvas.drawRightString(w-108,y-7,'Importe Debe');canvas.drawRightString(w-28,y-7,'Importe Haber')
   canvas.restoreState()
  doc.build(story,onFirstPage=_cab,onLaterPages=_cab);bio.seek(0)
  return send_file(bio,as_attachment=False,download_name=f'{tipo}_RUBRICADO_{desde}_{hasta}.pdf',mimetype='application/pdf')
 # Resto de informes: conserva tabla completa, con identidad y foliado rubricado.
 doc=SimpleDocTemplate(bio,pagesize=landscape(A4),leftMargin=20,rightMargin=20,topMargin=30,bottomMargin=30)
 story=[]
 if pdf_logo():story.append(pdf_logo())
 story += [Paragraph(empresa,styles['Title']),Paragraph(titulo,styles['Heading2']),Paragraph(f'RUC: {ruc or "-"} &nbsp;&nbsp; | &nbsp;&nbsp; Periodo: {desde} al {hasta}',styles['Normal'])]
 if modo=='rubricado':
  aviso=ParagraphStyle('rubrica',parent=styles['Normal'],alignment=TA_CENTER,fontSize=8,leading=10)
  story += [Paragraph('<b>FORMATO PARA IMPRESIÓN / ARCHIVO CONTABLE RUBRICADO</b>',aviso),Paragraph('Vista de libro contable con foliado correlativo. La emisión desde el sistema no sustituye la rúbrica o autorización legal que corresponda.',aviso)]
 story += [Paragraph(f'Emitido: {datetime.datetime.now():%d/%m/%Y %H:%M}',styles['Normal']),Spacer(1,8)]
 data=[headers]+[[_report_value(v,headers[i]) for i,v in enumerate(r)] for r in rows]
 tbl=Table(data,repeatRows=1)
 tbl.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.white if modo=='rubricado' else colors.lightgrey),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),7),('GRID',(0,0),(-1,-1),0.35 if modo=='rubricado' else 0.25,colors.black if modo=='rubricado' else colors.grey),('VALIGN',(0,0),(-1,-1),'TOP'),('ALIGN',(0,0),(-1,0),'CENTER')]))
 story.append(tbl);story.append(Spacer(1,8));story.append(Paragraph(f'Total de registros: {len(rows)}',styles['Normal']))
 for h,v in _report_totals(headers,rows): story.append(Paragraph(f'<b>{h}:</b> Gs. {_money_local(v,"PYG")}',styles['Normal']))
 def _pie(canvas,doc):
  canvas.saveState();canvas.setFont('Helvetica',7)
  if modo=='rubricado':
   canvas.drawString(20,15,f'{empresa} - RUC {ruc or "-"} - {titulo}');canvas.drawRightString(landscape(A4)[0]-20,15,f'Pág.: {doc.page}')
  else: canvas.drawRightString(landscape(A4)[0]-20,15,f'Página {doc.page}')
  canvas.restoreState()
 doc.build(story,onFirstPage=_pie,onLaterPages=_pie);bio.seek(0)
 suf='_RUBRICADO' if modo=='rubricado' else ''
 return send_file(bio,as_attachment=False,download_name=f'{tipo}{suf}_{desde}_{hasta}.pdf',mimetype='application/pdf')


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
 pars=[fecha];sql='''select g.*,p.nombre paciente,p.telefono,m.nombre medico,e.nombre especialidad,a.nombre aseguradora from agenda g join pacientes p on p.id=g.paciente_id join medicos m on m.id=g.medico_id left join especialidades e on e.id=g.especialidad_id left join aseguradoras a on a.id=g.aseguradora_id where g.fecha=?'''
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


@app.post('/agendamiento/facturar-seleccion')
def init_v13915_agenda_venta():
 c=db()
 c.execute("""create table if not exists agenda_facturacion_items(
 id integer primary key,agenda_id int not null,tipo text not null,referencia_id int,
 descripcion text not null,cantidad real default 1,precio_pyg real default 0,iva_pct real default 10,
 creado_por text,creado_en text)""")
 c.commit();c.close()
init_v13915_agenda_venta()

@app.route('/agendamiento/preparar-venta',methods=['POST'])
def agenda_preparar_venta():
 ids=[]
 for x in request.form.getlist('agenda_ids'):
  try:ids.append(int(x))
  except:pass
 if not ids:
  flash('Seleccione al menos un turno en la columna Fact.');return redirect(request.referrer or '/agendamiento/turnos')
 c=db()
 qmarks=','.join('?' for _ in ids)
 rows=c.execute(f"""select g.*,p.nombre paciente,p.documento,m.nombre medico,e.nombre especialidad,a.nombre aseguradora
 from agenda g join pacientes p on p.id=g.paciente_id join medicos m on m.id=g.medico_id
 left join especialidades e on e.id=g.especialidad_id left join aseguradoras a on a.id=g.aseguradora_id
 where g.id in ({qmarks}) order by g.fecha,g.hora""",ids).fetchall()
 servicios=c.execute('select * from servicios order by nombre').fetchall()
 productos=c.execute('select * from productos order by nombre').fetchall()
 c.close()
 return render_template('agenda_sale_prepare.html',rows=rows,servicios=servicios,productos=productos)

@app.post('/agendamiento/generar-ventas')
def agenda_generar_ventas():
 import json
 payload=request.form.get('payload') or '[]'
 try: grupos=json.loads(payload)
 except:grupos=[]
 if not grupos:
  flash('No hay prestaciones para facturar.');return redirect('/agendamiento/turnos')
 c=db();ventas_creadas=0;seguros=0
 try:
  for gdata in grupos:
   gid=int(gdata['agenda_id']);g=c.execute("""select g.*,p.tercero_id,e.nombre especialidad from agenda g join pacientes p on p.id=g.paciente_id left join especialidades e on e.id=g.especialidad_id where g.id=?""",(gid,)).fetchone()
   if not g:continue
   items=gdata.get('items') or []
   if not items:raise ValueError('Cada turno seleccionado debe tener al menos una consulta, procedimiento o producto.')
   total=0;detalle=[]
   for it in items:
    tipo=(it.get('tipo') or '').upper();rid=int(it.get('referencia_id') or 0);qty=float(it.get('cantidad') or 1);precio=float(it.get('precio') or 0)
    if tipo not in ('CONSULTA','PROCEDIMIENTO','PRODUCTO') or qty<=0 or precio<0:raise ValueError('Revise el detalle de prestaciones.')
    if tipo=='PRODUCTO':
     r=c.execute('select * from productos where id=?',(rid,)).fetchone()
     if not r:raise ValueError('Producto no encontrado.')
     if _producto_controla_stock(r) and float(r['stock'] or 0)<qty:raise ValueError('Stock insuficiente para '+r['nombre'])
     desc=r['nombre'];iva=float(r['iva_pct'] or 0);costo=float(r['costo_pyg'] or 0)
    elif tipo=='PROCEDIMIENTO':
     r=c.execute('select * from servicios where id=?',(rid,)).fetchone()
     if not r:raise ValueError('Procedimiento/servicio no encontrado.')
     desc=r['nombre'];iva=10.0;costo=0
    else:
     desc=it.get('descripcion') or ('Consulta '+(g['especialidad'] or 'médica'));iva=10.0;costo=0
    line=qty*precio;total+=line;detalle.append((tipo,rid,desc,qty,precio,line,iva,costo))
   # Always preserve the sale header. For insurance, client is insurer; for particular, patient/client.
   if g['aseguradora_id']:
    aseg=c.execute('select tercero_id from aseguradoras where id=?',(g['aseguradora_id'],)).fetchone();cliente=(aseg['tercero_id'] if aseg else None)
    if not cliente:raise ValueError('La aseguradora debe estar vinculada a un cliente para generar la venta.')
    numero='SEG-'+g['fecha'].replace('-','')+'-'+str(gid).zfill(6);cond='CREDITO'
   else:
    cliente=g['tercero_id']
    if not cliente:raise ValueError('El paciente debe estar vinculado a un cliente.')
    numero='PAR-'+g['fecha'].replace('-','')+'-'+str(gid).zfill(6);cond='CONTADO'
   grav=iva_total=exento=g10=i10=g5=i5=0
   for _,_,_,_,_,line,ivap,_ in detalle:
    base,iv=desglosar_iva_incluido(line,ivap);iva_total+=iv
    if ivap==10:g10+=base;i10+=iv;grav+=base
    elif ivap==5:g5+=base;i5+=iv;grav+=base
    else:exento+=line
   vid=c.execute("""insert into ventas(fecha,cliente_id,numero,moneda,tipo_cambio,gravado,iva,exento,total,total_pyg,gravado_10,iva_10,gravado_5,iva_5,exento_iva,condicion_venta)
    values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(g['fecha'],cliente,numero,'PYG',1,grav,iva_total,exento,total,total,g10,i10,g5,i5,exento,cond)).lastrowid
   for tipo,rid,desc,qty,precio,line,ivap,costo in detalle:
    c.execute('insert into agenda_facturacion_items(agenda_id,tipo,referencia_id,descripcion,cantidad,precio_pyg,iva_pct,creado_por,creado_en) values(?,?,?,?,?,?,?,?,?)',(gid,tipo,rid,desc,qty,precio,ivap,session.get('user'),now()))
    if tipo=='PRODUCTO':
     c.execute('insert into venta_items(venta_id,producto_id,cantidad,precio,total,total_pyg,costo_pyg,iva_pct) values(?,?,?,?,?,?,?,?)',(vid,rid,qty,precio,line,line,costo*qty,ivap))
     if _producto_controla_stock(r):
      c.execute('update productos set stock=stock-? where id=?',(qty,rid));c.execute("insert into stock_mov(fecha,producto_id,tipo,cantidad,costo_pyg,origen_tipo,origen_id) values(?,?,?,?,?,'VENTA',?)",(g['fecha'],rid,'SALIDA',-qty,costo,vid))
    if g['aseguradora_id']:
     c.execute("""insert into seguro_pendientes(fecha,aseguradora_id,paciente_id,origen_tipo,origen_id,categoria,descripcion,importe_pyg,iva_pct,estado)
      values(?,?,?,?,?,?,?,?,?,'PENDIENTE')""",(g['fecha'],g['aseguradora_id'],g['paciente_id'],'AGENDA_VENTA',vid,'MEDICAMENTOS' if tipo=='PRODUCTO' else 'SERVICIOS SANATORIALES',desc,line,ivap))
   saldo=total if g['aseguradora_id'] else 0
   c.execute("insert into cxc(venta_id,tercero_id,moneda,tipo_cambio_origen,importe,saldo,importe_pyg,estado) values(?,?,?,?,?,?,?,?)",(vid,cliente,'PYG',1,total,saldo,total,'PENDIENTE' if saldo else 'PAGADO'))
   c.execute("update agenda set venta_id=?,factura_numero=?,facturada=1,condicion_venta=?,estado=case when estado='AGENDADO' then 'ATENDIDO' else estado end where id=?",(vid,numero,'SEGURO' if g['aseguradora_id'] else 'PARTICULAR',gid))
   ventas_creadas+=1
   if g['aseguradora_id']:seguros+=1
  c.commit();audit('AGENDA_VENTAS_GENERADAS',f'ventas={ventas_creadas}; seguros={seguros}');flash(f'Se generaron {ventas_creadas} ventas. {seguros} fueron enviadas también a Pendientes de Facturación del Seguro.')
 except Exception as ex:c.rollback();flash('No se pudieron generar las ventas: '+str(ex))
 finally:c.close()
 return redirect('/agendamiento/turnos')

def agenda_facturar_seleccion():
 ids=[]
 for raw in request.form.getlist('agenda_ids'):
  try:ids.append(int(raw))
  except:pass
 if not ids:
  flash('Seleccione al menos un turno para procesar.');return redirect(request.referrer or '/agendamiento/turnos')
 c=db();ok=0;seguros=0;particulares=0;errores=[]
 try:
  for gid in ids:
   g=c.execute("""select g.*,m.honorario_consulta,e.nombre especialidad from agenda g
    join medicos m on m.id=g.medico_id left join especialidades e on e.id=g.especialidad_id where g.id=?""",(gid,)).fetchone()
   if not g or g['facturada']:continue
   q=c.execute('select id from consultas where agenda_id=?',(gid,)).fetchone()
   if q:qid=q['id']
   else:
    precio=float(g['precio_pyg'] or 0);hon=float(g['honorario_consulta'] or 0)
    qid=c.execute("""insert into consultas(fecha,hora,paciente_id,medico_id,especialidad_id,aseguradora_id,moneda,tipo_cambio,precio,honorario_medico,precio_pyg,honorario_pyg,observacion,estado,agenda_id,tipo_prestacion,origen_facturacion,facturada)
     values(?,?,?,?,?,?,'PYG',1,?,?,?,?,?,'REALIZADA',?,'CONSULTA',?,0)""",(g['fecha'],g['hora'],g['paciente_id'],g['medico_id'],g['especialidad_id'],g['aseguradora_id'],precio,hon,precio,hon,g['motivo'],gid,'SEGURO' if g['aseguradora_id'] else 'PARTICULAR')).lastrowid
    c.execute('update agenda set consulta_id=? where id=?',(qid,gid))
   if g['aseguradora_id']:
    existe=c.execute("select id from seguro_pendientes where origen_tipo='CONSULTA' and origen_id=?",(qid,)).fetchone()
    if not existe:
     c.execute("""insert into seguro_pendientes(fecha,aseguradora_id,paciente_id,origen_tipo,origen_id,categoria,descripcion,importe_pyg,iva_pct,estado)
      values(?,?,?,?,?,?,?,?,10,'PENDIENTE')""",(g['fecha'],g['aseguradora_id'],g['paciente_id'],'CONSULTA',qid,'SERVICIOS SANATORIALES','Consulta - '+(g['especialidad'] or 'Consulta médica'),float(g['precio_pyg'] or 0)))
    c.execute("update agenda set facturada=1,condicion_venta='SEGURO',estado=case when estado='AGENDADO' then 'ATENDIDO' else estado end where id=?",(gid,))
    c.execute("update consultas set facturada=1 where id=?",(qid,));seguros+=1
   else:
    # Particular seleccionado queda preparado para facturación particular, sin emitir automáticamente.
    c.execute("update agenda set condicion_venta='PARTICULAR',estado=case when estado='AGENDADO' then 'ATENDIDO' else estado end where id=?",(gid,))
    particulares+=1
   ok+=1
  c.commit();audit('AGENDA_FACTURACION_SELECCION',f'{ok} turnos; seguros={seguros}; particulares={particulares}')
  flash(f'Procesados {ok} turnos. Seguros enviados a pendientes: {seguros}. Particulares preparados para facturación: {particulares}.')
 except Exception as ex:
  c.rollback();flash('No se pudo procesar la selección: '+str(ex))
 finally:c.close()
 return redirect(request.referrer or '/agendamiento/turnos')

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

# ===== V13.9.110: cajas por usuario/rol =====
def init_v139110_cajas_usuario():
 c=db()
 c.execute('''CREATE TABLE IF NOT EXISTS usuario_cajas(
   usuario_id INTEGER NOT NULL,
   caja_id INTEGER NOT NULL,
   activo INTEGER DEFAULT 1,
   PRIMARY KEY(usuario_id,caja_id)
 )''')
 # Cajas operativas base. INSERT OR IGNORE conserva las existentes.
 for nombre in ('Caja Recepción','Caja Admisiones','Caja Urgencias'):
  c.execute('insert or ignore into cajas(nombre,activo) values(?,1)',(nombre,))
 # Asignación inicial solicitada, solo si el usuario ya existe y aún no tiene cajas.
 seeds=(('cristiane','Caja Admisiones'),('ana','Caja Urgencias'),('talia','Caja Recepción'))
 for patron,caja_nombre in seeds:
  caja=c.execute('select id from cajas where lower(nombre)=lower(?)',(caja_nombre,)).fetchone()
  if not caja: continue
  usuarios=c.execute("select id,nombre,usuario from usuarios where lower(nombre) like ? or lower(usuario) like ?",('%'+patron+'%','%'+patron+'%')).fetchall()
  for u in usuarios:
   if not c.execute('select 1 from usuario_cajas where usuario_id=? limit 1',(u['id'],)).fetchone():
    c.execute('insert or ignore into usuario_cajas(usuario_id,caja_id,activo) values(?,?,1)',(u['id'],caja['id']))
 c.commit();c.close()

def usuario_es_admin_cajas(c, usuario=None):
 usuario=(usuario or session.get('user') or '').strip()
 if usuario.lower()=='admin': return True
 row=c.execute('''select 1 from usuarios u
   join usuario_roles ur on ur.usuario_id=u.id
   join roles r on r.id=ur.rol_id
   where u.usuario=? and u.activo=1 and upper(r.nombre) in ('ADMINISTRADOR','ADMIN') limit 1''',(usuario,)).fetchone()
 return bool(row)

def cajas_autorizadas_usuario(c, usuario=None):
 usuario=usuario or session.get('user')
 if usuario_es_admin_cajas(c,usuario):
  return c.execute('select * from cajas where activo=1 order by nombre').fetchall()
 return c.execute('''select ca.* from cajas ca
   join usuario_cajas uc on uc.caja_id=ca.id and uc.activo=1
   join usuarios u on u.id=uc.usuario_id
   where u.usuario=? and u.activo=1 and ca.activo=1 order by ca.nombre''',(usuario,)).fetchall()

def caja_autorizada(c,caja_id,usuario=None):
 return any(int(x['id'])==int(caja_id) for x in cajas_autorizadas_usuario(c,usuario))

init_v139110_cajas_usuario()

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
   for r in rows:
    v=c.execute("select id from seguro_visaciones where (origen_tipo='PENDIENTE_SEGURO' and origen_id=?) or (origen_id=? and ((?='CARGO' and origen_tipo='CARGO_SERVICIO') or origen_tipo=?)) limit 1",(r['id'],r['origen_id'],r['origen_tipo'],r['origen_tipo'])).fetchone()
    if not v:raise ValueError('No se puede facturar al seguro: existe una prestación seleccionada sin visación registrada. Cargue la visación desde Pendientes de Seguro.')
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
 rows=c.execute("""select sp.*,p.nombre paciente,a.nombre seguro,
 coalesce((select v.id from seguro_visaciones v where v.origen_tipo='PENDIENTE_SEGURO' and v.origen_id=sp.id limit 1),
 (select v.id from seguro_visaciones v where v.origen_id=sp.origen_id and ((sp.origen_tipo='CARGO' and v.origen_tipo='CARGO_SERVICIO') or v.origen_tipo=sp.origen_tipo) limit 1)) visacion_id
 from seguro_pendientes sp left join pacientes p on p.id=sp.paciente_id join aseguradoras a on a.id=sp.aseguradora_id where """+' and '.join(wh)+' order by a.nombre,sp.fecha,sp.id',pa).fetchall();asegs=c.execute('select * from aseguradoras order by nombre').fetchall();c.commit();c.close();return render_template('insurance_billing.html',rows=rows,asegs=asegs,aseg_id=aseg_id,desde=desde,hasta=hasta)

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




# ===== V13.9.35: formato documental institucional tipo KuDE =====
def _kude_empresa(inst):
    def g(k,default=''):
        try: return inst[k] or default
        except Exception: return default
    ruc=g('ruc','-'); dv=g('dv','')
    if dv and '-' not in str(ruc): ruc=f"{ruc}-{dv}"
    return {
      'nombre':g('razon_social',g('nombre','CENTRO MEDICO SANTA CLARA')),
      'fantasia':g('nombre_fantasia',g('nombre','CENTRO MEDICO SANTA CLARA')),
      'ruc':ruc,'timbrado':g('timbrado','-'),'inicio':g('timbrado_desde','-'),
      'direccion':g('direccion',''),'ciudad':g('ciudad',''),'departamento':g('departamento',''),
      'telefono':g('telefono',''),'email':g('email',''),'pie':g('pie_documento','')
    }

def _kude_qr_flowable(text,size_mm=28):
    if not text: return None
    try:
        from reportlab.graphics.barcode import qr
        from reportlab.graphics.shapes import Drawing
        from reportlab.lib.units import mm
        q=qr.QrCodeWidget(text); b=q.getBounds(); w=b[2]-b[0]; h=b[3]-b[1]
        d=Drawing(size_mm*mm,size_mm*mm,transform=[size_mm*mm/w,0,0,size_mm*mm/h,0,0]); d.add(q); return d
    except Exception:return None

def _kude_header(story,inst,tipo,numero,subtitulo='Representación gráfica del documento emitido por el sistema'):
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import Table,TableStyle,Paragraph,Image,Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    st=getSampleStyleSheet(); e=_kude_empresa(inst); logo=logo_path_actual()
    iz=[]
    if os.path.exists(logo): iz.append(Image(logo,width=38*mm,height=18*mm))
    iz += [Paragraph('<b>'+str(e['nombre'])+'</b>',st['Heading3']),Paragraph(str(e['direccion'])+' '+str(e['ciudad'])+' '+str(e['departamento']),st['Normal']),Paragraph('Tel.: '+str(e['telefono'])+' &nbsp; Email: '+str(e['email']),st['Normal'])]
    der=Paragraph(f"<b>RUC:</b> {e['ruc']}<br/><b>Timbrado N°:</b> {e['timbrado']}<br/><b>Inicio de vigencia:</b> {e['inicio']}<br/><br/><b>{tipo}</b><br/><font size=12><b>N°: {numero}</b></font>",st['Normal'])
    t=Table([[iz,der]],colWidths=[124*mm,62*mm]);t.setStyle(TableStyle([('BOX',(0,0),(-1,-1),1,colors.black),('LINEBEFORE',(1,0),(1,0),1,colors.black),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]));story += [Paragraph('<para alignment="center"><b>'+subtitulo+'</b></para>',st['Normal']),t,Spacer(1,2*mm)]

def _kude_footer(story,inst,cdc=None,consulta_url=None,es_dte=False):
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import Table,TableStyle,Paragraph,Spacer
    from reportlab.lib.styles import getSampleStyleSheet
    st=getSampleStyleSheet(); e=_kude_empresa(inst); qr=_kude_qr_flowable(consulta_url) if consulta_url else None
    if es_dte and cdc:
        txt=f"<b>Consulte este Documento Electrónico con el CDC:</b><br/>{cdc}<br/><b>ESTE DOCUMENTO ES UNA REPRESENTACIÓN GRÁFICA DE UN DOCUMENTO ELECTRÓNICO (XML)</b>"
    elif cdc:
        txt=f'<b>CDC DE PRUEBA (SIFEN TEST):</b><br/>{cdc}<br/><b>NO ENVIADO / NO APROBADO · SIN VALOR FISCAL</b><br/>Generado localmente para pruebas de integración.'
    else:
        txt='<b>DOCUMENTO EMITIDO POR SANTA CLARA ERP</b><br/>Este comprobante no debe identificarse como DTE aprobado por SIFEN mientras no cuente con CDC y aprobación correspondiente.'
    if e['pie']: txt += '<br/>'+str(e['pie'])
    row=[Paragraph(txt,st['Normal']),qr or Paragraph('',st['Normal'])]
    t=Table([row],colWidths=[150*mm,36*mm]);t.setStyle(TableStyle([('BOX',(0,0),(-1,-1),1,colors.black),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LEFTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]));story += [Spacer(1,3*mm),t]

# ===== V13.6.4: Factura imprimible/PDF y preparación SIFEN =====
def init_v1364_factura_electronica():
    c=db()
    cols={r['name'] for r in c.execute('pragma table_info(ventas)').fetchall()}
    for col,defn in [('cdc','TEXT'),('estado_sifen',"TEXT DEFAULT 'NO_ENVIADO'"),('protocolo_sifen','TEXT'),('fecha_aprobacion_sifen','TEXT'),('qr_sifen','TEXT')]:
        if col not in cols:
            c.execute(f'alter table ventas add column {col} {defn}')
    c.execute("CREATE TABLE IF NOT EXISTS schema_migrations(version TEXT PRIMARY KEY, aplicado_en TEXT)")
    c.execute("INSERT OR IGNORE INTO schema_migrations(version,aplicado_en) VALUES('13.6.4-factura-pdf',?)",(now(),))
    c.commit();c.close()
init_v1364_factura_electronica()

def _factura_venta_data(venta_id):
    c=db()
    v=c.execute('''select v.*,t.nombre cliente,t.ruc,t.telefono cliente_telefono,t.email cliente_email,t.sifen_direccion cliente_direccion,t.sifen_tipo_operacion,t.sifen_naturaleza,cb.banco,cb.numero_cuenta,cb.alias cuenta_alias,tp.nombre terminal_pos
                   from ventas v left join terceros t on t.id=v.cliente_id
                   left join cuentas_bancarias cb on cb.id=v.cuenta_bancaria_id
                   left join terminales_pos tp on tp.id=v.terminal_pos_id where v.id=?''',(venta_id,)).fetchone()
    items=c.execute('''select vi.*,p.codigo,coalesce(p.nombre,vi.descripcion,'Servicio') nombre from venta_items vi left join productos p on p.id=vi.producto_id where vi.venta_id=? order by vi.id''',(venta_id,)).fetchall()
    inst=c.execute('select * from institucion_config where id=1').fetchone()
    if v and not v['cdc']:
        try:
            cdc=_generar_cdc_test_venta(c,v['id'],v['fecha'],v['numero'])
            if cdc:c.commit();v=c.execute('''select v.*,t.nombre cliente,t.ruc,t.telefono cliente_telefono,t.email cliente_email,t.sifen_direccion cliente_direccion,t.sifen_tipo_operacion,t.sifen_naturaleza,cb.banco,cb.numero_cuenta,cb.alias cuenta_alias,tp.nombre terminal_pos from ventas v left join terceros t on t.id=v.cliente_id left join cuentas_bancarias cb on cb.id=v.cuenta_bancaria_id left join terminales_pos tp on tp.id=v.terminal_pos_id where v.id=?''',(venta_id,)).fetchone()
        except Exception as ex:
            _sifen_log('CDC_TEST','ERROR',f'Factura {venta_id}: {ex}')
    c.close();return v,items,inst

@app.get('/ventas/<int:venta_id>/factura')
def factura_venta(venta_id):
    v,items,inst=_factura_venta_data(venta_id)
    if not v: flash('Factura no encontrada.'); return redirect('/ventas/carga')
    cc=db(); cfg=cc.execute('select * from sifen_config where id=1').fetchone(); cc.close(); sifen_produccion=bool(cfg and str(cfg['ambiente'] or '').upper()=='PRODUCCION' and int(cfg['produccion_habilitada'] or 0)); return render_template('invoice_sale.html',v=v,items=items,inst=inst,sifen_produccion=sifen_produccion)

@app.get('/ventas/<int:venta_id>/factura/pdf')
def factura_venta_pdf(venta_id):
    """KuDE de Factura Electrónica: formato visual compacto basado en el modelo aportado por el usuario.
    No cambia datos fiscales ni lógica SIFEN; solamente la representación gráfica PDF.
    """
    from io import BytesIO
    from flask import send_file
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,Image,KeepTogether
    v,items,inst=_factura_venta_data(venta_id)
    if not v: flash('Factura no encontrada.'); return redirect('/ventas/carga')
    c=db()
    try:
        acts=c.execute("select codigo,descripcion from sifen_actividades_economicas where activo=1 order by principal desc,id").fetchall()
        punto=c.execute("select * from sifen_puntos_expedicion where id=?",(v['sifen_punto_id'],)).fetchone() if v['sifen_punto_id'] else None
    except Exception:
        acts=[]; punto=None
    finally:c.close()
    e=_kude_empresa(inst)
    es_dte=bool(v['cdc']) and str(v['estado_sifen'] or '').upper() in ('APROBADO','APROBADA','ACEPTADO','ACEPTADA','DTE','APROBADO_SIFEN')
    b=BytesIO(); doc=SimpleDocTemplate(b,pagesize=A4,rightMargin=7*mm,leftMargin=7*mm,topMargin=7*mm,bottomMargin=7*mm)
    st=getSampleStyleSheet()
    normal=ParagraphStyle('kNormal',parent=st['Normal'],fontName='Helvetica',fontSize=7.2,leading=8.6,textColor=colors.black)
    small=ParagraphStyle('kSmall',parent=normal,fontSize=6.4,leading=7.4)
    tiny=ParagraphStyle('kTiny',parent=normal,fontSize=5.8,leading=6.7)
    center=ParagraphStyle('kCenter',parent=normal,alignment=TA_CENTER)
    title=ParagraphStyle('kTitle',parent=normal,fontName='Helvetica-Bold',fontSize=10,leading=11,alignment=TA_CENTER)
    big=ParagraphStyle('kBig',parent=normal,fontName='Helvetica-Bold',fontSize=11,leading=13,alignment=TA_CENTER)
    story=[]

    # Franja superior como el modelo KuDE de referencia.
    top=Table([[Paragraph('<b>KuDE de Factura Electrónica</b>',center)]],colWidths=[196*mm])
    top.setStyle(TableStyle([('BOX',(0,0),(-1,-1),.8,colors.black),('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#f2f2f2')),('TOPPADDING',(0,0),(-1,-1),2.5),('BOTTOMPADDING',(0,0),(-1,-1),2.5)]));story.append(top)

    logo=logo_path_actual(); left=[]
    if os.path.exists(logo): left.append(Image(logo,width=42*mm,height=18*mm))
    left.append(Paragraph('<b>'+str(e['nombre'])+'</b>',title))
    acttxt='<br/>'.join([str(a['descripcion'] or '') for a in acts[:3]]) or ''
    if acttxt:left.append(Paragraph(acttxt,small))
    ubic=' - '.join([x for x in [str(e['direccion'] or '').strip(),str(e['ciudad'] or '').strip(),str(e['departamento'] or '').strip()] if x])
    if ubic:left.append(Paragraph(ubic,small))
    left.append(Paragraph('<b>Teléfono:</b> '+str(e['telefono'] or '-')+'<br/><b>Email:</b> '+str(e['email'] or '-'),small))
    timbrado=(punto['timbrado'] if punto and 'timbrado' in punto.keys() and punto['timbrado'] else e['timbrado'])
    est=str(v['establecimiento'] or (punto['establecimiento'] if punto else '') or '').zfill(3)
    pexp=str(v['punto_expedicion'] or (punto['punto_expedicion'] if punto else '') or '').zfill(3)
    nro=str(v['numero'] or v['id'])
    # Si el número almacenado ya contiene establecimiento-punto, no se vuelve a prefijar.
    nro_imp=nro if '-' in nro else f"{est}-{pexp}-{str(nro).zfill(7)}"
    right=Paragraph(f"<b>RUC:</b>&nbsp;&nbsp; {e['ruc']}<br/><b>Timbrado Nº:</b>&nbsp;&nbsp; {timbrado or '-'}<br/><b>Inicio de vigencia:</b>&nbsp;&nbsp; {e['inicio'] or '-'}<br/><b>Código interno:</b>&nbsp;&nbsp; {v['id']}<br/><br/><b>FACTURA ELECTRÓNICA</b><br/><font size='11'><b>N°: {nro_imp}</b></font>",normal)
    head=Table([[left,right]],colWidths=[133*mm,63*mm])
    head.setStyle(TableStyle([('BOX',(0,0),(-1,-1),.8,colors.black),('LINEBEFORE',(1,0),(1,0),.8,colors.black),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6),('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4)]));story += [head,Spacer(1,1.2*mm)]

    # Datos del receptor/operación en dos columnas, conservando toda la información ya existente.
    tipo_tx=('B2B' if str(v['sifen_tipo_operacion'] or '')=='1' else 'B2C' if str(v['sifen_tipo_operacion'] or '')=='2' else 'B2G' if str(v['sifen_tipo_operacion'] or '')=='3' else 'B2F' if str(v['sifen_tipo_operacion'] or '')=='4' else '-')
    operacion='Prestación de servicios / venta' if items else 'Venta'
    fecha=str(v['fecha'] or '-')
    left_cli=Paragraph(f"<b>Nombre o Razón Social:</b>&nbsp;&nbsp; {v['cliente'] or '-'}<br/><b>RUC/Documento de Identidad Nº:</b>&nbsp;&nbsp; {v['ruc'] or '-'}<br/><b>Fecha y hora:</b>&nbsp;&nbsp; {fecha}<br/><b>Dirección:</b>&nbsp;&nbsp; {v['cliente_direccion'] or '-'}<br/><b>Teléfono:</b>&nbsp;&nbsp; {v['cliente_telefono'] or '-'}<br/><b>Correo Electrónico:</b>&nbsp;&nbsp; {v['cliente_email'] or '-'}",normal)
    right_cli=Paragraph(f"<b>Condición de Venta:</b>&nbsp;&nbsp; {v['condicion_venta'] or '-'}<br/><b>Moneda:</b>&nbsp;&nbsp; {v['moneda'] or 'PYG'}<br/><b>Tipo de Cambio:</b>&nbsp;&nbsp; {v['tipo_cambio'] or 1}<br/><b>Operación:</b>&nbsp;&nbsp; {operacion}<br/><b>Tipo de Transacción:</b>&nbsp;&nbsp; {tipo_tx}<br/><b>N° Venta:</b>&nbsp;&nbsp; {v['id']}",normal)
    cli=Table([[left_cli,right_cli]],colWidths=[116*mm,80*mm])
    cli.setStyle(TableStyle([('BOX',(0,0),(-1,-1),.8,colors.black),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6),('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4)]));story += [cli,Spacer(1,1.2*mm)]

    # Detalle alto, con la misma disposición visual del KuDE modelo.
    hdr=[Paragraph('<b>Cod.</b>',center),Paragraph('<b>Descripción</b>',center),Paragraph('<b>UNI</b>',center),Paragraph('<b>Cantidad</b>',center),Paragraph('<b>Precio Unitario</b>',center),Paragraph('<b>Descuento</b>',center),Paragraph('<b>Exentas</b>',center),Paragraph('<b>5%</b>',center),Paragraph('<b>10%</b>',center)]
    data=[hdr]; ex=base5=base10=0.0
    for x in items:
        pct=float(x['iva_pct'] or 0); total=float(x['total'] or 0); exv=total if pct==0 else 0; v5=total if pct==5 else 0; v10=total if pct==10 else 0; ex+=exv;base5+=v5;base10+=v10
        data.append([str(x['codigo'] or ''),Paragraph(str(x['nombre'] or ''),small),'UNI',f"{float(x['cantidad'] or 0):,.2f}",f"{float(x['precio'] or 0):,.0f}",'0',f"{exv:,.0f}" if exv else '',f"{v5:,.0f}" if v5 else '',f"{v10:,.0f}" if v10 else ''])
    # Filas vacías para conservar la apariencia vertical del modelo sin alterar datos.
    min_rows=15
    while len(data)<min_rows:data.append(['','','','','','','','',''])
    widths=[13*mm,52*mm,10*mm,16*mm,25*mm,20*mm,20*mm,20*mm,20*mm]
    detail=Table(data,colWidths=widths,repeatRows=1,rowHeights=[8*mm]+[5.4*mm]*(len(data)-1))
    detail.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#eeeeee')),('GRID',(0,0),(-1,-1),.45,colors.black),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),6.4),('ALIGN',(0,0),(0,-1),'CENTER'),('ALIGN',(2,0),(-1,-1),'RIGHT'),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),2),('RIGHTPADDING',(0,0),(-1,-1),2),('TOPPADDING',(0,1),(-1,-1),2)]));story.append(detail)

    total=float(v['total'] or 0); descuento=0.0
    totals=[
      [Paragraph('<b>Sub Total:</b>',small),'','','','','',f"{ex:,.0f}" if ex else '',f"{base5:,.0f}" if base5 else '',f"{base10:,.0f}" if base10 else ''],
      [Paragraph('<b>Descuento global:</b>',small),'','','','','','','',f"- {descuento:,.0f}"],
      [Paragraph('<b>Total a pagar</b>&nbsp;&nbsp; '+monto_letras(total),small),'','','','','','','',f"{total:,.0f}"],
      [Paragraph('<b>Total en guaraníes</b>',small),'','','','','','','',f"{float(v['total_pyg'] or total):,.0f}"],
      [Paragraph('<b>Liquidación IVA</b>',small),'','',Paragraph('<b>(5%)</b> '+f"{float(v['iva_5'] or 0):,.0f}",small),'','',Paragraph('<b>(10%)</b> '+f"{float(v['iva_10'] or 0):,.0f}",small),'',Paragraph('<b>Total IVA</b> '+f"{float(v['iva'] or 0):,.0f}",small)]
    ]
    tt=Table(totals,colWidths=widths)
    tt.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.45,colors.black),('SPAN',(0,0),(5,0)),('SPAN',(0,1),(7,1)),('SPAN',(0,2),(7,2)),('SPAN',(0,3),(7,3)),('SPAN',(0,4),(2,4)),('SPAN',(3,4),(5,4)),('SPAN',(6,4),(7,4)),('ALIGN',(-1,0),(-1,-1),'RIGHT'),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LEFTPADDING',(0,0),(-1,-1),3),('RIGHTPADDING',(0,0),(-1,-1),3),('TOPPADDING',(0,0),(-1,-1),2.5),('BOTTOMPADDING',(0,0),(-1,-1),2.5)]));story.append(tt)

    # Bloque CDC/QR como el modelo. QR siempre deriva del dCarQR real guardado en la factura.
    qr_url=(v['qr_sifen'] if 'qr_sifen' in v.keys() else None) or None
    qr=_kude_qr_flowable(qr_url,27) if qr_url else None
    if es_dte and v['cdc']:
        consulta=(qr_url or '')
        msg=f"<b>Consulte esta Factura Electrónica con el número impreso abajo:</b><br/>{consulta}<br/><b>CDC: {v['cdc']}</b><br/><br/><b>ESTE DOCUMENTO ES UNA REPRESENTACIÓN GRÁFICA DE UN DOCUMENTO ELECTRÓNICO (XML)</b><br/><font size='6'>Si su documento electrónico presenta algún error, podrá solicitar la modificación/cancelación conforme a las reglas vigentes de SIFEN.</font>"
    elif v['cdc']:
        msg=f"<b>CDC DE PRUEBA: {v['cdc']}</b><br/><b>SIFEN TEST · NO APROBADO · SIN VALOR FISCAL</b><br/><font size='6'>Este documento todavía no constituye un DTE aprobado por SIFEN.</font>"
    else:
        msg="<b>DOCUMENTO PENDIENTE DE VALIDACIÓN SIFEN</b><br/><font size='6'>El QR y la identificación como KuDE/DTE se habilitan con el CDC y la respuesta correspondiente de SIFEN.</font>"
    foot=Table([[Paragraph(msg,small),qr or Paragraph('',small)]],colWidths=[165*mm,31*mm])
    foot.setStyle(TableStyle([('BOX',(0,0),(-1,-1),.8,colors.black),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5),('TOPPADDING',(0,0),(-1,-1),4),('BOTTOMPADDING',(0,0),(-1,-1),4)]));story += [Spacer(1,1.2*mm),foot]
    if e['pie']: story.append(Paragraph(str(e['pie']),tiny))
    doc.build(story);b.seek(0);return send_file(b,mimetype='application/pdf',as_attachment=False,download_name=f"KuDE_Factura_{v['numero'] or venta_id}.pdf")


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
    # V13.9.99: Empresa e Identidad se unifica con Facturación Electrónica.
    # Se conserva esta URL solo como compatibilidad con marcadores/enlaces antiguos.
    return redirect('/configuracion/sifen#empresa')
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
                try:
                    from PIL import Image as PILImage
                    logo.stream.seek(0); imagen=PILImage.open(logo.stream); imagen.verify(); logo.stream.seek(0)
                    nombre='logo_empresa'+ext
                    destino=os.path.join(BRANDING_DIR,nombre)
                    # Mantener una sola imagen institucional activa para documentos.
                    for anterior in Path(BRANDING_DIR).glob('logo_empresa.*'):
                        try: anterior.unlink()
                        except OSError: pass
                    logo.save(destino)
                    c.execute('update institucion_config set logo_archivo=? where id=1',(nombre,))
                except Exception:
                    flash('Logo no actualizado: el archivo no es una imagen válida.')
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

# ===== V13.9.85: Depósitos bancarios =====
def init_v13985_depositos_bancarios():
    c=db()
    c.execute("""CREATE TABLE IF NOT EXISTS depositos_bancarios(
      id INTEGER PRIMARY KEY, fecha TEXT NOT NULL, cuenta_bancaria_id INTEGER NOT NULL,
      moneda TEXT NOT NULL DEFAULT 'PYG', tipo_cambio REAL NOT NULL DEFAULT 1,
      importe REAL NOT NULL, importe_pyg REAL NOT NULL, tipo_deposito TEXT NOT NULL DEFAULT 'EFECTIVO',
      origen TEXT NOT NULL DEFAULT 'CAJA', referencia TEXT, concepto TEXT, observaciones TEXT,
      estado TEXT NOT NULL DEFAULT 'CONFIRMADO', movimiento_financiero_id INTEGER,
      asiento_id INTEGER, creado_por TEXT, creado_en TEXT, anulado_por TEXT, anulado_en TEXT
    )""")
    c.execute("insert or ignore into schema_migrations(version,aplicado_en) values('13.9.85-depositos-bancarios',?)",(now(),))
    c.commit();c.close()
init_v13985_depositos_bancarios()

@app.route('/bancos/depositos',methods=['GET','POST'])
def depositos_bancarios():
    c=db()
    if request.method=='POST':
        try:
            f=request.form; fecha=f['fecha']; cuenta_id=int(f['cuenta_bancaria_id']); mon=(f.get('moneda') or 'PYG').upper()
            imp=float(f.get('importe') or 0); tc=tc_fecha(c,fecha,mon,f.get('tipo_cambio'))
            if imp<=0: raise ValueError('El importe del depósito debe ser mayor a cero.')
            b=c.execute('select * from cuentas_bancarias where id=? and activo=1',(cuenta_id,)).fetchone()
            if not b: raise ValueError('La cuenta bancaria seleccionada no existe o está inactiva.')
            if not b['cuenta_contable']: raise ValueError('La cuenta bancaria no tiene cuenta contable vinculada. Configure Cuentas Bancarias.')
            origen=(f.get('origen') or 'CAJA').upper(); tipo=(f.get('tipo_deposito') or 'EFECTIVO').upper()
            if origen not in ('CAJA','COBRANZA','OTRO'): raise ValueError('Origen del depósito inválido.')
            pyg=imp*tc; concepto=(f.get('concepto') or 'Depósito bancario').strip(); ref=(f.get('referencia') or '').strip(); obs=(f.get('observaciones') or '').strip()
            cur=c.execute("""insert into depositos_bancarios(fecha,cuenta_bancaria_id,moneda,tipo_cambio,importe,importe_pyg,tipo_deposito,origen,referencia,concepto,observaciones,estado,creado_por,creado_en)
              values(?,?,?,?,?,?,?,?,?,?,?,'CONFIRMADO',?,?)""",(fecha,cuenta_id,mon,tc,imp,pyg,tipo,origen,ref,concepto,obs,session.get('user'),now()))
            did=cur.lastrowid
            mov=c.execute("insert into caja_banco(fecha,tipo,medio,moneda,tipo_cambio,importe,importe_pyg,concepto,origen_tipo,origen_id,cuenta_bancaria_id) values(?,'INGRESO','DEPOSITO_BANCARIO',?,?,?,?,?,'DEPOSITO_BANCARIO',?,?)",(fecha,mon,tc,imp,pyg,concepto,did,cuenta_id)).lastrowid
            cfg=c.execute('select * from tesoreria_config where id=1').fetchone(); contrapartida=(cfg['cuenta_caja'] if cfg else '1.1.01')
            aid=asiento(c,fecha,concepto,'DEPOSITO_BANCARIO',did,mon,tc,[(b['cuenta_contable'],pyg,0,imp,'Ingreso a banco'),(contrapartida,0,pyg,imp,'Salida/depósito desde caja')])
            c.execute('update depositos_bancarios set movimiento_financiero_id=?,asiento_id=? where id=?',(mov,aid,did))
            c.commit();c.close();audit('DEPOSITO_BANCARIO',f'Depósito {did} / {imp} {mon} / cuenta {cuenta_id}');flash('Depósito bancario registrado correctamente.');return redirect('/bancos/depositos')
        except Exception as ex:
            c.rollback();c.close();flash('No se pudo registrar el depósito: '+str(ex));return redirect('/bancos/depositos')
    desde=request.args.get('desde') or '';hasta=request.args.get('hasta') or '';cuenta=request.args.get('cuenta_bancaria_id') or ''
    sql='select d.*,b.banco,b.alias,b.numero_cuenta from depositos_bancarios d join cuentas_bancarias b on b.id=d.cuenta_bancaria_id where 1=1';ps=[]
    if desde: sql+=' and d.fecha>=?';ps.append(desde)
    if hasta: sql+=' and d.fecha<=?';ps.append(hasta)
    if cuenta: sql+=' and d.cuenta_bancaria_id=?';ps.append(int(cuenta))
    sql+=' order by d.fecha desc,d.id desc'
    rows=c.execute(sql,ps).fetchall();cuentas=c.execute('select * from cuentas_bancarias where activo=1 order by banco,alias').fetchall();c.close()
    return render_template('bank_deposits.html',rows=rows,cuentas=cuentas,desde=desde,hasta=hasta,cuenta_sel=cuenta)

@app.post('/bancos/depositos/<int:did>/anular')
def deposito_bancario_anular(did):
    c=db();d=c.execute('select * from depositos_bancarios where id=?',(did,)).fetchone()
    if not d:c.close();flash('Depósito no encontrado.');return redirect('/bancos/depositos')
    if d['estado']=='ANULADO':c.close();flash('El depósito ya está anulado.');return redirect('/bancos/depositos')
    if d['movimiento_financiero_id']:c.execute('delete from caja_banco where id=?',(d['movimiento_financiero_id'],))
    if d['asiento_id']:c.execute("update asientos set estado='ANULADO' where id=?",(d['asiento_id'],))
    c.execute("update depositos_bancarios set estado='ANULADO',anulado_por=?,anulado_en=? where id=?",(session.get('user'),now(),did));c.commit();c.close()
    audit('ANULAR_DEPOSITO_BANCARIO',str(did));flash('Depósito bancario anulado. El movimiento bancario fue revertido.');return redirect('/bancos/depositos')

ROUTE_MODULE.update({'depositos_bancarios':'FINANZAS','deposito_bancario_anular':'FINANZAS'})

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



# ===== V13.9.32: Backups exclusivamente manuales =====
def _backup_manual_files():
 raiz=os.path.join(DATA_DIR,'backups','manual');os.makedirs(raiz,exist_ok=True)
 out=[]
 for f in Path(raiz).glob('santa_clara_manual_*.db'):
  try:out.append({'name':f.name,'size':f.stat().st_size,'mtime':datetime.datetime.fromtimestamp(f.stat().st_mtime).strftime('%d/%m/%Y %H:%M:%S')})
  except OSError:pass
 return sorted(out,key=lambda x:x['name'],reverse=True)

@app.route('/seguridad/backups',methods=['GET','POST'])
def backups_manuales():
 if not (user_has('USUARIOS','ADMINISTRAR') or user_has('CONFIG_SANATORIO','EDITAR')):
  flash('No tiene permiso para administrar backups.');return redirect('/')
 raiz=os.path.join(DATA_DIR,'backups','manual');os.makedirs(raiz,exist_ok=True)
 if request.method=='POST':
  try:
   total,used,free=shutil.disk_usage(DATA_DIR);dbsize=os.path.getsize(DB) if os.path.exists(DB) else 0
   if free < dbsize + 100*1024*1024: raise RuntimeError('No hay espacio libre suficiente para crear una copia manual. Libere espacio antes de continuar.')
   destino=os.path.join(raiz,'santa_clara_manual_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'.db')
   src=sqlite3.connect(DB);dst=sqlite3.connect(destino)
   try:src.backup(dst)
   finally:dst.close();src.close()
   audit('BACKUP_MANUAL',os.path.basename(destino));flash('Backup manual creado correctamente.')
  except Exception as e:flash('No se pudo crear el backup: '+str(e))
  return redirect('/seguridad/backups')
 total,used,free=shutil.disk_usage(DATA_DIR);return render_template('manual_backups.html',files=_backup_manual_files(),free=free,total=total)

@app.get('/seguridad/backups/descargar/<path:nombre>')
def backup_manual_descargar(nombre):
 if not (user_has('USUARIOS','ADMINISTRAR') or user_has('CONFIG_SANATORIO','EDITAR')):return redirect('/')
 from flask import send_from_directory
 if '/' in nombre or '\\' in nombre:return ('Archivo inválido',400)
 return send_from_directory(os.path.join(DATA_DIR,'backups','manual'),nombre,as_attachment=True)

@app.post('/seguridad/backups/eliminar/<path:nombre>')
def backup_manual_eliminar(nombre):
 if not (user_has('USUARIOS','ADMINISTRAR') or user_has('CONFIG_SANATORIO','EDITAR')):return redirect('/')
 if '/' not in nombre and '\\' not in nombre:
  f=os.path.join(DATA_DIR,'backups','manual',nombre)
  try:os.remove(f);audit('ELIMINAR_BACKUP_MANUAL',nombre);flash('Backup eliminado.')
  except OSError:flash('No se pudo eliminar el backup.')
 return redirect('/seguridad/backups')

ROUTE_MODULE.update({'backups_manuales':'CONFIG_SANATORIO','backup_manual_descargar':'CONFIG_SANATORIO','backup_manual_eliminar':'CONFIG_SANATORIO'})


# ===== V13.9.30: Caja central - localizar preventa/remision/cuenta completa =====
def init_v13930_caja_central():
 c=db()
 try:
  cols=[r[1] for r in c.execute('pragma table_info(venta_items)').fetchall()]
  if 'descripcion' not in cols:c.execute('alter table venta_items add column descripcion TEXT')
  c.execute("create table if not exists remisiones_internas(id integer primary key,numero text unique,fecha text not null,paciente_id integer not null,admision_id integer,estado text default 'PENDIENTE',observacion text,creado_por text,creado_en text)")
  c.execute("insert or ignore into schema_migrations(version,aplicado_en) values('13.9.30-caja-central',?)",(now(),));c.commit()
 finally:c.close()
init_v13930_caja_central()

@app.get('/ventas/caja-central')
def caja_central_facturacion():
 q=(request.args.get('q') or '').strip();c=db();cuentas=[];consultas=[]
 if q:
  like='%'+q+'%';digits=''.join(ch for ch in q if ch.isdigit())
  sql="""select distinct a.id admision_id,a.fecha,a.tipo,a.estado,p.id paciente_id,p.nombre paciente,p.documento,p.telefono,p.tercero_id,coalesce((select sum(cp.total_pyg) from cargos_paciente cp where cp.admision_id=a.id and coalesce(cp.facturado,0)=0),0) saldo_pyg,coalesce(r.numero,'REM-'||a.id) remision from admisiones a join pacientes p on p.id=a.paciente_id left join remisiones_internas r on r.admision_id=a.id and r.estado='PENDIENTE' where (p.nombre like ? or coalesce(p.documento,'') like ? or coalesce(r.numero,'') like ? or cast(a.id as text)=?) and exists(select 1 from cargos_paciente cp where cp.admision_id=a.id and coalesce(cp.facturado,0)=0) order by a.id desc limit 100"""
  cuentas=c.execute(sql,(like,like,like,digits or q)).fetchall()
  consultas=c.execute("""select k.id pendiente_id,k.consulta_id,k.fecha,k.descripcion,k.importe_pyg,p.id paciente_id,p.nombre paciente,p.documento,p.telefono,p.tercero_id,m.nombre medico from caja_pendientes_consultorio k join pacientes p on p.id=k.paciente_id left join consultas co on co.id=k.consulta_id left join medicos m on m.id=co.medico_id where k.estado='PENDIENTE' and (p.nombre like ? or coalesce(p.documento,'') like ? or cast(k.consulta_id as text)=?) order by k.id desc limit 100""",(like,like,digits or q)).fetchall()
 else:
  consultas=c.execute("""select k.id pendiente_id,k.consulta_id,k.fecha,k.descripcion,k.importe_pyg,p.id paciente_id,p.nombre paciente,p.documento,p.telefono,p.tercero_id,m.nombre medico from caja_pendientes_consultorio k join pacientes p on p.id=k.paciente_id left join consultas co on co.id=k.consulta_id left join medicos m on m.id=co.medico_id where k.estado='PENDIENTE' order by k.id desc limit 100""").fetchall()
 c.close();return render_template('cash_account_locator.html',q=q,cuentas=cuentas,consultas=consultas)

@app.get('/ventas/caja-central/<int:aid>')
def caja_central_detalle(aid):
 c=db();a=c.execute('select a.*,p.nombre paciente,p.documento,p.telefono,p.tercero_id from admisiones a join pacientes p on p.id=a.paciente_id where a.id=?',(aid,)).fetchone()
 if not a:c.close();flash('Cuenta no encontrada.');return redirect('/ventas/caja-central')
 items=c.execute('select * from cargos_paciente where admision_id=? and coalesce(facturado,0)=0 order by id',(aid,)).fetchall();total=sum(float(x['total_pyg'] or 0) for x in items);rem=c.execute("select * from remisiones_internas where admision_id=? and estado='PENDIENTE' order by id desc limit 1",(aid,)).fetchone()
 if not rem:
  numero='REM-'+str(aid);c.execute('insert or ignore into remisiones_internas(numero,fecha,paciente_id,admision_id,creado_por,creado_en) values(?,?,?,?,?,?)',(numero,a['fecha'],a['paciente_id'],aid,session.get('user'),now()));c.commit();rem=c.execute('select * from remisiones_internas where numero=?',(numero,)).fetchone()
 puntos=[p for p in c.execute("select * from sifen_puntos_expedicion order by predeterminado desc,establecimiento,punto_expedicion").fetchall() if _flag_activo(p['activo']) and _flag_activo(p['autorizado_dnit']) and _flag_activo(p['factura_electronica'])];c.close();return render_template('cash_account_detail.html',a=a,items=items,total=total,rem=rem,puntos=puntos)

@app.post('/ventas/caja-central/<int:aid>/facturar')
def caja_central_facturar(aid):
 c=db()
 try:
  a=c.execute('select a.*,p.tercero_id,p.nombre paciente from admisiones a join pacientes p on p.id=a.paciente_id where a.id=?',(aid,)).fetchone()
  if not a or not a['tercero_id']:raise ValueError('El paciente debe estar vinculado a un cliente/tercero para facturar.')
  items=c.execute('select * from cargos_paciente where admision_id=? and coalesce(facturado,0)=0 order by id',(aid,)).fetchall()
  if not items:raise ValueError('La cuenta no tiene cargos pendientes para facturar.')
  fecha=request.form.get('fecha') or datetime.date.today().isoformat();numero,punto_factura=_siguiente_numero_factura(c,_punto_id_caja_actual(c,'RECEPCION',True));medio=(request.form.get('forma_cobro') or 'Efectivo').strip()
  total=sum(float(x['total_pyg'] or 0) for x in items)
  if medio=='Efectivo' and not caja_abierta(c):raise ValueError('Debe abrir la caja antes de facturar una cuenta en efectivo.')
  vid=c.execute("insert into ventas(fecha,cliente_id,numero,moneda,tipo_cambio,gravado,iva,exento,total,total_pyg,gravado_10,iva_10,gravado_5,iva_5,exento_iva,condicion_venta,forma_cobro,entrega_inicial) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(fecha,a['tercero_id'],numero,'PYG',1,total,0,0,total,total,total,0,0,0,0,'CONTADO',medio,total)).lastrowid
  ap_fact=caja_abierta(c);c.execute('update ventas set sifen_punto_id=?,establecimiento=?,punto_expedicion=?,caja_id=?,origen_area=? where id=?',(punto_factura['id'],punto_factura['establecimiento'],punto_factura['punto_expedicion'],ap_fact['caja_id'] if ap_fact else None,str(a['tipo'] or 'OTROS'),vid))
  for x in items:c.execute('insert into venta_items(venta_id,producto_id,cantidad,precio,total,total_pyg,costo_pyg,iva_pct,descripcion) values(?,?,?,?,?,?,?,?,?)',(vid,None,float(x['cantidad'] or 1),float(x['precio'] or 0),float(x['total_pyg'] or 0),float(x['total_pyg'] or 0),0,0,x['descripcion']))
  c.execute('update cargos_paciente set facturado=1 where admision_id=? and coalesce(facturado,0)=0',(aid,));c.execute("update remisiones_internas set estado='FACTURADA' where admision_id=? and estado='PENDIENTE'",(aid,));c.execute('insert into cxc(venta_id,tercero_id,moneda,tipo_cambio_origen,importe,saldo,importe_pyg,estado) values(?,?,?,?,?,?,?,?)',(vid,a['tercero_id'],'PYG',1,total,0,0,'PAGADO'));c.execute('insert into caja_banco(fecha,tipo,medio,moneda,tipo_cambio,importe,importe_pyg,concepto,origen_tipo,origen_id) values(?,?,?,?,?,?,?,?,?,?)',(fecha,'INGRESO',medio,'PYG',1,total,total,'Cobro cuenta completa '+a['paciente'],'VENTA',vid))
  if medio=='Efectivo':
   ap=caja_abierta(c);fid=c.execute("select id from formas_cobro where nombre='Efectivo'").fetchone();c.execute("insert into movimientos_caja(apertura_id,fecha,tipo,forma_cobro_id,concepto,importe_pyg,origen_tipo,origen_id,usuario) values(?,?,'INGRESO',?,?,?,?,?,?)",(ap['id'],now(),fid['id'] if fid else None,'Cobro cuenta completa '+a['paciente'],total,'VENTA',vid,session.get('user')))
  asiento(c,fecha,'Factura caja cuenta '+numero,'VENTA',vid,'PYG',1,[('1.1.01',total,0,total,'Cobro'),('4.1.02',0,total,total,'Servicios')]);_generar_cdc_test_venta(c,vid,fecha,numero);c.commit();audit('FACTURAR_CUENTA_CAJA',f'{aid}:{vid}');flash('Cuenta completa facturada correctamente. Factura '+numero);return redirect(f'/ventas/{vid}/factura')
 except Exception as e:c.rollback();flash('No se pudo facturar la cuenta: '+str(e));return redirect(f'/ventas/caja-central/{aid}')
 finally:c.close()

@app.get('/ventas/caja-central/consultorio/<int:pid>')
def caja_central_consultorio_detalle(pid):
 c=db();x=c.execute("select k.*,p.nombre paciente,p.documento,p.telefono,p.tercero_id,m.nombre medico from caja_pendientes_consultorio k join pacientes p on p.id=k.paciente_id left join consultas co on co.id=k.consulta_id left join medicos m on m.id=co.medico_id where k.id=? and k.estado='PENDIENTE'",(pid,)).fetchone();puntos=[p for p in c.execute("select * from sifen_puntos_expedicion order by predeterminado desc,establecimiento,punto_expedicion").fetchall() if _flag_activo(p['activo']) and _flag_activo(p['autorizado_dnit']) and _flag_activo(p['factura_electronica'])];c.close()
 if not x:flash('La prestación ya fue facturada o no existe.');return redirect('/ventas/caja-central')
 return render_template('cash_consult_detail.html',x=x,puntos=puntos)

@app.post('/ventas/caja-central/consultorio/<int:pid>/facturar')
def caja_central_consultorio_facturar(pid):
 c=db()
 try:
  x=c.execute("select k.*,p.nombre paciente,p.tercero_id from caja_pendientes_consultorio k join pacientes p on p.id=k.paciente_id where k.id=? and k.estado='PENDIENTE'",(pid,)).fetchone()
  if not x:raise ValueError('La prestación ya fue procesada o no existe.')
  if not x['tercero_id']:raise ValueError('El paciente debe estar vinculado a un cliente/tercero para facturar.')
  fecha=request.form.get('fecha') or datetime.date.today().isoformat();numero,punto_factura=_siguiente_numero_factura(c,_punto_id_caja_actual(c,'RECEPCION',True));medio=(request.form.get('forma_cobro') or 'Efectivo').strip();total=float(x['importe_pyg'] or 0)
  if medio=='Efectivo' and not caja_abierta(c):raise ValueError('Debe abrir la caja antes de cobrar en efectivo.')
  base,iva=desglosar_iva_incluido(total,10)
  vid=c.execute("insert into ventas(fecha,cliente_id,numero,moneda,tipo_cambio,gravado,iva,exento,total,total_pyg,gravado_10,iva_10,gravado_5,iva_5,exento_iva,condicion_venta,forma_cobro,entrega_inicial) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(fecha,x['tercero_id'],numero,'PYG',1,base,iva,0,total,total,base,iva,0,0,0,'CONTADO',medio,total)).lastrowid
  ap_fact=caja_abierta(c);c.execute('update ventas set sifen_punto_id=?,establecimiento=?,punto_expedicion=?,caja_id=?,origen_area=? where id=?',(punto_factura['id'],punto_factura['establecimiento'],punto_factura['punto_expedicion'],ap_fact['caja_id'] if ap_fact else None,'CONSULTORIO',vid))
  c.execute('insert into venta_items(venta_id,producto_id,cantidad,precio,total,total_pyg,costo_pyg,iva_pct,descripcion) values(?,?,?,?,?,?,?,?,?)',(vid,None,1,total,total,total,0,10,x['descripcion']))
  c.execute("update caja_pendientes_consultorio set estado='FACTURADO',venta_id=?,procesado_en=? where id=?",(vid,now(),pid));c.execute('update consultas set facturada=1,venta_id=? where id=?',(vid,x['consulta_id']))
  c.execute('insert into cxc(venta_id,tercero_id,moneda,tipo_cambio_origen,importe,saldo,importe_pyg,estado) values(?,?,?,?,?,?,?,?)',(vid,x['tercero_id'],'PYG',1,total,0,0,'PAGADO'))
  c.execute('insert into caja_banco(fecha,tipo,medio,moneda,tipo_cambio,importe,importe_pyg,concepto,origen_tipo,origen_id) values(?,?,?,?,?,?,?,?,?,?)',(fecha,'INGRESO',medio,'PYG',1,total,total,'Cobro consultorio '+x['paciente'],'VENTA',vid))
  if medio=='Efectivo':
   ap=caja_abierta(c);fid=c.execute("select id from formas_cobro where nombre='Efectivo'").fetchone();c.execute("insert into movimientos_caja(apertura_id,fecha,tipo,forma_cobro_id,concepto,importe_pyg,origen_tipo,origen_id,usuario) values(?,?,'INGRESO',?,?,?,?,?,?)",(ap['id'],now(),fid['id'] if fid else None,'Cobro consultorio '+x['paciente'],total,'VENTA',vid,session.get('user')))
  asiento(c,fecha,'Factura consultorio '+numero,'VENTA',vid,'PYG',1,[('1.1.01',total,0,total,'Cobro'),('4.1.02',0,base,base,'Servicio'),('2.1.02',0,iva,iva,'IVA débito')]);_generar_cdc_test_venta(c,vid,fecha,numero);c.commit();audit('FACTURAR_CONSULTORIO_CAJA',f'{pid}:{vid}');flash('Prestación facturada y cobrada correctamente en Caja.');return redirect(f'/ventas/{vid}/factura')
 except Exception as e:c.rollback();flash('No se pudo facturar: '+str(e));return redirect(f'/ventas/caja-central/consultorio/{pid}')
 finally:c.close()

ROUTE_MODULE.update({'caja_central_facturacion':'CAJA','caja_central_detalle':'CAJA','caja_central_facturar':'FACTURACION','caja_central_consultorio_detalle':'CAJA','caja_central_consultorio_facturar':'FACTURACION'})

# ===== V13.9.31: Arqueo de Caja Diario con PDF =====
def init_v13931_arqueo():
 c=db()
 try:
  c.execute('''CREATE TABLE IF NOT EXISTS arqueos_caja_diarios(
   id INTEGER PRIMARY KEY, apertura_id INTEGER UNIQUE, fecha TEXT, responsable TEXT,
   m50 REAL DEFAULT 0,m100 REAL DEFAULT 0,m500 REAL DEFAULT 0,m1000 REAL DEFAULT 0,
   b2000 REAL DEFAULT 0,b5000 REAL DEFAULT 0,b10000 REAL DEFAULT 0,b20000 REAL DEFAULT 0,b50000 REAL DEFAULT 0,b100000 REAL DEFAULT 0,
   cheques REAL DEFAULT 0,otros REAL DEFAULT 0,
   venta_facturas REAL DEFAULT 0,venta_boletas REAL DEFAULT 0,venta_nc REAL DEFAULT 0,venta_nd REAL DEFAULT 0,
   compra_facturas REAL DEFAULT 0,compra_boletas REAL DEFAULT 0,compra_nc REAL DEFAULT 0,compra_nd REAL DEFAULT 0,
   entregado_admin REAL DEFAULT 0,saldo_siguiente REAL DEFAULT 0,observaciones TEXT,
   efectivo REAL DEFAULT 0,equiv_efectivo REAL DEFAULT 0,documentos REAL DEFAULT 0,resultado_esperado REAL DEFAULT 0,total REAL DEFAULT 0,diferencia REAL DEFAULT 0,
   estado TEXT DEFAULT 'BORRADOR',creado_en TEXT,actualizado_en TEXT)''')
  c.execute("insert or ignore into schema_migrations(version,aplicado_en) values('13.9.31-arqueo-diario-pdf',?)",(now(),));c.commit()
 finally:c.close()
init_v13931_arqueo()

def _arqueo_calc(form, saldo_inicial):
 vals={}
 campos=['m50','m100','m500','m1000','b2000','b5000','b10000','b20000','b50000','b100000','cheques','otros','venta_facturas','venta_boletas','venta_nc','venta_nd','compra_facturas','compra_boletas','compra_nc','compra_nd','entregado_admin','saldo_siguiente']
 for k in campos:
  try: vals[k]=max(0,float(form.get(k) or 0))
  except: vals[k]=0
 efectivo=vals['m50']*50+vals['m100']*100+vals['m500']*500+vals['m1000']*1000+vals['b2000']*2000+vals['b5000']*5000+vals['b10000']*10000+vals['b20000']*20000+vals['b50000']*50000+vals['b100000']*100000
 equiv=vals['cheques']+vals['otros']
 ventas=vals['venta_facturas']+vals['venta_boletas']-vals['venta_nc']+vals['venta_nd']
 compras=vals['compra_facturas']+vals['compra_boletas']-vals['compra_nc']+vals['compra_nd']
 documentos=ventas-compras
 esperado=float(saldo_inicial or 0)+documentos
 total=efectivo+equiv
 vals.update(efectivo=efectivo,equiv_efectivo=equiv,documentos=documentos,resultado_esperado=esperado,total=total,diferencia=total-esperado)
 return vals

@app.route('/ventas/arqueo/<int:apertura_id>',methods=['GET','POST'])
def arqueo_caja_diario(apertura_id):
 c=db();ap=c.execute('select a.*,cx.nombre caja from aperturas_caja a join cajas cx on cx.id=a.caja_id where a.id=?',(apertura_id,)).fetchone()
 if not ap:c.close();flash('Apertura de caja no encontrada.');return redirect('/ventas/recepcion-caja')
 if ap['usuario']!=session.get('user') and not user_has('CAJA','VER'):c.close();return ('Acceso no autorizado',403)
 ar=c.execute('select * from arqueos_caja_diarios where apertura_id=?',(apertura_id,)).fetchone()
 if request.method=='POST':
  v=_arqueo_calc(request.form,ap['saldo_inicial']); estado='FINALIZADO' if request.form.get('accion')=='finalizar' else 'BORRADOR';obs=(request.form.get('observaciones') or '').strip()
  cols=['m50','m100','m500','m1000','b2000','b5000','b10000','b20000','b50000','b100000','cheques','otros','venta_facturas','venta_boletas','venta_nc','venta_nd','compra_facturas','compra_boletas','compra_nc','compra_nd','entregado_admin','saldo_siguiente','efectivo','equiv_efectivo','documentos','resultado_esperado','total','diferencia']
  if ar:
   sets=','.join(k+'=?' for k in cols)+',observaciones=?,estado=?,actualizado_en=?';c.execute('update arqueos_caja_diarios set '+sets+' where apertura_id=?',[v[k] for k in cols]+[obs,estado,now(),apertura_id])
  else:
   names='apertura_id,fecha,responsable,'+','.join(cols)+',observaciones,estado,creado_en,actualizado_en';qs=','.join('?' for _ in names.split(','));c.execute('insert into arqueos_caja_diarios('+names+') values('+qs+')',[apertura_id,datetime.date.today().isoformat(),ap['usuario']]+[v[k] for k in cols]+[obs,estado,now(),now()])
  if estado=='FINALIZADO':
   c.execute("update aperturas_caja set fecha_cierre=coalesce(fecha_cierre,?),total_sistema=?,total_declarado=?,diferencia=?,estado='CERRADA' where id=?",(now(),v['resultado_esperado'],v['total'],v['diferencia'],apertura_id))
  c.commit();flash('Arqueo '+('finalizado' if estado=='FINALIZADO' else 'guardado')+' correctamente.');c.close();return redirect('/ventas/arqueo/'+str(apertura_id))
 # sugerir ventas/compras del turno solo la primera vez
 suger={}
 if not ar:
  fi=ap['fecha_apertura'][:10]
  suger['venta_facturas']=c.execute('select coalesce(sum(total_pyg),0) from ventas where fecha>=?',(fi,)).fetchone()[0] or 0
  suger['compra_facturas']=c.execute('select coalesce(sum(total_pyg),0) from compras where fecha>=?',(fi,)).fetchone()[0] or 0
 c.close();return render_template('cash_count_daily.html',ap=ap,ar=ar,suger=suger)

@app.get('/ventas/arqueo/<int:apertura_id>/pdf')
def arqueo_caja_pdf(apertura_id):
 from reportlab.lib.pagesizes import A4
 from reportlab.lib import colors
 from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
 from reportlab.lib.units import mm
 from reportlab.platypus import SimpleDocTemplate,Table,TableStyle,Paragraph,Spacer
 c=db();ap=c.execute('select a.*,cx.nombre caja from aperturas_caja a join cajas cx on cx.id=a.caja_id where a.id=?',(apertura_id,)).fetchone();ar=c.execute('select * from arqueos_caja_diarios where apertura_id=?',(apertura_id,)).fetchone();c.close()
 if not ap or not ar:return ('Arqueo no encontrado',404)
 def gs(x):return 'Gs. {:,.0f}'.format(float(x or 0)).replace(',','.')
 blue=colors.HexColor('#06285f'); pale=colors.HexColor('#d9e8f5'); cream=colors.HexColor('#fff4cc'); st=getSampleStyleSheet();buf=io.BytesIO();doc=SimpleDocTemplate(buf,pagesize=A4,leftMargin=10*mm,rightMargin=10*mm,topMargin=8*mm,bottomMargin=8*mm)
 title=Table([['FORMATO DE ARQUEO DE CAJA DIARIO']],colWidths=[190*mm]);title.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),blue),('TEXTCOLOR',(0,0),(-1,-1),colors.white),('ALIGN',(0,0),(-1,-1),'CENTER'),('FONTNAME',(0,0),(-1,-1),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),12),('BOTTOMPADDING',(0,0),(-1,-1),6),('TOPPADDING',(0,0),(-1,-1),6)]))
 story=([pdf_logo(55,38)] if pdf_logo(55,38) else [])+[title,Spacer(1,4*mm)]
 info=Table([['FECHA:',ar['fecha'],'ARQUEO N°:',str(ar['id'])],['RESPONSABLE DE CAJA',ar['responsable'],'CAJA:',ap['caja']]],colWidths=[38*mm,62*mm,28*mm,62*mm]);info.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.5,colors.grey),('BACKGROUND',(1,0),(1,-1),cream),('BACKGROUND',(3,0),(3,-1),cream),('FONTNAME',(0,0),(0,-1),'Helvetica-Bold'),('FONTNAME',(2,0),(2,-1),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),8)]));story += [info,Spacer(1,4*mm),Paragraph('1.- SALDO INICIAL: <b>'+gs(ap['saldo_inicial'])+'</b>',st['Normal']),Spacer(1,2*mm),Paragraph('2.- EFECTIVO: <b>'+gs(ar['efectivo'])+'</b>',st['Normal'])]
 def den_table(title,rows):
  data=[[title,'',''],['Valor','Cantidad','Total']]+[[gs(v),str(int(ar[k] or 0)),gs((ar[k] or 0)*v)] for k,v in rows];t=Table(data,colWidths=[30*mm,25*mm,35*mm]);t.setStyle(TableStyle([('SPAN',(0,0),(-1,0)),('BACKGROUND',(0,0),(-1,0),blue),('TEXTCOLOR',(0,0),(-1,0),colors.white),('ALIGN',(0,0),(-1,-1),'CENTER'),('BACKGROUND',(0,1),(-1,1),pale),('GRID',(0,0),(-1,-1),.4,colors.grey),('FONTSIZE',(0,0),(-1,-1),7),('FONTNAME',(0,0),(-1,1),'Helvetica-Bold')]));return t
 story += [Spacer(1,2*mm),Table([[den_table('DETALLE DE ARQUEO MONEDAS',[('m50',50),('m100',100),('m500',500),('m1000',1000)]),den_table('DETALLE DE ARQUEO BILLETES',[('b2000',2000),('b5000',5000),('b10000',10000),('b20000',20000),('b50000',50000),('b100000',100000)])]],colWidths=[92*mm,92*mm]),Spacer(1,3*mm),Paragraph('3.- EQUIVALENTE DE EFECTIVO: <b>'+gs(ar['equiv_efectivo'])+'</b> &nbsp;&nbsp; Cheques: '+gs(ar['cheques'])+' &nbsp;&nbsp; Otros: '+gs(ar['otros']),st['Normal']),Spacer(1,3*mm),Paragraph('4.- DOCUMENTOS: <b>'+gs(ar['documentos'])+'</b>',st['Normal'])]
 def docs(title,prefix):
  data=[[title,''],['Facturas',gs(ar[prefix+'_facturas'])],['Boletas de Venta',gs(ar[prefix+'_boletas'])],['Nota de Crédito',gs(ar[prefix+'_nc'])],['Nota de Débito',gs(ar[prefix+'_nd'])]];t=Table(data,colWidths=[55*mm,35*mm]);t.setStyle(TableStyle([('SPAN',(0,0),(-1,0)),('BACKGROUND',(0,0),(-1,0),blue),('TEXTCOLOR',(0,0),(-1,0),colors.white),('GRID',(0,0),(-1,-1),.4,colors.grey),('BACKGROUND',(1,1),(1,-1),cream),('FONTSIZE',(0,0),(-1,-1),7),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold')]));return t
 story += [Spacer(1,2*mm),Table([[docs('VENTAS - INGRESOS','venta'),docs('COMPRAS - EGRESOS','compra')]],colWidths=[92*mm,92*mm]),Spacer(1,4*mm)]
 resumen=[['RESUMEN',''],['SALDO INICIAL',gs(ap['saldo_inicial'])],['DOCUMENTOS',gs(ar['documentos'])],['RESULTADO ESPERADO',gs(ar['resultado_esperado'])],['EFECTIVO',gs(ar['efectivo'])],['EQUIVALENTE DE EFECTIVO',gs(ar['equiv_efectivo'])],['TOTAL',gs(ar['total'])],['DIFERENCIA',gs(ar['diferencia'])],['FALTANTE',gs(abs(ar['diferencia'])) if ar['diferencia']<0 else gs(0)],['SOBRANTE',gs(ar['diferencia']) if ar['diferencia']>0 else gs(0)]];rt=Table(resumen,colWidths=[55*mm,35*mm]);rt.setStyle(TableStyle([('SPAN',(0,0),(-1,0)),('BACKGROUND',(0,0),(-1,0),blue),('TEXTCOLOR',(0,0),(-1,0),colors.white),('GRID',(0,0),(-1,-1),.35,colors.grey),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),7)]))
 obs='<b>OBSERVACIONES:</b><br/>'+((ar['observaciones'] or '').replace('\n','<br/>'))+'<br/><br/>ENTREGADO A ADMINISTRACIÓN '+gs(ar['entregado_admin'])+'<br/>SALDO PARA CAJA DEL SIGUIENTE '+gs(ar['saldo_siguiente']);ot=Table([[Paragraph(obs,st['Normal'])]],colWidths=[90*mm],rowHeights=[48*mm]);ot.setStyle(TableStyle([('BOX',(0,0),(-1,-1),.5,colors.grey),('VALIGN',(0,0),(-1,-1),'TOP')]))
 story += [Table([[rt,ot]],colWidths=[92*mm,92*mm]),Spacer(1,4*mm),Paragraph('Se finaliza el presente arqueo de caja con un total de Guaraníes <b>'+monto_letras(ar['total'])+'</b>, pasando a firmar en señal de conformidad.',st['Normal']),Spacer(1,10*mm),Table([['_______________________________','_______________________________'],['Encargado de Caja','Supervisor Administrativo']],colWidths=[90*mm,90*mm],style=[('ALIGN',(0,0),(-1,-1),'CENTER'),('FONTNAME',(0,1),(-1,1),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),8)])]
 doc.build(story);buf.seek(0);return send_file(buf,as_attachment=True,download_name='arqueo_caja_%s.pdf'%ar['id'],mimetype='application/pdf')

ROUTE_MODULE.update({'arqueo_caja_diario':'CAJA','arqueo_caja_pdf':'CAJA'})

# V13.9.35 - Formato documental unificado tipo KuDE para facturas, recibos y futuros documentos electrónicos.

# ===== V13.9.38: SIFEN TEST - configuración segura, certificado y prueba mTLS =====
def init_v13938_sifen():
    c=db()
    c.execute("""CREATE TABLE IF NOT EXISTS sifen_config(
      id INTEGER PRIMARY KEY CHECK(id=1), ambiente TEXT NOT NULL DEFAULT 'TEST',
      ruc TEXT, dv TEXT, timbrado TEXT, establecimiento TEXT DEFAULT '001', punto_expedicion TEXT DEFAULT '001',
      csc_id TEXT, csc TEXT, cert_subject TEXT, cert_serial TEXT, cert_not_before TEXT, cert_not_after TEXT,
      cert_path TEXT, key_path TEXT, ultimo_test TEXT, ultimo_estado TEXT, ultimo_detalle TEXT, actualizado_en TEXT)""")
    c.execute("INSERT OR IGNORE INTO sifen_config(id,ambiente) VALUES(1,'TEST')")
    c.execute("CREATE TABLE IF NOT EXISTS sifen_eventos(id INTEGER PRIMARY KEY,fecha TEXT,tipo TEXT,estado TEXT,detalle TEXT)")
    c.execute("CREATE TABLE IF NOT EXISTS schema_migrations(version TEXT PRIMARY KEY, aplicado_en TEXT)")
    c.execute("INSERT OR IGNORE INTO schema_migrations(version,aplicado_en) VALUES('13.9.38-sifen-test',?)",(now(),))
    c.commit();c.close()
init_v13938_sifen()
init_v13944_puntos_expedicion()


# ===== V13.9.77: punto de expedición determinado por caja/origen =====
def init_v13977_puntos_por_caja():
    c=db()
    c.execute("""CREATE TABLE IF NOT EXISTS caja_punto_expedicion(
      caja_id INTEGER PRIMARY KEY,punto_id INTEGER NOT NULL,codigo_area TEXT,actualizado_en TEXT)""")
    # Trazabilidad: el origen clínico no se pierde aunque otra caja facture la cuenta.
    vcols={r['name'] for r in c.execute('pragma table_info(ventas)').fetchall()}
    for col,ddl in [('caja_id','INTEGER'),('origen_area','TEXT')]:
        if col not in vcols:c.execute(f'alter table ventas add column {col} {ddl}')
    fcols={r['name'] for r in c.execute('pragma table_info(facturas_sanatorio)').fetchall()}
    for col,ddl in [('sifen_punto_id','INTEGER'),('establecimiento','TEXT'),('punto_expedicion','TEXT'),('caja_id','INTEGER'),('origen_area','TEXT')]:
        if col not in fcols:c.execute(f'alter table facturas_sanatorio add column {col} {ddl}')
    base=c.execute("select * from sifen_puntos_expedicion order by predeterminado desc,id limit 1").fetchone()
    est=str((base['establecimiento'] if base else '001') or '001').zfill(3)
    tim=(base['timbrado'] if base else '') or ''
    aut=int((base['autorizado_dnit'] if base else 0) or 0)
    # Se crean los tres puntos operativos. El indicador de autorización se hereda de la
    # configuración existente; el administrador debe verificar que 001/002/003 estén autorizados por DNIT.
    for cod,desc in [('001','Recepción'),('002','Urgencias'),('003','Internaciones / Cirugías / Otros')]:
        c.execute("""insert or ignore into sifen_puntos_expedicion
          (establecimiento,punto_expedicion,descripcion,timbrado,factura_electronica,nota_credito_electronica,nota_debito_electronica,autorizado_dnit,activo,predeterminado,proximo_numero_factura,creado_en,actualizado_en)
          values(?,?,?,?,1,1,1,?,1,0,1,?,?)""",(est,cod,desc,tim,aut,now(),now()))
        c.execute("update sifen_puntos_expedicion set factura_electronica=1,nota_credito_electronica=1,nota_debito_electronica=1,activo=1,actualizado_en=? where establecimiento=? and punto_expedicion=?",(now(),est,cod))
    # Asignación automática de cajas existentes por nombre.
    for caja in c.execute('select id,nombre from cajas').fetchall():
        n=str(caja['nombre'] or '').upper()
        cod='001' if 'RECEP' in n else ('002' if 'URGEN' in n else '003')
        pt=c.execute('select id from sifen_puntos_expedicion where establecimiento=? and punto_expedicion=?',(est,cod)).fetchone()
        if pt:c.execute('insert or replace into caja_punto_expedicion(caja_id,punto_id,codigo_area,actualizado_en) values(?,?,?,?)',(caja['id'],pt['id'],cod,now()))
    # Bloqueo de duplicados futuros. No altera documentos históricos ya existentes.
    c.executescript("""
    CREATE TRIGGER IF NOT EXISTS trg_ventas_numero_unico_ins BEFORE INSERT ON ventas
    WHEN NEW.numero IS NOT NULL AND trim(NEW.numero)<>'' AND EXISTS(SELECT 1 FROM ventas WHERE numero=NEW.numero)
    BEGIN SELECT RAISE(ABORT,'Número de factura ya utilizado. La correlatividad no permite duplicados.'); END;
    CREATE TRIGGER IF NOT EXISTS trg_ventas_numero_unico_upd BEFORE UPDATE OF numero ON ventas
    WHEN NEW.numero IS NOT NULL AND trim(NEW.numero)<>'' AND EXISTS(SELECT 1 FROM ventas WHERE numero=NEW.numero AND id<>OLD.id)
    BEGIN SELECT RAISE(ABORT,'Número de factura ya utilizado. La correlatividad no permite duplicados.'); END;
    CREATE TRIGGER IF NOT EXISTS trg_nce_numero_unico_ins BEFORE INSERT ON notas_credito_ventas
    WHEN NEW.numero IS NOT NULL AND trim(NEW.numero)<>'' AND EXISTS(SELECT 1 FROM notas_credito_ventas WHERE numero=NEW.numero)
    BEGIN SELECT RAISE(ABORT,'Número de Nota de Crédito ya utilizado.'); END;
    CREATE TRIGGER IF NOT EXISTS trg_nde_numero_unico_ins BEFORE INSERT ON notas_debito_ventas
    WHEN NEW.numero IS NOT NULL AND trim(NEW.numero)<>'' AND EXISTS(SELECT 1 FROM notas_debito_ventas WHERE numero=NEW.numero)
    BEGIN SELECT RAISE(ABORT,'Número de Nota de Débito ya utilizado.'); END;
    """)
    c.execute("insert or ignore into schema_migrations(version,aplicado_en) values('13.9.77-puntos-por-caja',?)",(now(),))
    c.commit();c.close()

def _punto_id_codigo(c,codigo):
    base=c.execute("select establecimiento from sifen_puntos_expedicion order by predeterminado desc,id limit 1").fetchone()
    est=str((base['establecimiento'] if base else '001') or '001').zfill(3)
    p=c.execute("select * from sifen_puntos_expedicion where establecimiento=? and punto_expedicion=? and activo=1 and factura_electronica=1",(est,str(codigo).zfill(3))).fetchone()
    if not p:raise ValueError('No está configurado el punto de expedición '+str(codigo).zfill(3)+'.')
    if not int(p['autorizado_dnit'] or 0):raise ValueError('El punto '+est+'-'+str(codigo).zfill(3)+' debe verificarse/habilitarse como autorizado DNIT antes de emitir.')
    return p['id']

def _punto_id_caja_actual(c,origen_area=None,forzar_recepcion=False):
    if forzar_recepcion:return _punto_id_codigo(c,'001')
    ap=caja_abierta(c)
    if ap:
        m=c.execute('select punto_id from caja_punto_expedicion where caja_id=?',(ap['caja_id'],)).fetchone()
        if m:return m['punto_id']
        nom=str(ap['caja'] or '').upper();cod='001' if 'RECEP' in nom else ('002' if 'URGEN' in nom else '003')
        return _punto_id_codigo(c,cod)
    area=str(origen_area or '').upper()
    if 'URGEN' in area:return _punto_id_codigo(c,'002')
    if area in ('INTERNACION','QUIROFANO','CIRUGIA','CIRUGÍAS','OTROS'):return _punto_id_codigo(c,'003')
    return _punto_id_codigo(c,'001')

init_v13977_puntos_por_caja()

# ===== V13.9.78: Preparación segura TEST / PRODUCCIÓN SIFEN =====
SIFEN_TEST_BASE='https://sifen-test.set.gov.py'
SIFEN_PROD_BASE='https://sifen.set.gov.py'
SIFEN_XML_VERSION='150'

def init_v13978_sifen_produccion():
    c=db(); cols={r['name'] for r in c.execute('pragma table_info(sifen_config)').fetchall()}
    for col,ddl in [('timbrado_desde','TEXT'),('xml_version',"TEXT DEFAULT '150'"),('produccion_habilitada','INTEGER DEFAULT 0'),('produccion_activada_en','TEXT'),('emis_departamento_codigo','TEXT'),('emis_departamento_desc','TEXT'),('emis_distrito_codigo','TEXT'),('emis_distrito_desc','TEXT'),('emis_ciudad_codigo','TEXT'),('emis_ciudad_desc','TEXT'),('emis_telefono','TEXT'),('emis_direccion','TEXT')]:
        if col not in cols:c.execute(f'alter table sifen_config add column {col} {ddl}')
    c.execute("update sifen_config set xml_version='150' where xml_version is null or trim(xml_version)=''")
    c.execute("insert or ignore into schema_migrations(version,aplicado_en) values('13.9.78-sifen-produccion-segura',?)",(now(),))
    c.execute("insert or ignore into schema_migrations(version,aplicado_en) values('13.9.84-emisor-v150',?)",(now(),))
    c.commit();c.close()

def init_v13996_sifen_emisor_firma():
    """Completa datos obligatorios del emisor V150 sin inventar información fiscal."""
    c=db(); cols={r['name'] for r in c.execute('pragma table_info(sifen_config)').fetchall()}
    for col,ddl in [('emis_actividad_codigo','TEXT'),('emis_actividad_desc','TEXT')]:
        if col not in cols: c.execute(f'alter table sifen_config add column {col} {ddl}')
    c.execute("insert or ignore into schema_migrations(version,aplicado_en) values('13.9.96-sifen-emisor-firma',?)",(now(),))
    c.commit();c.close()

init_v13996_sifen_emisor_firma()

# ===== V13.9.105: múltiples actividades económicas del emisor =====
def init_v13105_actividades_economicas():
    c=db()
    c.execute("""CREATE TABLE IF NOT EXISTS sifen_actividades_economicas(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo TEXT NOT NULL,
        descripcion TEXT NOT NULL,
        principal INTEGER DEFAULT 0,
        activo INTEGER DEFAULT 1,
        creado_en TEXT,
        actualizado_en TEXT,
        UNIQUE(codigo)
    )""")
    cfg=c.execute('select * from sifen_config where id=1').fetchone()
    if cfg:
        cod=str(cfg['emis_actividad_codigo'] or '').strip(); des=str(cfg['emis_actividad_desc'] or '').strip()
        if cod and des:
            existe=c.execute('select id from sifen_actividades_economicas where codigo=?',(cod,)).fetchone()
            if not existe:
                c.execute('insert into sifen_actividades_economicas(codigo,descripcion,principal,activo,creado_en,actualizado_en) values(?,?,?,?,?,?)',(cod,des,1,1,now(),now()))
    if c.execute('select count(*) from sifen_actividades_economicas where activo=1 and principal=1').fetchone()[0]==0:
        primero=c.execute('select id from sifen_actividades_economicas where activo=1 order by id limit 1').fetchone()
        if primero:c.execute('update sifen_actividades_economicas set principal=1 where id=?',(primero['id'],))
    c.execute("insert or ignore into schema_migrations(version,aplicado_en) values('13.9.105-actividades-economicas-multiples',?)",(now(),))
    c.commit();c.close()
init_v13105_actividades_economicas()

def _sifen_base(cfg):
    return SIFEN_PROD_BASE if str(cfg['ambiente'] or '').upper()=='PRODUCCION' else SIFEN_TEST_BASE

def init_v13102_produccion_segura():
    c=db(); cols={r['name'] for r in c.execute('pragma table_info(sifen_config)').fetchall()}
    for col,ddl in [('dnit_habilitado_produccion','INTEGER DEFAULT 0'),('dnit_habilitado_confirmado_en','TEXT'),('ultimo_envio_prod','TEXT'),('ultimo_envio_prod_estado','TEXT')]:
        if col not in cols: c.execute(f'alter table sifen_config add column {col} {ddl}')
    c.execute("CREATE TABLE IF NOT EXISTS schema_migrations(version TEXT PRIMARY KEY, aplicado_en TEXT)")
    c.execute("insert or ignore into schema_migrations(version,aplicado_en) values('13.9.102-kude-produccion-segura',?)",(now(),))
    c.commit();c.close()
init_v13102_produccion_segura()

# ===== V13.9.126: reparación segura de geografía SIFEN del emisor =====
def init_v13126_geo_emisor():
    c=db(); cfg=c.execute('select * from sifen_config where id=1').fetchone()
    if cfg:
        dep=str(cfg['emis_departamento_desc'] or '').upper(); dis=str(cfg['emis_distrito_desc'] or '').upper(); ciu=str(cfg['emis_ciudad_desc'] or '').upper()
        if 'CANINDEY' in dep and 'NUEVA ESPERANZA' in (dis+' '+ciu):
            c.execute("update sifen_config set emis_departamento_codigo='18',emis_departamento_desc='CANINDEYU',emis_distrito_codigo='238',emis_distrito_desc='NUEVA ESPERANZA',emis_ciudad_codigo='4603',emis_ciudad_desc='NUEVA ESPERANZA' where id=1")
    c.execute("insert or ignore into schema_migrations(version,aplicado_en) values('13.9.126-geo-emisor-dnit',?)",(now(),))
    c.commit(); c.close()
init_v13126_geo_emisor()


def _sifen_diagnostico(c,cfg):
    import os
    puntos=c.execute("select * from sifen_puntos_expedicion where activo=1 order by establecimiento,punto_expedicion").fetchall()
    checks=[]
    def add(nombre,ok,detalle):checks.append({'nombre':nombre,'ok':bool(ok),'detalle':detalle})
    add('RUC y DV',bool(_solo_digitos(cfg['ruc']) and _solo_digitos(cfg['dv'])),'Emisor configurado' if _solo_digitos(cfg['ruc']) else 'Falta RUC/DV')
    add('Timbrado electrónico',bool(_solo_digitos(cfg['timbrado'])),'Timbrado '+str(cfg['timbrado'] or '') if cfg['timbrado'] else 'Falta timbrado')
    add('Inicio de vigencia',bool(cfg['timbrado_desde']),str(cfg['timbrado_desde'] or 'Falta fecha de inicio'))
    add('XML SIFEN',str(cfg['xml_version'] or '')=='150','Versión '+str(cfg['xml_version'] or ''))
    add('CSC / IdCSC',bool((cfg['csc_id'] or '').strip() and (cfg['csc'] or '').strip()),'Configurados' if (cfg['csc_id'] and cfg['csc']) else 'Falta CSC o IdCSC')
    certok=bool(cfg['cert_path'] and cfg['key_path'] and os.path.exists(cfg['cert_path']) and os.path.exists(cfg['key_path']))
    add('Certificado digital',certok,'Instalado en almacenamiento persistente' if certok else 'No instalado o archivo no disponible')
    aut=[p for p in puntos if int(p['autorizado_dnit'] or 0)]
    add('Puntos autorizados',bool(aut),', '.join(str(p['establecimiento'])+'-'+str(p['punto_expedicion']) for p in aut) if aut else 'No hay puntos marcados como autorizados')
    add('Habilitación DNIT para Producción',bool(cfg['dnit_habilitado_produccion'] if 'dnit_habilitado_produccion' in cfg.keys() else 0),'Confirmada por el administrador' if (cfg['dnit_habilitado_produccion'] if 'dnit_habilitado_produccion' in cfg.keys() else 0) else 'Debe confirmar que DNIT habilitó al contribuyente y que el timbrado/puntos corresponden a Producción')
    emis_req=[('Departamento',cfg['emis_departamento_codigo'],cfg['emis_departamento_desc']),('Ciudad',cfg['emis_ciudad_codigo'],cfg['emis_ciudad_desc'])]
    emis_faltan=[n for n,cod,des in emis_req if not str(cod or '').strip() or not str(des or '').strip()]
    if not str(cfg['emis_telefono'] or '').strip(): emis_faltan.append('Teléfono')
    add('Datos emisor XML',not emis_faltan,'Configurados' if not emis_faltan else 'Falta: '+', '.join(emis_faltan))
    acts=c.execute("select codigo,descripcion,principal from sifen_actividades_economicas where activo=1 order by principal desc,id").fetchall()
    act_ok=bool(acts)
    add('Actividades económicas emisor',act_ok,(', '.join(str(a['codigo'])+' · '+str(a['descripcion']) for a in acts)) if acts else 'Falta al menos una actividad económica activa declarada en el RUC')
    # V13.9.79: motor real de firma XMLDSig + transporte SOAP/mTLS instalado.
    try:
        import lxml.etree, signxml
        motor_ok=True
    except Exception:
        motor_ok=False
    add('Motor XMLDSig + SOAP',motor_ok,'Motor instalado' if motor_ok else 'Dependencias lxml/signxml no disponibles')
    # V13.9.80: generador estructural rDE/DE V150 instalado. Sigue bloqueado para
    # PRODUCCION hasta validar el XML contra los XSD oficiales vigentes.
    gen_ok=callable(globals().get('_sifen_generar_de_v150'))
    add('Generador DE XML V150',gen_ok,'Generador estructural instalado' if gen_ok else 'Generador no disponible')
    # V13.9.82: validación real contra los XSD V150 empaquetados por pysifen,
    # bindings generados desde los esquemas oficiales SIFEN. PRODUCCIÓN exige que
    # el motor esté instalado Y que exista al menos una validación exitosa reciente.
    try:
        from pysifen.de.bindings.de_v150.de_v150 import RDe as _RDeV150
        xsd_motor_ok=True
    except Exception:
        xsd_motor_ok=False
    ult_xsd=c.execute("select estado,detalle,fecha from sifen_eventos where tipo='XSD_V150' order by id desc limit 1").fetchone()
    xsd_doc_ok=bool(ult_xsd and str(ult_xsd['estado'] or '').upper()=='OK')
    if not xsd_motor_ok:
        xsd_det='Motor XSD no disponible. Verifique dependencia sifen==0.2.0 en Render.'
    elif xsd_doc_ok:
        xsd_det='Motor XSD V150 instalado · última validación OK: '+str(ult_xsd['fecha'] or '')
    elif ult_xsd:
        xsd_det='Motor instalado · última validación falló: '+str(ult_xsd['detalle'] or '')[:260]
    else:
        xsd_det='Motor XSD V150 instalado. Ejecute “Generar y validar XML V150”.'
    # V13.9.123: no bloquear Producción por una validación histórica.
    # Cada DE se valida contra XSD inmediatamente antes de transmitirlo; exigir un
    # XSD previo OK creaba un bloqueo circular para la primera factura.
    add('Validación XSD V150',xsd_motor_ok,xsd_det)
    mtls_ok=str(cfg['ultimo_estado'] or '').upper()=='OK' if 'ultimo_estado' in cfg.keys() else False
    add('Conexión mTLS SIFEN',mtls_ok,('Última conexión OK: '+str(cfg['ultimo_test'] or '')) if mtls_ok else 'Ejecute y apruebe la prueba de conexión segura antes de Producción')
    return checks

init_v13978_sifen_produccion()

# ===== V13.9.80: generador estructural DE XML V150 (TEST/prevalidación) =====
def _sifen_xml_text(parent, tag, value, ns='http://ekuatia.set.gov.py/sifen/xsd'):
    from lxml import etree
    if value is None:return None
    value=str(value).strip()
    if value=='':return None
    e=etree.SubElement(parent,'{%s}%s'%(ns,tag));e.text=value;return e

def _sifen_numero_partes(numero):
    import re
    m=re.match(r'^\s*(\d{3})-(\d{3})-(\d{1,7})\s*$',str(numero or ''))
    if not m:raise ValueError('Número fiscal inválido. Use formato 001-001-0000001.')
    return m.group(1),m.group(2),m.group(3).zfill(7)

def _sifen_cdc_base(cfg,tipo_de,numero,fecha,cod_seg,tipo_emision='1'):
    # CDC V150: 43 dígitos base + DV módulo 11 = 44.
    # Normaliza cada componente y devuelve un error específico si un dato no cumple.
    import re, datetime as _dt
    est,pun,num=_sifen_numero_partes(numero)
    tipo=_solo_digitos(tipo_de).zfill(2)
    ruc=_solo_digitos(cfg['ruc'])
    dv=_solo_digitos(cfg['dv'])
    tc=_solo_digitos(cfg['tipo_contribuyente'] or '2')
    emi=_solo_digitos(tipo_emision or '1')
    seg=_solo_digitos(cod_seg)

    fs=str(fecha or '').strip()
    f=''
    for fmt in ('%Y-%m-%d','%d/%m/%Y','%Y-%m-%d %H:%M:%S','%Y-%m-%dT%H:%M:%S'):
        try:
            f=_dt.datetime.strptime(fs[:19] if 'H' not in fmt and fmt.endswith('%S') else fs,fmt).strftime('%Y%m%d');break
        except Exception: pass
    if not f:
        digs=_solo_digitos(fs)
        if len(digs)>=8:
            cand=digs[:8]
            try:_dt.datetime.strptime(cand,'%Y%m%d');f=cand
            except Exception:pass

    errores=[]
    if len(tipo)!=2 or not tipo.isdigit(): errores.append('tipo de documento debe tener 2 dígitos')
    if len(ruc)!=8: errores.append('RUC debe tener 8 dígitos (actual: %s)'%len(ruc))
    if len(dv)!=1: errores.append('DV debe tener 1 dígito')
    if len(est)!=3: errores.append('establecimiento debe tener 3 dígitos')
    if len(pun)!=3: errores.append('punto de expedición debe tener 3 dígitos')
    if len(num)!=7: errores.append('número debe tener 7 dígitos')
    if len(tc)!=1 or tc not in ('1','2'): errores.append('tipo de contribuyente debe ser 1 o 2')
    if len(f)!=8: errores.append('fecha inválida; se requiere AAAAMMDD')
    if len(emi)!=1: errores.append('tipo de emisión debe tener 1 dígito')
    if len(seg)>9: errores.append('código de seguridad supera 9 dígitos')
    seg=seg.zfill(9)
    if len(seg)!=9: errores.append('código de seguridad debe tener 9 dígitos')
    if errores: raise ValueError('CDC inválido: '+'; '.join(errores)+'.')
    base=tipo+ruc+dv+est+pun+num+tc+f+emi+seg
    if len(base)!=43 or not base.isdigit():
        raise ValueError('CDC base inválido: se obtuvieron %s caracteres en vez de 43.'%len(base))
    return base

def _sifen_dv_mod11(base):
    k=2;total=0
    for ch in reversed(str(base)):
        total+=int(ch)*k;k+=1
        if k>11:k=2
    r=total%11;dv=11-r
    return 0 if dv in (10,11) else dv

def _sifen_generar_de_v150(c, doc_tipo, doc_id):
    """Genera rDE V150 estructural para TEST/prevalidación.
    No transmite ni declara aprobación. PRODUCCIÓN permanece bloqueada hasta XSD oficial.
    doc_tipo: FE, NCE, NDE.
    """
    from lxml import etree
    import secrets, datetime
    NS='http://ekuatia.set.gov.py/sifen/xsd';XSI='http://www.w3.org/2001/XMLSchema-instance'
    cfg=c.execute('select * from sifen_config where id=1').fetchone()
    inst=c.execute('select * from institucion_config where id=1').fetchone()
    if not cfg:raise ValueError('Configuración SIFEN inexistente.')
    tipo=str(doc_tipo).upper()
    if tipo=='FE':
        d=c.execute("select v.*,t.nombre receptor,t.ruc receptor_doc,t.sifen_naturaleza,t.sifen_tipo_operacion,t.sifen_tipo_contribuyente,t.sifen_tipo_documento,t.sifen_numero_documento,t.sifen_pais,t.sifen_pais_desc,t.sifen_direccion,t.sifen_numero_casa,t.sifen_departamento_codigo,t.sifen_departamento_desc,t.sifen_distrito_codigo,t.sifen_distrito_desc,t.sifen_ciudad_codigo,t.sifen_ciudad_desc,t.telefono receptor_tel,t.email receptor_email,p.timbrado punto_timbrado from ventas v left join terceros t on t.id=v.cliente_id left join sifen_puntos_expedicion p on p.id=v.sifen_punto_id where v.id=?",(doc_id,)).fetchone()
        if not d:raise ValueError('Factura no encontrada.')
        items=c.execute("select vi.*,p.codigo,coalesce(nullif(trim(p.sifen_descripcion),''),nullif(trim(p.nombre),''),nullif(trim(vi.descripcion),''),'Servicio medico') sifen_desc_item,coalesce(nullif(trim(p.sifen_unidad_codigo),''),'77') sifen_unidad_codigo,coalesce(nullif(trim(p.sifen_unidad_desc),''),'UNI') sifen_unidad_desc,p.tipo_producto sifen_tipo_producto,p.clasif_general sifen_clasif_general,p.categoria sifen_categoria from venta_items vi left join productos p on p.id=vi.producto_id where vi.venta_id=? order by vi.id",(doc_id,)).fetchall()
        ide=1;des='Factura electrónica';fecha=d['fecha'];numero=d['numero'];asoc=None
    elif tipo=='NCE':
        d=c.execute("select n.*,v.numero factura_numero,v.cdc factura_cdc,v.cliente_id,t.nombre receptor,t.ruc receptor_doc,t.sifen_naturaleza,t.sifen_tipo_operacion,t.sifen_tipo_contribuyente,t.sifen_tipo_documento,t.sifen_numero_documento,t.sifen_pais,t.sifen_pais_desc,t.sifen_direccion,t.sifen_numero_casa,t.sifen_departamento_codigo,t.sifen_departamento_desc,t.sifen_distrito_codigo,t.sifen_distrito_desc,t.sifen_ciudad_codigo,t.sifen_ciudad_desc,t.telefono receptor_tel,t.email receptor_email,v.sifen_punto_id,p.timbrado punto_timbrado from notas_credito_ventas n join ventas v on v.id=n.venta_id left join terceros t on t.id=v.cliente_id left join sifen_puntos_expedicion p on p.id=v.sifen_punto_id where n.id=?",(doc_id,)).fetchone()
        if not d:raise ValueError('Nota de Crédito no encontrada.')
        items=c.execute("select i.*,p.codigo,coalesce(nullif(trim(p.sifen_descripcion),''),nullif(trim(i.descripcion),''),nullif(trim(p.nombre),''),'Servicio medico') descripcion,coalesce(nullif(trim(p.sifen_unidad_codigo),''),'77') sifen_unidad_codigo,coalesce(nullif(trim(p.sifen_unidad_desc),''),'UNI') sifen_unidad_desc from nota_credito_venta_items i left join productos p on p.id=i.producto_id where i.nota_id=? order by i.id",(doc_id,)).fetchall()
        ide=5;des='Nota de crédito electrónica';fecha=d['fecha'];numero=d['numero'];asoc=d['factura_cdc']
    elif tipo=='NDE':
        d=c.execute("select n.*,v.numero factura_numero,v.cdc factura_cdc,v.cliente_id,t.nombre receptor,t.ruc receptor_doc,t.sifen_naturaleza,t.sifen_tipo_operacion,t.sifen_tipo_contribuyente,t.sifen_tipo_documento,t.sifen_numero_documento,t.sifen_pais,t.sifen_pais_desc,t.sifen_direccion,t.sifen_numero_casa,t.sifen_departamento_codigo,t.sifen_departamento_desc,t.sifen_distrito_codigo,t.sifen_distrito_desc,t.sifen_ciudad_codigo,t.sifen_ciudad_desc,t.telefono receptor_tel,t.email receptor_email,v.sifen_punto_id,p.timbrado punto_timbrado from notas_debito_ventas n join ventas v on v.id=n.venta_id left join terceros t on t.id=v.cliente_id left join sifen_puntos_expedicion p on p.id=v.sifen_punto_id where n.id=?",(doc_id,)).fetchone()
        if not d:raise ValueError('Nota de Débito no encontrada.')
        items=c.execute("select i.*,p.codigo,coalesce(nullif(trim(p.sifen_descripcion),''),nullif(trim(i.descripcion),''),nullif(trim(p.nombre),''),'Servicio medico') descripcion,coalesce(nullif(trim(p.sifen_unidad_codigo),''),'77') sifen_unidad_codigo,coalesce(nullif(trim(p.sifen_unidad_desc),''),'UNI') sifen_unidad_desc from nota_debito_venta_items i left join productos p on p.id=i.producto_id where i.nota_id=? order by i.id",(doc_id,)).fetchall()
        ide=6;des='Nota de débito electrónica';fecha=d['fecha'];numero=d['numero'];asoc=d['factura_cdc']
    else:raise ValueError('Tipo de DE no soportado.')
    est,pun,num=_sifen_numero_partes(numero)
    # V13.9.101: FE debe conservar un único CDC/código de seguridad. El XML, QR y factura
    # impresa tienen que referirse al mismo identificador; no se regenera un CDC al validar.
    cdc_guardado=str(d['cdc'] or '').strip() if tipo=='FE' and 'cdc' in d.keys() else ''
    cod_guardado=str(d['codigo_seguridad_sifen'] or '').strip() if tipo=='FE' and 'codigo_seguridad_sifen' in d.keys() else ''
    if tipo=='FE' and len(cdc_guardado)==44 and cdc_guardado.isdigit() and len(cod_guardado)==9 and cod_guardado.isdigit():
        cdc=cdc_guardado; cod_seg=cod_guardado
    else:
        cod_seg=str(secrets.randbelow(1000000000)).zfill(9)
        base=_sifen_cdc_base(cfg,ide,numero,fecha,cod_seg);cdc=base+str(_sifen_dv_mod11(base))
        if tipo=='FE':
            estado='TEST_GENERADO' if str(cfg['ambiente'] or '').upper()=='TEST' else 'NO_ENVIADO'
            c.execute("update ventas set cdc=?,codigo_seguridad_sifen=?,cdc_ambiente=?,estado_sifen=? where id=?",(cdc,cod_seg,str(cfg['ambiente'] or '').upper(),estado,doc_id))
    root=etree.Element('{%s}rDE'%NS,nsmap={None:NS,'xsi':XSI})
    root.set('{%s}schemaLocation'%XSI,NS+' siRecepDE_v150.xsd')
    _sifen_xml_text(root,'dVerFor','150',NS)
    de=etree.SubElement(root,'{%s}DE'%NS);de.set('Id',cdc)
    _sifen_xml_text(de,'dDVId',cdc[-1],NS)
    # V13.9.124: Render ejecuta en UTC. SIFEN V150 exige dFecFirma en hora local
    # de Paraguay, sin offset y anterior a la transmisión. ZoneInfo respeta los
    # cambios históricos/vigentes de America/Asuncion; un margen de 5 segundos
    # evita rechazo 1004 por pequeñas diferencias de reloj/red.
    try:
        from zoneinfo import ZoneInfo
        fec_firma=(datetime.datetime.now(datetime.timezone.utc).astimezone(ZoneInfo('America/Asuncion'))-datetime.timedelta(seconds=5)).replace(tzinfo=None,microsecond=0)
    except Exception:
        fec_firma=(datetime.datetime.utcnow()-datetime.timedelta(hours=3,seconds=5)).replace(microsecond=0)
    _sifen_xml_text(de,'dFecFirma',fec_firma.isoformat(),NS);_sifen_xml_text(de,'dSisFact','1',NS)
    go=etree.SubElement(de,'{%s}gOpeDE'%NS);_sifen_xml_text(go,'iTipEmi','1',NS);_sifen_xml_text(go,'dDesTipEmi','Normal',NS);_sifen_xml_text(go,'dCodSeg',cod_seg,NS)
    gt=etree.SubElement(de,'{%s}gTimb'%NS);_sifen_xml_text(gt,'iTiDE',ide,NS);_sifen_xml_text(gt,'dDesTiDE',des,NS);_sifen_xml_text(gt,'dNumTim',d['punto_timbrado'] or cfg['timbrado'],NS);_sifen_xml_text(gt,'dEst',est,NS);_sifen_xml_text(gt,'dPunExp',pun,NS);_sifen_xml_text(gt,'dNumDoc',num,NS);_sifen_xml_text(gt,'dFeIniT',cfg['timbrado_desde'],NS)
    gg=etree.SubElement(de,'{%s}gDatGralOpe'%NS)
    # V13.9.130: fecha/hora de emisión coherente con la firma. Para documentos del día
    # usamos el mismo reloj America/Asuncion; para históricos conservamos la fecha y 12:00.
    try:
        _fdoc=str(fecha)[:10]
        _hoy=fec_firma.date().isoformat()
        _fec_emi=(fec_firma+datetime.timedelta(seconds=1)).replace(microsecond=0).isoformat() if _fdoc==_hoy else _fdoc+'T12:00:00'
    except Exception:
        _fec_emi=str(fecha)[:10]+'T12:00:00'
    _sifen_xml_text(gg,'dFeEmiDE',_fec_emi,NS)
    # V13.9.125: iTipTra y dDesTipTra deben ser una pareja exacta del catálogo SIFEN V150.
    # Detectamos el contenido real de la factura: servicios=2, mercaderías=1, mixto=3.
    # En versiones anteriores FE enviaba iTipTra=1 con la descripción 'Prestación de servicios',
    # lo que provocaba el rechazo SIFEN 1203.
    tiene_servicio=False; tiene_mercaderia=False
    for _it in items:
        # V13.9.131: aliases únicos evitan que vi.* oculte la descripción/clasificación del maestro.
        _vals=[]
        for _k in ('sifen_tipo_producto','sifen_clasif_general','sifen_categoria','sifen_desc_item','descripcion'):
            if _k in _it.keys(): _vals.append(str(_it[_k] or '').strip().upper())
        _texto=' '.join(_vals)
        if any(k in _texto for k in ('SERVICIO','CONSULTA','PROCEDIMIENTO','HONORARIO','ESTUDIO','ANALISIS','ANÁLISIS','MEDICO','MÉDICO')):
            tiene_servicio=True
        else:
            tiene_mercaderia=True
    if tiene_servicio and tiene_mercaderia:
        tip_tra,des_tip_tra='3','Mixto (Venta de mercadería y servicios)'
    elif tiene_servicio:
        tip_tra,des_tip_tra='2','Prestación de servicios'
    else:
        tip_tra,des_tip_tra='1','Venta de mercadería'
    mon_ope=str(d['moneda'] if 'moneda' in d.keys() and d['moneda'] else 'PYG').upper().strip()
    gc=etree.SubElement(gg,'{%s}gOpeCom'%NS);_sifen_xml_text(gc,'iTipTra',tip_tra,NS);_sifen_xml_text(gc,'dDesTipTra',des_tip_tra,NS);_sifen_xml_text(gc,'iTImp','1',NS);_sifen_xml_text(gc,'dDesTImp','IVA',NS);_sifen_xml_text(gc,'cMoneOpe',mon_ope,NS);_sifen_xml_text(gc,'dDesMoneOpe','Guarani' if mon_ope=='PYG' else mon_ope,NS)
    ge=etree.SubElement(gg,'{%s}gEmis'%NS)
    # V13.9.84: TgEmis V150 exige ubicación y teléfono del emisor. Se toman de Configuración SIFEN; no se inventan códigos geográficos.
    dep_cod=str(cfg['emis_departamento_codigo'] or '').strip();dep_desc=str(cfg['emis_departamento_desc'] or '').strip();dis_cod=str(cfg['emis_distrito_codigo'] or '').strip();dis_desc=str(cfg['emis_distrito_desc'] or '').strip();ciu_cod=str(cfg['emis_ciudad_codigo'] or '').strip();ciu_desc=str(cfg['emis_ciudad_desc'] or '').strip();tel=str(cfg['emis_telefono'] or inst['telefono'] or '').strip();dire=str(cfg['emis_direccion'] or inst['direccion'] or '').strip()
    # V13.9.126: normalización geográfica oficial DNIT/SIFEN. Los códigos de SIFEN
    # NO son los códigos distritales INE (ej. 14/1410). Para Nueva Esperanza,
    # Canindeyú, el catálogo SIFEN usa Departamento=18, Distrito=238, Ciudad=4603.
    _geo_name=lambda x: str(x or '').strip().upper().replace('Ú','U').replace('Í','I').replace('É','E').replace('Á','A').replace('Ó','O')
    if 'CANINDEY' in _geo_name(dep_desc) and 'NUEVA ESPERANZA' in (_geo_name(dis_desc)+' '+_geo_name(ciu_desc)):
        dep_cod,dep_desc='18','CANINDEYU'
        dis_cod,dis_desc='238','NUEVA ESPERANZA'
        ciu_cod,ciu_desc='4603','NUEVA ESPERANZA'
    falt=[n for n,v in [('Departamento código',dep_cod),('Departamento',dep_desc),('Distrito código',dis_cod),('Distrito',dis_desc),('Ciudad código',ciu_cod),('Ciudad',ciu_desc),('Teléfono',tel)] if not v]
    if falt: raise ValueError('Datos obligatorios del emisor incompletos: '+', '.join(falt)+'. Complete Configuración → SIFEN → Datos del establecimiento emisor.')
    _sifen_xml_text(ge,'dRucEm',cfg['ruc'],NS);_sifen_xml_text(ge,'dDVEmi',cfg['dv'],NS);_sifen_xml_text(ge,'iTipCont',cfg['tipo_contribuyente'] or '2',NS);_sifen_xml_text(ge,'dNomEmi',(inst['razon_social'] if 'razon_social' in inst.keys() else inst['nombre']) or 'CENTRO MEDICO SANTA CLARA',NS);_sifen_xml_text(ge,'dNomFanEmi',(inst['nombre_fantasia'] if 'nombre_fantasia' in inst.keys() else inst['nombre']) or '',NS);_sifen_xml_text(ge,'dDirEmi',dire,NS);_sifen_xml_text(ge,'dNumCas','0',NS);_sifen_xml_text(ge,'cDepEmi',dep_cod,NS);_sifen_xml_text(ge,'dDesDepEmi',dep_desc,NS)
    if dis_cod:_sifen_xml_text(ge,'cDisEmi',dis_cod,NS)
    if dis_desc:_sifen_xml_text(ge,'dDesDisEmi',dis_desc,NS)
    _sifen_xml_text(ge,'cCiuEmi',ciu_cod,NS);_sifen_xml_text(ge,'dDesCiuEmi',ciu_desc,NS);_sifen_xml_text(ge,'dTelEmi',tel,NS);_sifen_xml_text(ge,'dEmailE',inst['email'] or '',NS)
    actividades=c.execute("select codigo,descripcion from sifen_actividades_economicas where activo=1 order by principal desc,id").fetchall()
    if not actividades:
        raise ValueError('Falta al menos una actividad económica activa del emisor. Complete Empresa y Facturación Electrónica → Actividades económicas.')
    for act in actividades:
        act_cod=str(act['codigo'] or '').strip(); act_desc=str(act['descripcion'] or '').strip()
        if not act_cod or not act_desc: continue
        gact=etree.SubElement(ge,'{%s}gActEco'%NS);_sifen_xml_text(gact,'cActEco',act_cod,NS);_sifen_xml_text(gact,'dDesActEco',act_desc,NS)
    gr=etree.SubElement(gg,'{%s}gDatRec'%NS)
    # V13.9.116: para contribuyentes, el RUC/DV sale del RUC del Maestro de Clientes.
    # sifen_numero_documento queda reservado al documento de identidad de no contribuyentes.
    ruc_maestro=str(d['receptor_doc'] or '').strip()
    doc_identidad=str((d['sifen_numero_documento'] if 'sifen_numero_documento' in d.keys() else None) or '').strip()
    rdoc=ruc_maestro if str(d['sifen_naturaleza'] or '1')=='1' else (doc_identidad or ruc_maestro)
    rruc=ruc_maestro.split('-')[0].strip() if '-' in ruc_maestro else ruc_maestro
    rdv=ruc_maestro.split('-')[-1].strip() if '-' in ruc_maestro else ''
    nat=str(d['sifen_naturaleza'] or '1') if 'sifen_naturaleza' in d.keys() else '1';tiop=str(d['sifen_tipo_operacion'] or '1') if 'sifen_tipo_operacion' in d.keys() else '1';pais=str(d['sifen_pais'] or 'PRY') if 'sifen_pais' in d.keys() else 'PRY';paisd=str(d['sifen_pais_desc'] or 'Paraguay') if 'sifen_pais_desc' in d.keys() else 'Paraguay'
    # V13.9.93: prevención del rechazo SIFEN 1300 (naturaleza/tipo de operación).
    if nat=='1' and tiop not in ('1','3'):
        raise ValueError('SIFEN 1300 preventivo: receptor Contribuyente incompatible con tipo de operación '+tiop+'. Revise el maestro del cliente (normalmente B2B).')
    if nat=='2' and pais=='PRY' and tiop not in ('2','3'):
        raise ValueError('SIFEN 1300 preventivo: receptor No contribuyente paraguayo incompatible con tipo de operación '+tiop+'. Corresponde B2C, salvo caso B2G válido.')
    if nat=='2' and pais!='PRY' and tiop!='4':
        raise ValueError('SIFEN 1300 preventivo: receptor del exterior debe configurarse como operación B2F.')
    _sifen_xml_text(gr,'iNatRec',nat,NS);_sifen_xml_text(gr,'iTiOpe',tiop,NS);_sifen_xml_text(gr,'cPaisRec',pais,NS);_sifen_xml_text(gr,'dDesPaisRe',paisd,NS)
    if nat=='1':
        _sifen_xml_text(gr,'iTiContRec',str(d['sifen_tipo_contribuyente'] or '2') if 'sifen_tipo_contribuyente' in d.keys() else '2',NS)
        if not (rruc.isdigit() and rdv.isdigit() and len(rdv)==1):
            raise ValueError('Cliente contribuyente sin RUC-DV válido. Complete el Maestro de Clientes con formato RUC-DV antes de emitir el DE.')
        _sifen_xml_text(gr,'dRucRec',rruc,NS);_sifen_xml_text(gr,'dDVRec',rdv,NS)
    else:
        _sifen_xml_text(gr,'iTipIDRec',str(d['sifen_tipo_documento'] or '1') if 'sifen_tipo_documento' in d.keys() else '1',NS);_sifen_xml_text(gr,'dDTipIDRec','Cédula paraguaya',NS);_sifen_xml_text(gr,'dNumIDRec',rdoc,NS)
    _sifen_xml_text(gr,'dNomRec',d['receptor'] or 'SIN NOMBRE',NS);_sifen_xml_text(gr,'dDirRec',(d['sifen_direccion'] if 'sifen_direccion' in d.keys() else '') or '',NS);_sifen_xml_text(gr,'dNumCasRec',(d['sifen_numero_casa'] if 'sifen_numero_casa' in d.keys() else '') or '0',NS)
    for tag,key in [('cDepRec','sifen_departamento_codigo'),('dDesDepRec','sifen_departamento_desc'),('cDisRec','sifen_distrito_codigo'),('dDesDisRec','sifen_distrito_desc'),('cCiuRec','sifen_ciudad_codigo'),('dDesCiuRec','sifen_ciudad_desc'),('dTelRec','receptor_tel'),('dEmailRec','receptor_email')]:
        if key in d.keys() and d[key]:_sifen_xml_text(gr,tag,d[key],NS)
    _sifen_xml_text(gr,'dCodCliente','CLI'+str(d['cliente_id'] if 'cliente_id' in d.keys() else doc_id).zfill(3),NS)
    gd=etree.SubElement(de,'{%s}gDtipDE'%NS)
    if tipo=='FE':
        gf=etree.SubElement(gd,'{%s}gCamFE'%NS);_sifen_xml_text(gf,'iIndPres','1',NS);_sifen_xml_text(gf,'dDesIndPres','Operación presencial',NS)
    else:
        gn=etree.SubElement(gd,'{%s}gCamNCDE'%NS);_sifen_xml_text(gn,'iMotEmi','1',NS);_sifen_xml_text(gn,'dDesMotEmi','Devolución y ajuste de precios' if tipo=='NCE' else 'Ajuste de precios',NS)
    # V13.9.116: condición de operación tomada del modelo real de factura.
    # Para FE, gCamCond es obligatorio: contado incluye la forma/monto de pago;
    # crédito informa la condición y deja al XSD validar los grupos crediticios aplicables.
    if tipo=='FE':
        condicion=str(d['condicion_venta'] or 'CONTADO').upper() if 'condicion_venta' in d.keys() else 'CONTADO'
        gcond=etree.SubElement(gd,'{%s}gCamCond'%NS)
        es_contado=(condicion=='CONTADO')
        _sifen_xml_text(gcond,'iCondOpe','1' if es_contado else '2',NS)
        _sifen_xml_text(gcond,'dDCondOpe','Contado' if es_contado else 'Crédito',NS)
        if es_contado:
            forma=str(d['forma_cobro'] or 'Efectivo').strip() if 'forma_cobro' in d.keys() else 'Efectivo'
            mapa={'EFECTIVO':('1','Efectivo'),'CHEQUE':('2','Cheque'),'TARJETA DE CRÉDITO':('3','Tarjeta de crédito'),'TARJETA DE CREDITO':('3','Tarjeta de crédito'),'TARJETA DE DÉBITO':('4','Tarjeta de débito'),'TARJETA DE DEBITO':('4','Tarjeta de débito'),'TRANSFERENCIA':('5','Transferencia'),'BANCO':('5','Transferencia'),'POS':('4','Tarjeta de débito')}
            codp,desp=mapa.get(forma.upper(),('1','Efectivo'))
            gp=etree.SubElement(gcond,'{%s}gPaConEIni'%NS)
            _sifen_xml_text(gp,'iTiPago',codp,NS);_sifen_xml_text(gp,'dDesTiPag',desp,NS)
            # V13.9.128: el monto de pago debe coincidir con el total matemático de los ítems, no con un total histórico potencialmente desfasado.
            from decimal import Decimal, ROUND_HALF_UP
            _pay_total=sum((Decimal(str(x['cantidad'] or 1))*Decimal(str(x['precio'] or 0)) for x in items), Decimal('0'))
            _pay_q=Decimal('1') if mon_ope=='PYG' else Decimal('0.0001')
            _sifen_xml_text(gp,'dMonTiPag',format(_pay_total.quantize(_pay_q, rounding=ROUND_HALF_UP),'f'),NS)
            mon=mon_ope
            _sifen_xml_text(gp,'cMoneTiPag',mon,NS);_sifen_xml_text(gp,'dDMoneTiPag','Guarani' if mon=='PYG' else mon,NS)
            if mon!='PYG' and 'tipo_cambio' in d.keys() and d['tipo_cambio']:
                _sifen_xml_text(gp,'dTiCamTiPag',str(round(float(d['tipo_cambio']),4)),NS)
    if not items:
        raise ValueError('La factura no tiene líneas en venta_items. SIFEN exige al menos un gCamItem. Abra/corrija el detalle de esta factura antes de transmitirla; el ERP no inventará productos ni servicios fiscales.')
    # V13.9.89: construcción integral de importes obligatorios V150.
    # TgValorItem exige un grupo gValorRestaItem real (no una etiqueta vacía) y
    # TgCamIVA exige dBasExe incluso cuando el ítem está gravado.
    # V13.9.135: escala monetaria dependiente de la moneda.
    # Para PYG se calculan/escriben importes monetarios a 0 decimales. Esto evita que
    # el evaluador de reglas SIFEN recalcule el IVA en guaraníes a escala 0 mientras
    # el XML trae base/IVA fraccionarios. Para otras monedas conservamos 4 decimales.
    # V13.9.128: motor aritmético SIFEN con Decimal. La regla de SIFEN evalúa
    # los valores escritos en XML; por ello precio*cantidad, dTotOpeItem, base e IVA
    # se derivan de una única fuente y con redondeo HALF_UP uniforme.
    from decimal import Decimal, ROUND_HALF_UP
    QM=Decimal('1') if mon_ope=='PYG' else Decimal('0.0001')
    def D(v, default='0'):
        try: return Decimal(str(v if v not in (None,'') else default))
        except Exception: return Decimal(default)
    def X(v):
        v=D(v).quantize(QM, rounding=ROUND_HALF_UP)
        return format(v,'f')
    total=Decimal('0'); sub_exe=Decimal('0'); sub5=Decimal('0'); sub10=Decimal('0')
    iva5=Decimal('0'); iva10=Decimal('0'); base5=Decimal('0'); base10=Decimal('0')
    for ix,it in enumerate(items,1):
        gi=etree.SubElement(gd,'{%s}gCamItem'%NS)
        _sifen_xml_text(gi,'dCodInt',it['codigo'] if 'codigo' in it.keys() and it['codigo'] else str(ix),NS)
        desc_item=(str(it['sifen_desc_item'] or '').strip() if 'sifen_desc_item' in it.keys() else (str(it['descripcion'] or '').strip() if 'descripcion' in it.keys() else '')) or 'Servicio medico'
        _sifen_xml_text(gi,'dDesProSer',desc_item[:120],NS)
        _sifen_xml_text(gi,'cUniMed',(it['sifen_unidad_codigo'] if 'sifen_unidad_codigo' in it.keys() else None) or '77',NS);_sifen_xml_text(gi,'dDesUniMed',(it['sifen_unidad_desc'] if 'sifen_unidad_desc' in it.keys() else None) or 'UNI',NS)
        q=D(it['cantidad'], '1'); precio=D(it['precio']); pct=D(it['iva_pct'])
        # E727 = E721 * E711; EA008 coincide con E727 cuando no hay descuentos/anticipos.
        bruto=(q*precio).quantize(QM, rounding=ROUND_HALF_UP)
        ope=bruto
        _sifen_xml_text(gi,'dCantProSer',format(q.normalize(),'f'),NS)
        gv=etree.SubElement(gi,'{%s}gValorItem'%NS)
        _sifen_xml_text(gv,'dPUniProSer',X(precio),NS);_sifen_xml_text(gv,'dTotBruOpeItem',X(bruto),NS)
        gvr=etree.SubElement(gv,'{%s}gValorRestaItem'%NS)
        _sifen_xml_text(gvr,'dDescItem','0',NS);_sifen_xml_text(gvr,'dPorcDesIt','0',NS)
        _sifen_xml_text(gvr,'dDescGloItem','0',NS);_sifen_xml_text(gvr,'dAntPreUniIt','0',NS)
        _sifen_xml_text(gvr,'dAntGloPreUniIt','0',NS);_sifen_xml_text(gvr,'dTotOpeItem',X(ope),NS)
        giv=etree.SubElement(gi,'{%s}gCamIVA'%NS)
        af='3' if pct<=0 else '1'
        _sifen_xml_text(giv,'iAfecIVA',af,NS);_sifen_xml_text(giv,'dDesAfecIVA','Exento' if pct<=0 else 'Gravado IVA',NS)
        _sifen_xml_text(giv,'dPropIVA','100',NS);_sifen_xml_text(giv,'dTasaIVA',str(int(pct)),NS)
        if pct>0:
            divisor=Decimal('1')+(pct/Decimal('100'))
            base=(ope/divisor).quantize(QM, rounding=ROUND_HALF_UP)
            # E736: en PYG el motor usa escala 0; derivamos el impuesto como diferencia
            # entre la porción gravada y la base ya redondeada para conservar identidad monetaria.
            gravada=(ope*(Decimal('100')/Decimal('100'))).quantize(QM, rounding=ROUND_HALF_UP)
            iva=(gravada-base).quantize(QM, rounding=ROUND_HALF_UP)
        else:
            base=Decimal('0'); iva=Decimal('0')
        _sifen_xml_text(giv,'dBasGravIVA',X(base),NS);_sifen_xml_text(giv,'dLiqIVAItem',X(iva),NS)
        _sifen_xml_text(giv,'dBasExe',X(ope if pct<=0 else 0),NS)
        total+=ope
        if pct<=0: sub_exe+=ope
        elif pct==Decimal('5'): sub5+=ope; iva5+=iva; base5+=base
        elif pct==Decimal('10'): sub10+=ope; iva10+=iva; base10+=base
        else: raise ValueError('Tasa IVA SIFEN no soportada: %s. Use 0, 5 o 10.'%pct)

    tots=etree.SubElement(de,'{%s}gTotSub'%NS)
    # V13.9.132: respetar la semántica 0-1 del Manual Técnico V150.
    # Los campos opcionales se informan únicamente cuando existe una operación que los origina.
    # En particular, dLiqTotIVA5/10 son IVA DEL REDONDEO (F036/F037), no el IVA normal;
    # dComi/dIVAComi sólo corresponden cuando existe comisión. No se crean nodos opcionales
    # artificiales en cero, evitando que el evaluador de reglas procese combinaciones inexistentes.
    if sub_exe != 0: _sifen_xml_text(tots,'dSubExe',X(sub_exe),NS)
    if sub5 != 0: _sifen_xml_text(tots,'dSub5',X(sub5),NS)
    if sub10 != 0: _sifen_xml_text(tots,'dSub10',X(sub10),NS)
    _sifen_xml_text(tots,'dTotOpe',X(total),NS);_sifen_xml_text(tots,'dTotDesc','0',NS)
    _sifen_xml_text(tots,'dTotDescGlotem','0',NS);_sifen_xml_text(tots,'dTotAntItem','0',NS);_sifen_xml_text(tots,'dTotAnt','0',NS)
    _sifen_xml_text(tots,'dPorcDescTotal','0',NS);_sifen_xml_text(tots,'dDescTotal','0',NS);_sifen_xml_text(tots,'dAnticipo','0',NS)
    _sifen_xml_text(tots,'dRedon','0',NS);_sifen_xml_text(tots,'dTotGralOpe',X(total),NS)
    # V13.9.133: ORDEN XSD V150 ESTRICTO dentro de gTotSub.
    # El XSD usa xs:sequence: IVA5, IVA10, IVA de redondeo/comisión (si existen),
    # dTotIVA y SOLO DESPUÉS las bases gravadas. No intercalar dBaseGrav5 entre
    # dIVA5 y dTotIVA: SIFEN/XSD lo rechaza como SCHEMAV_ELEMENT_CONTENT.
    if sub5 != 0:
        _sifen_xml_text(tots,'dIVA5',X(iva5),NS)
    if sub10 != 0:
        _sifen_xml_text(tots,'dIVA10',X(iva10),NS)
    # dLiqTotIVA5/dLiqTotIVA10: únicamente si dRedon != 0 (aquí redondeo=0).
    # dIVAComi: únicamente si existe comisión (aquí no existe).
    if sub5 != 0 or sub10 != 0:
        _sifen_xml_text(tots,'dTotIVA',X(iva5+iva10),NS)
    if sub5 != 0:
        _sifen_xml_text(tots,'dBaseGrav5',X(base5),NS)
    if sub10 != 0:
        _sifen_xml_text(tots,'dBaseGrav10',X(base10),NS)
    if sub5 != 0 or sub10 != 0:
        _sifen_xml_text(tots,'dTBasGraIVA',X(base5+base10),NS)
    if asoc:
        ga=etree.SubElement(de,'{%s}gCamDEAsoc'%NS);_sifen_xml_text(ga,'iTipDocAso','1',NS);_sifen_xml_text(ga,'dDesTipDocAso','Electrónico',NS);_sifen_xml_text(ga,'dCdCDERef',asoc,NS)
    xml=etree.tostring(root,encoding='UTF-8',xml_declaration=True,pretty_print=False)
    return xml,cdc

def _sifen_generar_factura_test_autocontenida(c):
    """Genera una FE TEST completa sin depender de ventas históricas.

    Los registros se crean dentro de un SAVEPOINT y se revierten siempre; no
    quedan clientes, productos, ventas ni ítems de prueba en la base.
    """
    import datetime
    sp='sifen_autotest_fixture'
    c.execute('SAVEPOINT '+sp)
    try:
        # Receptor B2C de prueba: evita depender del maestro de clientes.
        cur=c.execute("insert into terceros(tipo,ruc,nombre,telefono,email,moneda,sifen_naturaleza,sifen_tipo_operacion,sifen_tipo_contribuyente,sifen_tipo_documento,sifen_numero_documento,sifen_pais,sifen_pais_desc,sifen_direccion,sifen_numero_casa) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                      ('CLIENTE','1234567','CONSUMIDOR FINAL TEST','','','PYG','2','2','2','1','1234567','PRY','Paraguay','Domicilio TEST','0'))
        tid=cur.lastrowid
        cur=c.execute("insert into productos(codigo,nombre,categoria,costo_pyg,precio_pyg,stock,stock_min,iva_pct,sifen_descripcion,sifen_unidad_codigo,sifen_unidad_desc) values(?,?,?,?,?,?,?,?,?,?,?)",
                      ('SIFEN-TEST','Servicio medico TEST','SERVICIO',0,11000,0,0,10,'Servicio medico TEST','77','UNI'))
        pid=cur.lastrowid
        # Número reservado únicamente dentro del SAVEPOINT. No consume correlativos.
        cur=c.execute("insert into ventas(fecha,cliente_id,numero,moneda,tipo_cambio,gravado,iva,exento,total,total_pyg,estado) values(?,?,?,?,?,?,?,?,?,?,?)",
                      (datetime.date.today().isoformat(),tid,'001-001-0000001','PYG',1,10000,1000,0,11000,11000,'TEST_SIFEN'))
        vid=cur.lastrowid
        cols={r['name'] for r in c.execute('pragma table_info(venta_items)').fetchall()}
        if 'descripcion' in cols:
            c.execute("insert into venta_items(venta_id,producto_id,cantidad,precio,total,total_pyg,costo_pyg,iva_pct,descripcion) values(?,?,?,?,?,?,?,?,?)",
                      (vid,pid,1,11000,11000,11000,0,10,'Servicio medico TEST'))
        else:
            c.execute("insert into venta_items(venta_id,producto_id,cantidad,precio,total,total_pyg,costo_pyg,iva_pct) values(?,?,?,?,?,?,?,?)",
                      (vid,pid,1,11000,11000,11000,0,10))
        xml,cdc=_sifen_generar_de_v150(c,'FE',vid)
        return xml,cdc,vid
    finally:
        c.execute('ROLLBACK TO '+sp)
        c.execute('RELEASE '+sp)

def _sifen_validar_xsd_v150(xml_bytes):
    """Valida un rDE V150 contra el esquema de recepción oficial.

    V13.9.120: el rDE se valida como documento completo contra siRecepDE_v150.xsd, que es el esquema de recepción oficial publicado por DNIT.
    """
    try:
        from lxml import etree
        raw = xml_bytes if isinstance(xml_bytes, bytes) else str(xml_bytes).encode('utf-8')
        doc = etree.fromstring(raw)
        qn = etree.QName(doc)
        ns_sifen = 'http://ekuatia.set.gov.py/sifen/xsd'
        if qn.localname != 'rDE' or qn.namespace != ns_sifen:
            return False, [f'Raíz/namespace inválido: {{{qn.namespace}}}{qn.localname}. Se requiere {{{ns_sifen}}}rDE.']
        ns={'s':ns_sifen}
        falt=[]
        for xp,nombre in [
          ('s:DE','DE'),('s:DE/s:gOpeDE','gOpeDE'),('s:DE/s:gTimb','gTimb'),
          ('s:DE/s:gDatGralOpe/s:gEmis','gEmis'),('s:DE/s:gDatGralOpe/s:gDatRec','gDatRec'),
          ('s:DE/s:gDtipDE','gDtipDE'),('s:DE/s:gDtipDE/s:gCamItem','gCamItem'),
          ('s:DE/s:gDtipDE/s:gCamItem/s:dCodInt','gCamItem/dCodInt'),
          ('s:DE/s:gDtipDE/s:gCamItem/s:dDesProSer','gCamItem/dDesProSer'),
          ('s:DE/s:gDtipDE/s:gCamItem/s:cUniMed','gCamItem/cUniMed'),
          ('s:DE/s:gDtipDE/s:gCamItem/s:dDesUniMed','gCamItem/dDesUniMed'),
          ('s:DE/s:gDtipDE/s:gCamItem/s:dCantProSer','gCamItem/dCantProSer'),
          ('s:DE/s:gDtipDE/s:gCamItem/s:gValorItem/s:dPUniProSer','gValorItem/dPUniProSer'),
          ('s:DE/s:gDtipDE/s:gCamItem/s:gValorItem/s:dTotBruOpeItem','gValorItem/dTotBruOpeItem'),
          ('s:DE/s:gDtipDE/s:gCamItem/s:gValorItem/s:gValorRestaItem/s:dTotOpeItem','gValorRestaItem/dTotOpeItem'),
          ('s:DE/s:gDtipDE/s:gCamItem/s:gCamIVA/s:dBasExe','gCamIVA/dBasExe'),
          ('s:DE/s:gTotSub/s:dTotOpe','gTotSub/dTotOpe'),('s:DE/s:gTotSub/s:dTotGralOpe','gTotSub/dTotGralOpe'),
          ('s:gCamFuFD','gCamFuFD'),('s:gCamFuFD/s:dCarQR','gCamFuFD/dCarQR')]:
            if not doc.xpath(xp,namespaces=ns): falt.append(nombre)
        if falt:
            return False,['Prevalidación V150: faltan grupos/campos: '+', '.join(falt)]
        for i,item in enumerate(doc.xpath('.//s:gCamItem',namespaces=ns),1):
            for tag in ('dCodInt','dDesProSer','cUniMed','dDesUniMed','dCantProSer'):
                e=item.find('{%s}%s'%(ns_sifen,tag))
                if e is None or not (e.text or '').strip():
                    return False,['Prevalidación V150: ítem %s con campo obligatorio vacío/faltante: %s.'%(i,tag)]
        # V13.9.133: barrera local contra errores de secuencia de gTotSub.
        # Si una futura modificación vuelve a desordenar estos nodos, se bloquea
        # el envío ANTES de consumir un intento en SIFEN.
        gt=doc.find('.//{%s}gTotSub'%ns_sifen)
        if gt is not None:
            orden=['dSubExe','dSubExo','dSub5','dSub10','dTotOpe','dTotDesc','dTotDescGlotem','dTotAntItem','dTotAnt','dPorcDescTotal','dDescTotal','dAnticipo','dRedon','dComi','dTotGralOpe','dIVA5','dIVA10','dLiqTotIVA5','dLiqTotIVA10','dIVAComi','dTotIVA','dBaseGrav5','dBaseGrav10','dTBasGraIVA','dTotalGs','dTotCom']
            pos={n:i for i,n in enumerate(orden)}
            nombres=[etree.QName(x).localname for x in gt]
            conocidos=[n for n in nombres if n in pos]
            if conocidos != sorted(conocidos,key=lambda n:pos[n]):
                return False,['Prevalidación V150: orden XSD inválido en gTotSub: '+', '.join(nombres)]
    except Exception as e:
        return False,['XML V150 no pudo analizarse: '+str(e)]

    try:
        import os, pysifen
        from lxml import etree
        base=os.path.dirname(os.path.abspath(pysifen.__file__))
        # V13.9.120: validar el DOCUMENTO rDE completo con el esquema de recepción.
        # DNIT define rDE como raíz de siRecepDE_v150.xsd. DE_v150.xsd es una
        # dependencia y no debe usarse como esquema raíz del rDE.
        candidatos=[]
        for root_dir, subdirs, files in os.walk(base):
            for nombre in ('siRecepDE_v150.xsd','SiRecepDE_v150.xsd'):
                if nombre in files:
                    candidatos.append(os.path.join(root_dir,nombre))
        if not candidatos:
            return False,['Motor SIFEN instalado, pero no contiene siRecepDE_v150.xsd. Reinstale las dependencias con requirements.txt; no se habilita Producción.']
        errores=[]
        for schema_path in candidatos:
            try:
                schema_doc=etree.parse(schema_path)
                schema=etree.XMLSchema(schema_doc)
                schema.assertValid(doc)
                return True,[]
            except etree.DocumentInvalid as e:
                return False,[str(x) for x in e.error_log]
            except (etree.XMLSchemaParseError, etree.XMLSyntaxError, OSError) as e:
                errores.append(os.path.basename(schema_path)+': '+str(e))
        return False, errores or ['No fue posible compilar siRecepDE_v150.xsd con sus imports/includes.']
    except Exception as e:
        return False,['Validación XSD V150 no disponible: '+str(e)]

def _sifen_guardar_xml_test(tipo,doc_id,xml,cdc):
    p=Path(_sifen_dir())/'xml_test';p.mkdir(parents=True,exist_ok=True)
    f=p/(str(tipo).upper()+'_'+str(doc_id)+'_'+str(cdc)+'.xml');f.write_bytes(xml);return str(f)

# ===== V13.9.79: motor SIFEN XMLDSig + SOAP/mTLS =====
def _sifen_endpoint(cfg, servicio='sync'):
    base=_sifen_base(cfg)
    rutas={
      'sync':'/de/ws/sync/recibe.wsdl',
      'lote':'/de/ws/async/recibe-lote.wsdl',
      'consulta_lote':'/de/ws/consultas/consulta-lote.wsdl',
      'consulta_cdc':'/de/ws/consultas/consulta.wsdl',
      'eventos':'/de/ws/eventos/evento.wsdl',
    }
    if servicio not in rutas: raise ValueError('Servicio SIFEN no soportado: '+str(servicio))
    return base+rutas[servicio]

def _sifen_qr_url_rde(root,cfg):
    """Construye dCarQR V150 con el DigestValue de la firma y CSC configurado."""
    import hashlib
    from lxml import etree
    NS='http://ekuatia.set.gov.py/sifen/xsd'; DS='http://www.w3.org/2000/09/xmldsig#'
    de=root.find('{%s}DE'%NS)
    if de is None: raise ValueError('No existe DE para construir QR.')
    cdc=(de.get('Id') or '').strip(); fec=de.findtext('.//{%s}dFeEmiDE'%NS) or ''
    rec=de.find('.//{%s}gDatRec'%NS)
    recid=''
    if rec is not None: recid=(rec.findtext('{%s}dRucRec'%NS) or rec.findtext('{%s}dNumIDRec'%NS) or '').strip()
    tot=de.findtext('.//{%s}gTotSub/{%s}dTotGralOpe'%(NS,NS)) or '0'; iva=de.findtext('.//{%s}gTotSub/{%s}dTotIVA'%(NS,NS)) or '0'
    cant=len(de.findall('.//{%s}gCamItem'%NS))
    digest=root.findtext('.//{%s}DigestValue'%DS) or ''
    if not digest: raise ValueError('La firma XMLDSig no contiene DigestValue para generar el QR.')
    idcsc=str(cfg['csc_id'] or '').strip(); csc=str(cfg['csc'] or '').strip()
    if not idcsc or not csc: raise ValueError('Falta IdCSC/CSC. Configure el Código de Seguridad del Contribuyente para generar gCamFuFD/dCarQR.')
    def hx(x): return str(x).encode('utf-8').hex()
    # MT V150: fecha y DigestValue se representan en hexadecimal.
    base='nVersion=150&Id='+cdc+'&dFeEmiDE='+hx(fec)+'&dRucRec='+recid+'&dTotGralOpe='+str(tot)+'&dTotIVA='+str(iva)+'&cItems='+str(cant)+'&DigestValue='+hx(digest)+'&IdCSC='+idcsc
    h=hashlib.sha256((base+csc).encode('utf-8')).hexdigest().lower()
    pref='https://ekuatia.set.gov.py/consultas/qr?' if str(cfg['ambiente'] or '').upper()=='PRODUCCION' else 'https://ekuatia.set.gov.py/consultas-test/qr?'
    return pref+base+'&cHashQR='+h

def _sifen_firmar_rde(xml_bytes,cfg):
    """Firma DE y agrega gCamFuFD/dCarQR fuera de la firma, conforme MT V150."""
    from lxml import etree
    from signxml import XMLSigner,methods
    if isinstance(xml_bytes,str): xml_bytes=xml_bytes.encode('utf-8')
    parser=etree.XMLParser(remove_blank_text=True,resolve_entities=False,no_network=True)
    root=etree.fromstring(xml_bytes,parser);ns='http://ekuatia.set.gov.py/sifen/xsd'
    if etree.QName(root).localname!='rDE': raise ValueError('El XML debe tener raíz rDE.')
    ver=root.find('{%s}dVerFor'%ns);de=root.find('{%s}DE'%ns)
    if ver is None or (ver.text or '').strip()!='150': raise ValueError('El DE debe ser versión 150.')
    if de is None or not (de.get('Id') or '').strip(): raise ValueError('El DE no contiene CDC/Id.')
    if not cfg['cert_path'] or not cfg['key_path']: raise ValueError('Certificado digital no instalado.')
    cert=Path(cfg['cert_path']).read_bytes();key=Path(cfg['key_path']).read_bytes()
    signer=XMLSigner(method=methods.enveloped,signature_algorithm='rsa-sha256',digest_algorithm='sha256',c14n_algorithm='http://www.w3.org/2001/10/xml-exc-c14n#')
    firmado=signer.sign(root,key=key,cert=cert,reference_uri='#'+de.get('Id'),id_attribute='Id')
    # El grupo J va después de Signature y no forma parte de la firma digital.
    for viejo in firmado.findall('{%s}gCamFuFD'%ns): firmado.remove(viejo)
    gf=etree.SubElement(firmado,'{%s}gCamFuFD'%ns)
    _sifen_xml_text(gf,'dCarQR',_sifen_qr_url_rde(firmado,cfg),ns)
    return etree.tostring(firmado,encoding='UTF-8',xml_declaration=True,pretty_print=False)

def _sifen_extraer_qr_rde(xml_bytes):
    from lxml import etree
    NS='http://ekuatia.set.gov.py/sifen/xsd'
    root=etree.fromstring(xml_bytes if isinstance(xml_bytes,(bytes,bytearray)) else xml_bytes.encode('utf-8'))
    return (root.findtext('{%s}gCamFuFD/{%s}dCarQR'%(NS,NS)) or '').strip()

def init_v139112_respuesta_sifen_detallada():
    c=db(); cols={r['name'] for r in c.execute('pragma table_info(ventas)').fetchall()}
    for col,ddl in [('respuesta_sifen','TEXT'),('sifen_http_status','INTEGER'),('sifen_fecha_respuesta','TEXT')]:
        if col not in cols: c.execute(f'alter table ventas add column {col} {ddl}')
    c.execute("insert or ignore into schema_migrations(version,aplicado_en) values('13.9.112-respuesta-sifen-detallada',?)",(now(),))
    c.commit();c.close()
init_v139112_respuesta_sifen_detallada()

def _sifen_guardar_respuesta_venta(c,venta_id,status,resp,parsed,estado,cdc,qr):
    aprobado=estado in ('APROBADO','APROBADA','ACEPTADO','ACEPTADA')
    codigo=str(parsed.get('codigo') or parsed.get('codigo_lote') or '')
    mensaje=str(parsed.get('mensaje') or parsed.get('mensaje_lote') or '')
    raw=(resp.decode('utf-8','replace') if isinstance(resp,(bytes,bytearray)) else str(resp or ''))
    sql="""update ventas set cdc=?,qr_sifen=?,estado_sifen=?,protocolo_sifen=?,fecha_aprobacion_sifen=?,
             sifen_codigo_error=?,sifen_mensaje_error=?,sifen_ultimo_intento=?,sifen_intentos=coalesce(sifen_intentos,0)+1,
             respuesta_sifen=?,sifen_http_status=?,sifen_fecha_respuesta=? where id=?"""
    c.execute(sql,(cdc,qr,estado,parsed.get('protocolo',''),now() if aprobado else None,codigo,mensaje,now(),raw[:50000],status,parsed.get('fecha_proceso') or now(),venta_id))

def _sifen_emitir_factura_automatico(venta_id):
    """Proceso único FE: CDC -> XML -> firma -> QR -> XSD -> WS SIFEN.
    TEST transmite al WS TEST para obtener el resultado real de validación, sin valor fiscal.
    PRODUCCION transmite solo cuando la habilitación segura está activa.
    """
    c=db()
    try:
        cfg=c.execute('select * from sifen_config where id=1').fetchone()
        if not cfg: raise ValueError('Configuración SIFEN inexistente.')
        ambiente=str(cfg['ambiente'] or 'TEST').upper()
        xml,cdc=_sifen_generar_de_v150(c,'FE',venta_id)
        # V13.9.123: el CDC identifica al DE y debe sobrevivir a cualquier error posterior.
        c.execute('update ventas set cdc=? where id=?',(cdc,venta_id)); c.commit()
        firmado=_sifen_firmar_rde(xml,cfg)
        qr=_sifen_extraer_qr_rde(firmado)
        if not qr: raise ValueError('El XML firmado no contiene dCarQR.')
        # El dCarQR también se persiste ANTES de XSD/transporte. Un rechazo no lo borra.
        c.execute('update ventas set cdc=?,qr_sifen=? where id=?',(cdc,qr,venta_id)); c.commit()
        _sifen_guardar_xml_test('FE',venta_id,firmado,cdc)
        ok,detalle=_sifen_validar_xsd_v150(firmado)
        if not ok: raise ValueError('XSD V150 rechazó el XML: '+str(detalle))
        if ambiente=='PRODUCCION':
            if not int(cfg['produccion_habilitada'] or 0):
                raise ValueError('Producción SIFEN no está habilitada en el ERP.')
            checks=_sifen_diagnostico(c,cfg); faltan=[x['nombre'] for x in checks if not x['ok']]
            if faltan: raise ValueError('Diagnóstico de Producción pendiente: '+', '.join(faltan))
        elif ambiente!='TEST':
            raise ValueError('Ambiente SIFEN no reconocido: '+ambiente)
        # TEST también debe transmitir: el objetivo del ambiente de pruebas es
        # recibir la validación real de SIFEN (aprobación/rechazo sin valor fiscal).
        # V13.9.114: el RUC puede no estar habilitado para recepción síncrona (1264).
        # La FE se transmite por el WS oficial de lote y luego se consulta por protocolo.
        status,resp,url=_sifen_enviar_lote(firmado,cfg)
        parsed=_sifen_parse_respuesta(resp); estado=str(parsed.get('estado') or 'RESPUESTA_RECIBIDA').upper()
        protocolo=str(parsed.get('lote') or parsed.get('protocolo') or '')
        if str(parsed.get('codigo') or '')=='0300' and protocolo:
            estado='LOTE_RECIBIDO'
            parsed['protocolo']=protocolo;parsed['lote']=protocolo
        _sifen_guardar_respuesta_venta(c,venta_id,status,resp,parsed,estado,cdc,qr)
        if ambiente=='PRODUCCION':
            c.execute('update sifen_config set ultimo_envio_prod=?,ultimo_envio_prod_estado=?,actualizado_en=? where id=1',(now(),estado,now()))
        c.execute('insert into sifen_eventos(fecha,tipo,estado,detalle) values(?,?,?,?)',(now(),'FE_EMISION_AUTOMATICA_'+ambiente,estado,f'Factura {venta_id} · CDC {cdc} · HTTP {status} · {parsed.get("codigo","")} {parsed.get("mensaje","")} · {url}'))
        c.commit()
        return estado
    except Exception as ex:
        c.rollback()
        # Un fallo local/de conexión NO es un rechazo SIFEN. Se conserva el
        # motivo técnico y se permite reintentar sin alterar número/CDC/importe.
        try:
            c.execute("update ventas set estado_sifen='ERROR_ENVIO',sifen_codigo_error='',sifen_mensaje_error=?,sifen_ultimo_intento=?,sifen_intentos=coalesce(sifen_intentos,0)+1,sifen_fecha_respuesta=null where id=?",(str(ex)[:3000],now(),venta_id))
            c.execute('insert into sifen_eventos(fecha,tipo,estado,detalle) values(?,?,?,?)',(now(),'FE_EMISION_AUTOMATICA','ERROR_ENVIO',f'Factura {venta_id}: {ex}'))
            c.commit()
        except Exception:
            c.rollback()
        raise
    finally:
        c.close()

@app.post('/ventas/<int:venta_id>/sifen/preparar-validacion')
def sifen_preparar_validacion_factura(venta_id):
    c=db()
    try:
        cfg=c.execute('select * from sifen_config where id=1').fetchone()
        if not cfg: raise ValueError('Configuración SIFEN inexistente.')
        xml,cdc=_sifen_generar_de_v150(c,'FE',venta_id)
        c.execute('update ventas set cdc=? where id=?',(cdc,venta_id)); c.commit()
        firmado=_sifen_firmar_rde(xml,cfg)
        qr=_sifen_extraer_qr_rde(firmado)
        if not qr: raise ValueError('El rDE firmado no contiene dCarQR.')
        c.execute('update ventas set cdc=?,qr_sifen=? where id=?',(cdc,qr,venta_id)); c.commit()
        ok,detalle=_sifen_validar_xsd_v150(firmado)
        if not ok: raise ValueError('El XML firmado no pasó XSD V150: '+str(detalle))
        estado_actual=c.execute('select estado_sifen from ventas where id=?',(venta_id,)).fetchone()
        ea=str(estado_actual['estado_sifen'] or '').upper() if estado_actual else ''
        nuevo=ea if ea in ('APROBADO','APROBADA','ACEPTADO','ACEPTADA') else 'TEST_VALIDADO_XSD'
        c.execute('update ventas set cdc=?,qr_sifen=?,estado_sifen=? where id=?',(cdc,qr,nuevo,venta_id))
        c.execute('insert into sifen_eventos(fecha,tipo,estado,detalle) values(?,?,?,?)',(now(),'FE_PREVALIDACION','OK',f'Factura {venta_id} · CDC {cdc} · QR generado desde dCarQR del XML firmado · XSD V150 OK'))
        c.commit();flash('CDC y QR generados desde el XML firmado. XSD V150: OK. El QR queda en la factura para validación; esto no equivale a aprobación SIFEN.')
    except Exception as ex:
        c.rollback();_sifen_log('FE_PREVALIDACION','ERROR',f'Factura {venta_id}: {ex}');flash('No se pudo generar CDC/QR para validación: '+str(ex))
    finally:
        c.close()
    return redirect(f'/ventas/{venta_id}/factura')

@app.post('/ventas/<int:venta_id>/sifen/enviar')
def sifen_enviar_factura(venta_id):
    c=db()
    try:
        cfg=c.execute('select * from sifen_config where id=1').fetchone()
        if not cfg or str(cfg['ambiente'] or '').upper()!='PRODUCCION' or not int(cfg['produccion_habilitada'] or 0):
            raise ValueError('Producción SIFEN no está habilitada en el ERP.')
        xml,cdc=_sifen_generar_de_v150(c,'FE',venta_id)
        c.execute('update ventas set cdc=? where id=?',(cdc,venta_id)); c.commit()
        firmado=_sifen_firmar_rde(xml,cfg)
        qr=_sifen_extraer_qr_rde(firmado)
        if not qr: raise ValueError('El rDE firmado no contiene dCarQR.')
        c.execute('update ventas set cdc=?,qr_sifen=? where id=?',(cdc,qr,venta_id)); c.commit()
        _sifen_guardar_xml_test('FE',venta_id,firmado,cdc)
        ok,detalle=_sifen_validar_xsd_v150(firmado)
        if not ok: raise ValueError('XSD V150 rechazó el XML: '+str(detalle))
        checks=_sifen_diagnostico(c,cfg); faltan=[x['nombre'] for x in checks if not x['ok']]
        if faltan: raise ValueError('Diagnóstico de Producción pendiente: '+', '.join(faltan))
        status,resp,url=_sifen_enviar_sync(firmado,cfg)
        parsed=_sifen_parse_respuesta(resp); estado=str(parsed.get('estado') or 'RESPUESTA_RECIBIDA').upper()
        _sifen_guardar_respuesta_venta(c,venta_id,status,resp,parsed,estado,cdc,qr)
        c.execute('update sifen_config set ultimo_envio_prod=?,ultimo_envio_prod_estado=?,actualizado_en=? where id=1',(now(),estado,now()))
        c.execute('insert into sifen_eventos(fecha,tipo,estado,detalle) values(?,?,?,?)',(now(),'FE_ENVIO_PRODUCCION',estado,f'Factura {venta_id} · CDC {cdc} · HTTP {status} · {parsed.get("codigo","")} {parsed.get("mensaje","")}'))
        c.commit()
        if estado in ('APROBADO','APROBADA','ACEPTADO','ACEPTADA'): flash('SIFEN aprobó la factura. El PDF queda habilitado como KuDE con CDC y QR de Producción.')
        else: flash('SIFEN respondió: '+estado+' · '+str(parsed.get('codigo',''))+' · '+str(parsed.get('mensaje','')))
    except Exception as ex:
        c.rollback(); _sifen_log('FE_ENVIO_PRODUCCION','ERROR',f'Factura {venta_id}: {ex}'); flash('Factura NO enviada/aprobada: '+str(ex))
    finally: c.close()
    return redirect(f'/ventas/{venta_id}/factura')

@app.get('/ventas/<int:venta_id>/sifen/detalle')
def sifen_detalle_factura(venta_id):
    c=db(); v=c.execute("select v.*,t.nombre cliente,t.ruc cliente_ruc from ventas v left join terceros t on t.id=v.cliente_id where v.id=?",(venta_id,)).fetchone(); c.close()
    if not v:return ('Factura no encontrada',404)
    return render_template('sifen_invoice_detail.html',v=v)

@app.get('/ventas/<int:venta_id>/sifen/qr.svg')
def sifen_qr_factura_svg(venta_id):
    from flask import Response
    from reportlab.graphics.barcode import qr
    from reportlab.graphics.shapes import Drawing
    from reportlab.graphics import renderSVG
    c=db();r=c.execute('select qr_sifen from ventas where id=?',(venta_id,)).fetchone();c.close()
    texto=(r['qr_sifen'] if r and 'qr_sifen' in r.keys() else '') or ''
    if not texto:return Response('QR SIFEN no generado',status=404,mimetype='text/plain')
    q=qr.QrCodeWidget(texto);b=q.getBounds();w=b[2]-b[0];h=b[3]-b[1];size=180
    d=Drawing(size,size,transform=[size/w,0,0,size/h,0,0]);d.add(q)
    return Response(renderSVG.drawToString(d),mimetype='image/svg+xml')

def _sifen_enviar_sync(xml_firmado,cfg,timeout=35):
    """Transmite un rDE firmado por recepción sincrónica SIFEN usando mTLS."""
    import requests,secrets
    from lxml import etree
    if not cfg['cert_path'] or not cfg['key_path']: raise ValueError('Certificado digital no instalado.')
    parser=etree.XMLParser(remove_blank_text=True,resolve_entities=False,no_network=True)
    rde=etree.fromstring(xml_firmado if isinstance(xml_firmado,(bytes,bytearray)) else xml_firmado.encode(),parser)
    NS='http://ekuatia.set.gov.py/sifen/xsd'; SOAP='http://www.w3.org/2003/05/soap-envelope'
    # V13.9.103: SIFEN V150 prohíbe prefijos de namespace en las etiquetas del
    # request. El prefijo soap: se conserva únicamente para el sobre SOAP; el
    # documento SIFEN usa su namespace como namespace por defecto.
    env=etree.Element('{%s}Envelope'%SOAP,nsmap={'soap':SOAP})
    etree.SubElement(env,'{%s}Header'%SOAP)
    body=etree.SubElement(env,'{%s}Body'%SOAP)
    envio=etree.SubElement(body,'{%s}rEnviDe'%NS,nsmap={None:NS})
    etree.SubElement(envio,'{%s}dId'%NS).text=str(secrets.randbelow(900000000000000)+100000000000000)
    xde=etree.SubElement(envio,'{%s}xDE'%NS)
    xde.append(rde)
    payload=etree.tostring(env,encoding='UTF-8',xml_declaration=True,pretty_print=False)
    # No transmitir un request si lxml introdujo un prefijo automático (ns0,
    # ns1, etc.). Es preferible bloquear localmente que consumir un número con
    # un request que SIFEN rechazará por formato.
    import re
    if re.search(br'<\/?ns\d+:',payload) or re.search(br'xmlns:ns\d+=',payload):
        raise ValueError('SOAP SIFEN inválido: se detectó un prefijo namespace automático (ns0/ns1). El envío fue bloqueado localmente.')
    url=_sifen_endpoint(cfg,'sync')
    r=requests.post(url,data=payload,headers={'Content-Type':'application/soap+xml; charset=utf-8'},cert=(cfg['cert_path'],cfg['key_path']),timeout=timeout)
    return r.status_code,r.content,url

def _sifen_enviar_lote(xml_firmado,cfg,timeout=35):
    """Envía un lote SIFEN V150 (1 DE en este flujo) por el WS asíncrono oficial."""
    import requests,secrets,base64,io,zipfile,re
    from lxml import etree
    if not cfg['cert_path'] or not cfg['key_path']: raise ValueError('Certificado digital no instalado.')
    NS='http://ekuatia.set.gov.py/sifen/xsd'; SOAP='http://www.w3.org/2003/05/soap-envelope'
    parser=etree.XMLParser(remove_blank_text=True,resolve_entities=False,no_network=True)
    rde=etree.fromstring(xml_firmado if isinstance(xml_firmado,(bytes,bytearray)) else xml_firmado.encode(),parser)
    qn=etree.QName(rde)
    if qn.localname!='rDE' or qn.namespace!=NS:
        raise ValueError(f'El documento firmado para lote debe ser {{{NS}}}rDE; recibido {{{qn.namespace}}}{qn.localname}.')
    # V13.9.116: conservar el schemaLocation oficial del rDE indicado por DNIT.
    XSI='http://www.w3.org/2001/XMLSchema-instance'
    schema_loc=(rde.get('{%s}schemaLocation'%XSI) or '').strip()
    if not schema_loc or 'siRecepDE_v150.xsd' not in schema_loc:
        rde.set('{%s}schemaLocation'%XSI,NS+' siRecepDE_v150.xsd')
    # V13.9.121: en el archivo comprimido el CONTENEDOR rLoteDE NO lleva
    # el namespace SIFEN como namespace por defecto. Cada rDE debe conservar
    # individualmente su declaración xmlns, tal como exige la guía DNIT para
    # envíos por lote. Si rLoteDE hereda xmlns=SIFEN, lxml elimina la
    # declaración individual del rDE y SIFEN termina rechazándolo (0160:
    # Cannot find the declaration of element 'rDE').
    lote=etree.Element('rLoteDE')
    lote.append(rde)
    lote_xml=etree.tostring(lote,encoding='UTF-8',xml_declaration=True,pretty_print=False)
    # Guardia técnica: el lote debe ser raíz sin namespace y el rDE hijo debe
    # seguir perteneciendo al namespace oficial SIFEN.
    chk=etree.fromstring(lote_xml,parser)
    if etree.QName(chk).localname!='rLoteDE' or etree.QName(chk).namespace:
        raise ValueError('Lote SIFEN inválido: rLoteDE no debe heredar namespace.')
    hijos=list(chk)
    if not hijos or etree.QName(hijos[0]).localname!='rDE' or etree.QName(hijos[0]).namespace!=NS:
        raise ValueError('Lote SIFEN inválido: rDE perdió su namespace individual.')
    # Manual Técnico V150: xDE es un archivo .zip codificado Base64.
    mem=io.BytesIO()
    with zipfile.ZipFile(mem,'w',compression=zipfile.ZIP_DEFLATED) as z:z.writestr('lote.xml',lote_xml)
    b64=base64.b64encode(mem.getvalue()).decode('ascii')
    env=etree.Element('{%s}Envelope'%SOAP,nsmap={'soap':SOAP});etree.SubElement(env,'{%s}Header'%SOAP);body=etree.SubElement(env,'{%s}Body'%SOAP)
    envio=etree.SubElement(body,'{%s}rEnvioLote'%NS,nsmap={None:NS})
    etree.SubElement(envio,'{%s}dId'%NS).text=str(secrets.randbelow(900000000000000)+100000000000000)
    etree.SubElement(envio,'{%s}xDE'%NS).text=b64
    payload=etree.tostring(env,encoding='UTF-8',xml_declaration=True,pretty_print=False)
    if re.search(br'<\/?ns\d+:',payload) or re.search(br'xmlns:ns\d+=',payload): raise ValueError('SOAP SIFEN lote inválido: prefijo namespace automático ns0/ns1.')
    url=_sifen_endpoint(cfg,'lote')
    r=requests.post(url,data=payload,headers={'Content-Type':'application/soap+xml; charset=utf-8'},cert=(cfg['cert_path'],cfg['key_path']),timeout=timeout)
    return r.status_code,r.content,url

def _sifen_consultar_lote(protocolo,cfg,timeout=35):
    """Consulta el resultado de un lote usando dProtConsLote devuelto por SIFEN."""
    import requests,secrets,re
    from lxml import etree
    protocolo=str(protocolo or '').strip()
    if not protocolo: raise ValueError('No existe número/protocolo de lote para consultar.')
    NS='http://ekuatia.set.gov.py/sifen/xsd'; SOAP='http://www.w3.org/2003/05/soap-envelope'
    env=etree.Element('{%s}Envelope'%SOAP,nsmap={'soap':SOAP});etree.SubElement(env,'{%s}Header'%SOAP);body=etree.SubElement(env,'{%s}Body'%SOAP)
    req=etree.SubElement(body,'{%s}rEnviConsLoteDe'%NS,nsmap={None:NS})
    etree.SubElement(req,'{%s}dId'%NS).text=str(secrets.randbelow(900000000000000)+100000000000000)
    etree.SubElement(req,'{%s}dProtConsLote'%NS).text=protocolo
    payload=etree.tostring(env,encoding='UTF-8',xml_declaration=True,pretty_print=False)
    if re.search(br'<\/?ns\d+:',payload) or re.search(br'xmlns:ns\d+=',payload): raise ValueError('SOAP consulta lote inválido: prefijo namespace automático ns0/ns1.')
    url=_sifen_endpoint(cfg,'consulta_lote')
    r=requests.post(url,data=payload,headers={'Content-Type':'application/soap+xml; charset=utf-8'},cert=(cfg['cert_path'],cfg['key_path']),timeout=timeout)
    return r.status_code,r.content,url

def _sifen_parse_respuesta(xml_bytes):
    """Interpreta respuestas SOAP SIFEN sync y consulta de lote sin depender del prefijo XML."""
    from lxml import etree
    out={'estado':'SIN_RESPUESTA','codigo':'','mensaje':'','protocolo':'','cdc':'','lote':'','fecha_proceso':'','codigo_lote':'','mensaje_lote':'','resultados':[]}
    try:
        root=etree.fromstring(xml_bytes if isinstance(xml_bytes,(bytes,bytearray)) else str(xml_bytes).encode(),etree.XMLParser(resolve_entities=False,no_network=True))
        def first(local,ctx=None):
            base=ctx if ctx is not None else root;x=base.xpath('.//*[local-name()=$n]',n=local)
            return (x[0].text or '').strip() if x else ''
        out['fecha_proceso']=first('dFecProc');out['codigo_lote']=first('dCodResLot');out['mensaje_lote']=first('dMsgResLot')
        import re
        m=re.search(r'\{(\d+)\}',out['mensaje_lote'] or '')
        if m:out['lote']=m.group(1)
        bloques=root.xpath('//*[local-name()="gResProcLote"]')
        if bloques:
            for b in bloques:out['resultados'].append({'cdc':first('id',b),'estado':first('dEstRes',b),'codigo':first('dCodRes',b),'mensaje':first('dMsgRes',b)})
            r=out['resultados'][0];out['cdc']=r['cdc'];out['estado']=r['estado'] or 'RESPUESTA_RECIBIDA';out['codigo']=r['codigo'];out['mensaje']=r['mensaje']
        else:
            out['estado']=first('dEstRes') or 'RESPUESTA_RECIBIDA';out['codigo']=first('dCodRes');out['mensaje']=first('dMsgRes');out['protocolo']=first('dProtAut') or first('dProtConsLote');out['cdc']=first('dId') or first('id')
            if first('dProtConsLote'):
                out['lote']=first('dProtConsLote')
                # 0300 = lote recibido. Todavía no significa aprobación del DE.
                if out['codigo']=='0300': out['estado']='LOTE_RECIBIDO'
        if not out['mensaje'] and out['mensaje_lote']:out['mensaje']=out['mensaje_lote']
    except Exception as e:out['estado']='ERROR_XML';out['mensaje']=str(e)
    return out

def _sifen_motor_autotest(cfg):
    """Prueba local: construye un XML mínimo técnico, firma y verifica XMLDSig sin enviarlo."""
    from lxml import etree
    from signxml import XMLVerifier
    if not cfg['cert_path'] or not cfg['key_path']: raise ValueError('Instale primero el certificado digital.')
    NS='http://ekuatia.set.gov.py/sifen/xsd'; XSI='http://www.w3.org/2001/XMLSchema-instance'
    root=etree.Element('{%s}rDE'%NS,nsmap={None:NS,'xsi':XSI}); etree.SubElement(root,'{%s}dVerFor'%NS).text='150'
    de=etree.SubElement(root,'{%s}DE'%NS);de.set('Id','0'*44)
    firmado=_sifen_firmar_rde(etree.tostring(root),cfg)
    XMLVerifier().verify(firmado,x509_cert=Path(cfg['cert_path']).read_bytes(),id_attribute='Id')
    return True

def _sifen_dir():
    p=os.path.join(DATA_DIR,'sifen');os.makedirs(p,exist_ok=True)
    try: os.chmod(p,0o700)
    except OSError: pass
    return p

def _sifen_log(tipo,estado,detalle):
    c=db();c.execute('insert into sifen_eventos(fecha,tipo,estado,detalle) values(?,?,?,?)',(now(),tipo,estado,str(detalle)[:3000]));c.commit();c.close()

def _sifen_cert_info(p12_bytes,password):
    from cryptography.hazmat.primitives.serialization import pkcs12,Encoding,PrivateFormat,NoEncryption
    key,cert,chain=pkcs12.load_key_and_certificates(p12_bytes,password.encode() if password else None)
    if not key or not cert: raise ValueError('El archivo no contiene certificado y clave privada.')
    d=_sifen_dir(); cert_path=os.path.join(d,'client-cert.pem'); key_path=os.path.join(d,'client-key.pem')
    with open(cert_path,'wb') as f:f.write(cert.public_bytes(Encoding.PEM))
    with open(key_path,'wb') as f:f.write(key.private_bytes(Encoding.PEM,PrivateFormat.PKCS8,NoEncryption()))
    try: os.chmod(cert_path,0o600);os.chmod(key_path,0o600)
    except OSError: pass
    return cert,cert_path,key_path

@app.route('/configuracion/sifen',methods=['GET','POST'])
def configuracion_sifen():
    if not (user_has('USUARIOS','ADMINISTRAR') or user_has('CONFIG_SANATORIO','EDITAR')):
        flash('No tiene permiso para configurar SIFEN.');return redirect('/')
    c=db()
    if request.method=='POST':
        accion=request.form.get('accion','guardar')
        if accion=='punto_guardar':
            try:
                est=_solo_digitos(request.form.get('p_establecimiento'))[-3:].zfill(3);pex=_solo_digitos(request.form.get('p_punto'))[-3:].zfill(3)
                if not est or not pex: raise ValueError('Establecimiento y punto son obligatorios.')
                pid=int(request.form.get('p_id') or 0);pred=1 if request.form.get('p_predeterminado') else 0
                # V13.9.104: si el usuario carga una combinación ya existente sin p_id,
                # tratarla como edición del maestro en vez de intentar INSERT y disparar UNIQUE.
                # Esto mantiene un solo registro por establecimiento+punto y evita duplicados.
                if not pid:
                    existente=c.execute('select id from sifen_puntos_expedicion where establecimiento=? and punto_expedicion=?',(est,pex)).fetchone()
                    if existente: pid=int(existente['id'])
                descripcion=(request.form.get('p_descripcion') or '').strip();timbrado=(request.form.get('p_timbrado') or '').strip()
                fe=1 if request.form.get('p_factura') else 0;nc=1 if request.form.get('p_nc') else 0;nd=1 if request.form.get('p_nd') else 0
                autorizado=1 if request.form.get('p_autorizado') else 0;activo=1 if request.form.get('p_activo') else 0
                solicitado=max(1,int(request.form.get('p_proximo') or 1))
                if pid:
                    actual=c.execute('select * from sifen_puntos_expedicion where id=?',(pid,)).fetchone()
                    if not actual: raise ValueError('Punto de expedición no encontrado.')
                    uso_fe=c.execute('select count(*) from ventas where sifen_punto_id=?',(pid,)).fetchone()[0]
                    uso_nc=0
                    try: uso_nc=c.execute('select count(*) from notas_credito_ventas n join ventas v on v.id=n.venta_id where v.sifen_punto_id=?',(pid,)).fetchone()[0]
                    except Exception: pass
                    usado=(uso_fe or uso_nc)
                    # V13.9.108: un punto ya utilizado sigue siendo editable en sus datos operativos.
                    # Los campos que identifican fiscalmente documentos históricos se preservan
                    # automáticamente en vez de rechazar todo el formulario con un error.
                    if usado:
                        est=str(actual['establecimiento'] or '').zfill(3)
                        pex=str(actual['punto_expedicion'] or '').zfill(3)
                        timbrado=(actual['timbrado'] or '')
                        solicitado=int(actual['proximo_numero_factura'] or 1)
                    if pred:c.execute('update sifen_puntos_expedicion set predeterminado=0 where id<>?',(pid,))
                    c.execute('update sifen_puntos_expedicion set establecimiento=?,punto_expedicion=?,descripcion=?,timbrado=?,factura_electronica=?,nota_credito_electronica=?,nota_debito_electronica=?,autorizado_dnit=?,activo=?,predeterminado=?,proximo_numero_factura=?,actualizado_en=? where id=?',(est,pex,descripcion,timbrado,fe,nc,nd,autorizado,activo,pred,solicitado,now(),pid))
                    # Mantener la configuración institucional alineada con el punto
                    # predeterminado para que los formularios/KuDE no muestren datos antiguos.
                    if pred:
                        c.execute('update institucion_config set establecimiento=?,punto_expedicion=?,timbrado=coalesce(nullif(?,''),timbrado) where id=1',(est,pex,timbrado))
                    flash('Punto de expedición actualizado correctamente. Los próximos documentos usarán estos datos; los documentos ya emitidos conservan su numeración histórica.')
                else:
                    if pred:c.execute('update sifen_puntos_expedicion set predeterminado=0')
                    c.execute('insert into sifen_puntos_expedicion(establecimiento,punto_expedicion,descripcion,timbrado,factura_electronica,nota_credito_electronica,nota_debito_electronica,autorizado_dnit,activo,predeterminado,proximo_numero_factura,creado_en,actualizado_en) values(?,?,?,?,?,?,?,?,?,?,?,?,?)',(est,pex,descripcion,timbrado,fe,nc,nd,autorizado,activo,pred,solicitado,now(),now()))
                    if pred:
                        c.execute('update institucion_config set establecimiento=?,punto_expedicion=?,timbrado=coalesce(nullif(?,''),timbrado) where id=1',(est,pex,timbrado))
                    flash('Punto de expedición registrado. Use únicamente códigos previamente autorizados por DNIT.')
                c.commit()
            except Exception as e:c.rollback();flash('No se pudo guardar el punto: '+str(e))
            c.close();return redirect('/configuracion/sifen')
        elif accion=='punto_eliminar':
            pid=int(request.form.get('p_id') or 0)
            try:
                pto=c.execute('select * from sifen_puntos_expedicion where id=?',(pid,)).fetchone()
                if not pto: raise ValueError('Punto de expedición no encontrado.')
                uso=c.execute('select count(*) from ventas where sifen_punto_id=?',(pid,)).fetchone()[0]
                try:
                    uso+=c.execute('select count(*) from facturas_sanatorio where sifen_punto_id=?',(pid,)).fetchone()[0]
                except Exception: pass
                if uso:
                    c.execute('update sifen_puntos_expedicion set activo=0,predeterminado=0,actualizado_en=? where id=?',(now(),pid))
                    c.commit();flash('El punto tiene documentos emitidos y no puede borrarse del historial fiscal. Fue DESACTIVADO y ya no se usará para nuevas facturas.')
                else:
                    c.execute('delete from caja_punto_expedicion where punto_id=?',(pid,))
                    c.execute('delete from sifen_puntos_expedicion where id=?',(pid,))
                    c.commit();flash('Punto de expedición eliminado. Ya puede registrar el nuevo punto autorizado por DNIT.')
            except Exception as e:
                c.rollback();flash('No se pudo eliminar el punto: '+str(e))
            c.close();return redirect('/configuracion/sifen')
        elif accion=='punto_predeterminado':
            pid=int(request.form.get('p_id') or 0);c.execute('update sifen_puntos_expedicion set predeterminado=0');c.execute('update sifen_puntos_expedicion set predeterminado=1,activo=1 where id=?',(pid,));c.commit();c.close();return redirect('/configuracion/sifen')
        if accion=='actividad_guardar':
            aid=int(request.form.get('actividad_id') or 0); cod=request.form.get('actividad_codigo','').strip(); des=request.form.get('actividad_descripcion','').strip(); principal=1 if request.form.get('actividad_principal') else 0; activo=1 if request.form.get('actividad_activo') else 0
            try:
                if not cod or not des: raise ValueError('Código y descripción son obligatorios.')
                if principal and not activo: raise ValueError('La actividad principal debe estar activa.')
                dup=c.execute('select id from sifen_actividades_economicas where codigo=? and id<>?',(cod,aid)).fetchone()
                if dup: raise ValueError('Ya existe una actividad económica con el código '+cod+'.')
                if principal:c.execute('update sifen_actividades_economicas set principal=0')
                if aid:
                    c.execute('update sifen_actividades_economicas set codigo=?,descripcion=?,principal=?,activo=?,actualizado_en=? where id=?',(cod,des,principal,activo,now(),aid))
                else:
                    c.execute('insert into sifen_actividades_economicas(codigo,descripcion,principal,activo,creado_en,actualizado_en) values(?,?,?,?,?,?)',(cod,des,principal,activo,now(),now()))
                    aid=c.execute('select last_insert_rowid()').fetchone()[0]
                if activo and c.execute('select count(*) from sifen_actividades_economicas where activo=1 and principal=1').fetchone()[0]==0:
                    c.execute('update sifen_actividades_economicas set principal=1 where id=?',(aid,))
                pr=c.execute('select * from sifen_actividades_economicas where activo=1 order by principal desc,id limit 1').fetchone()
                if pr:c.execute('update sifen_config set emis_actividad_codigo=?,emis_actividad_desc=?,actualizado_en=? where id=1',(pr['codigo'],pr['descripcion'],now()))
                c.commit(); flash('Actividad económica guardada correctamente.')
            except Exception as e:c.rollback();flash('No se pudo guardar la actividad económica: '+str(e))
            c.close();return redirect('/configuracion/sifen#actividades')
        elif accion=='actividad_principal':
            aid=int(request.form.get('actividad_id') or 0); a=c.execute('select * from sifen_actividades_economicas where id=?',(aid,)).fetchone()
            if a:
                c.execute('update sifen_actividades_economicas set principal=0');c.execute('update sifen_actividades_economicas set principal=1,activo=1,actualizado_en=? where id=?',(now(),aid));c.execute('update sifen_config set emis_actividad_codigo=?,emis_actividad_desc=?,actualizado_en=? where id=1',(a['codigo'],a['descripcion'],now()));c.commit();flash('Actividad principal actualizada.')
            c.close();return redirect('/configuracion/sifen#actividades')
        elif accion=='actividad_estado':
            aid=int(request.form.get('actividad_id') or 0); a=c.execute('select * from sifen_actividades_economicas where id=?',(aid,)).fetchone()
            if a:
                nuevo=0 if int(a['activo'] or 0) else 1
                if int(a['principal'] or 0) and not nuevo: flash('No puede desactivar la actividad principal. Seleccione primero otra actividad principal.')
                else: c.execute('update sifen_actividades_economicas set activo=?,actualizado_en=? where id=?',(nuevo,now(),aid));c.commit();flash('Estado de actividad actualizado.')
            c.close();return redirect('/configuracion/sifen#actividades')
        if accion=='guardar_empresa':
            campos=['razon_social','nombre_fantasia','direccion','telefono','whatsapp','email','web','pie_documento']
            vals=[request.form.get(x,'').strip() for x in campos]
            c.execute('update institucion_config set '+','.join(f'{x}=?' for x in campos)+' where id=1',vals)
            logo=request.files.get('logo')
            if logo and logo.filename:
                ext=Path(logo.filename).suffix.lower()
                if ext in ('.png','.jpg','.jpeg','.webp'):
                    try:
                        from PIL import Image as PILImage
                        logo.stream.seek(0);imagen=PILImage.open(logo.stream);imagen.verify();logo.stream.seek(0)
                        nombre='logo_empresa'+ext;destino=os.path.join(BRANDING_DIR,nombre)
                        for anterior in Path(BRANDING_DIR).glob('logo_empresa.*'):
                            try: anterior.unlink()
                            except OSError: pass
                        logo.save(destino);c.execute('update institucion_config set logo_archivo=? where id=1',(nombre,))
                    except Exception: flash('Logo no actualizado: el archivo no es una imagen válida.')
                else: flash('Logo no actualizado: use PNG, JPG, JPEG o WEBP.')
            c.commit();audit('CONFIG_EMPRESA','Actualización desde Empresa y Facturación Electrónica');flash('Datos de empresa e identidad guardados.')
        elif accion=='guardar':
            vals=[request.form.get(x,'').strip() for x in ('ruc','dv','timbrado','csc_id','csc','tipo_contribuyente')]
            tim_desde=request.form.get('timbrado_desde','').strip()
            emis=[request.form.get(x,'').strip() for x in ('emis_departamento_codigo','emis_departamento_desc','emis_distrito_codigo','emis_distrito_desc','emis_ciudad_codigo','emis_ciudad_desc','emis_telefono','emis_direccion')]
            c.execute("update sifen_config set ruc=?,dv=?,timbrado=?,csc_id=?,csc=?,tipo_contribuyente=?,timbrado_desde=?,xml_version='150',emis_departamento_codigo=?,emis_departamento_desc=?,emis_distrito_codigo=?,emis_distrito_desc=?,emis_ciudad_codigo=?,emis_ciudad_desc=?,emis_telefono=?,emis_direccion=?,actualizado_en=? where id=1",(*vals,tim_desde,*emis,now()))
            # Fuente fiscal única: SIFEN gobierna RUC/DV/timbrado/domicilio fiscal. La identidad institucional solo refleja esos datos.
            c.execute("update institucion_config set ruc=?,dv=?,timbrado=?,timbrado_desde=?,direccion=?,telefono=?,departamento=?,ciudad=?,ambiente_sifen=? where id=1",(vals[0],vals[1],vals[2],tim_desde,emis[7],emis[6],emis[1],emis[5],c.execute('select ambiente from sifen_config where id=1').fetchone()[0] or 'TEST'))
            c.commit();_sifen_log('CONFIG','OK','Empresa y Facturación Electrónica actualizadas desde la fuente fiscal única');flash('Datos fiscales guardados. Los campos compartidos se sincronizaron automáticamente.')
        elif accion=='confirmar_habilitacion_dnit':
            confirmado=1 if request.form.get('confirmado')=='1' else 0
            c.execute('update sifen_config set dnit_habilitado_produccion=?,dnit_habilitado_confirmado_en=?,actualizado_en=? where id=1',(confirmado,now() if confirmado else None,now()))
            c.commit();_sifen_log('HABILITACION_DNIT','OK' if confirmado else 'PENDIENTE','Administrador confirmó habilitación externa DNIT para Producción' if confirmado else 'Confirmación de habilitación DNIT retirada')
            flash('Confirmación DNIT actualizada. Esta marca no habilita ante DNIT; solo registra que la habilitación externa ya fue obtenida.')
        elif accion=='ambiente_test':
            c.execute("update sifen_config set ambiente='TEST',produccion_habilitada=0,actualizado_en=? where id=1",(now(),));c.commit();_sifen_log('AMBIENTE','OK','Ambiente cambiado a TEST');flash('SIFEN quedó en ambiente TEST.')
        elif accion=='ambiente_produccion':
            cfgx=c.execute('select * from sifen_config where id=1').fetchone();checks=_sifen_diagnostico(c,cfgx)
            faltan=[x['nombre'] for x in checks if not x['ok']]
            if faltan:
                flash('Producción NO activada. Diagnóstico pendiente: '+', '.join(faltan)+'.')
            else:
                c.execute("update sifen_config set ambiente='PRODUCCION',produccion_habilitada=1,produccion_activada_en=?,actualizado_en=? where id=1",(now(),now()));c.commit();_sifen_log('AMBIENTE','OK','PRODUCCION activada tras diagnóstico');flash('Ambiente PRODUCCIÓN activado.')
        elif accion=='certificado':
            archivo=request.files.get('certificado');password=request.form.get('password','')
            if not archivo or not archivo.filename: flash('Seleccione un certificado .p12 o .pfx.')
            elif Path(archivo.filename).suffix.lower() not in ('.p12','.pfx'): flash('Formato no permitido. Use .p12 o .pfx.')
            else:
                try:
                    cert,cp,kp=_sifen_cert_info(archivo.read(),password)
                    subj=cert.subject.rfc4514_string();serial=str(cert.serial_number)
                    nb=getattr(cert,'not_valid_before_utc',cert.not_valid_before).isoformat();na=getattr(cert,'not_valid_after_utc',cert.not_valid_after).isoformat()
                    c.execute('update sifen_config set cert_subject=?,cert_serial=?,cert_not_before=?,cert_not_after=?,cert_path=?,key_path=?,actualizado_en=? where id=1',(subj,serial,nb,na,cp,kp,now()));c.commit()
                    _sifen_log('CERTIFICADO','OK',f'{subj} | vence {na}');flash('Certificado y clave privada validados e instalados en el almacenamiento persistente protegido. La contraseña no fue guardada.')
                except Exception as e:
                    _sifen_log('CERTIFICADO','ERROR',e);flash('No se pudo instalar el certificado: '+str(e))
        elif accion in ('generador_autotest','xsd_autotest'):
            try:
                # V13.9.98: autoprueba autocontenida. No depende de facturas históricas
                # ni deja registros TEST en la base; el SAVEPOINT se revierte al terminar.
                xml,cdc,test_vid=_sifen_generar_factura_test_autocontenida(c)
                cfgx=c.execute('select * from sifen_config where id=1').fetchone()
                firmado=_sifen_firmar_rde(xml,cfgx)
                ruta=_sifen_guardar_xml_test('FE',0,firmado,cdc)
                _sifen_log('XML_V150','GENERADO_FIRMADO_TEST','FE autocontenida CDC %s · XMLDSig aplicado · archivo %s'%(cdc,ruta))
                ok,errores=_sifen_validar_xsd_v150(firmado)
                if ok:
                    _sifen_log('XSD_V150','OK','FE autocontenida CDC %s firmada y validada contra XSD V150'%cdc)
                    flash('XML V150 generado, firmado con el certificado instalado y validado correctamente contra XSD. No fue enviado a SIFEN.')
                else:
                    detalle=' | '.join(errores[:8])
                    _sifen_log('XSD_V150','ERROR',detalle)
                    flash('El XML fue generado, pero NO pasó XSD V150. Revise el Registro técnico: '+detalle[:500])
            except Exception as e:
                _sifen_log('XSD_V150','ERROR',e);flash('Validación XSD V150: '+str(e))
        elif accion=='motor_autotest':
            cfg=c.execute('select * from sifen_config where id=1').fetchone()
            try:
                _sifen_motor_autotest(cfg);_sifen_log('XMLDSIG','OK','Firma XMLDSig RSA-SHA256 generada y verificada localmente. No se transmitió ningún documento.')
                flash('Motor XMLDSig: firma y verificación local correctas. No se envió ningún documento a SIFEN.')
            except Exception as e:
                _sifen_log('XMLDSIG','ERROR',e);flash('Autoprueba XMLDSig fallida: '+str(e))
        elif accion=='probar':
            cfg=c.execute('select * from sifen_config where id=1').fetchone()
            try:
                import requests
                if not cfg['cert_path'] or not cfg['key_path'] or not os.path.exists(cfg['cert_path']) or not os.path.exists(cfg['key_path']): raise ValueError('Primero instale el certificado .p12/.pfx.')
                url=_sifen_base(cfg)+'/de/ws/consultas/consulta.wsdl?wsdl'
                resp=requests.get(url,cert=(cfg['cert_path'],cfg['key_path']),timeout=20)
                ok=200 <= resp.status_code < 400; estado='OK' if ok else 'ERROR';detalle=f'HTTP {resp.status_code} - {url}'
                c.execute('update sifen_config set ultimo_test=?,ultimo_estado=?,ultimo_detalle=? where id=1',(now(),estado,detalle));c.commit();_sifen_log('CONEXION_MTLS',estado,detalle)
                flash(('Conexión SIFEN '+str(cfg['ambiente'] or 'TEST')+' realizada correctamente.' if ok else 'SIFEN respondió con error: ')+detalle)
            except Exception as e:
                detalle=str(e);c.execute("update sifen_config set ultimo_test=?,ultimo_estado='ERROR',ultimo_detalle=? where id=1",(now(),detalle));c.commit();_sifen_log('CONEXION_MTLS','ERROR',detalle);flash('Prueba de conexión fallida: '+detalle)
        c.close();return redirect('/configuracion/sifen')
    cfg=c.execute('select * from sifen_config where id=1').fetchone();inst=c.execute('select * from institucion_config where id=1').fetchone();logs=c.execute('select * from sifen_eventos order by id desc limit 30').fetchall();puntos=c.execute("select p.*, (select count(*) from ventas v where v.sifen_punto_id=p.id) as documentos_emitidos from sifen_puntos_expedicion p order by establecimiento,punto_expedicion").fetchall();actividades=c.execute('select * from sifen_actividades_economicas order by principal desc,activo desc,codigo').fetchall();diagnostico=_sifen_diagnostico(c,cfg);base_actual=_sifen_base(cfg);c.close()
    return render_template('sifen_config.html',cfg=cfg,inst=inst,logs=logs,puntos=puntos,actividades=actividades,test_base=SIFEN_TEST_BASE,prod_base=SIFEN_PROD_BASE,base_actual=base_actual,diagnostico=diagnostico)

ROUTE_MODULE.update({'configuracion_sifen':'CONFIG_SANATORIO'})


# ===== V13.9.39: Facturar al confirmar venta + CDC local de PRUEBA =====
def init_v13939_facturacion_venta_test():
    c=db()
    scols={r['name'] for r in c.execute('pragma table_info(sifen_config)').fetchall()}
    if 'tipo_contribuyente' not in scols:
        c.execute("alter table sifen_config add column tipo_contribuyente TEXT DEFAULT '2'")
    vcols={r['name'] for r in c.execute('pragma table_info(ventas)').fetchall()}
    for col,defn in [('codigo_seguridad_sifen','TEXT'),('cdc_ambiente','TEXT')]:
        if col not in vcols:c.execute(f'alter table ventas add column {col} {defn}')
    c.execute("INSERT OR IGNORE INTO schema_migrations(version,aplicado_en) VALUES('13.9.39-venta-factura-cdc-test',?)",(now(),))
    c.commit();c.close()
init_v13939_facturacion_venta_test()

def _mod11_cdc(base43):
    if not str(base43).isdigit(): raise ValueError('La base del CDC debe ser numérica.')
    k=2; total=0
    for ch in reversed(str(base43)):
        total += int(ch)*k; k += 1
        if k>11:k=2
    r=11-(total%11)
    return '0' if r in (10,11) else str(r)

def _solo_digitos(v):
    return ''.join(ch for ch in str(v or '') if ch.isdigit())

def _generar_cdc_test_venta(c,venta_id,fecha,numero):
    import secrets
    cfg=c.execute('select * from sifen_config where id=1').fetchone()
    if not cfg or str(cfg['ambiente'] or '').upper()!='TEST': return None
    # El CDC se construye antes de la firma/transmisión. No depende de que el certificado
    # esté instalado; el certificado será obligatorio al firmar/transmitir el XML DE.
    ruc=_solo_digitos(cfg['ruc']); dv=_solo_digitos(cfg['dv']); venta=c.execute('select sifen_punto_id,establecimiento,punto_expedicion from ventas where id=?',(venta_id,)).fetchone(); pto=_punto_facturacion(c,venta['sifen_punto_id'] if venta else None); est=_solo_digitos((venta['establecimiento'] if venta else None) or pto['establecimiento']); pexp=_solo_digitos((venta['punto_expedicion'] if venta else None) or pto['punto_expedicion'])
    tip=_solo_digitos(cfg['tipo_contribuyente'] or '2')
    if not (ruc and dv and est and pexp and tip): raise ValueError('Complete RUC, DV, establecimiento, punto de expedición y tipo de contribuyente en Configuración SIFEN.')
    if len(ruc)>8: raise ValueError('El RUC emisor del CDC no puede superar 8 dígitos.')
    ruc=ruc.zfill(8); est=est.zfill(3); pexp=pexp.zfill(3)
    # Número de documento: se toman los últimos 7 dígitos del comprobante y se completa con ceros.
    nd=_solo_digitos(numero)[-7:].zfill(7)
    fec=_solo_digitos(fecha)[:8]
    if len(fec)!=8: raise ValueError('La fecha de emisión no permite formar AAAAMMDD.')
    # C002=01 Factura electrónica; B002=1 emisión normal; B004=9 dígitos de seguridad.
    codseg=f'{secrets.randbelow(1_000_000_000):09d}'
    base='01'+ruc+dv[:1]+est+pexp+nd+tip[:1]+fec+'1'+codseg
    if len(base)!=43: raise ValueError(f'Longitud base CDC inválida ({len(base)}).')
    cdc=base+_mod11_cdc(base)
    c.execute("update ventas set cdc=?,estado_sifen='TEST_GENERADO',codigo_seguridad_sifen=?,cdc_ambiente='TEST' where id=?",(cdc,codseg,venta_id))
    c.execute('insert into sifen_eventos(fecha,tipo,estado,detalle) values(?,?,?,?)',(now(),'CDC_TEST','GENERADO',f'Venta {venta_id} · CDC {cdc} · NO ENVIADO / NO APROBADO'))
    return cdc


def _generar_cdc_test_complementario(c,tipo_doc,fecha,numero,punto_id,registro_tipo,registro_id):
    """Genera CDC local TEST para NCE(05) o NDE(06). No transmite a DNIT."""
    import secrets
    tipo_doc=str(tipo_doc).zfill(2)
    if tipo_doc not in ('05','06'): raise ValueError('Tipo de documento complementario inválido para CDC TEST.')
    cfg=c.execute('select * from sifen_config where id=1').fetchone()
    if not cfg or str(cfg['ambiente'] or '').upper()!='TEST': return None
    pto=_punto_facturacion(c,punto_id)
    ruc=_solo_digitos(cfg['ruc']); dv=_solo_digitos(cfg['dv']); est=_solo_digitos(pto['establecimiento']); pexp=_solo_digitos(pto['punto_expedicion']); tip=_solo_digitos(cfg['tipo_contribuyente'] or '2')
    if not (ruc and dv and est and pexp and tip): raise ValueError('Complete RUC, DV, establecimiento, punto de expedición y tipo de contribuyente en Configuración SIFEN.')
    if len(ruc)>8: raise ValueError('El RUC emisor del CDC no puede superar 8 dígitos.')
    ruc=ruc.zfill(8); est=est.zfill(3); pexp=pexp.zfill(3)
    nd=_solo_digitos(numero)[-7:].zfill(7); fec=_solo_digitos(fecha)[:8]
    if len(fec)!=8: raise ValueError('La fecha de emisión no permite formar AAAAMMDD.')
    codseg=f'{secrets.randbelow(1_000_000_000):09d}'
    base=tipo_doc+ruc+dv[:1]+est+pexp+nd+tip[:1]+fec+'1'+codseg
    if len(base)!=43: raise ValueError(f'Longitud base CDC inválida ({len(base)}).')
    cdc=base+_mod11_cdc(base)
    tabla='notas_credito_ventas' if registro_tipo=='NCE' else 'notas_debito_ventas'
    c.execute(f"update {tabla} set cdc=?,estado_sifen='TEST_GENERADO',codigo_seguridad_sifen=?,cdc_ambiente='TEST' where id=?",(cdc,codseg,registro_id))
    c.execute('insert into sifen_eventos(fecha,tipo,estado,detalle) values(?,?,?,?)',(now(),registro_tipo+'_CDC_TEST','GENERADO',f'{registro_tipo} {numero} · CDC {cdc} · NO ENVIADO / NO APROBADO'))
    return cdc


# ===== V13.9.71: CDC TEST corregido para FE/NCE/NDE =====
def init_v13971_cdc_test_documentos():
    c=db()
    nccols={r['name'] for r in c.execute('pragma table_info(notas_credito_ventas)').fetchall()}
    for col,defn in [('codigo_seguridad_sifen','TEXT'),('cdc_ambiente','TEXT')]:
        if col not in nccols:c.execute(f'alter table notas_credito_ventas add column {col} {defn}')
    c.execute("""CREATE TABLE IF NOT EXISTS notas_debito_ventas(
      id INTEGER PRIMARY KEY,venta_id INTEGER NOT NULL,fecha TEXT NOT NULL,numero TEXT NOT NULL,
      motivo TEXT NOT NULL,total REAL NOT NULL DEFAULT 0,estado TEXT NOT NULL DEFAULT 'EMITIDA',
      estado_sifen TEXT NOT NULL DEFAULT 'NO_ENVIADA',cdc TEXT,codigo_seguridad_sifen TEXT,cdc_ambiente TEXT,
      protocolo_sifen TEXT,respuesta_sifen TEXT,creado_en TEXT,usuario TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS nota_debito_venta_items(
      id INTEGER PRIMARY KEY,nota_id INTEGER NOT NULL,producto_id INTEGER,descripcion TEXT,
      cantidad REAL NOT NULL DEFAULT 0,precio REAL NOT NULL DEFAULT 0,total REAL NOT NULL DEFAULT 0,iva_pct REAL DEFAULT 10)""")
    c.execute("INSERT OR IGNORE INTO schema_migrations(version,aplicado_en) VALUES('13.9.71-cdc-test-fe-nce-nde',?)",(now(),))
    c.commit();c.close()
init_v13971_cdc_test_documentos()

def _nd_numero(c,punto_id=None):
    p=_punto_facturacion(c,punto_id)
    if not p or not int(p['nota_debito_electronica'] or 0): raise ValueError('El punto de expedición no está habilitado para Nota de Débito Electrónica.')
    c.execute("CREATE TABLE IF NOT EXISTS sifen_correlativos(tipo TEXT,punto_id INTEGER,proximo INTEGER DEFAULT 1,PRIMARY KEY(tipo,punto_id))")
    c.execute("insert or ignore into sifen_correlativos(tipo,punto_id,proximo) values('NDE',?,1)",(p['id'],))
    n=int(c.execute("select proximo from sifen_correlativos where tipo='NDE' and punto_id=?",(p['id'],)).fetchone()[0])
    if n>9999999:raise ValueError('Se agotó la numeración de Nota de Débito para este punto.')
    c.execute("update sifen_correlativos set proximo=? where tipo='NDE' and punto_id=?",(n+1,p['id']))
    return f"{str(p['establecimiento']).zfill(3)}-{str(p['punto_expedicion']).zfill(3)}-{str(n).zfill(7)}",p

@app.route('/ventas/<int:venta_id>/nota-debito',methods=['GET','POST'])
def nota_debito_venta(venta_id):
    c=db();v=c.execute("select v.*,t.nombre cliente,t.ruc from ventas v left join terceros t on t.id=v.cliente_id where v.id=?",(venta_id,)).fetchone()
    if not v:c.close();return ('Venta no encontrada',404)
    if request.method=='POST':
      try:
       motivo=(request.form.get('motivo') or '').strip(); descripcion=(request.form.get('descripcion') or '').strip()
       cantidad=float(request.form.get('cantidad') or 1); precio=float(request.form.get('precio') or 0); iva_pct=float(request.form.get('iva_pct') or 10)
       if not motivo:raise ValueError('Indique el motivo de la Nota de Débito.')
       if not descripcion:raise ValueError('Indique el concepto del débito.')
       if cantidad<=0 or precio<=0:raise ValueError('Cantidad y precio deben ser mayores a cero.')
       total=cantidad*precio;numero,p=_nd_numero(c,v['sifen_punto_id']);fecha=datetime.date.today().isoformat()
       cur=c.execute("insert into notas_debito_ventas(venta_id,fecha,numero,motivo,total,estado,estado_sifen,creado_en,usuario) values(?,?,?,?,?,'EMITIDA','PENDIENTE_ENVIO',?,?)",(venta_id,fecha,numero,motivo,total,now(),session.get('user')));nid=cur.lastrowid
       c.execute("insert into nota_debito_venta_items(nota_id,descripcion,cantidad,precio,total,iva_pct) values(?,?,?,?,?,?)",(nid,descripcion,cantidad,precio,total,iva_pct))
       cdc=_generar_cdc_test_complementario(c,'06',fecha,numero,p['id'],'NDE',nid)
       c.commit();flash('Nota de Débito emitida con CDC DE PRUEBA: '+str(cdc) if cdc else 'Nota de Débito emitida. SIFEN no está en ambiente TEST.');c.close();return redirect(f'/notas-debito/ventas/{nid}/pdf')
      except Exception as e:c.rollback();flash(str(e))
    puntos=c.execute("select * from sifen_puntos_expedicion where activo=1 and autorizado_dnit=1 and nota_debito_electronica=1 order by predeterminado desc,id").fetchall();c.close();return render_template('debit_note_sale.html',v=v,puntos=puntos)

@app.get('/notas-debito/ventas/<int:nid>/pdf')
def nota_debito_venta_pdf(nid):
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph,Spacer,Table,TableStyle
    c=db();n=c.execute("select n.*,v.numero factura,v.cdc factura_cdc,t.nombre cliente,t.ruc from notas_debito_ventas n join ventas v on v.id=n.venta_id left join terceros t on t.id=v.cliente_id where n.id=?",(nid,)).fetchone()
    if not n:c.close();return ('Nota de Débito no encontrada',404)
    items=c.execute("select i.*,p.codigo,coalesce(nullif(trim(p.sifen_descripcion),''),nullif(trim(i.descripcion),''),nullif(trim(p.nombre),''),'Servicio medico') descripcion,coalesce(nullif(trim(p.sifen_unidad_codigo),''),'77') sifen_unidad_codigo,coalesce(nullif(trim(p.sifen_unidad_desc),''),'UNI') sifen_unidad_desc from nota_debito_venta_items i left join productos p on p.id=i.producto_id where i.nota_id=? order by i.id",(nid,)).fetchall();inst=c.execute('select * from institucion_config where id=1').fetchone();c.close()
    st=getSampleStyleSheet();small=ParagraphStyle('NDItem',parent=st['Normal'],fontSize=7,leading=9);story=[]
    _kude_header(story,inst,'NOTA DE DÉBITO',n['numero'],'Documento de prueba SIFEN')
    info=[[Paragraph('<b>Cliente:</b> '+str(n['cliente'] or '-'),st['Normal']),Paragraph('<b>RUC/CI:</b> '+str(n['ruc'] or '-'),st['Normal'])],[Paragraph('<b>Fecha:</b> '+str(n['fecha']),st['Normal']),Paragraph('<b>Factura relacionada:</b> '+str(n['factura'] or '-'),st['Normal'])],[Paragraph('<b>Motivo:</b> '+str(n['motivo'] or '-'),st['Normal']),Paragraph('<b>Estado SIFEN:</b> '+str(n['estado_sifen'] or '-'),st['Normal'])]]
    t=Table(info,colWidths=[93*mm,93*mm]);t.setStyle(TableStyle([('BOX',(0,0),(-1,-1),.7,colors.black),('INNERGRID',(0,0),(-1,-1),.25,colors.grey),('PADDING',(0,0),(-1,-1),5)]));story += [t,Spacer(1,3*mm)]
    data=[['Descripción','Cantidad','Precio','IVA','Total']]+[[Paragraph(str(x['descripcion'] or ''),small),str(x['cantidad']),_pdf_money(x['precio']),str(x['iva_pct'])+'%',_pdf_money(x['total'])] for x in items]
    t=Table(data,colWidths=[90*mm,22*mm,27*mm,18*mm,29*mm],repeatRows=1);t.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.4,colors.black),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),7)]));story += [t,Spacer(1,3*mm),Paragraph('<b>TOTAL NOTA DE DÉBITO: Gs. '+_pdf_money(n['total'])+'</b>',st['Heading3'])]
    _kude_footer(story,inst,n['cdc'],None,False)
    return _pdf_doc_response(story,'ND-'+str(n['numero'])+'.pdf')

ROUTE_MODULE.update({'nota_debito_venta':'FACTURACION','nota_debito_venta_pdf':'FACTURACION'})

# ===== V13.9.45: Recursos Humanos Integral =====
def init_v13945_rrhh():
    c=db()
    c.executescript('''
    CREATE TABLE IF NOT EXISTS empleados(
      id INTEGER PRIMARY KEY,nombre TEXT NOT NULL,documento TEXT,ruc TEXT,fecha_nacimiento TEXT,telefono TEXT,email TEXT,direccion TEXT,
      cargo TEXT,departamento TEXT,fecha_ingreso TEXT,fecha_salida TEXT,tipo_contrato TEXT,salario_base REAL DEFAULT 0,
      ips_numero TEXT,ips_activo INTEGER DEFAULT 1,turno TEXT,usuario_id INTEGER,estado TEXT DEFAULT 'ACTIVO',observacion TEXT,creado_en TEXT,actualizado_en TEXT);
    CREATE TABLE IF NOT EXISTS rrhh_config(id INTEGER PRIMARY KEY CHECK(id=1),ips_obrero_pct REAL DEFAULT 9,ips_patronal_pct REAL DEFAULT 16.5,
      cuenta_sueldos TEXT DEFAULT '5.4.01',cuenta_cargas TEXT DEFAULT '5.4.02',cuenta_obligaciones TEXT DEFAULT '2.1.04',actualizado_en TEXT);
    INSERT OR IGNORE INTO rrhh_config(id,ips_obrero_pct,ips_patronal_pct) VALUES(1,9,16.5);
    CREATE TABLE IF NOT EXISTS rrhh_asistencias(id INTEGER PRIMARY KEY,empleado_id INTEGER NOT NULL,fecha TEXT NOT NULL,hora_entrada TEXT,hora_salida TEXT,
      estado TEXT DEFAULT 'PRESENTE',minutos_tardanza INTEGER DEFAULT 0,horas_extra REAL DEFAULT 0,observacion TEXT,registrado_por TEXT,creado_en TEXT,UNIQUE(empleado_id,fecha));
    CREATE TABLE IF NOT EXISTS rrhh_novedades(id INTEGER PRIMARY KEY,empleado_id INTEGER NOT NULL,fecha TEXT NOT NULL,periodo TEXT NOT NULL,tipo TEXT NOT NULL,
      descripcion TEXT,monto REAL DEFAULT 0,cantidad REAL DEFAULT 0,desde TEXT,hasta TEXT,estado TEXT DEFAULT 'PENDIENTE',archivo_ref TEXT,creado_por TEXT,creado_en TEXT);
    CREATE TABLE IF NOT EXISTS rrhh_liquidaciones(id INTEGER PRIMARY KEY,empleado_id INTEGER NOT NULL,periodo TEXT NOT NULL,fecha TEXT NOT NULL,
      salario_base REAL DEFAULT 0,haberes REAL DEFAULT 0,horas_extra REAL DEFAULT 0,bonificaciones REAL DEFAULT 0,otros_haberes REAL DEFAULT 0,
      ips_base REAL DEFAULT 0,ips_obrero REAL DEFAULT 0,ips_patronal REAL DEFAULT 0,anticipos REAL DEFAULT 0,prestamos REAL DEFAULT 0,otros_descuentos REAL DEFAULT 0,
      neto REAL DEFAULT 0,costo_empresa REAL DEFAULT 0,estado TEXT DEFAULT 'BORRADOR',asiento_id INTEGER,pagado_en TEXT,creado_por TEXT,creado_en TEXT,
      UNIQUE(empleado_id,periodo));
    CREATE TABLE IF NOT EXISTS rrhh_vacaciones(id INTEGER PRIMARY KEY,empleado_id INTEGER NOT NULL,desde TEXT,hasta TEXT,dias REAL DEFAULT 0,
      tipo TEXT DEFAULT 'VACACIONES',motivo TEXT,estado TEXT DEFAULT 'SOLICITADO',creado_por TEXT,creado_en TEXT);
    CREATE TABLE IF NOT EXISTS rrhh_documentos(id INTEGER PRIMARY KEY,empleado_id INTEGER NOT NULL,tipo TEXT,nombre TEXT,referencia TEXT,vencimiento TEXT,observacion TEXT,creado_en TEXT);
    ''')
    c.execute("INSERT OR IGNORE INTO schema_migrations(version,aplicado_en) VALUES('13.9.45-recursos-humanos-integral',?)",(now(),))
    # Cuentas RRHH, sin reemplazar plan existente.
    for x in [('2.1.06','IPS a Pagar','PASIVO'),('1.1.05','Anticipos al Personal','ACTIVO')]:
        c.execute('insert or ignore into plan_cuentas(codigo,nombre,tipo) values(?,?,?)',x)
    # Módulo y permisos de administrador.
    MODULES['RRHH']='Recursos Humanos'
    rid=c.execute("select id from roles where nombre='ADMINISTRADOR'").fetchone()
    if rid:
        for a in ACTIONS:c.execute('insert or ignore into permisos_rol(rol_id,modulo,accion,permitido) values(?,?,?,1)',(rid[0],'RRHH',a))
    c.commit();c.close()
init_v13945_rrhh()

ROUTE_MODULE.update({
 'rrhh_inicio':'RRHH','rrhh_funcionarios':'RRHH','rrhh_funcionario_editar':'RRHH','rrhh_asistencia':'RRHH','rrhh_novedades':'RRHH',
 'rrhh_liquidaciones':'RRHH','rrhh_liquidar':'RRHH','rrhh_liquidacion_detalle':'RRHH','rrhh_liquidacion_pdf':'RRHH','rrhh_configuracion':'RRHH','rrhh_informes':'RRHH'
})

def _rrhh_perm(accion='VER'):
    return user_has('RRHH',accion)

def _rrhh_periodo(v=None):
    return (v or datetime.date.today().strftime('%Y-%m'))[:7]

@app.route('/rrhh')
def rrhh_inicio():
    if not _rrhh_perm(): return ('Acceso no autorizado',403)
    c=db();periodo=_rrhh_periodo(request.args.get('periodo'))
    stats={
      'activos':c.execute("select count(*) n from empleados where estado='ACTIVO'").fetchone()['n'],
      'ausencias':c.execute("select count(*) n from rrhh_asistencias where substr(fecha,1,7)=? and estado in ('AUSENTE','REPOSO','PERMISO')",(periodo,)).fetchone()['n'],
      'anticipos':c.execute("select coalesce(sum(monto),0) n from rrhh_novedades where periodo=? and tipo='ANTICIPO' and estado!='ANULADO'",(periodo,)).fetchone()['n'],
      'nomina':c.execute("select coalesce(sum(neto),0) n from rrhh_liquidaciones where periodo=? and estado!='ANULADA'",(periodo,)).fetchone()['n']}
    recientes=c.execute('select e.nombre,n.tipo,n.descripcion,n.monto,n.fecha,n.estado from rrhh_novedades n join empleados e on e.id=n.empleado_id order by n.id desc limit 10').fetchall();c.close()
    return render_template('rrhh_dashboard.html',stats=stats,periodo=periodo,recientes=recientes)

@app.route('/rrhh/funcionarios',methods=['GET','POST'])
def rrhh_funcionarios():
    if request.method=='POST' and not _rrhh_perm('CREAR'): return ('Acceso no autorizado',403)
    if not _rrhh_perm(): return ('Acceso no autorizado',403)
    c=db()
    if request.method=='POST':
        f=request.form
        c.execute('''insert into empleados(nombre,documento,ruc,fecha_nacimiento,telefono,email,direccion,cargo,departamento,fecha_ingreso,tipo_contrato,salario_base,ips_numero,ips_activo,turno,estado,observacion,creado_en,actualizado_en)
        values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',(f.get('nombre','').strip(),f.get('documento'),f.get('ruc'),f.get('fecha_nacimiento'),f.get('telefono'),f.get('email'),f.get('direccion'),f.get('cargo'),f.get('departamento'),f.get('fecha_ingreso'),f.get('tipo_contrato'),float(f.get('salario_base') or 0),f.get('ips_numero'),1 if f.get('ips_activo') else 0,f.get('turno'),'ACTIVO',f.get('observacion'),now(),now()))
        c.commit();c.close();audit('RRHH_FUNCIONARIO_CREAR',f.get('nombre',''));flash('Funcionario registrado.');return redirect('/rrhh/funcionarios')
    q=(request.args.get('q') or '').strip();params=[];sql='select * from empleados'
    if q: sql+=' where nombre like ? or documento like ? or cargo like ? or departamento like ?';params=['%'+q+'%']*4
    sql+=' order by estado desc,nombre';rows=c.execute(sql,params).fetchall();c.close();return render_template('rrhh_employees.html',rows=rows,q=q)

@app.route('/rrhh/funcionarios/<int:i>/editar',methods=['GET','POST'])
def rrhh_funcionario_editar(i):
    if not _rrhh_perm('EDITAR'): return ('Acceso no autorizado',403)
    c=db();e=c.execute('select * from empleados where id=?',(i,)).fetchone()
    if not e:c.close();return ('Funcionario no encontrado',404)
    if request.method=='POST':
        f=request.form;c.execute('''update empleados set nombre=?,documento=?,ruc=?,fecha_nacimiento=?,telefono=?,email=?,direccion=?,cargo=?,departamento=?,fecha_ingreso=?,fecha_salida=?,tipo_contrato=?,salario_base=?,ips_numero=?,ips_activo=?,turno=?,estado=?,observacion=?,actualizado_en=? where id=?''',(f.get('nombre','').strip(),f.get('documento'),f.get('ruc'),f.get('fecha_nacimiento'),f.get('telefono'),f.get('email'),f.get('direccion'),f.get('cargo'),f.get('departamento'),f.get('fecha_ingreso'),f.get('fecha_salida'),f.get('tipo_contrato'),float(f.get('salario_base') or 0),f.get('ips_numero'),1 if f.get('ips_activo') else 0,f.get('turno'),f.get('estado','ACTIVO'),f.get('observacion'),now(),i));c.commit();c.close();audit('RRHH_FUNCIONARIO_EDITAR',str(i));flash('Ficha actualizada.');return redirect('/rrhh/funcionarios')
    c.close();return render_template('rrhh_employee_edit.html',e=e)

@app.route('/rrhh/asistencia',methods=['GET','POST'])
def rrhh_asistencia():
    if request.method=='POST' and not _rrhh_perm('CREAR'):return ('Acceso no autorizado',403)
    if not _rrhh_perm():return ('Acceso no autorizado',403)
    c=db()
    if request.method=='POST':
        f=request.form;c.execute('''insert into rrhh_asistencias(empleado_id,fecha,hora_entrada,hora_salida,estado,minutos_tardanza,horas_extra,observacion,registrado_por,creado_en) values(?,?,?,?,?,?,?,?,?,?)
        on conflict(empleado_id,fecha) do update set hora_entrada=excluded.hora_entrada,hora_salida=excluded.hora_salida,estado=excluded.estado,minutos_tardanza=excluded.minutos_tardanza,horas_extra=excluded.horas_extra,observacion=excluded.observacion,registrado_por=excluded.registrado_por''',(f['empleado_id'],f['fecha'],f.get('hora_entrada'),f.get('hora_salida'),f.get('estado','PRESENTE'),int(f.get('minutos_tardanza') or 0),float(f.get('horas_extra') or 0),f.get('observacion'),session.get('user'),now()));c.commit();flash('Asistencia guardada.')
    desde=request.args.get('desde') or datetime.date.today().replace(day=1).isoformat();hasta=request.args.get('hasta') or datetime.date.today().isoformat();emps=c.execute("select id,nombre from empleados where estado='ACTIVO' order by nombre").fetchall();bancos=c.execute("select * from cuentas_bancarias where activo=1 order by banco,alias").fetchall();rows=c.execute('''select a.*,e.nombre from rrhh_asistencias a join empleados e on e.id=a.empleado_id where a.fecha between ? and ? order by a.fecha desc,e.nombre''',(desde,hasta)).fetchall();c.close();return render_template('rrhh_attendance.html',emps=emps,rows=rows,desde=desde,hasta=hasta)

@app.route('/rrhh/novedades',methods=['GET','POST'])
def rrhh_novedades():
    if request.method=='POST' and not _rrhh_perm('CREAR'):return ('Acceso no autorizado',403)
    if not _rrhh_perm():return ('Acceso no autorizado',403)
    c=db();periodo=_rrhh_periodo(request.values.get('periodo'))
    if request.method=='POST':
        f=request.form;tipo=f.get('tipo','OTRO');estado='APROBADO' if tipo in ('ANTICIPO','DESCUENTO','BONIFICACION','PRESTAMO','HORA_EXTRA') else 'PENDIENTE';monto=float(f.get('monto') or 0);fecha=f.get('fecha') or datetime.date.today().isoformat();medio=f.get('medio_pago') or 'EFECTIVO';cuenta_id=int(f.get('cuenta_bancaria_id') or 0) or None
        cur=c.execute('insert into rrhh_novedades(empleado_id,fecha,periodo,tipo,descripcion,monto,cantidad,desde,hasta,estado,creado_por,creado_en,medio_pago,cuenta_bancaria_id) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(f['empleado_id'],fecha,periodo,tipo,f.get('descripcion'),monto,float(f.get('cantidad') or 0),f.get('desde'),f.get('hasta'),estado,session.get('user'),now(),medio,cuenta_id));nid=cur.lastrowid
        if tipo in ('ANTICIPO','PRESTAMO') and monto>0:
         cta_fin,_=_cuenta_financiera(c,medio,cuenta_id);cfg=c.execute('select * from tesoreria_config where id=1').fetchone();cta_ant=cfg['cuenta_anticipo_personal'];asi=asiento(c,fecha,'Anticipo/Préstamo al personal','ANTICIPO_PERSONAL',nid,'PYG',1,[(cta_ant,monto,0,monto,'Anticipo al funcionario'),(cta_fin,0,monto,monto,'Salida de fondos')]);mov=c.execute('insert into caja_banco(fecha,tipo,medio,moneda,tipo_cambio,importe,importe_pyg,concepto,origen_tipo,origen_id,cuenta_bancaria_id) values(?,?,?,?,?,?,?,?,?,?,?)',(fecha,'EGRESO',medio,'PYG',1,monto,monto,'Anticipo/Préstamo al personal','ANTICIPO_PERSONAL',nid,cuenta_id)).lastrowid;c.execute('update rrhh_novedades set asiento_id=?,movimiento_financiero_id=? where id=?',(asi,mov,nid))
        c.commit();flash('Novedad registrada y, cuando corresponde, integrada con Tesorería y Contabilidad.');c.close();return redirect('/rrhh/novedades?periodo='+periodo)
    emps=c.execute("select id,nombre from empleados where estado='ACTIVO' order by nombre").fetchall();rows=c.execute('''select n.*,e.nombre from rrhh_novedades n join empleados e on e.id=n.empleado_id where n.periodo=? order by n.fecha desc,n.id desc''',(periodo,)).fetchall();c.close();return render_template('rrhh_events.html',emps=emps,rows=rows,periodo=periodo,bancos=bancos)

@app.route('/rrhh/liquidaciones')
def rrhh_liquidaciones():
    if not _rrhh_perm():return ('Acceso no autorizado',403)
    c=db();periodo=_rrhh_periodo(request.args.get('periodo'));rows=c.execute('''select l.*,e.nombre,e.documento from rrhh_liquidaciones l join empleados e on e.id=l.empleado_id where l.periodo=? order by e.nombre''',(periodo,)).fetchall();emps=c.execute("select id,nombre from empleados where estado='ACTIVO' order by nombre").fetchall();c.close();return render_template('rrhh_payroll.html',rows=rows,emps=emps,periodo=periodo)

@app.post('/rrhh/liquidar')
def rrhh_liquidar():
    if not _rrhh_perm('CREAR'):return ('Acceso no autorizado',403)
    eid=int(request.form['empleado_id']);periodo=_rrhh_periodo(request.form.get('periodo'));c=db();e=c.execute('select * from empleados where id=?',(eid,)).fetchone();cfg=c.execute('select * from rrhh_config where id=1').fetchone()
    if not e:c.close();return ('Funcionario no encontrado',404)
    nov=c.execute("select tipo,coalesce(sum(monto),0) monto,coalesce(sum(cantidad),0) cantidad from rrhh_novedades where empleado_id=? and periodo=? and estado in ('APROBADO','PENDIENTE') group by tipo",(eid,periodo)).fetchall();d={r['tipo']:(r['monto'],r['cantidad']) for r in nov};base=float(e['salario_base'] or 0);bon=d.get('BONIFICACION',(0,0))[0];he=d.get('HORA_EXTRA',(0,0))[0];otros=d.get('OTRO_HABER',(0,0))[0];anticipos=d.get('ANTICIPO',(0,0))[0];prest=d.get('PRESTAMO',(0,0))[0];desc=d.get('DESCUENTO',(0,0))[0];ipsbase=base+bon+he+otros if e['ips_activo'] else 0;ipso=round(ipsbase*float(cfg['ips_obrero_pct'] or 0)/100);ipsp=round(ipsbase*float(cfg['ips_patronal_pct'] or 0)/100);hab=base+bon+he+otros;neto=hab-ipso-anticipos-prest-desc;costo=hab+ipsp
    c.execute('''insert into rrhh_liquidaciones(empleado_id,periodo,fecha,salario_base,haberes,horas_extra,bonificaciones,otros_haberes,ips_base,ips_obrero,ips_patronal,anticipos,prestamos,otros_descuentos,neto,costo_empresa,estado,creado_por,creado_en) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
    on conflict(empleado_id,periodo) do update set salario_base=excluded.salario_base,haberes=excluded.haberes,horas_extra=excluded.horas_extra,bonificaciones=excluded.bonificaciones,otros_haberes=excluded.otros_haberes,ips_base=excluded.ips_base,ips_obrero=excluded.ips_obrero,ips_patronal=excluded.ips_patronal,anticipos=excluded.anticipos,prestamos=excluded.prestamos,otros_descuentos=excluded.otros_descuentos,neto=excluded.neto,costo_empresa=excluded.costo_empresa''',(eid,periodo,datetime.date.today().isoformat(),base,hab,he,bon,otros,ipsbase,ipso,ipsp,anticipos,prest,desc,neto,costo,'BORRADOR',session.get('user'),now()));c.commit();c.close();flash('Liquidación calculada.');return redirect('/rrhh/liquidaciones?periodo='+periodo)

@app.route('/rrhh/liquidaciones/<int:i>')
def rrhh_liquidacion_detalle(i):
    if not _rrhh_perm():return ('Acceso no autorizado',403)
    c=db();l=c.execute('select l.*,e.nombre,e.documento,e.cargo,e.departamento,e.ips_numero from rrhh_liquidaciones l join empleados e on e.id=l.empleado_id where l.id=?',(i,)).fetchone();c.close()
    if not l:return ('Liquidación no encontrada',404)
    return render_template('rrhh_payroll_detail.html',l=l)

@app.get('/rrhh/liquidaciones/<int:i>/pdf')
def rrhh_liquidacion_pdf(i):
    if not _rrhh_perm():return ('Acceso no autorizado',403)
    from reportlab.lib.pagesizes import A4
    from reportlab.platypus import SimpleDocTemplate,Table,TableStyle,Paragraph,Spacer
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet
    c=db();l=c.execute('select l.*,e.nombre,e.documento,e.cargo,e.ips_numero from rrhh_liquidaciones l join empleados e on e.id=l.empleado_id where l.id=?',(i,)).fetchone();c.close()
    if not l:return ('Liquidación no encontrada',404)
    out=io.BytesIO();doc=SimpleDocTemplate(out,pagesize=A4);st=getSampleStyleSheet();story=([pdf_logo()] if pdf_logo() else [])+[Paragraph('Recibo de Liquidación de Salario',st['Title']),Paragraph(f"Funcionario: {l['nombre']} · CI: {l['documento'] or '-'} · Periodo: {l['periodo']}",st['Normal']),Spacer(1,12)]
    data=[['Concepto','Haberes Gs.','Descuentos Gs.'],['Salario base',_money_local(l['salario_base']),''],['Bonificaciones',_money_local(l['bonificaciones']),''],['Horas extra',_money_local(l['horas_extra']),''],['Otros haberes',_money_local(l['otros_haberes']),''],['IPS obrero','',_money_local(l['ips_obrero'])],['Anticipos','',_money_local(l['anticipos'])],['Préstamos','',_money_local(l['prestamos'])],['Otros descuentos','',_money_local(l['otros_descuentos'])],['NETO A COBRAR',_money_local(l['neto']),'']]
    t=Table(data,colWidths=[230,120,120]);t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.lightgrey),('GRID',(0,0),(-1,-1),.4,colors.grey),('ALIGN',(1,1),(-1,-1),'RIGHT'),('FONTNAME',(0,-1),(-1,-1),'Helvetica-Bold')]));story += [t,Spacer(1,40),Paragraph('Firma del funcionario: ______________________________',st['Normal'])];doc.build(story);out.seek(0);return send_file(out,as_attachment=True,download_name=f"liquidacion_{l['periodo']}_{i}.pdf",mimetype='application/pdf')

@app.route('/rrhh/configuracion',methods=['GET','POST'])
def rrhh_configuracion():
    if request.method=='POST' and not _rrhh_perm('ADMINISTRAR'):return ('Acceso no autorizado',403)
    if not _rrhh_perm():return ('Acceso no autorizado',403)
    c=db()
    if request.method=='POST':
        c.execute('update rrhh_config set ips_obrero_pct=?,ips_patronal_pct=?,cuenta_sueldos=?,cuenta_cargas=?,cuenta_obligaciones=?,actualizado_en=? where id=1',(float(request.form.get('ips_obrero_pct') or 0),float(request.form.get('ips_patronal_pct') or 0),request.form.get('cuenta_sueldos'),request.form.get('cuenta_cargas'),request.form.get('cuenta_obligaciones'),now()));c.commit();flash('Parámetros RR.HH. actualizados.')
    cfg=c.execute('select * from rrhh_config where id=1').fetchone();c.close();return render_template('rrhh_config.html',cfg=cfg)

@app.get('/rrhh/informes')
def rrhh_informes():
    if not _rrhh_perm():return ('Acceso no autorizado',403)
    c=db();periodo=_rrhh_periodo(request.args.get('periodo'));res=c.execute('''select count(*) funcionarios,coalesce(sum(haberes),0) haberes,coalesce(sum(ips_obrero),0) ips_obrero,coalesce(sum(ips_patronal),0) ips_patronal,coalesce(sum(anticipos),0) anticipos,coalesce(sum(otros_descuentos),0) descuentos,coalesce(sum(neto),0) neto,coalesce(sum(costo_empresa),0) costo from rrhh_liquidaciones where periodo=? and estado!='ANULADA' ''',(periodo,)).fetchone();asist=c.execute("select estado,count(*) cantidad from rrhh_asistencias where substr(fecha,1,7)=? group by estado",(periodo,)).fetchall();c.close();return render_template('rrhh_reports.html',periodo=periodo,res=res,asist=asist)

# ===== V13.9.46: Centro de intercambio tabular + exportación Marangatu =====
import csv, zipfile

def _tabular_xlsx(titulo,headers,rows,filename):
 from openpyxl import Workbook
 from openpyxl.styles import Font,Alignment
 wb=Workbook();ws=wb.active;ws.title='Datos';ws.append(headers)
 for cell in ws[1]: cell.font=Font(bold=True);cell.alignment=Alignment(horizontal='center')
 for r in rows: ws.append([v for v in r])
 for col in ws.columns:
  ws.column_dimensions[col[0].column_letter].width=min(45,max(12,max(len(_safe(x.value)) for x in col)+2))
 bio=io.BytesIO();wb.save(bio);bio.seek(0)
 return send_file(bio,as_attachment=True,download_name=filename,mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

def _tabular_csv(headers,rows,filename,delimiter=','):
 # Generar primero como texto evita que TextIOWrapper cierre el BytesIO
 # antes de que Flask/WSGI termine de transmitir el archivo en Render.
 txt=io.StringIO(newline='')
 w=csv.writer(txt,delimiter=delimiter,lineterminator='\n')
 w.writerow([_safe(v) for v in headers])
 for r in rows:
  w.writerow(['' if v is None else v for v in r])
 data=('\ufeff'+txt.getvalue()).encode('utf-8')
 bio=io.BytesIO(data);bio.seek(0)
 return send_file(bio,as_attachment=True,download_name=filename,mimetype='text/csv; charset=utf-8')

@app.get('/informes/<tipo>/excel')
def informe_excel_tabla(tipo):
 if tipo not in {x[0] for x in REPORT_GROUPS}:return ('Informe no encontrado',404)
 desde=request.args.get('desde') or '1900-01-01';hasta=request.args.get('hasta') or datetime.date.today().isoformat();c=db();titulo,headers,rows=_report_data(c,tipo,desde,hasta);c.close();return _tabular_xlsx(titulo,headers,rows,f'{tipo}_{desde}_{hasta}.xlsx')

@app.get('/informes/<tipo>/csv')
def informe_csv_tabla(tipo):
 if tipo not in {x[0] for x in REPORT_GROUPS}:return ('Informe no encontrado',404)
 desde=request.args.get('desde') or '1900-01-01';hasta=request.args.get('hasta') or datetime.date.today().isoformat();c=db();titulo,headers,rows=_report_data(c,tipo,desde,hasta);c.close();return _tabular_csv(headers,rows,f'{tipo}_{desde}_{hasta}.csv')

@app.get('/contabilidad/informe/<tipo>/csv')
def contabilidad_csv(tipo):
 if tipo not in {x[0] for x in ACCOUNTING_REPORTS}:return ('Informe contable no encontrado',404)
 desde=request.args.get('desde') or '1900-01-01';hasta=request.args.get('hasta') or datetime.date.today().isoformat();cuenta=request.args.get('cuenta') or None;c=db();titulo,headers,rows=_accounting_report(c,tipo,desde,hasta,cuenta);c.close();return _tabular_csv(headers,rows,f'{tipo}_{desde}_{hasta}.csv')

# ===== V13.9.59: exportación universal de libros contables =====
@app.get('/contabilidad/informe/<tipo>/exportar/<formato>')
def contabilidad_exportar_formato(tipo,formato):
 if tipo not in {x[0] for x in ACCOUNTING_REPORTS}: return ('Informe contable no encontrado',404)
 desde=request.args.get('desde') or '1900-01-01'; hasta=request.args.get('hasta') or datetime.date.today().isoformat(); cuenta=request.args.get('cuenta') or None
 c=db(); titulo,headers,rows=_accounting_report(c,tipo,desde,hasta,cuenta); c.close()
 formato=(formato or '').lower()
 if formato in ('xlsx','excel'):
  return _tabular_xlsx(titulo,headers,rows,f'{tipo}_{desde}_{hasta}.xlsx')
 if formato=='csv': return _tabular_csv(headers,rows,f'{tipo}_{desde}_{hasta}.csv',',')
 if formato in ('tsv','txt'):
  delim='\t' if formato=='tsv' else ';'
  ext='tsv' if formato=='tsv' else 'txt'
  return _tabular_csv(headers,rows,f'{tipo}_{desde}_{hasta}.{ext}',delim)
 if formato=='json':
  import json
  data=[]
  for r in rows:data.append({str(headers[i]): (r[i] if i<len(r) else None) for i in range(len(headers))})
  raw=json.dumps({'libro':titulo,'desde':desde,'hasta':hasta,'registros':data},ensure_ascii=False,indent=2,default=str).encode('utf-8')
  bio=io.BytesIO(raw);bio.seek(0);return send_file(bio,as_attachment=True,download_name=f'{tipo}_{desde}_{hasta}.json',mimetype='application/json; charset=utf-8')
 if formato=='pdf':
  args=request.args.to_dict(flat=True); args['modo']=args.get('modo','normal')
  from urllib.parse import urlencode
  return redirect('/contabilidad/informe/'+tipo+'/pdf?'+urlencode(args))
 return ('Formato no admitido. Use XLSX, CSV, TXT, TSV, JSON o PDF.',400)

@app.get('/contabilidad/informe/<tipo>/importar')
def contabilidad_importar_desde_libro(tipo):
 if tipo not in {x[0] for x in ACCOUNTING_REPORTS}: return ('Libro no encontrado',404)
 # Los libros derivados no deben grabarse como saldos independientes: se reconstruyen desde Diario/operaciones.
 if tipo in ('diario','mayor','movimientos'):
  return redirect('/contabilidad/intercambio?tipo=diario&origen='+tipo)
 if tipo=='compras_iva': return redirect('/contabilidad/intercambio?tipo=compras&origen='+tipo)
 if tipo=='ventas_iva': return redirect('/contabilidad/intercambio?tipo=ventas&origen='+tipo)
 return redirect('/contabilidad/intercambio?tipo=derivado&origen='+tipo)

def _ruc_sin_dv(ruc):
 s=str(ruc or '').strip().replace('.','').replace(' ','')
 return s.split('-')[0] if '-' in s else s

def _fecha_dnit(v):
 try:return datetime.date.fromisoformat(str(v)[:10]).strftime('%d/%m/%Y')
 except:return str(v or '')

def _condicion_dnit(v): return '2' if str(v or '').upper() in ('CREDITO','CUOTAS') else '1'

def _marangatu_rows(c,desde,hasta,incluir_ventas=False,incluir_compras=True):
 rows=[];errores=[]
 if incluir_compras:
  data=c.execute("select co.*,t.ruc,t.nombre proveedor from compras co left join terceros t on t.id=co.proveedor_id where co.fecha between ? and ? and co.estado!='ANULADA' order by co.fecha,co.id",(desde,hasta)).fetchall()
  for x in data:
   ruc=_ruc_sin_dv(x['ruc']); tim=_solo_digitos(x['timbrado']); num=str(x['numero'] or '').strip()
   if not ruc or not tim or not num:errores.append(f"Compra #{x['id']}: falta RUC, timbrado o comprobante");continue
   g10=round(float(x['gravado_10'] or 0)+float(x['iva_10'] or 0));g5=round(float(x['gravado_5'] or 0)+float(x['iva_5'] or 0));ex=round(float(x['exento_iva'] or 0));total=g10+g5+ex
   rows.append(['2','11',ruc,'','109',_fecha_dnit(x['fecha']),tim,num,str(g10),str(g5),str(ex),str(total),_condicion_dnit(x['condicion_pago']),'S' if str(x['moneda'] or 'PYG').upper()!='PYG' else 'N','S','S','N','N','',''])
 if incluir_ventas:
  data=c.execute("select v.*,t.ruc,t.nombre cliente,p.timbrado punto_timbrado from ventas v left join terceros t on t.id=v.cliente_id left join sifen_puntos_expedicion p on p.id=v.sifen_punto_id where v.fecha between ? and ? and v.estado!='ANULADA' and coalesce(v.estado_sifen,'NO_ENVIADO') not in ('APROBADO','DTE','APROBADO_SIFEN') order by v.fecha,v.id",(desde,hasta)).fetchall()
  for x in data:
   ruc=_ruc_sin_dv(x['ruc']); tipoid='11' if ruc else '15'; ident=ruc or '0'; nombre='' if ruc else (x['cliente'] or 'SIN NOMBRE');tim=_solo_digitos(x['punto_timbrado']);num=str(x['numero'] or '').strip()
   if not tim or not num:errores.append(f"Venta #{x['id']}: falta timbrado o comprobante");continue
   g10=round(float(x['gravado_10'] or 0)+float(x['iva_10'] or 0));g5=round(float(x['gravado_5'] or 0)+float(x['iva_5'] or 0));ex=round(float(x['exento_iva'] or 0));total=g10+g5+ex
   rows.append(['1',tipoid,ident,nombre,'109',_fecha_dnit(x['fecha']),tim,num,str(g10),str(g5),str(ex),str(total),_condicion_dnit(x['condicion_venta']),'S' if str(x['moneda'] or 'PYG').upper()!='PYG' else 'N','S','S','N','',''])
 return rows,errores

@app.get('/intercambio')
def intercambio_centro():
 return render_template('data_exchange.html')

@app.post('/intercambio/validar')
def intercambio_validar():
 f=request.files.get('archivo')
 if not f or not f.filename:flash('Seleccione un archivo CSV, TXT o XLSX.');return redirect('/intercambio')
 try:
  ext=os.path.splitext(f.filename.lower())[1];rows=[]
  if ext=='.xlsx':
   from openpyxl import load_workbook
   wb=load_workbook(f,read_only=True,data_only=True);ws=wb.active;rows=[list(r) for r in ws.iter_rows(values_only=True)]
  elif ext in ('.csv','.txt'):
   raw=f.read().decode('utf-8-sig');dial=csv.excel_tab if ext=='.txt' else csv.excel;rows=[list(r) for r in csv.reader(io.StringIO(raw),dialect=dial)]
  else:raise ValueError('Formato no admitido. Use XLSX, CSV o TXT.')
  headers=rows[0] if rows else [];data=rows[1:501] if len(rows)>1 else []
  return render_template('data_import_preview.html',filename=f.filename,headers=headers,rows=data,total=max(0,len(rows)-1))
 except Exception as e:flash('No se pudo validar el archivo: '+str(e));return redirect('/intercambio')

@app.get('/marangatu/exportar')
def marangatu_exportar():
 periodo=(request.args.get('periodo') or datetime.date.today().strftime('%Y-%m'))[:7];tipo=request.args.get('tipo','compras');fmt=request.args.get('formato','zip')
 try:y,m=map(int,periodo.split('-'));desde=f'{y:04d}-{m:02d}-01';hasta=(datetime.date(y+1,1,1)-datetime.timedelta(days=1)).isoformat() if m==12 else (datetime.date(y,m+1,1)-datetime.timedelta(days=1)).isoformat()
 except:return ('Periodo inválido',400)
 c=db();cfg=c.execute('select * from institucion_config where id=1').fetchone();rows,errores=_marangatu_rows(c,desde,hasta,tipo in ('ventas','ambos'),tipo in ('compras','ambos'));c.close()
 if errores:flash('Advertencia: '+ ' | '.join(errores[:8]))
 ruc=_ruc_sin_dv(cfg['ruc'] if cfg else '')
 if not ruc:return ('Configure el RUC institucional antes de exportar para Marangatu.',400)
 base=f"{ruc}_REG_{m:02d}{y}_SC001";raw=io.StringIO(newline='');w=csv.writer(raw,delimiter=',',lineterminator='\n');
 for r in rows:w.writerow(r)
 data=raw.getvalue().encode('utf-8')
 if fmt=='csv':bio=io.BytesIO(data);return send_file(bio,as_attachment=True,download_name=base+'.csv',mimetype='text/csv; charset=utf-8')
 out=io.BytesIO();
 with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:z.writestr(base+'.csv',data)
 out.seek(0);return send_file(out,as_attachment=True,download_name=base+'.zip',mimetype='application/zip')

@app.get('/rrhh/informes/excel')
def rrhh_informes_excel():
 if not _rrhh_perm():return ('Acceso no autorizado',403)
 periodo=_rrhh_periodo(request.args.get('periodo'));c=db();rows=c.execute('''select e.documento,e.nombre,e.cargo,l.periodo,l.salario_base,l.haberes,l.ips_obrero,l.ips_patronal,l.anticipos,l.prestamos,l.otros_descuentos,l.neto,l.costo_empresa,l.estado from rrhh_liquidaciones l join empleados e on e.id=l.empleado_id where l.periodo=? order by e.nombre''',(periodo,)).fetchall();c.close();headers=['CI','Funcionario','Cargo','Periodo','Salario base','Haberes','IPS obrero','IPS patronal','Anticipos','Préstamos','Otros descuentos','Neto','Costo empresa','Estado'];return _tabular_xlsx('RRHH',headers,rows,f'rrhh_{periodo}.xlsx')

@app.get('/rrhh/informes/csv')
def rrhh_informes_csv():
 if not _rrhh_perm():return ('Acceso no autorizado',403)
 periodo=_rrhh_periodo(request.args.get('periodo'));c=db();rows=c.execute('''select e.documento,e.nombre,e.cargo,l.periodo,l.salario_base,l.haberes,l.ips_obrero,l.ips_patronal,l.anticipos,l.prestamos,l.otros_descuentos,l.neto,l.costo_empresa,l.estado from rrhh_liquidaciones l join empleados e on e.id=l.empleado_id where l.periodo=? order by e.nombre''',(periodo,)).fetchall();c.close();headers=['CI','Funcionario','Cargo','Periodo','Salario base','Haberes','IPS obrero','IPS patronal','Anticipos','Préstamos','Otros descuentos','Neto','Costo empresa','Estado'];return _tabular_csv(headers,rows,f'rrhh_{periodo}.csv')

ROUTE_MODULE.update({'intercambio_centro':'INFORMES','intercambio_validar':'INFORMES','marangatu_exportar':'CONTABILIDAD','informe_excel_tabla':'INFORMES','informe_csv_tabla':'INFORMES','contabilidad_csv':'CONTABILIDAD','contabilidad_exportar_formato':'CONTABILIDAD','contabilidad_importar_desde_libro':'CONTABILIDAD','rrhh_informes_excel':'RRHH','rrhh_informes_csv':'RRHH'})

# ===== V13.9.50: Importación / exportación contable operativa =====
def _leer_tabla_subida(f):
    ext=os.path.splitext((f.filename or '').lower())[1]
    if ext=='.xlsx':
        from openpyxl import load_workbook
        wb=load_workbook(f,read_only=True,data_only=True); ws=wb.active
        return [[v for v in row] for row in ws.iter_rows(values_only=True)]
    if ext in ('.csv','.txt'):
        raw=f.read().decode('utf-8-sig'); delimiter='\t' if ext=='.txt' else ','
        return [list(r) for r in csv.reader(io.StringIO(raw),delimiter=delimiter)]
    raise ValueError('Formato no admitido. Use XLSX, CSV o TXT.')

def _norm_header(v):
    import unicodedata,re
    t=unicodedata.normalize('NFKD',str(v or '')).encode('ascii','ignore').decode().lower().strip()
    return re.sub(r'[^a-z0-9]+','_',t).strip('_')

def _num_import(v):
    if v in (None,''): return 0.0
    if isinstance(v,(int,float)): return float(v)
    t=str(v).strip().replace('Gs.','').replace('Gs','').replace(' ','')
    if ',' in t and '.' in t: t=t.replace('.','').replace(',','.')
    elif ',' in t: t=t.replace(',','.')
    return float(t or 0)

def _fecha_import(v):
    if isinstance(v,datetime.datetime): return v.date().isoformat()
    if isinstance(v,datetime.date): return v.isoformat()
    t=str(v or '').strip()
    for fmt in ('%Y-%m-%d','%d/%m/%Y','%d-%m-%Y'):
        try:return datetime.datetime.strptime(t[:10],fmt).date().isoformat()
        except:pass
    raise ValueError('Fecha inválida: '+t)

@app.get('/contabilidad/intercambio')
def contabilidad_intercambio(): return render_template('accounting_exchange.html')

@app.get('/contabilidad/plantilla/<tipo>')
def contabilidad_plantilla(tipo):
    if tipo=='plan':
        h=['codigo','nombre','tipo','moneda','imputable','cuenta_padre','naturaleza','activa']; ejemplo=[['1.1.01.001','Caja Recepción','ACTIVO','PYG',1,'1.1.01','DEUDORA',1]]
    elif tipo=='diario':
        h=['fecha','asiento','concepto','cuenta','debe_pyg','haber_pyg','moneda','tipo_cambio','detalle']; ejemplo=[['2026-09-25','IMP-0001','Asiento importado','1.1.01',100000,0,'PYG',1,'Detalle'],['2026-09-25','IMP-0001','Asiento importado','4.1.02',0,100000,'PYG',1,'Detalle']]
    else:return ('Plantilla no encontrada',404)
    return _tabular_xlsx('Plantilla '+tipo,h,ejemplo,f'plantilla_{tipo}_contabilidad.xlsx')

@app.get('/contabilidad/plan/excel')
def plan_contable_excel():
    c=db();rows=c.execute('select codigo,nombre,tipo,moneda,imputable,cuenta_padre,naturaleza,activa from plan_cuentas order by codigo').fetchall();c.close()
    h=['codigo','nombre','tipo','moneda','imputable','cuenta_padre','naturaleza','activa'];return _tabular_xlsx('Plan de Cuentas',h,rows,'plan_cuentas.xlsx')

@app.get('/contabilidad/plan/csv')
def plan_contable_csv():
    c=db();rows=c.execute('select codigo,nombre,tipo,moneda,imputable,cuenta_padre,naturaleza,activa from plan_cuentas order by codigo').fetchall();c.close()
    h=['codigo','nombre','tipo','moneda','imputable','cuenta_padre','naturaleza','activa'];return _tabular_csv(h,rows,'plan_cuentas.csv')

@app.post('/contabilidad/importar/<tipo>')
def contabilidad_importar(tipo):
    if tipo not in ('plan','diario'): return ('Tipo de importación no admitido',404)
    f=request.files.get('archivo')
    if not f or not f.filename: flash('Seleccione un archivo XLS, XLSX, CSV o TXT.'); return redirect('/contabilidad/intercambio')
    confirmar=request.form.get('confirmar')=='1'; c=None
    try:
        tabla=_leer_tabla_subida(f)
        if not tabla: raise ValueError('El archivo está vacío.')
        headers=[_norm_header(x) for x in tabla[0]]; data=tabla[1:]
        req={'plan':['codigo','nombre','tipo'],'diario':['fecha','asiento','concepto','cuenta','debe_pyg','haber_pyg']}[tipo]
        faltan=[x for x in req if x not in headers]
        if faltan: raise ValueError('Faltan columnas obligatorias: '+', '.join(faltan))
        ix={h:i for i,h in enumerate(headers)}; errores=[];valid=[];c=db()
        if tipo=='plan':
            for n,row in enumerate(data,2):
                try:
                    get=lambda k,d='': row[ix[k]] if k in ix and ix[k]<len(row) and row[ix[k]] is not None else d
                    codigo=str(get('codigo')).strip();nombre=str(get('nombre')).strip();tipo_c=str(get('tipo')).upper().strip();mon=str(get('moneda','PYG')).upper().strip() or 'PYG'
                    if not codigo or not nombre:raise ValueError('código/nombre vacío')
                    if tipo_c not in ('ACTIVO','PASIVO','PATRIMONIO','INGRESO','EGRESO'):raise ValueError('tipo inválido')
                    valid.append((codigo,nombre,tipo_c,mon,int(_num_import(get('imputable',1))!=0),str(get('cuenta_padre','')).strip() or None,str(get('naturaleza','')).upper().strip() or ('DEUDORA' if tipo_c in ('ACTIVO','EGRESO') else 'ACREEDORA'),int(_num_import(get('activa',1))!=0)))
                except Exception as e: errores.append(f'Fila {n}: {e}')
        else:
            grupos={}
            for n,row in enumerate(data,2):
                try:
                    get=lambda k,d='': row[ix[k]] if k in ix and ix[k]<len(row) and row[ix[k]] is not None else d
                    fecha=_fecha_import(get('fecha')); num=str(get('asiento')).strip(); concepto=str(get('concepto')).strip();cuenta=str(get('cuenta')).strip();debe=_num_import(get('debe_pyg'));haber=_num_import(get('haber_pyg'));mon=str(get('moneda','PYG')).upper().strip() or 'PYG';tc=_num_import(get('tipo_cambio',1)) or 1;det=str(get('detalle','')).strip()
                    if not num:raise ValueError('asiento vacío')
                    if not c.execute('select 1 from plan_cuentas where codigo=?',(cuenta,)).fetchone():raise ValueError('cuenta inexistente '+cuenta)
                    if debe<0 or haber<0 or (debe>0 and haber>0):raise ValueError('Debe/Haber inválido')
                    grupos.setdefault(num,[]).append((fecha,concepto,cuenta,debe,haber,mon,tc,det))
                except Exception as e:errores.append(f'Fila {n}: {e}')
            for num,lineas in grupos.items():
                td=sum(x[3] for x in lineas);th=sum(x[4] for x in lineas)
                if abs(td-th)>0.5:errores.append(f'Asiento {num}: no balancea. Debe {td:.0f} / Haber {th:.0f}')
                elif c.execute('select 1 from asientos where numero=?',(num,)).fetchone():errores.append(f'Asiento {num}: ya existe')
                else:valid.append((num,lineas))
        if not confirmar:
            c.close();return render_template('accounting_import_preview.html',tipo=tipo,filename=f.filename,headers=headers,total=len(data),validos=len(valid),errores=errores[:100])
        if errores: raise ValueError('Corrija los errores antes de confirmar. Primer error: '+errores[0])
        if tipo=='plan':
            sql='''insert into plan_cuentas(codigo,nombre,tipo,moneda,imputable,cuenta_padre,naturaleza,activa) values(?,?,?,?,?,?,?,?) on conflict(codigo) do update set nombre=excluded.nombre,tipo=excluded.tipo,moneda=excluded.moneda,imputable=excluded.imputable,cuenta_padre=excluded.cuenta_padre,naturaleza=excluded.naturaleza,activa=excluded.activa'''
            for r in valid:c.execute(sql,r)
        else:
            for num,lineas in valid:
                x=lineas[0];cur=c.execute('insert into asientos(fecha,numero,concepto,origen_tipo,origen_id,moneda,tipo_cambio,estado) values(?,?,?,?,?,?,?,?)',(x[0],num,x[1],'IMPORTACION',None,x[5],x[6],'CONFIRMADO'));aid=cur.lastrowid
                for z in lineas:c.execute('insert into asiento_det(asiento_id,cuenta,debe_pyg,haber_pyg,importe_moneda,moneda,tipo_cambio,detalle) values(?,?,?,?,?,?,?,?)',(aid,z[2],z[3],z[4],0,z[5],z[6],z[7]))
        c.commit();c.close();audit('IMPORTACION_CONTABLE',f'{tipo}: {len(valid)} registros/grupos desde {f.filename}');flash(f'Importación completada: {len(valid)} registros/grupos procesados.');return redirect('/contabilidad/intercambio')
    except Exception as e:
        try:
            if c:c.rollback();c.close()
        except:pass
        flash('No se pudo importar: '+str(e));return redirect('/contabilidad/intercambio')

ROUTE_MODULE.update({'contabilidad_intercambio':'CONTABILIDAD','contabilidad_plantilla':'CONTABILIDAD','plan_contable_excel':'CONTABILIDAD','plan_contable_csv':'CONTABILIDAD','contabilidad_importar':'CONTABILIDAD'})

# ===== V13.9.72: Monitor SIFEN avanzado y corrección controlada =====
def init_v13972_monitor_sifen():
    c=db()
    for tab in ('notas_credito_ventas','notas_debito_ventas'):
        try:
            cols={r['name'] for r in c.execute('pragma table_info('+tab+')').fetchall()}
            for col,defn in [('sifen_codigo_error','TEXT'),('sifen_mensaje_error','TEXT'),('sifen_ultimo_intento','TEXT'),('sifen_intentos','INTEGER DEFAULT 0')]:
                if col not in cols:c.execute(f'alter table {tab} add column {col} {defn}')
        except Exception: pass
    c.execute("insert or ignore into schema_migrations(version,aplicado_en) values('13.9.72-monitor-sifen-avanzado',?)",(now(),));c.commit();c.close()
init_v13972_monitor_sifen()

# ===== V13.9.47: Control fiscal, NC ventas/compras y monitor SIFEN =====
def init_v13947_control_fiscal():
    c=db()
    c.execute("""CREATE TABLE IF NOT EXISTS notas_credito_ventas(
      id INTEGER PRIMARY KEY,venta_id INTEGER NOT NULL,fecha TEXT NOT NULL,numero TEXT,
      motivo TEXT NOT NULL,total REAL NOT NULL DEFAULT 0,estado TEXT NOT NULL DEFAULT 'EMITIDA',
      estado_sifen TEXT NOT NULL DEFAULT 'NO_ENVIADA',cdc TEXT,protocolo_sifen TEXT,respuesta_sifen TEXT,
      creado_en TEXT,usuario TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS nota_credito_venta_items(
      id INTEGER PRIMARY KEY,nota_id INTEGER NOT NULL,venta_item_id INTEGER,producto_id INTEGER,
      descripcion TEXT,cantidad REAL NOT NULL DEFAULT 0,precio REAL NOT NULL DEFAULT 0,total REAL NOT NULL DEFAULT 0,iva_pct REAL DEFAULT 10)""")
    c.execute("""CREATE TABLE IF NOT EXISTS notas_credito_compras(
      id INTEGER PRIMARY KEY,compra_id INTEGER NOT NULL,fecha TEXT NOT NULL,numero TEXT NOT NULL,
      timbrado TEXT,motivo TEXT NOT NULL,total REAL NOT NULL DEFAULT 0,estado TEXT NOT NULL DEFAULT 'REGISTRADA',creado_en TEXT,usuario TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS nota_credito_compra_items(
      id INTEGER PRIMARY KEY,nota_id INTEGER NOT NULL,compra_item_id INTEGER,producto_id INTEGER,
      descripcion TEXT,cantidad REAL NOT NULL DEFAULT 0,costo REAL NOT NULL DEFAULT 0,total REAL NOT NULL DEFAULT 0,iva_pct REAL DEFAULT 10)""")
    cols={r['name'] for r in c.execute('pragma table_info(ventas)').fetchall()}
    for col,defn in [('sifen_codigo_error','TEXT'),('sifen_mensaje_error','TEXT'),('sifen_ultimo_intento','TEXT'),('sifen_intentos','INTEGER DEFAULT 0'),('motivo_anulacion','TEXT'),('fecha_anulacion','TEXT')]:
        if col not in cols:c.execute(f'alter table ventas add column {col} {defn}')
    c.execute("insert or ignore into schema_migrations(version,aplicado_en) values('13.9.47-control-fiscal',?)",(now(),));c.commit();c.close()
init_v13947_control_fiscal()

# ===== V13.9.48: administración segura de puntos de expedición =====
def init_v13948_puntos_editables():
    c=db();c.execute("insert or ignore into schema_migrations(version,aplicado_en) values('13.9.48-puntos-editables',?)",(now(),));c.commit();c.close()
init_v13948_puntos_editables()

def _nc_numero(c,punto_id=None):
    p=_punto_facturacion(c,punto_id)
    if not p or not int(p['nota_credito_electronica'] or 0): raise ValueError('El punto de expedición no está habilitado para Nota de Crédito Electrónica.')
    # Secuencia independiente de NC por punto, conservada en tabla auxiliar.
    c.execute("CREATE TABLE IF NOT EXISTS sifen_correlativos(tipo TEXT,punto_id INTEGER,proximo INTEGER DEFAULT 1,PRIMARY KEY(tipo,punto_id))")
    c.execute("insert or ignore into sifen_correlativos(tipo,punto_id,proximo) values('NCE',?,1)",(p['id'],))
    n=int(c.execute("select proximo from sifen_correlativos where tipo='NCE' and punto_id=?",(p['id'],)).fetchone()[0]);
    if n>9999999:raise ValueError('Se agotó la numeración de Nota de Crédito para este punto.')
    c.execute("update sifen_correlativos set proximo=? where tipo='NCE' and punto_id=?",(n+1,p['id']))
    return f"{str(p['establecimiento']).zfill(3)}-{str(p['punto_expedicion']).zfill(3)}-{str(n).zfill(7)}",p

@app.route('/ventas/<int:venta_id>/nota-credito',methods=['GET','POST'])
def nota_credito_venta(venta_id):
    c=db();v=c.execute("select v.*,t.nombre cliente,t.ruc from ventas v left join terceros t on t.id=v.cliente_id where v.id=?",(venta_id,)).fetchone()
    if not v:c.close();return ('Venta no encontrada',404)
    items=c.execute("select vi.*,p.nombre,p.codigo from venta_items vi left join productos p on p.id=vi.producto_id where vi.venta_id=? order by vi.id",(venta_id,)).fetchall()
    if request.method=='POST':
      try:
       motivo=(request.form.get('motivo') or '').strip()
       if not motivo:raise ValueError('Indique el motivo de la Nota de Crédito.')
       seleccion=[];total=0
       for it in items:
        q=float(request.form.get(f'qty_{it["id"]}') or 0)
        if q<0 or q>float(it['cantidad'] or 0):raise ValueError('Cantidad inválida para '+str(it['nombre'] or 'ítem'))
        if q>0:
         t=q*float(it['precio'] or 0);total+=t;seleccion.append((it,q,t))
       if not seleccion:raise ValueError('Seleccione al menos un ítem/cantidad a acreditar.')
       numero,p=_nc_numero(c,v['sifen_punto_id']);cur=c.execute("insert into notas_credito_ventas(venta_id,fecha,numero,motivo,total,estado,estado_sifen,creado_en,usuario) values(?,?,?,?,?,'EMITIDA','PENDIENTE_ENVIO',?,?)",(venta_id,datetime.date.today().isoformat(),numero,motivo,total,now(),session.get('user')));nid=cur.lastrowid
       for it,q,t in seleccion:c.execute("insert into nota_credito_venta_items(nota_id,venta_item_id,producto_id,descripcion,cantidad,precio,total,iva_pct) values(?,?,?,?,?,?,?,?)",(nid,it['id'],it['producto_id'],it['nombre'] or 'Ítem',q,it['precio'],t,it['iva_pct']))
       cdc=_generar_cdc_test_complementario(c,'05',datetime.date.today().isoformat(),numero,p['id'],'NCE',nid)
       c.execute("insert into sifen_eventos(fecha,tipo,estado,detalle) values(?,?,?,?)",(now(),'NCE','TEST_GENERADO' if cdc else 'PENDIENTE_ENVIO',f'NC {numero} asociada a factura {v["numero"]}; CDC TEST '+str(cdc) if cdc else f'NC {numero} pendiente de integración SIFEN'))
       c.commit();flash(('Nota de Crédito emitida con CDC DE PRUEBA: '+cdc) if cdc else 'Nota de Crédito registrada. SIFEN no está en ambiente TEST.');c.close();return redirect(f'/notas-credito/ventas/{nid}/pdf')
      except Exception as e:c.rollback();flash(str(e))
    puntos=c.execute("select * from sifen_puntos_expedicion where activo=1 and autorizado_dnit=1 and nota_credito_electronica=1 order by predeterminado desc,id").fetchall();c.close();return render_template('credit_note_sale.html',v=v,items=items,puntos=puntos)

@app.post('/ventas/<int:venta_id>/anular')
def anular_factura_venta(venta_id):
    c=db()
    try:
      v=c.execute('select * from ventas where id=?',(venta_id,)).fetchone()
      if not v:raise ValueError('Factura no encontrada.')
      if str(v['estado'] or '').upper()=='ANULADA':raise ValueError('La factura ya está anulada.')
      motivo=(request.form.get('motivo') or '').strip()
      if not motivo:raise ValueError('Indique el motivo de anulación.')
      es_aprob=str(v['estado_sifen'] or '').upper() in ('APROBADO','APROBADA','ACEPTADO','ACEPTADA','DTE','APROBADO_SIFEN')
      if es_aprob:
       # No se falsifica una cancelación DNIT: queda pendiente hasta que el WS de eventos confirme.
       c.execute("update ventas set estado_sifen='CANCELACION_PENDIENTE',motivo_anulacion=?,sifen_ultimo_intento=? where id=?",(motivo,now(),venta_id))
       c.execute("insert into sifen_eventos(fecha,tipo,estado,detalle) values(?,?,?,?)",(now(),'CANCELACION','PENDIENTE_ENVIO',f'Factura {v["numero"]}: {motivo}'))
       flash('Solicitud preparada. La factura NO se marca anulada fiscalmente hasta recibir confirmación de SIFEN.')
      else:
       c.execute("update ventas set estado='ANULADA',motivo_anulacion=?,fecha_anulacion=? where id=?",(motivo,now(),venta_id));flash('Factura interna anulada. Si el número/CDC fue generado y no se utilizará, revise la inutilización correspondiente en SIFEN.')
      c.commit()
    except Exception as e:c.rollback();flash(str(e))
    finally:c.close()
    return redirect(f'/ventas/{venta_id}/factura')

# ===== V13.9.54: aplicación real de Notas de Crédito de Compras =====
def init_v13954_nc_compras_aplicables():
    c=db()
    cols={r['name'] for r in c.execute('pragma table_info(notas_credito_compras)').fetchall()}
    for col,defn in [('aplicado_cxp','REAL NOT NULL DEFAULT 0'),('saldo_credito','REAL NOT NULL DEFAULT 0'),('estado_aplicacion',"TEXT NOT NULL DEFAULT 'PENDIENTE'"),('asiento_id','INTEGER'),('stock_ajustado','INTEGER NOT NULL DEFAULT 1')]:
        if col not in cols:c.execute(f'alter table notas_credito_compras add column {col} {defn}')
    # NC históricas: ya habían descontado stock. Se habilita su aplicación financiera sin repetir inventario.
    c.execute("update notas_credito_compras set saldo_credito=case when coalesce(saldo_credito,0)=0 and coalesce(aplicado_cxp,0)=0 then coalesce(total,0) else saldo_credito end where coalesce(estado_aplicacion,'PENDIENTE')='PENDIENTE'")
    c.execute("INSERT OR IGNORE INTO schema_migrations(version,aplicado_en) VALUES('13.9.54-nc-compras-aplicables',?)",(now(),))
    c.commit();c.close()
init_v13954_nc_compras_aplicables()

def _nc_compra_totales(c,nid):
    rows=c.execute('select * from nota_credito_compra_items where nota_id=?',(nid,)).fetchall()
    bruto=base=iva=exento=0.0
    for x in rows:
        t=float(x['total'] or 0); pct=float(x['iva_pct'] or 0); b,i=desglosar_iva_incluido(t,pct)
        bruto+=t
        if pct>0:base+=b;iva+=i
        else:exento+=t
    return bruto,base,iva,exento

def _contabilizar_nc_compra(c,nid):
    n=c.execute('select n.*,co.moneda,co.tipo_cambio,co.numero compra_numero from notas_credito_compras n join compras co on co.id=n.compra_id where n.id=?',(nid,)).fetchone()
    if not n:return None
    if n['asiento_id']:return n['asiento_id']
    bruto,base,iva,exento=_nc_compra_totales(c,nid);tc=float(n['tipo_cambio'] or 1)
    # Reversión del comprobante de compra: Proveedores al Debe; Inventario e IVA Crédito al Haber.
    lineas=[('2.1.01',bruto*tc,0,bruto,'Nota de crédito proveedor '+str(n['numero']))]
    if base>0:lineas.append(('1.1.03',0,base*tc,base,'Reversión inventario por NC'))
    if exento>0:lineas.append(('1.1.03',0,exento*tc,exento,'Reversión inventario exento por NC'))
    if iva>0:lineas.append(('1.1.04',0,iva*tc,iva,'Reversión IVA crédito por NC'))
    aid=asiento(c,n['fecha'],'Nota de Crédito proveedor '+str(n['numero']),'NC_COMPRA',nid,n['moneda'],tc,lineas)
    c.execute('update notas_credito_compras set asiento_id=? where id=?',(aid,nid));return aid

def _aplicar_nc_a_cxp(c,nid,importe=None):
    n=c.execute('select n.*,co.moneda,co.tipo_cambio from notas_credito_compras n join compras co on co.id=n.compra_id where n.id=?',(nid,)).fetchone()
    if not n:raise ValueError('Nota de Crédito no encontrada.')
    disponible=max(0,float(n['saldo_credito'] or 0))
    if importe is None:importe=disponible
    importe=max(0,min(float(importe or 0),disponible))
    if importe<=0:return 0.0
    x=c.execute("select * from cxp where compra_id=? and coalesce(estado,'') not in ('ANULADA','ANULADO') order by id limit 1",(n['compra_id'],)).fetchone()
    if not x:raise ValueError('Esta compra no tiene saldo en Cuentas por Pagar. El importe queda como crédito disponible del proveedor.')
    saldo=max(0,float(x['saldo'] or 0));aplicar=min(importe,saldo)
    if aplicar<=0:raise ValueError('La compra ya no tiene saldo pendiente. La Nota de Crédito queda como crédito disponible.')
    nuevo=saldo-aplicar;c.execute("update cxp set saldo=?,estado=? where id=?",(nuevo,'PAGADO' if nuevo<=0.005 else 'PENDIENTE',x['id']))
    # Reduce cuotas pendientes sin alterar importes ya pagados, comenzando por las últimas.
    resto=aplicar
    for q in c.execute('select * from compra_cuotas where compra_id=? order by numero desc,id desc',(n['compra_id'],)).fetchall():
        if resto<=0:break
        pendiente=max(0,float(q['importe'] or 0)-float(q['pagado'] or 0))
        d=min(resto,pendiente)
        if d>0:
            nuevo_imp=float(q['importe'] or 0)-d
            c.execute("update compra_cuotas set importe=?,estado=? where id=?",(nuevo_imp,'PAGADA' if nuevo_imp<=float(q['pagado'] or 0)+0.005 else 'PENDIENTE',q['id']));resto-=d
    aplicado=float(n['aplicado_cxp'] or 0)+aplicar;disp=disponible-aplicar
    estado='APLICADA' if disp<=0.005 else 'PARCIAL'
    c.execute('update notas_credito_compras set aplicado_cxp=?,saldo_credito=?,estado_aplicacion=? where id=?',(aplicado,disp,estado,nid))
    return aplicar

@app.route('/compras/<int:compra_id>/nota-credito',methods=['GET','POST'])
def nota_credito_compra(compra_id):
    c=db();co=c.execute("select co.*,t.nombre proveedor,t.ruc from compras co left join terceros t on t.id=co.proveedor_id where co.id=?",(compra_id,)).fetchone()
    if not co:c.close();return ('Compra no encontrada',404)
    items=c.execute("select ci.*,p.nombre,p.codigo from compra_items ci left join productos p on p.id=ci.producto_id where ci.compra_id=? order by ci.id",(compra_id,)).fetchall()
    usados={r['compra_item_id']:float(r['q'] or 0) for r in c.execute('select i.compra_item_id,sum(i.cantidad) q from nota_credito_compra_items i join notas_credito_compras n on n.id=i.nota_id where n.compra_id=? group by i.compra_item_id',(compra_id,)).fetchall()}
    cxp=c.execute("select * from cxp where compra_id=? and coalesce(estado,'') not in ('ANULADA','ANULADO') order by id limit 1",(compra_id,)).fetchone()
    if request.method=='POST':
      try:
       numero=(request.form.get('numero') or '').strip();tim=(request.form.get('timbrado') or '').strip();motivo=(request.form.get('motivo') or '').strip();fecha=request.form.get('fecha') or datetime.date.today().isoformat()
       if not numero or not motivo:raise ValueError('Número de Nota de Crédito y motivo son obligatorios.')
       if c.execute('select 1 from notas_credito_compras where numero=? and compra_id=?',(numero,compra_id)).fetchone():raise ValueError('Esta Nota de Crédito ya fue registrada para la compra.')
       sel=[];total=0
       for it in items:
        q=float(request.form.get(f'qty_{it["id"]}') or 0);restante=max(0,float(it['cantidad'] or 0)-usados.get(it['id'],0))
        if q<0 or q>restante+0.000001:raise ValueError(f'Cantidad inválida para {it["nombre"] or "producto"}. Disponible para acreditar: {restante:g}.')
        if q>0:
         t=q*float(it['costo'] or 0);total+=t;sel.append((it,q,t))
       if not sel:raise ValueError('Seleccione al menos un producto.')
       cur=c.execute("insert into notas_credito_compras(compra_id,fecha,numero,timbrado,motivo,total,aplicado_cxp,saldo_credito,estado_aplicacion,stock_ajustado,creado_en,usuario) values(?,?,?,?,?,?,0,?,'PENDIENTE',1,?,?)",(compra_id,fecha,numero,tim,motivo,total,total,now(),session.get('user')));nid=cur.lastrowid
       for it,q,t in sel:
        c.execute("insert into nota_credito_compra_items(nota_id,compra_item_id,producto_id,descripcion,cantidad,costo,total,iva_pct) values(?,?,?,?,?,?,?,?)",(nid,it['id'],it['producto_id'],it['nombre'] or 'Ítem',q,it['costo'],t,it['iva_pct']))
        c.execute('update productos set stock=stock-? where id=?',(q,it['producto_id']));c.execute("insert into stock_mov(fecha,producto_id,tipo,cantidad,costo_pyg,origen_tipo,origen_id) values(?,?,?,?,?,'NC_COMPRA',?)",(fecha,it['producto_id'],'SALIDA',-q,float(it['costo'] or 0)*float(co['tipo_cambio'] or 1),nid))
       _contabilizar_nc_compra(c,nid)
       aplicado=0
       if request.form.get('aplicar_cxp')=='1':
        try:aplicado=_aplicar_nc_a_cxp(c,nid,total)
        except ValueError as e:
         # La NC sigue válida y queda como crédito si no existe saldo a pagar.
         flash(str(e))
       c.commit();audit('NC_COMPRA',f'NC {nid} compra {compra_id}; aplicada CxP {aplicado}')
       flash(f'Nota de Crédito registrada. Aplicado a CxP: {aplicado:,.0f}. Saldo de crédito disponible: {max(0,total-aplicado):,.0f}.')
       c.close();return redirect(f'/compras/{compra_id}/ver')
      except Exception as e:c.rollback();flash('No se pudo registrar/aplicar la Nota de Crédito: '+str(e))
    c.close();return render_template('credit_note_purchase.html',co=co,items=items,usados=usados,cxp=cxp)

@app.post('/notas-credito/compras/<int:nid>/aplicar')
def nota_credito_compra_aplicar(nid):
    c=db();n=c.execute('select * from notas_credito_compras where id=?',(nid,)).fetchone()
    if not n:c.close();flash('Nota de Crédito no encontrada.');return redirect('/notas-credito')
    try:
        _contabilizar_nc_compra(c,nid)
        solicitado=float(request.form.get('importe') or n['saldo_credito'] or 0);ap=_aplicar_nc_a_cxp(c,nid,solicitado);c.commit();audit('APLICAR_NC_COMPRA',f'NC {nid}; importe {ap}');flash(f'Nota de Crédito aplicada correctamente por {ap:,.0f}.')
    except Exception as e:c.rollback();flash('No se pudo aplicar la Nota de Crédito: '+str(e))
    finally:c.close()
    return redirect(request.form.get('volver') or '/notas-credito')

def _pdf_money(v):
    try:return f"{float(v or 0):,.0f}".replace(',', '.')
    except:return '0'

def _pdf_doc_response(story, filename):
    from io import BytesIO
    from flask import send_file
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.platypus import SimpleDocTemplate
    b=BytesIO();doc=SimpleDocTemplate(b,pagesize=A4,rightMargin=10*mm,leftMargin=10*mm,topMargin=8*mm,bottomMargin=8*mm)
    doc.build(story);b.seek(0)
    return send_file(b,mimetype='application/pdf',as_attachment=False,download_name=filename)

@app.get('/notas-credito/ventas/<int:nid>/pdf')
def nota_credito_venta_pdf(nid):
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph,Spacer,Table,TableStyle,PageBreak
    c=db();n=c.execute("select n.*,v.numero factura,v.cdc factura_cdc,t.nombre cliente,t.ruc from notas_credito_ventas n join ventas v on v.id=n.venta_id left join terceros t on t.id=v.cliente_id where n.id=?",(nid,)).fetchone();
    if not n:c.close();return ('Nota de Crédito no encontrada',404)
    items=c.execute("select i.*,p.codigo from nota_credito_venta_items i left join productos p on p.id=i.producto_id where i.nota_id=? order by i.id",(nid,)).fetchall();inst=c.execute('select * from institucion_config where id=1').fetchone();c.close()
    st=getSampleStyleSheet();small=ParagraphStyle('NCItem',parent=st['Normal'],fontSize=7,leading=9,wordWrap='CJK');story=[]
    _kude_header(story,inst,'NOTA DE CRÉDITO ELECTRÓNICA',n['numero'],'KuDE de Nota de Crédito Electrónica')
    info=[[Paragraph('<b>Cliente:</b> '+str(n['cliente'] or '-'),st['Normal']),Paragraph('<b>RUC/CI:</b> '+str(n['ruc'] or '-'),st['Normal'])],[Paragraph('<b>Fecha:</b> '+str(n['fecha']),st['Normal']),Paragraph('<b>Factura relacionada:</b> '+str(n['factura'] or '-'),st['Normal'])],[Paragraph('<b>Motivo:</b> '+str(n['motivo'] or '-'),st['Normal']),Paragraph('<b>Estado SIFEN:</b> '+str(n['estado_sifen'] or 'PENDIENTE_ENVIO'),st['Normal'])]]
    t=Table(info,colWidths=[93*mm,93*mm]);t.setStyle(TableStyle([('BOX',(0,0),(-1,-1),.7,colors.black),('INNERGRID',(0,0),(-1,-1),.25,colors.grey),('VALIGN',(0,0),(-1,-1),'TOP'),('PADDING',(0,0),(-1,-1),5)]));story += [t,Spacer(1,3*mm)]
    data=[['Código','Descripción completa','Cantidad','Precio','IVA','Total']]
    for x in items:data.append([x['codigo'] or '',Paragraph(str(x['descripcion'] or ''),small),str(x['cantidad'] or 0),_pdf_money(x['precio']),str(x['iva_pct'] or 0)+'%',_pdf_money(x['total'])])
    t=Table(data,colWidths=[22*mm,78*mm,20*mm,24*mm,15*mm,27*mm],repeatRows=1);t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e9eef3')),('GRID',(0,0),(-1,-1),.4,colors.black),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),7),('VALIGN',(0,0),(-1,-1),'TOP'),('ALIGN',(2,1),(-1,-1),'RIGHT'),('PADDING',(0,0),(-1,-1),4)]));story += [t,Spacer(1,3*mm),Paragraph('<b>TOTAL NOTA DE CRÉDITO: Gs. '+_pdf_money(n['total'])+'</b>',st['Heading3'])]
    if n['cdc']:story += [Paragraph('<b>CDC:</b> '+str(n['cdc']),small)]
    _kude_footer(story,inst,n['cdc'] if 'cdc' in n.keys() else None,None,False)
    return _pdf_doc_response(story,'NC-'+str(n['numero'])+'.pdf')

@app.get('/notas-credito/compras/<int:nid>/pdf')
def nota_credito_compra_pdf(nid):
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph,Spacer,Table,TableStyle
    c=db();n=c.execute("select n.*,co.numero compra,t.nombre proveedor,t.ruc from notas_credito_compras n join compras co on co.id=n.compra_id left join terceros t on t.id=co.proveedor_id where n.id=?",(nid,)).fetchone()
    if not n:c.close();return ('Nota de Crédito de compra no encontrada',404)
    items=c.execute("select i.*,p.codigo from nota_credito_compra_items i left join productos p on p.id=i.producto_id where i.nota_id=? order by i.id",(nid,)).fetchall();inst=c.execute('select * from institucion_config where id=1').fetchone();c.close()
    st=getSampleStyleSheet();small=ParagraphStyle('NCCItem',parent=st['Normal'],fontSize=7,leading=9,wordWrap='CJK');story=[]
    _kude_header(story,inst,'NOTA DE CRÉDITO DE COMPRA',n['numero'],'Registro de Nota de Crédito recibida')
    info=[[Paragraph('<b>Proveedor:</b> '+str(n['proveedor'] or '-'),st['Normal']),Paragraph('<b>RUC:</b> '+str(n['ruc'] or '-'),st['Normal'])],[Paragraph('<b>Fecha:</b> '+str(n['fecha']),st['Normal']),Paragraph('<b>Compra relacionada:</b> '+str(n['compra'] or '-'),st['Normal'])],[Paragraph('<b>Timbrado:</b> '+str(n['timbrado'] or '-'),st['Normal']),Paragraph('<b>Motivo:</b> '+str(n['motivo'] or '-'),st['Normal'])]]
    t=Table(info,colWidths=[93*mm,93*mm]);t.setStyle(TableStyle([('BOX',(0,0),(-1,-1),.7,colors.black),('INNERGRID',(0,0),(-1,-1),.25,colors.grey),('VALIGN',(0,0),(-1,-1),'TOP'),('PADDING',(0,0),(-1,-1),5)]));story += [t,Spacer(1,3*mm)]
    data=[['Código','Descripción completa','Cantidad','Costo','IVA','Total']]
    for x in items:data.append([x['codigo'] or '',Paragraph(str(x['descripcion'] or ''),small),str(x['cantidad'] or 0),_pdf_money(x['costo']),str(x['iva_pct'] or 0)+'%',_pdf_money(x['total'])])
    t=Table(data,colWidths=[22*mm,78*mm,20*mm,24*mm,15*mm,27*mm],repeatRows=1);t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e9eef3')),('GRID',(0,0),(-1,-1),.4,colors.black),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),7),('VALIGN',(0,0),(-1,-1),'TOP'),('ALIGN',(2,1),(-1,-1),'RIGHT'),('PADDING',(0,0),(-1,-1),4)]));story += [t,Spacer(1,3*mm),Paragraph('<b>TOTAL NOTA DE CRÉDITO: Gs. '+_pdf_money(n['total'])+'</b>',st['Heading3'])]
    _kude_footer(story,inst,None,None,False)
    return _pdf_doc_response(story,'NC-COMPRA-'+str(n['numero'])+'.pdf')

@app.get('/sifen/monitor')
def sifen_monitor():
    c=db(); estado=(request.args.get('estado') or '').strip().upper(); q=(request.args.get('q') or '').strip(); tipo=(request.args.get('tipo') or '').strip().upper(); fecha=(request.args.get('fecha') or '').strip()
    docs=[]
    def add_doc(r,tipo_doc,tipo_codigo,edit_url,view_url,retry_url):
        d=dict(r); d.update(tipo_doc=tipo_doc,tipo_codigo=tipo_codigo,edit_url=edit_url,view_url=view_url,retry_url=retry_url); docs.append(d)
    wr=[];args=[]
    if estado: wr.append("upper(coalesce(v.estado_sifen,'NO_ENVIADO'))=?");args.append(estado)
    if fecha: wr.append("substr(coalesce(v.fecha,''),1,10)=?");args.append(fecha)
    if q: wr.append("(v.numero like ? or coalesce(v.cdc,'') like ? or coalesce(t.nombre,'') like ? or coalesce(v.sifen_mensaje_error,'') like ?)");args += ['%'+q+'%']*4
    if tipo in ('','FE'):
        sql="select v.id,v.numero,v.fecha,v.cdc,v.estado_sifen,v.sifen_intentos,v.sifen_ultimo_intento,v.sifen_codigo_error,v.sifen_mensaje_error,t.nombre cliente,coalesce(v.sifen_lote,'') lote from ventas v left join terceros t on t.id=v.cliente_id"
        if wr: sql+=' where '+' and '.join(wr)
        for r in c.execute(sql+' order by v.id desc limit 500',args).fetchall(): add_doc(r,'Factura electrónica','01',f'/sifen/monitor/FE/{r["id"]}/corregir',f'/ventas/{r["id"]}/factura',f'/sifen/monitor/venta/{r["id"]}/reintentar')
    for tab,label,code,key,pdf,retry in [('notas_credito_ventas','Nota de Crédito','05','NCE','/notas-credito/ventas/{}/pdf','/sifen/monitor/nc/{}/reintentar'),('notas_debito_ventas','Nota de Débito','06','NDE','/notas-debito/ventas/{}/pdf','/sifen/monitor/nd/{}/reintentar')]:
        if tipo not in ('',key): continue
        cols={x['name'] for x in c.execute('pragma table_info('+tab+')').fetchall()}
        ec="coalesce(n.sifen_codigo_error,'')" if 'sifen_codigo_error' in cols else "''"; em="coalesce(n.sifen_mensaje_error,'')" if 'sifen_mensaje_error' in cols else "''"; si="coalesce(n.sifen_intentos,0)" if 'sifen_intentos' in cols else '0'; ul="coalesce(n.sifen_ultimo_intento,'')" if 'sifen_ultimo_intento' in cols else "''"
        sql=f"select n.id,n.numero,n.fecha,n.cdc,n.estado_sifen,{si} sifen_intentos,{ul} sifen_ultimo_intento,{ec} sifen_codigo_error,{em} sifen_mensaje_error,t.nombre cliente,coalesce(n.sifen_lote,'') lote from {tab} n join ventas v on v.id=n.venta_id left join terceros t on t.id=v.cliente_id where 1=1"; a=[]
        if estado: sql+=" and upper(coalesce(n.estado_sifen,'NO_ENVIADO'))=?";a.append(estado)
        if fecha: sql+=" and substr(coalesce(n.fecha,''),1,10)=?";a.append(fecha)
        if q: sql+=f" and (n.numero like ? or coalesce(n.cdc,'') like ? or coalesce(t.nombre,'') like ? or {em} like ?)";a += ['%'+q+'%']*4
        for r in c.execute(sql+' order by n.id desc limit 300',a).fetchall(): add_doc(r,label,code,f'/sifen/monitor/{key}/{r["id"]}/corregir',pdf.format(r['id']),retry.format(r['id']))
    docs.sort(key=lambda x:(str(x.get('fecha') or ''),int(x.get('id') or 0)),reverse=True); c.close()
    return render_template('sifen_monitor.html',docs=docs,estado=estado,q=q,tipo=tipo,fecha=fecha)

@app.route('/sifen/monitor/<tipo>/<int:doc_id>/corregir',methods=['GET','POST'])
def sifen_corregir_documento(tipo,doc_id):
    tipo=tipo.upper(); tablas={'FE':'ventas','NCE':'notas_credito_ventas','NDE':'notas_debito_ventas'}
    if tipo not in tablas:return ('Tipo no válido',400)
    c=db(); tab=tablas[tipo]
    if tipo=='FE': doc=c.execute("select v.*,t.nombre cliente,t.ruc cliente_ruc from ventas v left join terceros t on t.id=v.cliente_id where v.id=?",(doc_id,)).fetchone()
    else: doc=c.execute(f"select n.*,v.cliente_id,t.nombre cliente,t.ruc cliente_ruc from {tab} n join ventas v on v.id=n.venta_id left join terceros t on t.id=v.cliente_id where n.id=?",(doc_id,)).fetchone()
    if not doc:c.close();return ('Documento no encontrado',404)
    if request.method=='POST':
        try:
            # Datos del receptor sí pueden corregirse localmente. Número/CDC/totales no se alteran desde este monitor.
            cliente_id=doc['cliente_id']; nombre=(request.form.get('cliente') or '').strip(); ruc=(request.form.get('ruc') or '').strip()
            if cliente_id and (nombre or ruc): c.execute('update terceros set nombre=coalesce(nullif(?,\'\'),nombre),ruc=coalesce(nullif(?,\'\'),ruc) where id=?',(nombre,ruc,cliente_id))
            cols={x['name'] for x in c.execute('pragma table_info('+tab+')').fetchall()}
            sets=[];vals=[]
            for fld in ('sifen_codigo_error','sifen_mensaje_error'):
                if fld in cols: sets.append(fld+'=?');vals.append('')
            if 'estado_sifen' in cols: sets.append("estado_sifen='PENDIENTE_REENVIO'")
            if sets: c.execute('update '+tab+' set '+','.join(sets)+' where id=?',vals+[doc_id])
            c.execute('insert into sifen_eventos(fecha,tipo,estado,detalle) values(?,?,?,?)',(now(),tipo+'_CORRECCION','PENDIENTE_REENVIO',f'{tipo} {doc["numero"]}: corrección local de receptor por {session.get("user") or "usuario"}; CDC/número/importe preservados'))
            c.commit(); flash('Corrección guardada. El documento quedó PENDIENTE_REENVIO. Debe regenerarse/firmarse/transmitirse con el transmisor SIFEN real antes de considerarlo aceptado.'); c.close(); return redirect('/sifen/monitor')
        except Exception as e:c.rollback();flash(str(e))
    c.close(); return render_template('sifen_correct_document.html',doc=doc,tipo=tipo)

def init_v139113_sifen_test_transmision_real():
    c=db()
    # Versiones previas podían mostrar RECHAZADO aunque nunca hubiera existido
    # intento ni respuesta SOAP. Esos casos se reclasifican sin tocar el DE.
    c.execute("""update ventas set estado_sifen='NO_ENVIADO',sifen_mensaje_error='Documento generado anteriormente sin transmisión a SIFEN. Use Reintentar para enviarlo al ambiente configurado.'
                 where upper(coalesce(estado_sifen,''))='RECHAZADO'
                   and coalesce(sifen_intentos,0)=0
                   and coalesce(respuesta_sifen,'')=''""")
    c.execute("insert or ignore into schema_migrations(version,aplicado_en) values('13.9.113-sifen-test-transmision-real',?)",(now(),))
    c.commit();c.close()
init_v139113_sifen_test_transmision_real()

def init_v139114_sifen_lotes():
    c=db()
    c.execute("insert or ignore into schema_migrations(version,aplicado_en) values('13.9.114-sifen-lote-asincrono',?)",(now(),))
    c.commit();c.close()
init_v139114_sifen_lotes()



# ===== V13.9.129: auditoría matemática y XML exacto enviado a SIFEN =====
def _sifen_ultimo_xml_factura(venta_id):
    p=Path(_sifen_dir())/'xml_test'
    candidatos=sorted(p.glob('FE_'+str(venta_id)+'_*.xml'), key=lambda x:x.stat().st_mtime, reverse=True) if p.exists() else []
    return candidatos[0] if candidatos else None

def _sifen_diagnostico_matematico_xml(xml_bytes):
    from lxml import etree
    from decimal import Decimal, InvalidOperation
    NS='http://ekuatia.set.gov.py/sifen/xsd'
    root=etree.fromstring(xml_bytes if isinstance(xml_bytes,(bytes,bytearray)) else xml_bytes.encode('utf-8'))
    de=root.find('{%s}DE'%NS)
    if de is None: raise ValueError('XML sin DE.')
    def dec(txt):
        try:return Decimal(str(txt or '0'))
        except InvalidOperation:return Decimal('0')
    filas=[]; sum_total=Decimal('0'); sum5=sum10=Decimal('0'); b5=b10=Decimal('0')
    for n,it in enumerate(de.findall('.//{%s}gCamItem'%NS),1):
        def ft(path): return it.findtext(path) or '0'
        q=dec(ft('{%s}dCantProSer'%NS)); pu=dec(ft('{%s}gValorItem/{%s}dPUniProSer'%(NS,NS)))
        bruto=dec(ft('{%s}gValorItem/{%s}dTotBruOpeItem'%(NS,NS)))
        ope=dec(ft('{%s}gValorItem/{%s}gValorRestaItem/{%s}dTotOpeItem'%(NS,NS,NS)))
        tasa=dec(ft('{%s}gCamIVA/{%s}dTasaIVA'%(NS,NS))); prop=dec(ft('{%s}gCamIVA/{%s}dPropIVA'%(NS,NS)))
        base=dec(ft('{%s}gCamIVA/{%s}dBasGravIVA'%(NS,NS))); iva=dec(ft('{%s}gCamIVA/{%s}dLiqIVAItem'%(NS,NS)))
        exp_bruto=q*pu
        exp_base=(Decimal('100')*ope*prop)/(Decimal('10000')+(tasa*prop)) if tasa>0 else Decimal('0')
        exp_iva=base*(tasa/Decimal('100')) if tasa>0 else Decimal('0')
        filas.append({'item':n,'cantidad':str(q),'precio':str(pu),'bruto_xml':str(bruto),'bruto_calc':str(exp_bruto),'dif_bruto':str(bruto-exp_bruto),'total_item':str(ope),'tasa':str(tasa),'prop':str(prop),'base_xml':str(base),'base_calc':str(exp_base),'dif_base':str(base-exp_base),'iva_xml':str(iva),'iva_calc':str(exp_iva),'dif_iva':str(iva-exp_iva)})
        sum_total+=ope
        if tasa==5: sum5+=iva;b5+=base
        elif tasa==10: sum10+=iva;b10+=base
    gt=de.find('.//{%s}gTotSub'%NS)
    def g(name): return dec(gt.findtext('{%s}%s'%(NS,name)) if gt is not None else '0')
    tot={'dTotOpe':str(g('dTotOpe')),'calc_dTotOpe':str(sum_total),'dIVA5':str(g('dIVA5')),'calc_dIVA5':str(sum5),'dIVA10':str(g('dIVA10')),'calc_dIVA10':str(sum10),'dTotIVA':str(g('dTotIVA')),'calc_dTotIVA':str(sum5+sum10),'dBaseGrav5':str(g('dBaseGrav5')),'calc_dBaseGrav5':str(b5),'dBaseGrav10':str(g('dBaseGrav10')),'calc_dBaseGrav10':str(b10),'dTBasGraIVA':str(g('dTBasGraIVA')),'calc_dTBasGraIVA':str(b5+b10),'dTotGralOpe':str(g('dTotGralOpe'))}
    return filas,tot

@app.get('/ventas/<int:venta_id>/sifen/xml-enviado')
def sifen_descargar_xml_enviado(venta_id):
    f=_sifen_ultimo_xml_factura(venta_id)
    if not f:return ('No existe XML firmado guardado para esta factura.',404)
    return send_file(str(f),as_attachment=True,download_name=f.name,mimetype='application/xml')

@app.get('/ventas/<int:venta_id>/sifen/diagnostico-calculo')
def sifen_diagnostico_calculo(venta_id):
    f=_sifen_ultimo_xml_factura(venta_id)
    if not f:return ('No existe XML firmado guardado para esta factura.',404)
    filas,tot=_sifen_diagnostico_matematico_xml(f.read_bytes())
    return render_template('sifen_math_diagnostic.html',venta_id=venta_id,archivo=f.name,filas=filas,tot=tot)

@app.post('/sifen/monitor/venta/<int:venta_id>/consultar-lote')
def sifen_consultar_lote_venta(venta_id):
    c=db();v=c.execute('select * from ventas where id=?',(venta_id,)).fetchone();cfg=c.execute('select * from sifen_config where id=1').fetchone()
    if not v:c.close();return ('Factura no encontrada',404)
    protocolo=str((v['protocolo_sifen'] if 'protocolo_sifen' in v.keys() else '') or (v['sifen_lote'] if 'sifen_lote' in v.keys() else '') or '').strip()
    try:
        status,resp,url=_sifen_consultar_lote(protocolo,cfg);parsed=_sifen_parse_respuesta(resp)
        estado=str(parsed.get('estado') or 'RESPUESTA_RECIBIDA').upper()
        # 0361 significa que SIFEN todavía procesa el lote; no es rechazo.
        if str(parsed.get('codigo_lote') or parsed.get('codigo') or '')=='0361': estado='LOTE_PROCESANDO'
        # Cuando concluye, tomar específicamente el resultado del CDC de esta factura.
        if parsed.get('resultados'):
            match=next((x for x in parsed['resultados'] if str(x.get('cdc') or '')==str(v['cdc'] or '')),parsed['resultados'][0])
            estado=str(match.get('estado') or estado).upper();parsed['codigo']=match.get('codigo','');parsed['mensaje']=match.get('mensaje','');parsed['protocolo']=protocolo;parsed['lote']=protocolo
        else:
            parsed['protocolo']=protocolo;parsed['lote']=protocolo
        _sifen_guardar_respuesta_venta(c,venta_id,status,resp,parsed,estado,v['cdc'],v['qr_sifen'])
        c.execute('insert into sifen_eventos(fecha,tipo,estado,detalle) values(?,?,?,?)',(now(),'FE_CONSULTA_LOTE',estado,f'Factura {venta_id} · lote {protocolo} · HTTP {status} · {parsed.get("codigo","")} {parsed.get("mensaje","")}'))
        c.commit();flash('Consulta de lote procesada. Estado: '+estado+'.')
    except Exception as ex:
        c.rollback();flash('No se pudo consultar el lote SIFEN: '+str(ex))
    finally:c.close()
    return redirect(f'/ventas/{venta_id}/sifen/detalle')

@app.post('/sifen/monitor/venta/<int:venta_id>/reintentar')
def sifen_reintentar_venta(venta_id):
    c=db();v=c.execute('select id,numero,estado_sifen from ventas where id=?',(venta_id,)).fetchone();c.close()
    if not v:return ('Factura no encontrada',404)
    try:
        estado=_sifen_emitir_factura_automatico(venta_id)
        flash('SIFEN procesó el envío por lote. Estado recibido: '+str(estado)+'. Si figura LOTE_RECIBIDO, consulte el resultado del lote desde el detalle SIFEN.')
    except Exception as ex:
        flash('No se obtuvo una respuesta aprobada/rechazada de SIFEN. Error de envío: '+str(ex))
    return redirect(f'/ventas/{venta_id}/sifen/detalle')

@app.post('/sifen/monitor/nd/<int:nid>/reintentar')
def sifen_reintentar_nd(nid):
    c=db();n=c.execute('select * from notas_debito_ventas where id=?',(nid,)).fetchone()
    if not n:c.close();return ('Nota de Débito no encontrada',404)
    c.execute("update notas_debito_ventas set estado_sifen='PENDIENTE_REENVIO',sifen_intentos=coalesce(sifen_intentos,0)+1,sifen_ultimo_intento=? where id=?",(now(),nid))
    c.execute('insert into sifen_eventos(fecha,tipo,estado,detalle) values(?,?,?,?)',(now(),'NDE_REENVIO','PENDIENTE_REENVIO',f'NDE {n["numero"]}: reenvío solicitado; pendiente de transmisor XML/firma/WS SIFEN'))
    c.commit();c.close();flash('Nota de Débito colocada en PENDIENTE_REENVIO.');return redirect('/sifen/monitor')


# ===== V13.9.52: Centro de Notas de Crédito + diagnóstico SIFEN =====
@app.get('/notas-credito')
def notas_credito_centro():
    c=db()
    ventas=c.execute("""select n.*,v.numero factura,t.nombre cliente
      from notas_credito_ventas n join ventas v on v.id=n.venta_id
      left join terceros t on t.id=v.cliente_id order by n.id desc limit 500""").fetchall()
    compras=c.execute("""select n.*,co.numero compra,t.nombre proveedor
      from notas_credito_compras n join compras co on co.id=n.compra_id
      left join terceros t on t.id=co.proveedor_id order by n.id desc limit 500""").fetchall()
    c.close()
    return render_template('credit_notes_center.html',ventas=ventas,compras=compras)

@app.post('/sifen/monitor/nc/<int:nid>/reintentar')
def sifen_reintentar_nc(nid):
    c=db(); n=c.execute('select * from notas_credito_ventas where id=?',(nid,)).fetchone()
    if not n: c.close(); return ('Nota de Crédito no encontrada',404)
    # No simular transmisión: la versión actual aún no contiene generador XML NCE + firma + WS SIFEN.
    c.execute("update notas_credito_ventas set estado_sifen='PENDIENTE_ENVIO' where id=?",(nid,))
    c.execute("insert into sifen_eventos(fecha,tipo,estado,detalle) values(?,?,?,?)",
              (now(),'NCE_REENVIO','PENDIENTE_ENVIO',f'NC {n["numero"]}: reenvío solicitado; pendiente del transmisor XML/firma/WS SIFEN'))
    c.commit(); c.close()
    flash('La Nota de Crédito quedó en cola. Aún no se transmite hasta activar el transmisor XML/firma/WS SIFEN.')
    return redirect('/sifen/monitor')

@app.get('/diagnostico/sistema')
def diagnostico_sistema():
    c=db(); checks=[]
    for tabla in ('ventas','venta_items','compras','compra_items','notas_credito_ventas','notas_credito_compras','sifen_puntos_expedicion','sifen_eventos'):
        try:
            n=c.execute('select count(*) from '+tabla).fetchone()[0]; checks.append((tabla,'OK',n))
        except Exception as e: checks.append((tabla,'ERROR',str(e)))
    try:
        dup=c.execute("select numero,count(*) n from ventas where coalesce(numero,'')<>'' group by numero having count(*)>1").fetchall()
    except Exception as e: dup=[]; checks.append(('correlatividad','ERROR',str(e)))
    c.close()
    return render_template('system_diagnostics.html',checks=checks,duplicados=dup)

ROUTE_MODULE.update({'notas_credito_centro':'FACTURACION','sifen_reintentar_nc':'FACTURACION','diagnostico_sistema':'CONFIG_SANATORIO','nota_credito_venta':'FACTURACION','anular_factura_venta':'FACTURACION','nota_credito_compra':'COMPRAS','sifen_monitor':'FACTURACION','sifen_reintentar_venta':'FACTURACION','nota_credito_venta_pdf':'FACTURACION','nota_credito_compra_pdf':'COMPRAS','nota_credito_compra_aplicar':'COMPRAS'})

# ===== V13.9.53: Tesorería integrada, anticipos y contabilización por cuenta financiera =====
def init_v13953_tesoreria_integrada():
    c=db()
    def addcol(tabla,col,defn):
        cols=[r['name'] for r in c.execute(f'pragma table_info({tabla})').fetchall()]
        if col not in cols:c.execute(f'alter table {tabla} add column {col} {defn}')
    addcol('cuentas_bancarias','cuenta_contable','TEXT')
    for tabla,col,defn in [('rrhh_novedades','cuenta_bancaria_id','INTEGER'),('rrhh_novedades','medio_pago','TEXT'),('rrhh_novedades','asiento_id','INTEGER'),('rrhh_novedades','movimiento_financiero_id','INTEGER'),('pagos_proveedores','cuenta_bancaria_id','INTEGER')]:addcol(tabla,col,defn)
    c.execute("""CREATE TABLE IF NOT EXISTS anticipos_terceros(id INTEGER PRIMARY KEY,fecha TEXT NOT NULL,tipo TEXT NOT NULL,tercero_id INTEGER NOT NULL,moneda TEXT DEFAULT 'PYG',tipo_cambio REAL DEFAULT 1,importe REAL NOT NULL,importe_pyg REAL NOT NULL,medio TEXT NOT NULL,cuenta_bancaria_id INTEGER,referencia TEXT,concepto TEXT,cuenta_anticipo TEXT NOT NULL,cuenta_financiera TEXT NOT NULL,asiento_id INTEGER,movimiento_financiero_id INTEGER,saldo REAL NOT NULL,estado TEXT DEFAULT 'DISPONIBLE',creado_por TEXT,creado_en TEXT)""")
    c.execute("""CREATE TABLE IF NOT EXISTS tesoreria_config(id INTEGER PRIMARY KEY CHECK(id=1),cuenta_caja TEXT DEFAULT '1.1.01',cuenta_clientes TEXT DEFAULT '1.1.02',cuenta_proveedores TEXT DEFAULT '2.1.01',cuenta_anticipo_clientes TEXT DEFAULT '2.1.07',cuenta_anticipo_proveedores TEXT DEFAULT '1.1.06',cuenta_anticipo_personal TEXT DEFAULT '1.1.05')""")
    c.execute('insert or ignore into tesoreria_config(id) values(1)')
    for x in [('1.1.06','Anticipos a Proveedores','ACTIVO'),('2.1.07','Anticipos de Clientes','PASIVO')]:c.execute('insert or ignore into plan_cuentas(codigo,nombre,tipo) values(?,?,?)',x)
    c.execute("insert or ignore into schema_migrations(version,aplicado_en) values('13.9.53-tesoreria-integrada',?)",(now(),));c.commit();c.close()
init_v13953_tesoreria_integrada()

def _cuenta_financiera(c,medio,cuenta_id=None):
    if str(medio or '').upper()=='EFECTIVO':
        x=c.execute('select cuenta_caja from tesoreria_config where id=1').fetchone();return (x['cuenta_caja'] if x else '1.1.01'),None
    if not cuenta_id:raise ValueError('Debe seleccionar la cuenta bancaria de origen/destino.')
    b=c.execute('select * from cuentas_bancarias where id=? and activo=1',(int(cuenta_id),)).fetchone()
    if not b:raise ValueError('Cuenta bancaria no encontrada o inactiva.')
    if not b['cuenta_contable']:raise ValueError('La cuenta bancaria no tiene una cuenta contable vinculada. Configure Finanzas → Cuentas Bancarias.')
    return b['cuenta_contable'],b

@app.route('/finanzas/anticipos',methods=['GET','POST'])
def anticipos_financieros():
    c=db()
    if request.method=='POST':
        try:
            f=request.form;tipo=f.get('tipo');tid=int(f['tercero_id']);imp=float(f.get('importe') or 0)
            if tipo not in ('CLIENTE','PROVEEDOR') or imp<=0:raise ValueError('Tipo o importe de anticipo inválido.')
            t=c.execute('select * from terceros where id=?',(tid,)).fetchone()
            if not t:raise ValueError('Cliente/proveedor no encontrado.')
            fecha=f.get('fecha') or datetime.date.today().isoformat();mon=f.get('moneda') or 'PYG';tc=tc_fecha(c,fecha,mon,f.get('tipo_cambio'));pyg=round(imp*tc,2);medio=f.get('medio') or 'EFECTIVO';cuenta_id=int(f.get('cuenta_bancaria_id') or 0) or None
            cta_fin,_=_cuenta_financiera(c,medio,cuenta_id);cfg=c.execute('select * from tesoreria_config where id=1').fetchone();cta_ant=cfg['cuenta_anticipo_clientes'] if tipo=='CLIENTE' else cfg['cuenta_anticipo_proveedores']
            if tipo=='CLIENTE':lineas=[(cta_fin,pyg,0,imp,'Ingreso de anticipo'),(cta_ant,0,pyg,imp,'Anticipo recibido de cliente')];movtipo='INGRESO'
            else:lineas=[(cta_ant,pyg,0,imp,'Anticipo entregado a proveedor'),(cta_fin,0,pyg,imp,'Salida de anticipo')];movtipo='EGRESO'
            cur=c.execute('insert into anticipos_terceros(fecha,tipo,tercero_id,moneda,tipo_cambio,importe,importe_pyg,medio,cuenta_bancaria_id,referencia,concepto,cuenta_anticipo,cuenta_financiera,saldo,creado_por,creado_en) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',(fecha,tipo,tid,mon,tc,imp,pyg,medio,cuenta_id,f.get('referencia'),f.get('concepto'),cta_ant,cta_fin,imp,session.get('user'),now()));aid=cur.lastrowid
            asi=asiento(c,fecha,f'Anticipo {tipo.lower()} - {t["nombre"]}',f'ANTICIPO_{tipo}',aid,mon,tc,lineas)
            m=c.execute('insert into caja_banco(fecha,tipo,medio,moneda,tipo_cambio,importe,importe_pyg,concepto,origen_tipo,origen_id,cuenta_bancaria_id) values(?,?,?,?,?,?,?,?,?,?,?)',(fecha,movtipo,medio,mon,tc,imp,pyg,f'Anticipo {tipo.lower()} - {t["nombre"]}',f'ANTICIPO_{tipo}',aid,cuenta_id)).lastrowid
            c.execute('update anticipos_terceros set asiento_id=?,movimiento_financiero_id=? where id=?',(asi,m,aid));c.commit();audit('ANTICIPO_'+tipo,f'{aid} / {t["nombre"]} / {imp} {mon}');flash('Anticipo registrado, movimiento financiero y asiento contable generados.')
        except Exception as ex:c.rollback();flash(str(ex))
        c.close();return redirect('/finanzas/anticipos')
    ters=c.execute("select * from terceros where tipo in ('CLIENTE','PROVEEDOR','AMBOS') order by nombre").fetchall();bancos=c.execute('select * from cuentas_bancarias where activo=1 order by banco,alias').fetchall();rows=c.execute('select a.*,t.nombre tercero,b.banco,b.alias from anticipos_terceros a join terceros t on t.id=a.tercero_id left join cuentas_bancarias b on b.id=a.cuenta_bancaria_id order by a.id desc limit 200').fetchall();c.close();return render_template('treasury_advances.html',ters=ters,bancos=bancos,rows=rows)

ROUTE_MODULE.update({'anticipos_financieros':'FINANZAS'})


# ===== V13.9.56: Visaciones obligatorias para toda prestación por seguro =====
VISACIONES_DIR=os.path.join(DATA_DIR,'visaciones')
os.makedirs(VISACIONES_DIR,exist_ok=True)
VISACION_EXT={'pdf','jpg','jpeg','png','webp'}

def init_v13956_visaciones():
    c=db();c.execute("""CREATE TABLE IF NOT EXISTS seguro_visaciones(
      id INTEGER PRIMARY KEY,fecha TEXT NOT NULL,hora TEXT NOT NULL,numero_visacion TEXT NOT NULL,
      aseguradora_id INTEGER NOT NULL,paciente_id INTEGER,medico_id INTEGER,
      origen_tipo TEXT NOT NULL,origen_id INTEGER NOT NULL,archivo_nombre TEXT,archivo_guardado TEXT,
      archivo_tipo TEXT,observacion TEXT,creado_por TEXT,creado_en TEXT,
      UNIQUE(origen_tipo,origen_id))""")
    c.execute("CREATE INDEX IF NOT EXISTS idx_visacion_seguro ON seguro_visaciones(aseguradora_id,fecha)")
    c.execute("insert or ignore into schema_migrations(version,aplicado_en) values('13.9.56-visaciones-seguros',?)",(now(),));c.commit();c.close()
init_v13956_visaciones()

def _guardar_archivo_visacion(fileobj):
    if not fileobj or not getattr(fileobj,'filename',''):return None,None,None
    original=secure_filename(fileobj.filename)
    ext=original.rsplit('.',1)[-1].lower() if '.' in original else ''
    if ext not in VISACION_EXT:raise ValueError('La visación solo admite PDF, JPG, JPEG, PNG o WEBP.')
    nombre=secrets.token_hex(16)+'.'+ext
    fileobj.save(os.path.join(VISACIONES_DIR,nombre))
    return original,nombre,(getattr(fileobj,'mimetype',None) or '')

def _registrar_visacion(c,aseguradora_id,paciente_id,origen_tipo,origen_id,medico_id=None):
    if not aseguradora_id:return None
    numero=(request.form.get('numero_visacion') or '').strip();fecha=(request.form.get('fecha_visacion') or request.form.get('fecha') or '').strip();hora=(request.form.get('hora_visacion') or request.form.get('hora') or '').strip()
    mid=request.form.get('medico_visacion_id') or medico_id
    if not numero:raise ValueError('Para servicios por seguro debe ingresar el número de visación.')
    if not fecha:raise ValueError('Para servicios por seguro debe ingresar la fecha de visación.')
    if not hora:raise ValueError('Para servicios por seguro debe ingresar la hora de visación.')
    if not mid:raise ValueError('Para servicios por seguro debe seleccionar el médico que realiza la atención.')
    archivo=request.files.get('archivo_visacion');orig,guard,tipo=_guardar_archivo_visacion(archivo)
    cur=c.execute("""insert into seguro_visaciones(fecha,hora,numero_visacion,aseguradora_id,paciente_id,medico_id,origen_tipo,origen_id,archivo_nombre,archivo_guardado,archivo_tipo,observacion,creado_por,creado_en)
      values(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(fecha,hora,numero,int(aseguradora_id),paciente_id,int(mid),origen_tipo,int(origen_id),orig,guard,tipo,request.form.get('observacion_visacion'),session.get('user'),now()))
    return cur.lastrowid

@app.get('/seguros/visaciones')
def seguro_visaciones():
    c=db();q=(request.args.get('q') or '').strip();args=[];where='1=1'
    if q:where="(v.numero_visacion like ? or p.nombre like ? or a.nombre like ? or m.nombre like ?)";args=['%'+q+'%']*4
    rows=c.execute("""select v.*,p.nombre paciente,a.nombre aseguradora,m.nombre medico from seguro_visaciones v
      left join pacientes p on p.id=v.paciente_id left join aseguradoras a on a.id=v.aseguradora_id left join medicos m on m.id=v.medico_id
      where """+where+" order by v.fecha desc,v.hora desc,v.id desc limit 1000",args).fetchall();c.close()
    return render_template('insurance_authorizations.html',rows=rows,q=q)

@app.get('/seguros/visaciones/<int:vid>/archivo')
def seguro_visacion_archivo(vid):
    c=db();v=c.execute('select * from seguro_visaciones where id=?',(vid,)).fetchone();c.close()
    if not v or not v['archivo_guardado']:return ('Archivo no encontrado',404)
    ruta=os.path.join(VISACIONES_DIR,v['archivo_guardado'])
    if not os.path.isfile(ruta):return ('Archivo no encontrado',404)
    return send_file(ruta,as_attachment=False,download_name=v['archivo_nombre'] or v['archivo_guardado'])


@app.route('/seguros/pendiente/<int:spid>/visacion',methods=['GET','POST'])
def seguro_pendiente_visacion(spid):
    c=db();sp=c.execute("select sp.*,p.nombre paciente,a.nombre aseguradora from seguro_pendientes sp left join pacientes p on p.id=sp.paciente_id join aseguradoras a on a.id=sp.aseguradora_id where sp.id=?",(spid,)).fetchone()
    if not sp:c.close();return ('Pendiente no encontrado',404)
    if request.method=='POST':
        try:
            _registrar_visacion(c,sp['aseguradora_id'],sp['paciente_id'],'PENDIENTE_SEGURO',spid,request.form.get('medico_visacion_id'))
            c.commit();audit('VISACION_SEGURO',str(spid));flash('Visación vinculada correctamente a la prestación pendiente.')
        except Exception as ex:c.rollback();flash(str(ex))
        c.close();return redirect('/seguros/facturar')
    meds=c.execute('select * from medicos where activo=1 order by nombre').fetchall();c.close();return render_template('insurance_authorization_form.html',sp=sp,meds=meds)

ROUTE_MODULE.update({'seguro_visaciones':'FACTURACION','seguro_visacion_archivo':'FACTURACION','seguro_pendiente_visacion':'FACTURACION'})


# ===== V13.9.70 - Llamador independiente + histórico =====
def init_v13970_llamador():
 c=db()
 cols=[x['name'] for x in c.execute('pragma table_info(llamados_pacientes)').fetchall()]
 for name,typ in [('estado',"TEXT DEFAULT 'PENDIENTE'"),('dispositivo','TEXT'),('reproducido_en','TEXT'),('confirmado_en','TEXT')]:
  if name not in cols:c.execute(f'alter table llamados_pacientes add column {name} {typ}')
 c.execute("update llamados_pacientes set estado='REPRODUCIDO' where estado is null")
 c.execute("create table if not exists llamador_dispositivos(id integer primary key autoincrement,nombre text unique not null,sector text,ultimo_ping text,activo integer default 1,creado_en text)")
 c.commit();c.close()
init_v13970_llamador()

def _llamador_token_ok():
 # Si LLAMADOR_TOKEN está configurado en Render, se exige coincidencia exacta.
 # Si todavía no fue configurado, el llamador sigue operativo para no bloquear la sala de espera.
 esperado=(os.environ.get('LLAMADOR_TOKEN') or '').strip()
 recibido=(request.headers.get('X-Llamador-Token') or request.args.get('token') or '').strip()
 # El monitor web integrado usa la sesión autenticada del ERP; el dispositivo
 # Windows externo continúa usando LLAMADOR_TOKEN.
 if session.get('user'):
  return True
 if not esperado:
  return True
 return bool(recibido) and secrets.compare_digest(esperado,recibido)

@app.get('/api/llamador/ping')
def llamador_api_ping():
 if not _llamador_token_ok():return jsonify(ok=False,error='Token de llamador inválido'),401
 nombre=(request.args.get('dispositivo') or 'LLAMADOR-PRINCIPAL').strip()[:80];sector=(request.args.get('sector') or 'Sala de espera').strip()[:80]
 c=db();c.execute("insert into llamador_dispositivos(nombre,sector,ultimo_ping,activo,creado_en) values(?,?,?,1,?) on conflict(nombre) do update set sector=excluded.sector,ultimo_ping=excluded.ultimo_ping,activo=1",(nombre,sector,now(),now()));c.commit();c.close();return jsonify(ok=True)

@app.get('/api/llamador/pendientes')
def llamador_api_pendientes():
 if not _llamador_token_ok():return jsonify(ok=False,error='Token de llamador inválido'),401
 dispositivo=(request.args.get('dispositivo') or 'LLAMADOR-PRINCIPAL').strip()[:80]
 c=db()
 # Recupera también llamadas ENTREGADAS que no fueron confirmadas. Esto evita que una
 # caída/cierre del monitor después de leer una llamada la deje perdida para siempre.
 r=c.execute("""select l.id,l.fecha_hora,l.texto,p.nombre paciente,m.nombre medico,m.consultorio_numero
 from llamados_pacientes l join agenda g on g.id=l.agenda_id join pacientes p on p.id=g.paciente_id join medicos m on m.id=l.medico_id
 where coalesce(l.estado,'PENDIENTE') in ('PENDIENTE','ENTREGADO') order by l.id limit 1""").fetchone()
 if r:
  c.execute("update llamados_pacientes set estado='ENTREGADO',dispositivo=? where id=?",(dispositivo,r['id']));c.commit()
 c.close();return jsonify(ok=True,llamada=dict(r) if r else None)

@app.post('/api/llamador/<int:lid>/confirmar')
def llamador_api_confirmar(lid):
 if not _llamador_token_ok():return jsonify(ok=False,error='Token de llamador inválido'),401
 data=request.get_json(silent=True) or {};disp=str(data.get('dispositivo') or 'LLAMADOR-PRINCIPAL')[:80]
 c=db();c.execute("update llamados_pacientes set estado='REPRODUCIDO',dispositivo=?,reproducido_en=?,confirmado_en=? where id=?",(disp,now(),now(),lid));c.commit();c.close();return jsonify(ok=True)

@app.get('/llamador/monitor')
def llamador_monitor_web():
 return render_template('llamador_monitor_web.html')

@app.get('/llamador/historico')
def llamador_historico():
 fecha=request.args.get('fecha') or datetime.date.today().isoformat();medico_id=request.args.get('medico_id',type=int);c=db();pars=[fecha+'%'];where='l.fecha_hora like ?'
 if medico_id:where+=' and l.medico_id=?';pars.append(medico_id)
 rows=c.execute("""select l.*,p.nombre paciente,m.nombre medico,m.consultorio_numero from llamados_pacientes l join agenda g on g.id=l.agenda_id join pacientes p on p.id=g.paciente_id join medicos m on m.id=l.medico_id where """+where+' order by l.id desc',pars).fetchall();meds=c.execute('select id,nombre from medicos where activo=1 order by nombre').fetchall();c.close();return render_template('llamador_historico.html',rows=rows,fecha=fecha,meds=meds,medico_id=medico_id)

ROUTE_MODULE.update({'llamador_historico':'CONSULTORIO','llamador_monitor_web':'CONSULTORIO'})



# ===== V13.9.92: Panel de Internación + Catálogo Geográfico =====
@app.get('/internacion/panel')
def internacion_panel():
 c=db();camas=c.execute("""select ca.*,h.nombre habitacion,a.id admision_id,a.fecha fecha_ingreso,p.nombre paciente,coalesce(sg.nombre,'PARTICULAR') cobertura,case when a.id is not null then 'OCUPADA' when coalesce(ca.activo,1)=0 then 'BLOQUEADA' else 'DISPONIBLE' end estado_real from camas ca join habitaciones h on h.id=ca.habitacion_id left join admisiones a on a.cama_id=ca.id and a.estado='ABIERTA' left join pacientes p on p.id=a.paciente_id left join aseguradoras sg on sg.id=a.aseguradora_id order by h.nombre,ca.codigo""").fetchall();disponibles=c.execute("select ca.id,ca.codigo,h.nombre habitacion from camas ca join habitaciones h on h.id=ca.habitacion_id where coalesce(ca.activo,1)=1 and not exists(select 1 from admisiones a where a.cama_id=ca.id and a.estado='ABIERTA') order by h.nombre,ca.codigo").fetchall();historial=c.execute("""select t.*,p.nombre paciente,coalesce(co.codigo,'-') cama_origen,cd.codigo cama_destino from internacion_traslados t join admisiones a on a.id=t.admision_id join pacientes p on p.id=a.paciente_id left join camas co on co.id=t.cama_origen_id join camas cd on cd.id=t.cama_destino_id order by t.id desc limit 100""").fetchall();c.close();return render_template('internacion_panel.html',camas=camas,disponibles=disponibles,historial=historial)

@app.post('/internacion/trasladar/<int:aid>')
def internacion_trasladar(aid):
 if not (user_has('ADMISION','TRASLADAR') or user_has('USUARIOS','ADMINISTRAR')):flash('No tiene permiso para trasladar pacientes.');return redirect('/internacion/panel')
 c=db()
 try:
  a=c.execute("select * from admisiones where id=? and estado='ABIERTA'",(aid,)).fetchone();destino=int(request.form.get('cama_destino_id') or 0)
  if not a:raise ValueError('La internación ya no está abierta.')
  if not destino or destino==a['cama_id']:raise ValueError('Seleccione una cama de destino diferente.')
  if not c.execute('select 1 from camas where id=? and coalesce(activo,1)=1',(destino,)).fetchone():raise ValueError('La cama de destino no está disponible.')
  if c.execute("select 1 from admisiones where cama_id=? and estado='ABIERTA' and id<>?",(destino,aid)).fetchone():raise ValueError('La cama de destino está ocupada.')
  origen=a['cama_id'];c.execute('update admisiones set cama_id=? where id=?',(destino,aid))
  if origen:c.execute("update camas set estado='LIBRE' where id=?",(origen,))
  c.execute("update camas set estado='OCUPADA' where id=?",(destino,));c.execute('insert into internacion_traslados(admision_id,cama_origen_id,cama_destino_id,fecha,usuario,motivo) values(?,?,?,?,?,?)',(aid,origen,destino,now(),session.get('user'),request.form.get('motivo')));c.commit();flash('Paciente trasladado. Toda su cuenta permanece en la misma admisión.')
 except Exception as e:c.rollback();flash('No se pudo trasladar: '+str(e))
 finally:c.close()
 return redirect('/internacion/panel')

@app.route('/administracion/geografia',methods=['GET','POST'])
def administracion_geografia():
 if not (user_has('USUARIOS','ADMINISTRAR') or user_has('CONFIG_SANATORIO','EDITAR')):flash('No tiene permiso para administrar códigos geográficos.');return redirect('/')
 c=db()
 if request.method=='POST':
  f=request.files.get('archivo')
  if not f or not f.filename:c.close();flash('Seleccione un XLSX o CSV.');return redirect(request.path)
  try:
   import io,csv
   data=f.read();name=f.filename.lower()
   if name.endswith('.xlsx'):
    from openpyxl import load_workbook
    vals=list(load_workbook(io.BytesIO(data),read_only=True,data_only=True).active.iter_rows(values_only=True));headers=[str(x or '').strip().lower() for x in vals[0]];rows=[dict(zip(headers,r)) for r in vals[1:]]
   elif name.endswith('.csv'):
    txt=data.decode('utf-8-sig');dialect=csv.Sniffer().sniff(txt[:4096],delimiters=',;\t');rows=[{str(k).strip().lower():v for k,v in r.items()} for r in csv.DictReader(io.StringIO(txt),dialect=dialect)]
   else:raise ValueError('Use XLSX o CSV.')
   def pick(r,*names):
    for k,v in r.items():
     kk=''.join(ch for ch in str(k).lower() if ch.isalnum())
     if kk in names and v is not None and str(v).strip():return str(v).strip()
    return ''
   n=0
   for r in rows:
    dc=pick(r,'codigodepartamento','coddepartamento','cdep','departamentocodigo');dn=pick(r,'departamento','desdepartamento','ddesdep')
    if not dc or not dn:continue
    vals=(dc,dn,pick(r,'codigodistrito','coddistrito','cdis','distritocodigo'),pick(r,'distrito','desdistrito','ddesdis'),pick(r,'codigociudad','codciudad','cciu','ciudadcodigo'),pick(r,'ciudad','desciudad','ddesciu'),pick(r,'codigobarrio','codbarrio','barriocodigo'),pick(r,'barrio','desbarrio'),now())
    c.execute("insert into geo_ubicaciones(departamento_codigo,departamento,distrito_codigo,distrito,ciudad_codigo,ciudad,barrio_codigo,barrio,activo,actualizado_en) values(?,?,?,?,?,?,?,?,1,?) on conflict(departamento_codigo,distrito_codigo,ciudad_codigo,barrio_codigo) do update set departamento=excluded.departamento,distrito=excluded.distrito,ciudad=excluded.ciudad,barrio=excluded.barrio,activo=1,actualizado_en=excluded.actualizado_en",vals);n+=1
   c.commit();flash(f'Importación completada: {n} registros.')
  except Exception as e:c.rollback();flash('No se pudo importar: '+str(e))
  c.close();return redirect(request.path)
 rows=c.execute('select * from geo_ubicaciones order by departamento,distrito,ciudad,barrio limit 1000').fetchall();c.close();return render_template('geografia.html',rows=rows)

if __name__=='__main__':
    app.run(host='0.0.0.0',port=5000,debug=False)

# ===== V13.9.58 - Importacion / actualizacion CxC y CxP =====
def _imp_norm(v):
    return str(v or '').strip()

def _imp_key(v):
    """Normaliza encabezados de Gasparini/Excel sin depender de tildes o puntuación."""
    import re, unicodedata
    s=unicodedata.normalize('NFKD', _imp_norm(v)).encode('ascii','ignore').decode('ascii').lower()
    s=s.replace('nº','nro').replace('n°','nro').replace('numero','numero')
    s=re.sub(r'[^a-z0-9]+','_',s).strip('_')
    return s

def _imp_num(v):
    if v is None or v=='': return 0.0
    if isinstance(v,(int,float)): return float(v)
    s=str(v).strip().replace('Gs.','').replace('Gs','').replace('₲','').replace(' ','')
    if ',' in s and '.' in s:
        # Paraguay: 1.234.567,89
        if s.rfind(',') > s.rfind('.'):
            s=s.replace('.','').replace(',','.')
        else:
            s=s.replace(',','')
    elif ',' in s: s=s.replace(',','.')
    elif s.count('.')>1: s=s.replace('.','')
    return float(s or 0)

_IMP_ALIASES={
 'ruc':'ruc','ruc_ci':'ruc','rucci':'ruc','ci_ruc':'ruc','documento_tercero':'ruc','cliente_ruc':'ruc','proveedor_ruc':'ruc','nro_ruc':'ruc',
 'razon_social':'tercero','razon_social_nombre':'tercero','cliente':'tercero','proveedor':'tercero','nombre':'tercero','denominacion':'tercero','tercero':'tercero',
 'documento':'documento','factura':'documento','numero':'documento','nro':'documento','n_factura':'documento','no_factura':'documento','n_fact':'documento','nro_factura':'documento','numero_factura':'documento','factura_nro':'documento',
 'nro_documento':'documento','numero_documento':'documento','documento_nro':'documento','nro_comprobante':'documento','numero_comprobante':'documento',
 'comprobante':'documento','comprobante_nro':'documento','nro_doc':'documento','num_doc':'documento','doc_nro':'documento','nro_cuenta':'documento',
 'fecha':'fecha','fecha_cr':'fecha','fecha_creacion':'fecha','fecha_documento':'fecha','fecha_factura':'fecha','fecha_emision':'fecha','emision':'fecha','fecha_venc':'fecha_vencimiento','fecha_vencimiento':'fecha_vencimiento',
 'moneda':'moneda','cod_moneda':'moneda','codigo_moneda':'moneda',
 'tc':'tipo_cambio','tipo_cambio':'tipo_cambio','tipo_cambio_origen':'tipo_cambio','cotizacion':'tipo_cambio','cambio':'tipo_cambio',
 'importe':'importe','monto':'importe','total':'importe','importe_total':'importe','monto_total':'importe','valor_total':'importe','deuda_original':'importe','cuota':'cuota','n_compra':'numero_compra','no_compra':'numero_compra',
 'saldo':'saldo','saldo_pendiente':'saldo','saldo_actual':'saldo','saldo_documento':'saldo','pendiente':'saldo','importe_pendiente':'saldo','monto_pendiente':'saldo'
}

def _imp_decode_text(data):
    """Decodifica texto sin confundir CSV ANSI/CP1252 con UTF-16.
    Gasparini suele exportar CSV Windows-1252 sin BOM; probar UTF-16 a ciegas
    produce caracteres legibles pero falsos y rompe la detección de columnas.
    """
    if not data:
        return ''
    candidates=[]
    if data.startswith((b'\xff\xfe', b'\xfe\xff')):
        candidates.extend(('utf-16','utf-16-le','utf-16-be'))
    else:
        # Solo considerar UTF-16 sin BOM cuando hay patrón real de bytes NUL.
        sample=data[:4000]
        even_nul=sum(1 for i in range(0,len(sample),2) if sample[i:i+1]==b'\x00')
        odd_nul=sum(1 for i in range(1,len(sample),2) if sample[i:i+1]==b'\x00')
        slots=max(1,len(sample)//2)
        if max(even_nul,odd_nul)/slots > .20:
            candidates.extend(('utf-16-le','utf-16-be'))
    candidates.extend(('utf-8-sig','cp1252','latin1'))
    for enc in candidates:
        try:
            txt=data.decode(enc)
            probe=txt[:5000]
            printable=sum(ch.isprintable() or ch in '\r\n\t' for ch in probe)
            nul_ratio=probe.count('\x00')/max(1,len(probe))
            if txt and printable/max(1,len(probe))>.90 and nul_ratio<.02:
                return txt
        except Exception:
            pass
    return None

def _imp_detect_delimiter(text):
    """Detecta delimitador de exportaciones Gasparini aun cuando csv.Sniffer falla."""
    import csv
    sample='\n'.join((text or '').splitlines()[:25])[:50000]
    try:
        return csv.Sniffer().sniff(sample,delimiters=',;\t|').delimiter
    except Exception:
        pass
    # Elegir el separador que produzca una cantidad estable y útil de columnas.
    best=', '; best_score=-1
    for delim in (',',';','\t','|'):
        try:
            lens=[]
            for row in list(csv.reader(io.StringIO(sample),delimiter=delim))[:20]:
                if row: lens.append(len(row))
            if not lens: continue
            useful=sum(1 for n in lens if n>1)
            common=max(lens.count(n) for n in set(lens))
            score=useful*100+common*10+min(max(lens),200)
            if score>best_score:
                best_score=score;best=delim
        except Exception:
            continue
    return best.strip() or ','

def _imp_html_rows(txt):
    from html.parser import HTMLParser
    class P(HTMLParser):
        def __init__(self):super().__init__();self.rows=[];self.row=None;self.cell=None
        def handle_starttag(self,tag,attrs):
            tag=tag.lower()
            if tag=='tr':self.row=[]
            elif tag in ('td','th') and self.row is not None:self.cell=[]
        def handle_data(self,data):
            if self.cell is not None:self.cell.append(data)
        def handle_endtag(self,tag):
            tag=tag.lower()
            if tag in ('td','th') and self.cell is not None:
                self.row.append(''.join(self.cell).strip());self.cell=None
            elif tag=='tr' and self.row is not None:
                if any(_imp_norm(x) for x in self.row):self.rows.append(self.row)
                self.row=None
    x=P();x.feed(txt);return x.rows

def _imp_xml_rows(data):
    import xml.etree.ElementTree as ET
    root=ET.fromstring(data)
    rows=[]
    for row in root.iter():
        if row.tag.split('}')[-1].lower()!='row':continue
        vals=[]
        for cell in list(row):
            if cell.tag.split('}')[-1].lower()!='cell':continue
            texts=[]
            for e in cell.iter():
                if e.text:texts.append(e.text)
            vals.append(''.join(texts).strip())
        if vals:rows.append(vals)
    return rows


def _imp_legacy_biff_rows(data):
    """Lector tolerante para hojas BIFF antiguas/fragmentarias sin cabecera OLE/BOF.
    Algunos sistemas administrativos exportan .XLS como un flujo de registros BIFF crudo.
    Solo acepta el archivo si logra reconstruir una tabla coherente; en caso contrario devuelve [].
    """
    import struct, math
    cells={}; pos=0; records=0
    # IDs comunes BIFF2/3/4/5 para NUMBER, LABEL, RK, BOOLERR y BLANK.
    while pos+4 <= len(data) and records < 200000:
        rid, ln = struct.unpack_from('<HH', data, pos)
        if ln > 65535 or pos+4+ln > len(data):
            # tolerancia: buscar el siguiente registro plausible
            pos += 1; continue
        payload=data[pos+4:pos+4+ln]; records+=1; pos += 4+ln
        try:
            if rid in (0x0003,0x0203,0x0403) and len(payload)>=14: # NUMBER
                r,c=struct.unpack_from('<HH',payload,0); v=struct.unpack_from('<d',payload,6)[0]
                if math.isfinite(v): cells[(r,c)]=v
            elif rid in (0x0004,0x0204,0x0404) and len(payload)>=8: # LABEL
                r,c=struct.unpack_from('<HH',payload,0)
                # BIFF2/3 label length may be 1 or 2 bytes after XF.
                candidates=[]
                if len(payload)>=8:
                    n=payload[7]; candidates.append(payload[8:8+n])
                if len(payload)>=9:
                    n2=struct.unpack_from('<H',payload,7)[0]; candidates.append(payload[9:9+n2])
                raw=max(candidates,key=len) if candidates else b''
                if raw:
                    for enc in ('cp1252','latin1','utf-8'):
                        try: v=raw.decode(enc).strip('\x00 '); break
                        except Exception: v=''
                    if v: cells[(r,c)]=v
            elif rid in (0x027E,0x007E) and len(payload)>=10: # RK
                r,c=struct.unpack_from('<HH',payload,0); rk=struct.unpack_from('<I',payload,6)[0]
                if rk & 2: v=float(struct.unpack('<i',struct.pack('<I',rk))[0] >> 2)
                else: v=struct.unpack('<d', struct.pack('<Q', (rk & 0xFFFFFFFC) << 32))[0]
                if rk & 1: v/=100.0
                if math.isfinite(v): cells[(r,c)]=v
            elif rid in (0x0005,0x0205) and len(payload)>=9: # BOOLERR
                r,c=struct.unpack_from('<HH',payload,0); cells[(r,c)]=payload[7]
        except Exception:
            continue
    if len(cells)<3:return []
    maxr=max(r for r,c in cells); maxc=max(c for r,c in cells)
    if maxr>200000 or maxc>500:return []
    rows=[]
    for r in range(maxr+1):
        row=[cells.get((r,c),'') for c in range(maxc+1)]
        if any(str(x).strip() for x in row): rows.append(row)
    return rows

def _imp_csv_field_limit():
    """Eleva de forma segura el límite de campos CSV para exportaciones extensas de Gasparini."""
    import csv, sys
    limit = sys.maxsize
    while True:
        try:
            csv.field_size_limit(limit)
            return limit
        except OverflowError:
            limit //= 10

def _imp_gasparini_compras_sin_cabecera(vals):
    """Reconoce el CSV detallado de Compras Gasparini sin fila de encabezados.
    Mapea únicamente campos verificables del archivo; no inventa forma de pago.
    """
    import re
    if not vals or len(vals[0]) < 80:
        return []
    muestra=vals[:min(25,len(vals))]
    def factura(row):
        for v in reversed(row[-8:]):
            t=str(v or '').strip()
            if re.fullmatch(r'\d{3}-\d{3}-\d{6,8}',t): return t
        return ''
    ok=sum(1 for r in muestra if len(r)>=80 and factura(r) and len(r)>21 and str(r[2]).strip() and str(r[5]).strip() and str(r[13]).strip())
    if ok < max(2, len(muestra)//2):
        return []
    out=[]
    for r in vals:
        if len(r)<22: continue
        doc=factura(r)
        if not doc: continue
        # RUC + DV: en esta exportación aparecen cerca del final; buscar el par más plausible.
        ruc=''
        for i in range(max(0,len(r)-30),len(r)-1):
            a=str(r[i] or '').strip(); b=str(r[i+1] or '').strip()
            if re.fullmatch(r'\d{6,9}',a) and re.fullmatch(r'\d',b):
                ruc=a+'-'+b
        desc_iva=' '.join(str(x or '') for x in r[-20:]).lower()
        iva=5 if '5%' in desc_iva else (10 if '10%' in desc_iva else 0)
        clas=str(r[54] or '').strip() if len(r)>54 else ''
        out.append({
            'documento':doc,
            'fecha':str(r[2] or '').strip(),
            'ruc':ruc,
            'tercero':str(r[5] or '').strip(),
            'moneda':str(r[21] or '').strip() or 'Gs',
            'tipo_cambio':'1',
            'condicion':'CREDITO',
            'forma_pago':'',
            'referencia':'',
            # Sin información de pago/cobro en este archivo: se importa pendiente completo
            # y luego CxP puede actualizarse con el archivo específico de cuentas pendientes.
            'saldo':'',
            'producto_codigo':str(r[36] or '').strip() if len(r)>36 else '',
            'producto_nombre':str(r[13] or '').strip(),
            'clasificacion':clas,
            'cantidad':str(r[6] or '').strip(),
            'costo_unitario':str(r[8] or '').strip(),
            'importe':str(r[10] or '').strip(),
            'iva_pct':str(iva),
            '_gasparini_detallado':'1',
        })
    return out

def _imp_rows(file):
    name=(file.filename or '').lower();data=file.read();vals=[]
    sig=data[:16]
    is_zip=data[:2]==b'PK'; is_ole=data[:8]==bytes.fromhex('D0CF11E0A1B11AE1')
    text=_imp_decode_text(data)
    stripped=(text or '').lstrip().lower()
    try:
        # Detecta el formato REAL por contenido, no solamente por extensión.
        if is_zip or name.endswith(('.xlsx','.xlsm')):
            from openpyxl import load_workbook
            wb=load_workbook(io.BytesIO(data),data_only=True,read_only=True);ws=wb.active
            vals=list(ws.iter_rows(values_only=True))
        elif is_ole:
            import xlrd
            book=xlrd.open_workbook(file_contents=data);sh=book.sheet_by_index(0)
            vals=[sh.row_values(i) for i in range(sh.nrows)]
        elif stripped.startswith('<?xml') or stripped.startswith('<workbook') or 'urn:schemas-microsoft-com:office:spreadsheet' in stripped[:4000]:
            vals=_imp_xml_rows(data)
        elif '<table' in stripped[:10000] or stripped.startswith('<html'):
            vals=_imp_html_rows(text)
        elif name.endswith(('.csv','.txt','.tsv','.xls')) and text is not None:
            import csv
            _imp_csv_field_limit()
            delim=_imp_detect_delimiter(text)
            vals=list(csv.reader(io.StringIO(text),delimiter=delim))
        else:
            # Último intento: .XLS legado exportado como flujo BIFF crudo, sin contenedor OLE.
            # Esto cubre exportaciones antiguas que xlrd rechaza con "Expected BOF record".
            vals=_imp_legacy_biff_rows(data)
            if not vals:
                firma=data[:16].hex(' ').upper()
                raise ValueError('Formato no reconocido. El sistema intentó XLS clásico, XLSX/XLSM, CSV/TXT/TSV, XML/HTML y XLS-BIFF legado. Firma inicial: '+firma+'. Adjunte este archivo original para incorporar su variante exacta sin alterar los datos.')
    except ImportError as ex:
        raise ValueError('Falta una librería para leer este formato: '+str(ex))
    except ValueError: raise
    except Exception as ex:
        raise ValueError('No se pudo interpretar el archivo. Formato real no reconocido: '+str(ex))
    if not vals:return []
    gas_rows=_imp_gasparini_compras_sin_cabecera(vals)
    if gas_rows:
        return gas_rows
    best_i=0;best_score=-1
    for i,row in enumerate(vals[:40]):
        keys=[_IMP_ALIASES.get(_imp_key(x),_imp_key(x)) for x in row]
        score=sum(1 for k in keys if k in ('documento','ruc','tercero','fecha','importe','saldo','moneda','tipo_cambio'))
        if 'documento' in keys: score+=4
        if score>best_score:best_i,best_score=i,score
    rawheads=vals[best_i]
    heads=[];seen={}
    for x in rawheads:
        k=_IMP_ALIASES.get(_imp_key(x),_imp_key(x)) or 'columna'
        seen[k]=seen.get(k,0)+1;heads.append(k if seen[k]==1 else f'{k}_{seen[k]}')
    if 'documento' not in heads:
        encontrados=', '.join(_imp_norm(x) for x in rawheads if _imp_norm(x))[:500]
        raise ValueError('No se identificó la columna Documento/Factura/Comprobante. Encabezados detectados: '+encontrados)
    out=[]
    for row in vals[best_i+1:]:
        if not any(_imp_norm(x) for x in row):continue
        out.append(dict(zip(heads,list(row)+['']*max(0,len(heads)-len(row)))))
    return out

def _tercero_import(c,ruc,nombre,tipo):
    ruc=_imp_norm(ruc);nombre=_imp_norm(nombre) or ruc or 'SIN NOMBRE'
    row=c.execute("select * from terceros where trim(coalesce(ruc,''))=trim(?) order by id limit 1",(ruc,)).fetchone() if ruc else None
    if not row: row=c.execute("select * from terceros where lower(trim(nombre))=lower(trim(?)) order by id limit 1",(nombre,)).fetchone()
    if row:return row['id']
    cur=c.execute('insert into terceros(tipo,ruc,nombre,moneda) values(?,?,?,?)',(tipo,ruc,nombre,'PYG'));return cur.lastrowid

def _importar_cuentas(tipo,file):
    rows=_imp_rows(file);c=db();actualizados=nuevos=errores=0;detalle=[]
    try:
      c.execute('''create table if not exists importacion_cuentas_log(id integer primary key,fecha text,tipo text,archivo text,accion text,registro_id int,documento text,tercero text,antes text,despues text,usuario text)''')
      for n,r in enumerate(rows,2):
       try:
        doc=_imp_norm(r.get('documento'));ruc=_imp_norm(r.get('ruc'));nom=_imp_norm(r.get('tercero'))
        if not doc: raise ValueError('Falta documento/factura')
        moneda=(_imp_norm(r.get('moneda')) or 'PYG').upper();tc=_imp_num(r.get('tipo_cambio')) or 1
        imp=_imp_num(r.get('importe'));saldo=_imp_num(r.get('saldo')) if 'saldo' in r and _imp_norm(r.get('saldo'))!='' else imp
        if imp<=0: raise ValueError('Importe debe ser mayor a cero')
        if saldo<0 or saldo>imp+0.01: raise ValueError('Saldo inválido')
        tid=_tercero_import(c,ruc,nom,'CLIENTE' if tipo=='CXC' else 'PROVEEDOR')
        if tipo=='CXC':
          base='ventas';tab='cxc';fk='venta_id';terfk='cliente_id'
        else:
          base='compras';tab='cxp';fk='compra_id';terfk='proveedor_id'
        b=c.execute(f'select * from {base} where {terfk}=? and trim(numero)=trim(?) order by id desc limit 1',(tid,doc)).fetchone()
        if not b:
          fecha=_imp_norm(r.get('fecha')) or now()[:10];total_pyg=imp*tc
          cur=c.execute(f'''insert into {base}(fecha,{terfk},numero,moneda,tipo_cambio,gravado,iva,exento,total,total_pyg,estado) values(?,?,?,?,?,0,0,?,?,?,?)''',(fecha,tid,doc,moneda,tc,imp,imp,total_pyg,'IMPORTADA'))
          bid=cur.lastrowid
        else: bid=b['id']
        x=c.execute(f'select * from {tab} where {fk}=? order by id desc limit 1',(bid,)).fetchone()
        estado='PAGADO' if saldo<=0.0001 else 'PENDIENTE'
        after={'importe':imp,'saldo':saldo,'moneda':moneda,'tipo_cambio_origen':tc,'importe_pyg':imp*tc,'estado':estado}
        import json
        if x:
          before=dict(x);c.execute(f'update {tab} set tercero_id=?,moneda=?,tipo_cambio_origen=?,importe=?,saldo=?,importe_pyg=?,estado=? where id=?',(tid,moneda,tc,imp,saldo,imp*tc,estado,x['id']));rid=x['id'];actualizados+=1;accion='ACTUALIZAR'
        else:
          before={};cur=c.execute(f'insert into {tab}({fk},tercero_id,moneda,tipo_cambio_origen,importe,saldo,importe_pyg,estado) values(?,?,?,?,?,?,?,?)',(bid,tid,moneda,tc,imp,saldo,imp*tc,estado));rid=cur.lastrowid;nuevos+=1;accion='CREAR'
        c.execute('insert into importacion_cuentas_log(fecha,tipo,archivo,accion,registro_id,documento,tercero,antes,despues,usuario) values(?,?,?,?,?,?,?,?,?,?)',(now(),tipo,file.filename,accion,rid,doc,nom or ruc,json.dumps(before,ensure_ascii=False,default=str),json.dumps(after,ensure_ascii=False),session.get('user')))
       except Exception as e:
        errores+=1;detalle.append(f'Fila {n}: {e}')
      c.commit()
    except Exception:
      c.rollback();raise
    finally:c.close()
    audit('IMPORTAR_'+tipo,f'{file.filename}: {actualizados} actualizadas, {nuevos} nuevas, {errores} errores')
    return actualizados,nuevos,errores,detalle

@app.route('/finanzas/importar/<tipo>',methods=['GET','POST'])
def importar_cuentas(tipo):
 tipo=tipo.upper()
 if tipo not in ('CXC','CXP'):return redirect('/finanzas')
 if request.method=='POST':
  f=request.files.get('archivo')
  if not f or not f.filename:flash('Seleccione un archivo XLS, XLSX, CSV o TXT.');return redirect(request.path)
  try:
   a,n,e,d=_importar_cuentas(tipo,f);flash(f'Importación terminada: {a} cuentas actualizadas, {n} nuevas, {e} con error.' + ((' Primeros errores: '+' | '.join(d[:3])) if d else ''))
   return redirect('/finanzas')
  except Exception as ex:flash('No se pudo importar: '+str(ex));return redirect(request.path)
 return render_template('import_accounts.html',tipo=tipo)

def _cuentas_export_data(tipo):
    c=db()
    tab='cxc' if tipo=='CXC' else 'cxp'; base='ventas' if tipo=='CXC' else 'compras'; fk='venta_id' if tipo=='CXC' else 'compra_id'
    rows=c.execute(f"select t.ruc,t.nombre,b.numero,b.fecha,x.moneda,x.tipo_cambio_origen,x.importe,x.saldo,x.estado from {tab} x left join terceros t on t.id=x.tercero_id left join {base} b on b.id=x.{fk} order by x.id").fetchall();c.close()
    return ['RUC','Tercero','Documento','Fecha','Moneda','Tipo Cambio','Importe','Saldo','Estado'],[tuple(r) for r in rows]

def _cuentas_pdf(tipo,headers,rows):
    from reportlab.platypus import SimpleDocTemplate,Table,TableStyle,Paragraph,Spacer
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4,landscape
    from reportlab.lib.styles import getSampleStyleSheet
    b=io.BytesIO();doc=SimpleDocTemplate(b,pagesize=landscape(A4),leftMargin=20,rightMargin=20,topMargin=25,bottomMargin=25);st=getSampleStyleSheet()
    data=[headers]+[[str(v if v is not None else '') for v in r] for r in rows]
    t=Table(data,repeatRows=1);t.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.35,colors.grey),('FONTNAME',(0,0),(-1,0),'Helvetica-Bold'),('FONTSIZE',(0,0),(-1,-1),7),('VALIGN',(0,0),(-1,-1),'TOP')]))
    doc.build([Paragraph('CENTRO MÉDICO SANTA CLARA',st['Title']),Paragraph('Cuentas por Cobrar' if tipo=='CXC' else 'Cuentas por Pagar',st['Heading2']),Spacer(1,8),t]);b.seek(0)
    return send_file(b,as_attachment=True,download_name=f'{tipo}_Santa_Clara.pdf',mimetype='application/pdf')

@app.get('/finanzas/exportar/<tipo>/<formato>')
def exportar_cuentas(tipo,formato):
    tipo=tipo.upper();formato=formato.lower()
    if tipo not in ('CXC','CXP'):return ('Tipo no válido',404)
    h,r=_cuentas_export_data(tipo)
    if formato in ('xlsx','excel'):return _tabular_xlsx(tipo,h,r,f'{tipo}_Santa_Clara.xlsx')
    if formato=='csv':return _tabular_csv(h,r,f'{tipo}_Santa_Clara.csv',',')
    if formato=='txt':return _tabular_csv(h,r,f'{tipo}_Santa_Clara.txt',';')
    if formato=='tsv':return _tabular_csv(h,r,f'{tipo}_Santa_Clara.tsv','\t')
    if formato=='json':
        import json
        raw=json.dumps([dict(zip(h,row)) for row in r],ensure_ascii=False,indent=2,default=str).encode('utf-8');b=io.BytesIO(raw);b.seek(0);return send_file(b,as_attachment=True,download_name=f'{tipo}_Santa_Clara.json',mimetype='application/json')
    if formato=='xml':
        import xml.etree.ElementTree as ET
        root=ET.Element(tipo)
        for row in r:
            e=ET.SubElement(root,'registro')
            for k,v in zip(h,row):ET.SubElement(e,_imp_key(k) or 'campo').text='' if v is None else str(v)
        raw=ET.tostring(root,encoding='utf-8',xml_declaration=True);b=io.BytesIO(raw);return send_file(b,as_attachment=True,download_name=f'{tipo}_Santa_Clara.xml',mimetype='application/xml')
    if formato=='pdf':return _cuentas_pdf(tipo,h,r)
    return ('Formato no admitido',400)

@app.route('/finanzas/plantilla/<tipo>.xlsx')
def plantilla_cuentas(tipo):
 tipo=tipo.upper()
 if tipo not in ('CXC','CXP'):return redirect('/finanzas')
 from openpyxl import Workbook
 wb=Workbook();ws=wb.active;ws.title=tipo
 ws.append(['RUC','Tercero','Documento','Fecha','Moneda','Tipo Cambio','Importe','Saldo'])
 ws.append(['80000000-0','Ejemplo '+('Cliente' if tipo=='CXC' else 'Proveedor'),'001-001-0000001',now()[:10],'PYG',1,1000000,1000000])
 bio=io.BytesIO();wb.save(bio);bio.seek(0)
 return send_file(bio,as_attachment=True,download_name=f'Plantilla_{tipo}_Santa_Clara.xlsx',mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

# ===== V13.9.67 - Importacion detallada de Compras y Ventas =====
def init_v13967_importacion_detallada():
 c=db();c.execute('''CREATE TABLE IF NOT EXISTS importacion_transacciones_log(id INTEGER PRIMARY KEY,fecha TEXT,tipo TEXT,archivo TEXT,documento TEXT,tercero TEXT,accion TEXT,detalle TEXT,usuario TEXT)''');c.commit();c.close()
init_v13967_importacion_detallada()

# Alias adicionales para archivos Gasparini/Excel detallados.
_IMP_ALIASES.update({
 'codigo':'producto_codigo','cod_producto':'producto_codigo','codigo_producto':'producto_codigo','cod_articulo':'producto_codigo','codigo_articulo':'producto_codigo','articulo_codigo':'producto_codigo',
 'producto':'producto_nombre','articulo':'producto_nombre','descripcion_producto':'producto_nombre','descripcion_articulo':'producto_nombre','item':'producto_nombre','descripcion':'producto_nombre',
 'cantidad':'cantidad','cant':'cantidad','qty':'cantidad','unidades':'cantidad',
 'precio':'precio_unitario','precio_unitario':'precio_unitario','precio_venta':'precio_unitario','valor_unitario':'precio_unitario',
 'costo':'costo_unitario','costo_unitario':'costo_unitario','precio_compra':'costo_unitario',
 'iva':'iva_pct','iva_pct':'iva_pct','tasa_iva':'iva_pct','porcentaje_iva':'iva_pct',
 'condicion':'condicion','condicion_pago':'condicion','condicion_venta':'condicion','tipo_venta':'condicion','tipo_compra':'condicion',
 'forma_pago':'forma_pago','forma_cobro':'forma_pago','medio_pago':'forma_pago','medio':'forma_pago',
 'referencia':'referencia','nro_operacion':'referencia','operacion':'referencia',
 'timbrado':'timbrado','nro_timbrado':'timbrado','numero_timbrado':'timbrado','vencimiento_timbrado':'timbrado_vencimiento',
 'codigo_barras':'codigo_barras','barcode':'codigo_barras','categoria':'categoria','clasificacion':'clasificacion'
})

def _imp_fecha(v):
 if v is None or v=='': return datetime.date.today().isoformat()
 if isinstance(v,(datetime.datetime,datetime.date)): return v.date().isoformat() if isinstance(v,datetime.datetime) else v.isoformat()
 s=str(v).strip()
 for f in ('%Y-%m-%d','%d/%m/%Y','%d-%m-%Y','%d.%m.%Y','%Y/%m/%d'):
  try:return datetime.datetime.strptime(s[:10],f).date().isoformat()
  except Exception:pass
 return s[:10]

def _imp_tercero_tx(c,r,tipo):
 return _tercero_import(c,_imp_norm(r.get('ruc')),_imp_norm(r.get('tercero')),tipo)

def _imp_producto_tx(c,r,tipo):
 cod=_imp_norm(r.get('producto_codigo'));nom=_imp_norm(r.get('producto_nombre'));barra=_imp_norm(r.get('codigo_barras'))
 if not cod and not nom: raise ValueError('Falta código o nombre del producto/servicio')
 p=None
 if cod:p=c.execute('select * from productos where lower(trim(codigo))=lower(trim(?)) limit 1',(cod,)).fetchone()
 if not p and barra:p=c.execute("select * from productos where trim(coalesce(codigo_barras,''))=trim(?) limit 1",(barra,)).fetchone()
 if not p and nom:p=c.execute('select * from productos where lower(trim(nombre))=lower(trim(?)) limit 1',(nom,)).fetchone()
 iva=_imp_num(r.get('iva_pct'))
 if iva not in (0,5,10):iva=10
 if p:return p['id']
 # Servicios importados se crean sin control de stock cuando la clasificación lo indica.
 clas=(_imp_norm(r.get('clasificacion')) or _imp_norm(r.get('categoria'))).upper();es_serv='SERV' in clas
 codigo=cod or ('IMP-'+str(c.execute('select coalesce(max(id),0)+1 from productos').fetchone()[0]))
 cols=[x['name'] for x in c.execute('pragma table_info(productos)').fetchall()]
 cur=c.execute('insert into productos(codigo,nombre,iva_pct,stock,costo_pyg,precio_pyg) values(?,?,?,?,?,?)',(codigo,nom or codigo,iva,0,_imp_num(r.get('costo_unitario')),_imp_num(r.get('precio_unitario'))))
 pid=cur.lastrowid
 if 'codigo_barras' in cols and barra:c.execute('update productos set codigo_barras=? where id=?',(barra,pid))
 if es_serv:
  if 'tipo_producto' in cols:c.execute("update productos set tipo_producto='SERVICIO' where id=?",(pid,))
  if 'clasificacion' in cols:c.execute("update productos set clasificacion='SERVICIO' where id=?",(pid,))
 return pid

def _tx_rows(file):
 rows=_imp_rows(file)
 if not rows:return []
 # En archivos sin detalle explícito, no inventar productos.
 return rows

def _importar_transacciones_detalladas(tipo,file,afectar_stock=False):
 rows=_tx_rows(file);c=db();nuevos=actualizados=sin_cambios=errores=0;mensajes=[]
 groups={}
 for r in rows:
  doc=_imp_norm(r.get('documento'));ruc=_imp_norm(r.get('ruc'));ter=_imp_norm(r.get('tercero'))
  if not doc:
   errores+=1;mensajes.append('Fila sin Documento/Factura');continue
  groups.setdefault((doc,ruc or ter),[]).append(r)
 try:
  for (doc,_),grp in groups.items():
   try:
    r0=grp[0];terid=_imp_tercero_tx(c,r0,'PROVEEDOR' if tipo=='COMPRA' else 'CLIENTE');fecha=_imp_fecha(r0.get('fecha'));mon=(_imp_norm(r0.get('moneda')) or 'PYG').upper();mon='PYG' if mon in ('GS','G$','GUARANI','GUARANIES') else mon;tc=_imp_num(r0.get('tipo_cambio')) or 1
    condicion=(_imp_norm(r0.get('condicion')) or ('CREDITO' if _imp_num(r0.get('saldo'))>0 else 'CONTADO')).upper();condicion='CREDITO' if 'CRED' in condicion else ('CUOTAS' if 'CUOTA' in condicion else 'CONTADO')
    forma=_imp_norm(r0.get('forma_pago')) or None;ref=_imp_norm(r0.get('referencia')) or None
    detalles=[];total=grav=iva=exento=g10=i10=g5=i5=0.0
    for r in grp:
     pid=_imp_producto_tx(c,r,tipo);p=c.execute('select * from productos where id=?',(pid,)).fetchone();qty=_imp_num(r.get('cantidad')) or 1
     unit=_imp_num(r.get('costo_unitario' if tipo=='COMPRA' else 'precio_unitario'))
     if unit<=0:
      bruto_fila=_imp_num(r.get('importe'));unit=(bruto_fila/qty if bruto_fila and qty else 0)
     if qty<=0 or unit<0:raise ValueError('Cantidad/precio inválido en '+doc)
     pct=_imp_num(r.get('iva_pct'))
     if pct not in (0,5,10):pct=float(p['iva_pct'] or 0)
     bruto=qty*unit;base,iv=desglosar_iva_incluido(bruto,pct);total+=bruto;iva+=iv
     if pct==10:g10+=base;i10+=iv;grav+=base
     elif pct==5:g5+=base;i5+=iv;grav+=base
     else:exento+=bruto
     detalles.append((p,pid,qty,unit,base,pct,bruto))
    if total<=0:raise ValueError('Total cero en '+doc)
    tab='compras' if tipo=='COMPRA' else 'ventas';fk='proveedor_id' if tipo=='COMPRA' else 'cliente_id'
    old=c.execute(f'select * from {tab} where numero=? and {fk}=? order by id limit 1',(doc,terid)).fetchone()
    if old:
     oid=old['id']
     if tipo=='COMPRA' and _compra_tiene_pagos(c,oid):raise ValueError('No se actualizó '+doc+': posee pagos registrados')
     if tipo=='VENTA':
      cx=c.execute('select * from cxc where venta_id=?',(oid,)).fetchone()
      if cx and float(cx['importe'] or 0)-float(cx['saldo'] or 0)>0.0001:raise ValueError('No se actualizó '+doc+': posee cobros registrados')
     # Retirar efectos reconstruibles antes de actualizar.
     if tipo=='COMPRA':_quitar_efectos_compra(c,oid,False)
     else:
      for it in c.execute('select * from venta_items where venta_id=?',(oid,)).fetchall():
       p=c.execute('select * from productos where id=?',(it['producto_id'],)).fetchone()
       if afectar_stock and p and _producto_controla_stock(p):c.execute('update productos set stock=stock+? where id=?',(float(it['cantidad'] or 0),it['producto_id']))
      c.execute("delete from stock_mov where origen_tipo='VENTA' and origen_id=?",(oid,));c.execute('delete from venta_items where venta_id=?',(oid,));c.execute('delete from venta_cuotas where venta_id=?',(oid,));c.execute('delete from cxc where venta_id=?',(oid,))
      aids=[x['id'] for x in c.execute("select id from asientos where origen_tipo='VENTA' and origen_id=?",(oid,)).fetchall()]
      for aid in aids:c.execute('delete from asiento_det where asiento_id=?',(aid,))
      c.execute("delete from asientos where origen_tipo='VENTA' and origen_id=?",(oid,))
     xid=oid;actualizados+=1;accion='ACTUALIZADO'
    else:
     if tipo=='COMPRA':cur=c.execute('insert into compras(fecha,proveedor_id,numero,moneda,tipo_cambio,total,total_pyg,estado) values(?,?,?,?,?,?,?,?)',(fecha,terid,doc,mon,tc,total,total*tc,'CONFIRMADA'))
     else:cur=c.execute('insert into ventas(fecha,cliente_id,numero,moneda,tipo_cambio,total,total_pyg,estado) values(?,?,?,?,?,?,?,?)',(fecha,terid,doc,mon,tc,total,total*tc,'CONFIRMADA'))
     xid=cur.lastrowid;nuevos+=1;accion='NUEVO'
    saldo_importado=_imp_num(r0.get('saldo')) if _imp_norm(r0.get('saldo'))!='' else (total if (condicion!='CONTADO' or r0.get('_gasparini_detallado')=='1') else 0)
    saldo=max(0,min(total,saldo_importado));entrega=max(0,total-saldo)
    if tipo=='COMPRA':
     c.execute('''update compras set fecha=?,proveedor_id=?,numero=?,moneda=?,tipo_cambio=?,gravado=?,iva=?,exento=?,total=?,total_pyg=?,gravado_10=?,iva_10=?,gravado_5=?,iva_5=?,exento_iva=?,condicion_pago=?,fecha_vencimiento=?,entrega_inicial=?,medio_pago_inicial=?,referencia_pago=?,timbrado=?,timbrado_vencimiento=?,estado='CONFIRMADA' where id=?''',(fecha,terid,doc,mon,tc,grav,iva,exento,total,total*tc,g10,i10,g5,i5,exento,condicion,_imp_fecha(r0.get('fecha_vencimiento')) if _imp_norm(r0.get('fecha_vencimiento')) else None,entrega,forma,ref,_imp_norm(r0.get('timbrado')),_imp_norm(r0.get('timbrado_vencimiento')),xid))
     for p,pid,q,u,base,pct,bruto in detalles:
      c.execute('insert into compra_items(compra_id,producto_id,cantidad,costo,total,total_pyg,iva_pct) values(?,?,?,?,?,?,?)',(xid,pid,q,u,base,base*tc,pct))
      if afectar_stock and _producto_controla_stock(p):c.execute('update productos set stock=stock+? where id=?',(q,pid));c.execute('insert into stock_mov(fecha,producto_id,tipo,cantidad,costo_pyg,origen_tipo,origen_id) values(?,?,?,?,?,?,?)',(fecha,pid,'ENTRADA',q,(base/q*tc if q else 0),'COMPRA',xid))
     if saldo>0:c.execute('insert into cxp(compra_id,tercero_id,moneda,tipo_cambio_origen,importe,saldo,importe_pyg) values(?,?,?,?,?,?,?)',(xid,terid,mon,tc,total,saldo,total*tc))
     asiento(c,fecha,'Compra importada '+doc,'COMPRA',xid,mon,tc,[('1.1.03',grav*tc+exento*tc,0,grav+exento,'Compra importada'),('1.1.04',iva*tc,0,iva,'IVA crédito'),('2.1.01',0,saldo*tc,saldo,'Proveedor'),('1.1.01',0,entrega*tc,entrega,'Pagado')])
    else:
     c.execute('''update ventas set fecha=?,cliente_id=?,numero=?,moneda=?,tipo_cambio=?,gravado=?,iva=?,exento=?,total=?,total_pyg=?,gravado_10=?,iva_10=?,gravado_5=?,iva_5=?,exento_iva=?,condicion_venta=?,forma_cobro=?,referencia_cobro=?,entrega_inicial=?,fecha_vencimiento=?,estado='CONFIRMADA' where id=?''',(fecha,terid,doc,mon,tc,grav,iva,exento,total,total*tc,g10,i10,g5,i5,exento,condicion,forma,ref,entrega,_imp_fecha(r0.get('fecha_vencimiento')) if _imp_norm(r0.get('fecha_vencimiento')) else None,xid))
     costg=0
     for p,pid,q,u,base,pct,bruto in detalles:
      cost=(q*float(p['costo_pyg'] or 0)) if _producto_controla_stock(p) else 0;costg+=cost;c.execute('insert into venta_items(venta_id,producto_id,cantidad,precio,total,total_pyg,costo_pyg,iva_pct) values(?,?,?,?,?,?,?,?)',(xid,pid,q,u,bruto,bruto*tc,cost,pct))
      if afectar_stock and _producto_controla_stock(p):c.execute('update productos set stock=stock-? where id=?',(q,pid));c.execute('insert into stock_mov(fecha,producto_id,tipo,cantidad,costo_pyg,origen_tipo,origen_id) values(?,?,?,?,?,?,?)',(fecha,pid,'SALIDA',-q,p['costo_pyg'],'VENTA',xid))
     c.execute('insert into cxc(venta_id,tercero_id,moneda,tipo_cambio_origen,importe,saldo,importe_pyg,estado) values(?,?,?,?,?,?,?,?)',(xid,terid,mon,tc,total,saldo,total*tc,'PAGADO' if saldo<=.0001 else 'PENDIENTE'))
     asiento(c,fecha,'Venta importada '+doc,'VENTA',xid,mon,tc,[('1.1.02',saldo*tc,0,saldo,'Cliente'),('1.1.01',entrega*tc,0,entrega,'Cobrado'),('4.1.01',0,(grav+exento)*tc,grav+exento,'Venta importada'),('2.1.02',0,iva*tc,iva,'IVA débito')])
    c.execute('insert into importacion_transacciones_log(fecha,tipo,archivo,documento,tercero,accion,detalle,usuario) values(?,?,?,?,?,?,?,?)',(now(),tipo,file.filename,doc,_imp_norm(r0.get('tercero')),accion,f'{len(detalles)} ítems; total {total}',session.get('user')))
   except Exception as ex:
    errores+=1;mensajes.append(str(ex))
  c.commit();audit('IMPORTACION_'+tipo,f'{file.filename}: nuevos={nuevos}, actualizados={actualizados}, errores={errores}')
 except Exception:
  c.rollback();raise
 finally:c.close()
 return nuevos,actualizados,sin_cambios,errores,mensajes

@app.route('/intercambio/transacciones/<tipo>',methods=['GET','POST'])
def intercambio_transacciones(tipo):
 tipo=tipo.upper()
 if tipo not in ('COMPRA','VENTA'):return ('Tipo inválido',400)
 if request.method=='POST':
  f=request.files.get('archivo')
  if not f or not f.filename:flash('Seleccione un archivo.');return redirect(request.path)
  try:
   n,a,s,e,msg=_importar_transacciones_detalladas(tipo,f,request.form.get('afectar_stock')=='1');flash(f'Importación terminada: {n} nuevos, {a} actualizados, {e} con error.')
   for m in msg[:12]:flash(m)
  except Exception as ex:flash('No se pudo importar: '+str(ex))
  return redirect(request.path)
 return render_template('transaction_exchange.html',tipo=tipo)

@app.get('/intercambio/transacciones/<tipo>/plantilla.xlsx')
def intercambio_transacciones_plantilla(tipo):
 tipo=tipo.upper()
 if tipo not in ('COMPRA','VENTA'):return ('Tipo inválido',400)
 from openpyxl import Workbook
 wb=Workbook();ws=wb.active;ws.title='Detalle'
 headers=['Documento','Fecha','RUC','Tercero','Moneda','Tipo Cambio','Condicion','Forma Pago','Referencia','Saldo','Producto Codigo','Producto Nombre','Clasificacion','Cantidad',('Costo Unitario' if tipo=='COMPRA' else 'Precio Unitario'),'IVA %','Timbrado','Vencimiento Timbrado','Fecha Vencimiento']
 ws.append(headers);ws.append(['001-001-0000001',datetime.date.today().isoformat(),'80000000-0','EJEMPLO','PYG',1,'CREDITO','Transferencia','',100000,'COD001','Producto o servicio','SERVICIO' if tipo=='VENTA' else 'PRODUCTO',1,100000,10,'','',''])
 bio=io.BytesIO();wb.save(bio);bio.seek(0);return send_file(bio,as_attachment=True,download_name=f'plantilla_{tipo.lower()}_detallada.xlsx',mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

ROUTE_MODULE.update({'intercambio_transacciones':'COMPRAS','intercambio_transacciones_plantilla':'COMPRAS'})

ROUTE_MODULE.update({'sifen_corregir_documento':'FACTURACION','sifen_reintentar_nd':'FACTURACION'})


# ===== V13.9.87: Transferencias entre cuentas + Libro de Bancos =====
def init_v13987_transferencias_bancarias():
    c=db()
    c.execute('''CREATE TABLE IF NOT EXISTS transferencias_bancarias(
      id INTEGER PRIMARY KEY, fecha TEXT NOT NULL, cuenta_origen_id INTEGER NOT NULL,
      cuenta_destino_id INTEGER NOT NULL, moneda_origen TEXT NOT NULL, moneda_destino TEXT NOT NULL,
      tipo_cambio_origen REAL NOT NULL DEFAULT 1, tipo_cambio_destino REAL NOT NULL DEFAULT 1,
      importe_origen REAL NOT NULL, importe_destino REAL NOT NULL, importe_origen_pyg REAL NOT NULL,
      importe_destino_pyg REAL NOT NULL, referencia TEXT, concepto TEXT, observaciones TEXT,
      estado TEXT NOT NULL DEFAULT 'CONFIRMADA', movimiento_origen_id INTEGER, movimiento_destino_id INTEGER,
      asiento_id INTEGER, creado_por TEXT, creado_en TEXT, anulado_por TEXT, anulado_en TEXT
    )''')
    c.execute("insert or ignore into schema_migrations(version,aplicado_en) values('13.9.87-transferencias-libro-bancos',?)",(now(),))
    c.commit();c.close()
init_v13987_transferencias_bancarias()

@app.route('/bancos/transferencias',methods=['GET','POST'])
def transferencias_bancarias():
    c=db()
    if request.method=='POST':
        try:
            f=request.form; fecha=f['fecha']; origen=int(f['cuenta_origen_id']); destino=int(f['cuenta_destino_id'])
            if origen==destino: raise ValueError('La cuenta de origen y la cuenta de destino deben ser diferentes.')
            bo=c.execute('select * from cuentas_bancarias where id=? and activo=1',(origen,)).fetchone();bd=c.execute('select * from cuentas_bancarias where id=? and activo=1',(destino,)).fetchone()
            if not bo or not bd: raise ValueError('La cuenta bancaria de origen o destino no existe o está inactiva.')
            if not bo['cuenta_contable'] or not bd['cuenta_contable']: raise ValueError('Ambas cuentas bancarias deben tener una cuenta contable vinculada.')
            mo=(bo['moneda'] or 'PYG').upper();md=(bd['moneda'] or 'PYG').upper();io=float(f.get('importe_origen') or 0);idest=float(f.get('importe_destino') or io)
            if io<=0 or idest<=0: raise ValueError('Los importes deben ser mayores a cero.')
            tco=tc_fecha(c,fecha,mo,f.get('tipo_cambio_origen'));tcd=tc_fecha(c,fecha,md,f.get('tipo_cambio_destino'));pyo=io*tco;pyd=idest*tcd
            ref=(f.get('referencia') or '').strip();concepto=(f.get('concepto') or 'Transferencia entre cuentas').strip();obs=(f.get('observaciones') or '').strip()
            cur=c.execute('''insert into transferencias_bancarias(fecha,cuenta_origen_id,cuenta_destino_id,moneda_origen,moneda_destino,tipo_cambio_origen,tipo_cambio_destino,importe_origen,importe_destino,importe_origen_pyg,importe_destino_pyg,referencia,concepto,observaciones,estado,creado_por,creado_en) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,'CONFIRMADA',?,?)''',(fecha,origen,destino,mo,md,tco,tcd,io,idest,pyo,pyd,ref,concepto,obs,session.get('user'),now()));tid=cur.lastrowid
            m1=c.execute("insert into caja_banco(fecha,tipo,medio,moneda,tipo_cambio,importe,importe_pyg,concepto,origen_tipo,origen_id,cuenta_bancaria_id) values(?,'EGRESO','TRANSFERENCIA_INTERNA',?,?,?,?,?,'TRANSFERENCIA_BANCARIA',?,?)",(fecha,mo,tco,io,pyo,concepto,tid,origen)).lastrowid
            m2=c.execute("insert into caja_banco(fecha,tipo,medio,moneda,tipo_cambio,importe,importe_pyg,concepto,origen_tipo,origen_id,cuenta_bancaria_id) values(?,'INGRESO','TRANSFERENCIA_INTERNA',?,?,?,?,?,'TRANSFERENCIA_BANCARIA',?,?)",(fecha,md,tcd,idest,pyd,concepto,tid,destino)).lastrowid
            lineas=[(bd['cuenta_contable'],pyd,0,idest,'Ingreso por transferencia'),(bo['cuenta_contable'],0,pyo,io,'Salida por transferencia')]
            dif=pyo-pyd
            if abs(dif)>.5:
                lineas.append(('4.2.01',0,dif,0,'Ganancia por diferencia de cambio') if dif>0 else ('5.2.01',-dif,0,0,'Pérdida por diferencia de cambio'))
            aid=asiento(c,fecha,concepto,'TRANSFERENCIA_BANCARIA',tid,'PYG',1,lineas)
            c.execute('update transferencias_bancarias set movimiento_origen_id=?,movimiento_destino_id=?,asiento_id=? where id=?',(m1,m2,aid,tid));c.commit();c.close();audit('TRANSFERENCIA_BANCARIA',f'{tid}: cuenta {origen} -> {destino}');flash('Transferencia registrada y reflejada en Contabilidad y Libro de Bancos.');return redirect('/bancos/transferencias')
        except Exception as ex:
            c.rollback();c.close();flash('No se pudo registrar la transferencia: '+str(ex));return redirect('/bancos/transferencias')
    rows=c.execute('''select t.*,bo.banco banco_origen,bo.alias alias_origen,bo.numero_cuenta numero_origen,bd.banco banco_destino,bd.alias alias_destino,bd.numero_cuenta numero_destino from transferencias_bancarias t join cuentas_bancarias bo on bo.id=t.cuenta_origen_id join cuentas_bancarias bd on bd.id=t.cuenta_destino_id order by t.fecha desc,t.id desc limit 300''').fetchall();cuentas=c.execute('select * from cuentas_bancarias where activo=1 order by banco,alias').fetchall();c.close()
    return render_template('bank_transfers.html',rows=rows,cuentas=cuentas)

@app.post('/bancos/transferencias/<int:tid>/anular')
def transferencia_bancaria_anular(tid):
    c=db();t=c.execute('select * from transferencias_bancarias where id=?',(tid,)).fetchone()
    if not t:c.close();flash('Transferencia no encontrada.');return redirect('/bancos/transferencias')
    if t['estado']=='ANULADA':c.close();flash('La transferencia ya está anulada.');return redirect('/bancos/transferencias')
    if t['movimiento_origen_id']:c.execute('delete from caja_banco where id=?',(t['movimiento_origen_id'],))
    if t['movimiento_destino_id']:c.execute('delete from caja_banco where id=?',(t['movimiento_destino_id'],))
    if t['asiento_id']:c.execute("update asientos set estado='ANULADO' where id=?",(t['asiento_id'],))
    c.execute("update transferencias_bancarias set estado='ANULADA',anulado_por=?,anulado_en=? where id=?",(session.get('user'),now(),tid));c.commit();c.close();audit('ANULAR_TRANSFERENCIA_BANCARIA',str(tid));flash('Transferencia anulada con reversión bancaria y contable.');return redirect('/bancos/transferencias')

@app.get('/bancos/libro')
def libro_bancos():
    c=db();desde=request.args.get('desde') or datetime.date.today().replace(day=1).isoformat();hasta=request.args.get('hasta') or datetime.date.today().isoformat();cuenta=request.args.get('cuenta_bancaria_id') or ''
    cuentas=c.execute('select * from cuentas_bancarias where activo=1 order by banco,alias').fetchall();rows=[];saldo_anterior=0.0;saldo=0.0
    if cuenta:
        cid=int(cuenta);b=c.execute('select * from cuentas_bancarias where id=?',(cid,)).fetchone()
        saldo_anterior=float(c.execute("select coalesce(sum(case when tipo='INGRESO' then importe else -importe end),0) from caja_banco where cuenta_bancaria_id=? and fecha<?",(cid,desde)).fetchone()[0] or 0);saldo=saldo_anterior
        raw=c.execute('select * from caja_banco where cuenta_bancaria_id=? and fecha between ? and ? order by fecha,id',(cid,desde,hasta)).fetchall()
        for r in raw:
            saldo += float(r['importe'] or 0) if r['tipo']=='INGRESO' else -float(r['importe'] or 0)
            d=dict(r);d['saldo_acumulado']=saldo;rows.append(d)
    else:b=None
    c.close();return render_template('bank_book.html',rows=rows,cuentas=cuentas,cuenta_sel=cuenta,banco=b,desde=desde,hasta=hasta,saldo_anterior=saldo_anterior,saldo_final=saldo)

ROUTE_MODULE.update({'transferencias_bancarias':'FINANZAS','transferencia_bancaria_anular':'FINANZAS','libro_bancos':'FINANZAS'})


# ===== V13.9.93: respuestas SOAP SIFEN + prevención rechazo 1300 =====
def init_v13993_respuestas_sifen():
    c=db()
    for tab in ('ventas','notas_credito_ventas','notas_debito_ventas'):
        try:
            cols={r['name'] for r in c.execute('pragma table_info('+tab+')').fetchall()}
            for col,ddl in [('sifen_lote','TEXT'),('sifen_fecha_proceso','TEXT'),('sifen_respuesta_xml','TEXT')]:
                if col not in cols:c.execute(f'alter table {tab} add column {col} {ddl}')
        except Exception:pass
    c.execute("insert or ignore into schema_migrations(version,aplicado_en) values('13.9.93-respuestas-sifen-1300',?)",(now(),));c.commit();c.close()
init_v13993_respuestas_sifen()

def _sifen_aplicar_respuesta(c,tipo,doc_id,xml_respuesta):
    # Guarda únicamente una respuesta real recibida; no inventa aprobaciones.
    tipo=str(tipo).upper();tabs={'FE':'ventas','NCE':'notas_credito_ventas','NDE':'notas_debito_ventas'}
    if tipo not in tabs:raise ValueError('Tipo SIFEN no soportado.')
    r=_sifen_parse_respuesta(xml_respuesta);estado=str(r.get('estado') or 'RESPUESTA_RECIBIDA').upper();tab=tabs[tipo]
    raw=xml_respuesta.decode('utf-8','replace') if isinstance(xml_respuesta,(bytes,bytearray)) else str(xml_respuesta)
    c.execute(f'update {tab} set estado_sifen=?,sifen_codigo_error=?,sifen_mensaje_error=?,sifen_lote=?,sifen_fecha_proceso=?,sifen_respuesta_xml=? where id=?',(estado,r.get('codigo',''),r.get('mensaje',''),r.get('lote',''),r.get('fecha_proceso',''),raw,doc_id))
    c.execute('insert into sifen_eventos(fecha,tipo,estado,detalle) values(?,?,?,?)',(now(),tipo+'_RESPUESTA',estado,f'{tipo} {doc_id}: {r.get("codigo","")} · {r.get("mensaje","")}'))
    return r


@app.post('/sifen/respuesta/importar')
def sifen_importar_respuesta():
    if not (user_has('USUARIOS','ADMINISTRAR') or user_has('FACTURACION','EDITAR')):
        flash('No tiene permiso para importar respuestas SIFEN.');return redirect('/sifen/monitor')
    archivo=request.files.get('respuesta');texto=(request.form.get('xml_respuesta') or '').strip()
    raw=archivo.read() if archivo and archivo.filename else texto.encode('utf-8')
    if not raw:flash('Seleccione un XML SOAP o pegue la respuesta SIFEN.');return redirect('/sifen/monitor')
    c=db()
    try:
        r=_sifen_parse_respuesta(raw);resultados=r.get('resultados') or [r];aplicados=0
        for rr in resultados:
            cdc=(rr.get('cdc') or '').strip()
            if not cdc:continue
            encontrado=None
            for tipo,tab in [('FE','ventas'),('NCE','notas_credito_ventas'),('NDE','notas_debito_ventas')]:
                row=c.execute(f'select id from {tab} where cdc=?',(cdc,)).fetchone()
                if row:encontrado=(tipo,row['id']);break
            if encontrado:
                # Para respuestas de lote con múltiples DE se construye una vista lógica del resultado
                # y se conservan además fecha/lote de la respuesta contenedora.
                tipo,did=encontrado;tab={'FE':'ventas','NCE':'notas_credito_ventas','NDE':'notas_debito_ventas'}[tipo]
                estado=str(rr.get('estado') or 'RESPUESTA_RECIBIDA').upper()
                c.execute(f'update {tab} set estado_sifen=?,sifen_codigo_error=?,sifen_mensaje_error=?,sifen_lote=?,sifen_fecha_proceso=?,sifen_respuesta_xml=? where id=?',(estado,rr.get('codigo',''),rr.get('mensaje',''),r.get('lote',''),r.get('fecha_proceso',''),raw.decode('utf-8','replace'),did))
                c.execute('insert into sifen_eventos(fecha,tipo,estado,detalle) values(?,?,?,?)',(now(),tipo+'_RESPUESTA',estado,f'{tipo} {did}: {rr.get("codigo","")} · {rr.get("mensaje","")}'))
                aplicados+=1
        c.commit()
        if aplicados:flash(f'Respuesta SIFEN procesada: {aplicados} documento(s) actualizado(s) con la respuesta real.')
        else:flash('La respuesta SOAP es legible, pero ningún CDC de la respuesta coincide con documentos del ERP.')
    except Exception as e:c.rollback();flash('No se pudo procesar la respuesta SIFEN: '+str(e))
    finally:c.close()
    return redirect('/sifen/monitor')
ROUTE_MODULE.update({'sifen_importar_respuesta':'FACTURACION'})

# ===== V13.9.95: Puesta en marcha limpia + importación maestra + control SIFEN =====
def init_v13995_puesta_marcha():
 c=db();c.execute("CREATE TABLE IF NOT EXISTS puesta_marcha_importaciones(id INTEGER PRIMARY KEY,fecha TEXT,tipo TEXT,archivo TEXT,registros INTEGER DEFAULT 0,usuario TEXT,estado TEXT,detalle TEXT)");c.execute("insert or ignore into schema_migrations(version,aplicado_en) values('13.9.95-puesta-marcha',?)",(now(),));c.commit();c.close()
init_v13995_puesta_marcha()

def _admin_total(): return str(session.get('rol') or '').upper()=='ADMIN' or user_has('USUARIOS','ADMINISTRAR')

def _leer_importacion_maestra(f):
 nombre=(f.filename or '').lower();raw=f.read()
 if nombre.endswith('.xlsx'):
  import openpyxl
  wb=openpyxl.load_workbook(io.BytesIO(raw),read_only=True,data_only=True);ws=wb.active;filas=list(ws.iter_rows(values_only=True))
  if not filas:return []
  heads=[str(x or '').strip().lower() for x in filas[0]]
  return [{heads[i]:(r[i] if i<len(r) else None) for i in range(len(heads))} for r in filas[1:] if any(x not in (None,'') for x in r)]
 import csv
 txt=raw.decode('utf-8-sig','replace')
 try:dialect=csv.Sniffer().sniff(txt[:4096],delimiters=';,\t,')
 except Exception:dialect=csv.excel
 return [dict(r) for r in csv.DictReader(io.StringIO(txt),dialect=dialect)]

def _v(row,*names,default=''):
 norm={str(k or '').strip().lower().replace('_',' ').replace('-',' '):v for k,v in row.items()}
 for n in names:
  k=str(n).strip().lower().replace('_',' ').replace('-',' ')
  if k in norm and norm[k] not in (None,''):return str(norm[k]).strip()
 return default

@app.get('/administracion/puesta-en-marcha')
def puesta_en_marcha():
 if not _admin_total():flash('Acceso exclusivo de Administración.');return redirect('/')
 c=db();counts={}
 for t in ('terceros','pacientes','productos','servicios','medicos','aseguradoras','habitaciones','camas','ventas','compras','admisiones'):
  try:counts[t]=c.execute('select count(*) from '+t).fetchone()[0]
  except Exception:counts[t]=0
 imports=c.execute('select * from puesta_marcha_importaciones order by id desc limit 20').fetchall();c.close();return render_template('startup_center.html',counts=counts,imports=imports)

@app.post('/administracion/puesta-en-marcha/restablecer')
def puesta_marcha_reset():
 if not _admin_total():flash('Acceso exclusivo de Administración.');return redirect('/')
 if (request.form.get('confirmacion') or '').strip().upper()!='BORRAR TODO':flash('Restablecimiento cancelado. Debe escribir exactamente BORRAR TODO.');return redirect('/administracion/puesta-en-marcha')
 backup=os.path.join(DATA_DIR,'pre_reset_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+'.db');shutil.copy2(DB,backup)
 c=db();c.execute('PRAGMA foreign_keys=OFF')
 preservar={'usuarios','roles','permisos','rol_permisos','usuario_roles','schema_migrations','monedas','plan_cuentas','institucion_config','sifen_config','sifen_puntos_expedicion','caja_punto_expedicion','empresa_config','config_sanatorio','puesta_marcha_importaciones'}
 tablas=[r[0] for r in c.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%'").fetchall()]
 try:
  c.execute('BEGIN')
  for t in tablas:
   if t not in preservar:c.execute('DELETE FROM "'+t.replace('"','')+'"')
  try:c.execute('delete from sqlite_sequence')
  except Exception:pass
  c.commit()
 except Exception:c.rollback();c.close();raise
 c.close();flash('Sistema restablecido. Datos operativos y maestros eliminados. Se conservaron usuarios, configuración fiscal y correlativos SIFEN. Backup: '+os.path.basename(backup));return redirect('/administracion/puesta-en-marcha')

@app.post('/administracion/puesta-en-marcha/importar')
def puesta_marcha_importar():
 if not _admin_total():flash('Acceso exclusivo de Administración.');return redirect('/')
 tipo=(request.form.get('tipo') or '').upper();f=request.files.get('archivo')
 if not f or not f.filename:flash('Seleccione un archivo XLSX o CSV.');return redirect('/administracion/puesta-en-marcha')
 rows=_leer_importacion_maestra(f);c=db();n=0
 try:
  for r in rows:
   if tipo=='CLIENTES':
    nombre=_v(r,'nombre','razon social');ruc=_v(r,'ruc');doc=_v(r,'documento','numero documento',default=ruc)
    if not nombre:continue
    vals=('CLIENTE',ruc,nombre,_v(r,'telefono'),_v(r,'email'),_v(r,'moneda',default='PYG'),_v(r,'naturaleza',default='1'),_v(r,'tipo operacion','operacion',default='1'),_v(r,'tipo contribuyente',default='2'),_v(r,'tipo documento',default='1'),doc,_v(r,'pais',default='PRY'),_v(r,'pais descripcion',default='Paraguay'),_v(r,'direccion'),_v(r,'numero casa',default='0'),_v(r,'departamento codigo'),_v(r,'departamento'),_v(r,'distrito codigo'),_v(r,'distrito'),_v(r,'ciudad codigo'),_v(r,'ciudad'),_v(r,'barrio codigo'),_v(r,'barrio'))
    c.execute('insert into terceros(tipo,ruc,nombre,telefono,email,moneda,sifen_naturaleza,sifen_tipo_operacion,sifen_tipo_contribuyente,sifen_tipo_documento,sifen_numero_documento,sifen_pais,sifen_pais_desc,sifen_direccion,sifen_numero_casa,sifen_departamento_codigo,sifen_departamento_desc,sifen_distrito_codigo,sifen_distrito_desc,sifen_ciudad_codigo,sifen_ciudad_desc,sifen_barrio_codigo,sifen_barrio_desc) values(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',vals);n+=1
   elif tipo=='PRODUCTOS':
    codigo=_v(r,'codigo');nombre=_v(r,'nombre','descripcion')
    if not codigo or not nombre:continue
    c.execute('insert or replace into productos(codigo,nombre,categoria,costo_pyg,precio_pyg,stock,stock_min,iva_pct,sifen_descripcion,sifen_unidad_codigo,sifen_unidad_desc,activo) values(?,?,?,?,?,?,?,?,?,?,?,1)',(codigo,nombre,_v(r,'categoria'),float(_v(r,'costo',default='0') or 0),float(_v(r,'precio',default='0') or 0),float(_v(r,'stock',default='0') or 0),float(_v(r,'stock minimo',default='0') or 0),float(_v(r,'iva',default='10') or 10),_v(r,'descripcion sifen',default=nombre),_v(r,'unidad codigo',default='77'),_v(r,'unidad',default='UNI')));n+=1
   elif tipo=='SERVICIOS':
    codigo=_v(r,'codigo');nombre=_v(r,'nombre','descripcion')
    if not codigo or not nombre:continue
    c.execute('insert or replace into servicios(codigo,nombre,categoria,precio_pyg,cuenta_ingreso,iva_pct) values(?,?,?,?,?,?)',(codigo,nombre,_v(r,'categoria'),float(_v(r,'precio',default='0') or 0),_v(r,'cuenta ingreso',default='4.1.02'),float(_v(r,'iva',default='10') or 10)));n+=1
   elif tipo=='GEOGRAFIA':
    c.execute('insert or replace into sifen_geografia(dep_codigo,dep_nombre,dist_codigo,dist_nombre,ciudad_codigo,ciudad_nombre,barrio_codigo,barrio_nombre,activo) values(?,?,?,?,?,?,?,?,1)',(_v(r,'departamento codigo','codigo departamento'),_v(r,'departamento'),_v(r,'distrito codigo','codigo distrito'),_v(r,'distrito'),_v(r,'ciudad codigo','codigo ciudad'),_v(r,'ciudad'),_v(r,'barrio codigo','codigo barrio'),_v(r,'barrio')));n+=1
   elif tipo=='SALAS':
    hab=_v(r,'sala','habitacion');cama=_v(r,'cama','codigo cama')
    if not hab or not cama:continue
    h=c.execute('select id from habitaciones where nombre=?',(hab,)).fetchone()
    if h:hid=h['id']
    else:c.execute('insert into habitaciones(nombre,tipo) values(?,?)',(hab,_v(r,'tipo',default='INTERNACION')));hid=c.execute('select last_insert_rowid()').fetchone()[0]
    c.execute("insert or ignore into camas(habitacion_id,codigo,estado) values(?,?,'LIBRE')",(hid,cama));n+=1
  c.execute('insert into puesta_marcha_importaciones(fecha,tipo,archivo,registros,usuario,estado,detalle) values(?,?,?,?,?,?,?)',(now(),tipo,secure_filename(f.filename),n,session.get('user'),'OK','Importación maestra confirmada'));c.commit();flash(f'Importación {tipo}: {n} registro(s) procesados.')
 except Exception as e:c.rollback();flash('Importación cancelada: '+str(e))
 finally:c.close()
 return redirect('/administracion/puesta-en-marcha')

@app.get('/sifen/preparacion')
def sifen_preparacion():
 if not _admin_total():flash('Acceso exclusivo de Administración.');return redirect('/')
 c=db();checks=[]
 def add(nombre,ok,detalle):checks.append({'nombre':nombre,'ok':bool(ok),'detalle':detalle})
 cfg=c.execute('select * from sifen_config where id=1').fetchone() if c.execute("select 1 from sqlite_master where type='table' and name='sifen_config'").fetchone() else None
 add('Configuración SIFEN',cfg is not None,'Registro de configuración disponible')
 p=c.execute("select count(*) from sifen_puntos_expedicion where activo=1 and autorizado_dnit=1").fetchone()[0] if c.execute("select 1 from sqlite_master where type='table' and name='sifen_puntos_expedicion'").fetchone() else 0
 add('Puntos de expedición',p>0,f'{p} punto(s) activo(s) marcado(s) como autorizado(s)')
 malos=c.execute("select count(*) from terceros where tipo in ('CLIENTE','AMBOS') and (coalesce(nombre,'')='' or coalesce(sifen_naturaleza,'')='' or coalesce(sifen_tipo_operacion,'')='')").fetchone()[0];add('Clientes listos para SIFEN',malos==0,f'{malos} cliente(s) incompletos')
 malos_p=c.execute("select count(*) from productos where coalesce(activo,1)=1 and (coalesce(sifen_descripcion,'')='' or coalesce(sifen_unidad_codigo,'')='')").fetchone()[0];add('Productos listos para SIFEN',malos_p==0,f'{malos_p} producto(s) incompletos')
 c.close();return render_template('sifen_readiness.html',checks=checks)

ROUTE_MODULE.update({'puesta_en_marcha':'CONFIG_SANATORIO','puesta_marcha_reset':'CONFIG_SANATORIO','puesta_marcha_importar':'CONFIG_SANATORIO','sifen_preparacion':'FACTURACION'})
