import os, secrets, sqlite3, datetime
from pathlib import Path
from flask import request,session,redirect,render_template_string,abort,send_file,Response
from werkzeug.utils import secure_filename

STYLE='<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#087c8b"><link rel="manifest" href="/portal/manifest.webmanifest"><style>body{font-family:system-ui;background:#f2f7f8;color:#153944;margin:0}header{background:#07556b;color:white;padding:18px 6%}main{max-width:980px;margin:25px auto;padding:0 18px}.card{background:white;border:1px solid #d8e7eb;border-radius:14px;padding:22px;margin:14px 0}input,select,button{padding:11px;margin:5px;border:1px solid #b8cbd0;border-radius:8px}button{background:#087c8b;color:white;cursor:pointer}a{color:#087c8b}table{width:100%;border-collapse:collapse}td,th{padding:9px;border-bottom:1px solid #e1ecef;text-align:left}.muted{color:#607880}</style>'

def instalar_portal_rrhh(app,db,perm,hash_pw,check_pw,data_dir,now):
    base=Path(data_dir)/'rrhh'/'legajos_portal';base.mkdir(parents=True,exist_ok=True)
    def init():
        c=db()
        c.execute('CREATE TABLE IF NOT EXISTS rrhh_portal_cuentas (empleado_id INTEGER PRIMARY KEY,clave TEXT NOT NULL,activo INTEGER NOT NULL DEFAULT 1,creado_en TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS rrhh_portal_docs (id INTEGER PRIMARY KEY,empleado_id INTEGER NOT NULL,tipo TEXT NOT NULL,nombre TEXT NOT NULL,archivo TEXT NOT NULL,visible INTEGER NOT NULL DEFAULT 0,creado_en TEXT,creado_por TEXT)')
        c.commit();c.close()
    init()
    def token():
        if not session.get('rrhh_csrf'):session['rrhh_csrf']=secrets.token_urlsafe(32)
        return session['rrhh_csrf']
    def verify():
        if not secrets.compare_digest(request.form.get('csrf',''),token()):abort(403)
    def page(title,body,**ctx):
        return render_template_string('<!doctype html><html lang="es"><head><meta charset="utf-8"><title>'+title+'</title>'+STYLE+'</head><body><header><b>Centro Médico Santa Clara · '+title+'</b></header><main>'+body+'</main></body></html>',csrf=token(),**ctx)
    def admin():
        if not perm('VER'):abort(403)
    def self_id():
        eid=session.get('rrhh_portal_id')
        if not eid:abort(403)
        return int(eid)
    @app.route('/rrhh/portal',methods=['GET'])
    def rrhh_portal_admin():
        admin();c=db();rows=c.execute('SELECT e.id,e.nombre,e.documento,p.activo, (SELECT count(*) FROM rrhh_portal_docs d WHERE d.empleado_id=e.id) cantidad FROM empleados e LEFT JOIN rrhh_portal_cuentas p ON p.empleado_id=e.id ORDER BY e.nombre').fetchall();c.close()
        return page('Portal RRHH · Administración','''<div class="card"><h2>Funcionarios y legajos</h2><p>Seleccione un funcionario para crear acceso y cargar documentos.</p><table><tr><th>Funcionario</th><th>Documentos</th><th>Portal</th></tr>{% for e in rows %}<tr><td><a href="/rrhh/portal/empleado/{{e.id}}">{{e.nombre}}</a></td><td>{{e.cantidad}}</td><td>{{'Habilitado' if e.activo else 'Sin acceso'}}</td></tr>{% endfor %}</table></div>''',rows=rows)
    @app.route('/rrhh/portal/empleado/<int:eid>',methods=['GET','POST'])
    def rrhh_portal_empleado(eid):
        admin();c=db();e=c.execute('SELECT id,nombre,documento FROM empleados WHERE id=?',(eid,)).fetchone()
        if not e:c.close();abort(404)
        if request.method=='POST':
            verify()
            if not perm('ADMINISTRAR'):c.close();abort(403)
            action=request.form.get('accion')
            if action=='acceso':
                pw=request.form.get('clave','')
                if len(pw)<12:c.close();abort(400,'Contraseña de mínimo 12 caracteres')
                c.execute('INSERT INTO rrhh_portal_cuentas(empleado_id,clave,activo,creado_en) VALUES(?,?,1,?) ON CONFLICT(empleado_id) DO UPDATE SET clave=excluded.clave,activo=1',(eid,hash_pw(pw),now()))
            elif action=='desactivar':c.execute('UPDATE rrhh_portal_cuentas SET activo=0 WHERE empleado_id=?',(eid,))
            elif action=='archivo':
                f=request.files.get('archivo');tipo=request.form.get('tipo','OTROS')[:60]
                if not f or not f.filename:c.close();abort(400)
                ext=Path(f.filename).suffix.lower()
                if ext not in ('.pdf','.png','.jpg','.jpeg'):c.close();abort(400,'Formato no permitido')
                data=f.read(8*1024*1024+1)
                if len(data)>8*1024*1024:c.close();abort(413)
                if ext=='.pdf' and not data.startswith(b'%PDF-'):c.close();abort(400)
                if ext=='.png' and not data.startswith(b'\x89PNG'):c.close();abort(400)
                if ext in ('.jpg','.jpeg') and not data.startswith(b'\xff\xd8'):c.close();abort(400)
                name=secrets.token_hex(20)+ext;(base/name).write_bytes(data)
                c.execute('INSERT INTO rrhh_portal_docs(empleado_id,tipo,nombre,archivo,visible,creado_en,creado_por) VALUES(?,?,?,?,?,?,?)',(eid,tipo,secure_filename(f.filename)[:180],name,1 if request.form.get('visible') else 0,now(),session.get('user')))
            elif action=='publicar':c.execute('UPDATE rrhh_portal_docs SET visible=? WHERE id=? AND empleado_id=?',(1 if request.form.get('visible')=='1' else 0,int(request.form.get('doc_id') or 0),eid))
            c.commit();c.close();return redirect(request.path)
        docs=c.execute('SELECT * FROM rrhh_portal_docs WHERE empleado_id=? ORDER BY id DESC',(eid,)).fetchall();acc=c.execute('SELECT activo FROM rrhh_portal_cuentas WHERE empleado_id=?',(eid,)).fetchone();c.close()
        return page('Legajo digital','''<p><a href="/rrhh/portal">← Funcionarios</a></p><div class="card"><h2>{{e.nombre}}</h2><p>Documento: {{e.documento}} · Portal: {{'Activo' if acc and acc.activo else 'Inactivo'}}</p>{% if can_edit %}<form method="post"><input type="hidden" name="csrf" value="{{csrf}}"><input type="hidden" name="accion" value="acceso"><input name="clave" type="password" minlength="12" required placeholder="Nueva clave del funcionario"><button>Crear/restablecer acceso</button></form><form method="post"><input type="hidden" name="csrf" value="{{csrf}}"><input type="hidden" name="accion" value="desactivar"><button>Desactivar acceso</button></form>{% endif %}</div><div class="card"><h3>Documentos</h3>{% if can_edit %}<form method="post" enctype="multipart/form-data"><input type="hidden" name="csrf" value="{{csrf}}"><input type="hidden" name="accion" value="archivo"><select name="tipo"><option>CONTRATO</option><option>RECIBO SALARIAL</option><option>ANTICIPO</option><option>IPS</option><option>VACACIONES</option><option>OTROS</option></select><input type="file" name="archivo" accept=".pdf,.png,.jpg,.jpeg" required><label><input type="checkbox" name="visible">Visible al funcionario</label><button>Cargar documento</button></form>{% endif %}<table><tr><th>Tipo y nombre</th><th>Acceso</th><th>Publicación</th></tr>{% for d in docs %}<tr><td>{{d.tipo}} · {{d.nombre}}</td><td><a href="/rrhh/portal/archivo/{{d.id}}">Descargar</a></td><td>{{'Visible' if d.visible else 'Privado'}}{% if can_edit %}<form method="post" style="display:inline"><input type="hidden" name="csrf" value="{{csrf}}"><input type="hidden" name="accion" value="publicar"><input type="hidden" name="doc_id" value="{{d.id}}"><input type="hidden" name="visible" value="{{'0' if d.visible else '1'}}"><button>{{'Ocultar' if d.visible else 'Publicar'}}</button></form>{% endif %}</td></tr>{% endfor %}</table></div>''',e=e,acc=acc,docs=docs,can_edit=perm('ADMINISTRAR'))
    @app.route('/portal/login',methods=['GET','POST'])
    def portal_login():
        err=''
        if request.method=='POST':
            verify();doc=request.form.get('documento','').strip();pw=request.form.get('clave','');c=db();r=c.execute('SELECT e.id,p.clave FROM empleados e JOIN rrhh_portal_cuentas p ON p.empleado_id=e.id WHERE e.documento=? AND e.estado=? AND p.activo=1',(doc,'ACTIVO')).fetchone();c.close()
            if r and check_pw(r['clave'],pw):session.clear();session['rrhh_portal_id']=r['id'];return redirect('/portal')
            err='Credenciales incorrectas'
        return page('Acceso del funcionario','''<div class="card"><h2>Mi portal</h2><p>{{err}}</p><form method="post"><input type="hidden" name="csrf" value="{{csrf}}"><p><input name="documento" required placeholder="Número de cédula"></p><p><input name="clave" type="password" required placeholder="Contraseña"></p><button>Ingresar</button></form></div>''',err=err)
    @app.get('/portal')
    def portal_inicio():
        eid=self_id();c=db();e=c.execute('SELECT nombre,cargo,departamento FROM empleados WHERE id=?',(eid,)).fetchone();docs=c.execute('SELECT id,tipo,nombre,creado_en FROM rrhh_portal_docs WHERE empleado_id=? AND visible=1 ORDER BY id DESC',(eid,)).fetchall();c.close()
        if not e:abort(403)
        return page('Mi legajo digital','''<div class="card"><h2>Bienvenido/a, {{e.nombre}}</h2><p>{{e.cargo}} · {{e.departamento}}</p><a href="/portal/salir">Cerrar sesión</a></div><div class="card"><h3>Mis documentos y recibos</h3><table>{% for d in docs %}<tr><td>{{d.tipo}} · {{d.nombre}}</td><td><a href="/rrhh/portal/archivo/{{d.id}}">Descargar</a></td></tr>{% else %}<tr><td>No hay documentos publicados.</td></tr>{% endfor %}</table></div>''',e=e,docs=docs)
    @app.get('/rrhh/portal/archivo/<int:did>')
    def rrhh_portal_archivo(did):
        c=db();r=c.execute('SELECT * FROM rrhh_portal_docs WHERE id=?',(did,)).fetchone();c.close()
        if not r:abort(404)
        if session.get('rrhh_portal_id')==r['empleado_id'] and r['visible']:pass
        elif session.get('user') and perm('VER'):pass
        else:abort(403)
        path=base/Path(r['archivo']).name
        if not path.is_file():abort(404)
        return send_file(path,as_attachment=True,download_name=r['nombre'])
    @app.get('/portal/salir')
    def portal_logout():session.clear();return redirect('/portal/login')
    @app.get('/portal/manifest.webmanifest')
    def portal_manifest():return Response('{"name":"Santa Clara · Mi Portal","short_name":"Santa Clara RRHH","start_url":"/portal/login","display":"standalone","background_color":"#f2f7f8","theme_color":"#087c8b"}',mimetype='application/manifest+json')
