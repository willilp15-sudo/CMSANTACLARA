import os, secrets, sqlite3, datetime
from pathlib import Path
from flask import request,session,redirect,render_template_string,abort,send_file,Response
from werkzeug.utils import secure_filename

STYLE='<meta name="apple-mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-title" content="Mi Portal Santa Clara"><meta name="mobile-web-app-capable" content="yes"><link rel="apple-touch-icon" href="/static/portal-icon-180.png"><link rel="icon" type="image/png" href="/static/portal-icon-192.png"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="theme-color" content="#087c8b"><link rel="manifest" href="/portal/manifest.webmanifest"><style>body{font-family:system-ui;background:#f2f7f8;color:#153944;margin:0}header{background:#07556b;color:white;padding:14px 6%;display:flex;align-items:center;gap:16px}header img{width:72px;height:60px;object-fit:contain;background:white;border-radius:10px;padding:4px}header b{font-size:clamp(15px,3vw,21px)}main{max-width:980px;margin:25px auto;padding:0 18px}.card{background:white;border:1px solid #d8e7eb;border-radius:14px;padding:22px;margin:14px 0}input,select,button{padding:11px;margin:5px;border:1px solid #b8cbd0;border-radius:8px}button{background:#087c8b;color:white;cursor:pointer}a{color:#087c8b}table{width:100%;border-collapse:collapse}td,th{padding:9px;border-bottom:1px solid #e1ecef;text-align:left}.muted{color:#607880}</style>'

def instalar_portal_rrhh(app,db,perm,hash_pw,check_pw,data_dir,now):
    base=Path(data_dir)/'rrhh'/'legajos_portal';base.mkdir(parents=True,exist_ok=True)
    def init():
        c=db()
        c.execute('CREATE TABLE IF NOT EXISTS rrhh_portal_cuentas (empleado_id INTEGER PRIMARY KEY,clave TEXT NOT NULL,activo INTEGER NOT NULL DEFAULT 1,creado_en TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS rrhh_portal_docs (id INTEGER PRIMARY KEY,empleado_id INTEGER NOT NULL,tipo TEXT NOT NULL,nombre TEXT NOT NULL,archivo TEXT NOT NULL,visible INTEGER NOT NULL DEFAULT 0,creado_en TEXT,creado_por TEXT)')
        c.commit();c.close()
    init()
    def grupo_documento(tipo):
        t=(tipo or '').upper().strip()
        if any(k in t for k in ('RECIBO','SALAR','AGUINALDO','LIQUIDACION','LIQUIDACIÓN','ANTICIPO')):return 'recibos'
        if any(k in t for k in ('CONTRATO','ADENDA','RENOVACION','RENOVACIÓN')):return 'contratos'
        return 'documentos'
    def agrupar(rows):
        result={'recibos':[],'contratos':[],'documentos':[]}
        for d in rows:result[grupo_documento(d['tipo'])].append(d)
        return result
    TABS='''<style>.doc-tabs{display:flex;gap:8px;flex-wrap:wrap;margin:16px 0}.doc-tab{background:#edf5f6;border:1px solid #bcd9df;color:#07556b;padding:12px 16px;border-radius:10px;cursor:pointer;font-weight:600}.doc-tab[aria-selected="true"]{background:#087c8b;color:#fff}.doc-panel[hidden]{display:none}.doc-row{padding:14px 0;border-bottom:1px solid #e1ecef;display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}.doc-actions{display:flex;gap:12px;align-items:center;flex-wrap:wrap}.doc-actions form{display:inline}.doc-meta{font-size:13px;color:#607880}</style><div class="doc-tabs" role="tablist" aria-label="Categorías de documentos">{% for key,label in [('recibos','Recibos'),('contratos','Contratos'),('documentos','Documentos')] %}<button type="button" class="doc-tab" role="tab" id="tab-{{key}}" aria-controls="panel-{{key}}" aria-selected="{{'true' if loop.first else 'false'}}" onclick="mostrarGrupo('{{key}}')">{{label}} ({{grupos[key]|length}})</button>{% endfor %}</div>{% for key,label in [('recibos','Recibos'),('contratos','Contratos'),('documentos','Documentos')] %}<section class="doc-panel" id="panel-{{key}}" role="tabpanel" aria-labelledby="tab-{{key}}" {% if not loop.first %}hidden{% endif %}><h3>{{label}}</h3>{% for d in grupos[key] %}<div class="doc-row"><div><strong>{{d.nombre}}</strong><div class="doc-meta">{{d.tipo}} · {{d.creado_en or 'Sin fecha'}}</div></div><div class="doc-actions"><a href="/rrhh/portal/archivo/{{d.id}}?ver=1" target="_blank" rel="noopener">Ver</a><a href="/rrhh/portal/archivo/{{d.id}}">Descargar</a>{% if administracion %}<span class="doc-meta">{{'Visible' if d.visible else 'Privado'}}</span>{% if can_edit %}<form method="post"><input type="hidden" name="csrf" value="{{csrf}}"><input type="hidden" name="accion" value="publicar"><input type="hidden" name="doc_id" value="{{d.id}}"><input type="hidden" name="visible" value="{{'0' if d.visible else '1'}}"><button>{{'Ocultar' if d.visible else 'Publicar'}}</button></form>{% endif %}{% endif %}</div></div>{% else %}<p class="muted">No hay documentos en esta categoría.</p>{% endfor %}</section>{% endfor %}<script>function mostrarGrupo(g){document.querySelectorAll('.doc-tab').forEach(b=>b.setAttribute('aria-selected',String(b.id==='tab-'+g)));document.querySelectorAll('.doc-panel').forEach(p=>p.hidden=p.id!=='panel-'+g)}</script>'''
    def token():
        if not session.get('rrhh_csrf'):session['rrhh_csrf']=secrets.token_urlsafe(32)
        return session['rrhh_csrf']
    def verify():
        if not secrets.compare_digest(request.form.get('csrf',''),token()):abort(403)
    def page(title,body,**ctx):
        return render_template_string('<!doctype html><html lang="es"><head><meta charset="utf-8"><title>'+title+'</title>'+STYLE+'</head><body><header><img src="/static/logo_santa_clara_cropped.png" alt="Logo Centro Médico Santa Clara"><b>Mi Portal Santa Clara · '+title+'</b></header><main>'+body+'</main></body></html>',csrf=token(),**ctx)
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
        return page('Legajo digital','''<p><a href="/rrhh/portal">← Funcionarios</a></p><div class="card"><h2>{{e.nombre}}</h2><p>Documento: {{e.documento}} · Portal: {{'Activo' if acc and acc.activo else 'Inactivo'}}</p>{% if can_edit %}<form method="post"><input type="hidden" name="csrf" value="{{csrf}}"><input type="hidden" name="accion" value="acceso"><input name="clave" type="password" minlength="12" required placeholder="Nueva clave del funcionario"><button>Crear/restablecer acceso</button></form><form method="post"><input type="hidden" name="csrf" value="{{csrf}}"><input type="hidden" name="accion" value="desactivar"><button>Desactivar acceso</button></form>{% endif %}</div><div class="card"><h3>Gestión de documentos</h3>{% if can_edit %}<form method="post" enctype="multipart/form-data"><input type="hidden" name="csrf" value="{{csrf}}"><input type="hidden" name="accion" value="archivo"><select name="tipo"><option>RECIBO SALARIAL</option><option>AGUINALDO</option><option>LIQUIDACION</option><option>ANTICIPO</option><option>CONTRATO</option><option>ADENDA</option><option>RENOVACION</option><option>IPS</option><option>VACACIONES</option><option>CERTIFICADO</option><option>OTROS</option></select><input type="file" name="archivo" accept=".pdf,.png,.jpg,.jpeg" required><label><input type="checkbox" name="visible">Visible al funcionario</label><button>Cargar documento</button></form>{% endif %}'''+TABS+'''</div>''',e=e,acc=acc,grupos=agrupar(docs),administracion=True,can_edit=perm('ADMINISTRAR'))
    @app.route('/portal/login',methods=['GET','POST'])
    def portal_login():
        err=''
        if request.method=='POST':
            verify();doc=request.form.get('documento','').strip();pw=request.form.get('clave','');c=db();r=c.execute('SELECT e.id,p.clave FROM empleados e JOIN rrhh_portal_cuentas p ON p.empleado_id=e.id WHERE e.documento=? AND e.estado=? AND p.activo=1',(doc,'ACTIVO')).fetchone();c.close()
            if r and check_pw(r['clave'],pw):session.clear();session['rrhh_portal_id']=r['id'];return redirect('/portal')
            err='Credenciales incorrectas'
        return page('Acceso del funcionario','''<div class="card"><div style="text-align:center"><img src="/static/logo_santa_clara_cropped.png" alt="Centro Médico Santa Clara" style="width:180px;max-width:70%;height:auto"><h2>Mi Portal Santa Clara</h2><p class="muted">Acceso exclusivo para funcionarios</p></div><p>{{err}}</p><form method="post"><input type="hidden" name="csrf" value="{{csrf}}"><p><input name="documento" required placeholder="Número de cédula"></p><p><input name="clave" type="password" required placeholder="Contraseña"></p><button>Ingresar</button></form></div>''',err=err)
    def antiguedad(fecha):
        try:
            d=datetime.date.fromisoformat(str(fecha)[:10]);h=datetime.date.today()
            if d>h:return 'Fecha futura: revisar RRHH'
            y=h.year-d.year-((h.month,h.day)<(d.month,d.day))
            m=(h.year-d.year)*12+h.month-d.month-(h.day<d.day)
            return f'{y} años y {m%12} meses'
        except (ValueError,TypeError):return 'No disponible'
    @app.route('/portal/calculadora',methods=['GET','POST'])
    def portal_calculadora():
        eid=self_id();c=db();e=c.execute('SELECT nombre,fecha_ingreso,salario_base FROM empleados WHERE id=?',(eid,)).fetchone();c.close()
        if not e:abort(403)
        today=datetime.date.today();fecha=e['fecha_ingreso'] or '';salario=e['salario_base'] or 0
        resultado=None;error=''
        if request.method=='POST':
            verify()
            try:
                ini=datetime.date.fromisoformat(request.form['ingreso']);fin=datetime.date.fromisoformat(request.form['egreso'])
                sueldo=float(request.form['salario']);causa=request.form.get('causa','renuncia')
                if fin<ini or sueldo<=0 or sueldo>100000000000:raise ValueError('Revisá las fechas y el salario.')
                meses=(fin.year-ini.year)*12+fin.month-ini.month-(fin.day<ini.day)
                if meses<0:raise ValueError('Antigüedad inválida')
                anios=meses//12;resto=meses%12
                # Estimación básica: indemnización por despido injustificado, 15 jornales por año o fracción >=6 meses.
                dias_ind=15*(anios+(1 if resto>=6 else 0)) if causa=='injustificado' else 0
                # Preaviso: 30/45/60/90 días según antigüedad, únicamente si corresponde y no se otorgó.
                dias_pre=(30 if meses<12 else 45 if meses<=60 else 60 if meses<=120 else 90) if causa=='injustificado' and request.form.get('sin_preaviso')=='si' else 0
                dias_vac=0 if meses<12 else 12 if meses<=60 else 18 if meses<=120 else 30
                resultado={'meses':meses,'dias_vac':dias_vac,'dias_ind':dias_ind,'dias_pre':dias_pre,'ind':round(sueldo/30*dias_ind),'pre':round(sueldo/30*dias_pre)}
            except (ValueError,KeyError,OverflowError) as ex:error='Datos inválidos: '+str(ex)
        return page('Calculadora laboral','''<p><a href="/portal">← Volver a mis documentos</a></p><div class="card"><h2>Calculadora laboral paraguaya</h2><p class="muted">Simulación informativa. No constituye liquidación oficial ni modifica la nómina.</p><form method="post"><input type="hidden" name="csrf" value="{{csrf}}"><p><label>Fecha de ingreso <input type="date" name="ingreso" value="{{ingreso}}" required></label></p><p><label>Fecha de cálculo / egreso <input type="date" name="egreso" value="{{hoy}}" required></label></p><p><label>Salario mensual G. <input type="number" min="1" step="1" name="salario" value="{{salario}}" required></label></p><p><label>Situación <select name="causa"><option value="renuncia">Renuncia voluntaria</option><option value="injustificado">Despido sin causa justificada</option><option value="justificado">Despido con causa justificada</option></select></label></p><p><label><input type="checkbox" name="sin_preaviso" value="si"> No se otorgó el preaviso legal completo (solo despido sin causa)</label></p><button type="submit">Calcular</button></form>{% if error %}<p role="alert">{{error}}</p>{% endif %}{% if resultado %}<h3>Resultado orientativo</h3><p>Antigüedad: {{resultado.meses}} meses completos</p><p>Vacaciones anuales de referencia: {{resultado.dias_vac}} días (no equivale a saldo pendiente)</p><p>Indemnización estimada: G. {{'{:,.0f}'.format(resultado.ind).replace(',','.')}} ({{resultado.dias_ind}} jornales)</p><p>Preaviso estimado: G. {{'{:,.0f}'.format(resultado.pre).replace(',','.')}} ({{resultado.dias_pre}} días)</p><h3>Subtotal: G. {{'{:,.0f}'.format(resultado.ind+resultado.pre).replace(',','.')}}</h3><p class="muted">No incluye aguinaldo proporcional, vacaciones pendientes, salarios adeudados, remuneración variable, estabilidad especial ni otros ajustes. Revisar legislación y circunstancias con RRHH antes de liquidar.</p>{% endif %}</div>''',ingreso=fecha,hoy=today.isoformat(),salario=round(salario),resultado=resultado,error=error)
    @app.get('/portal')
    def portal_inicio():
        eid=self_id();c=db();e=c.execute('SELECT nombre,cargo,departamento,fecha_ingreso,salario_base FROM empleados WHERE id=?',(eid,)).fetchone();docs=c.execute('SELECT id,tipo,nombre,creado_en FROM rrhh_portal_docs WHERE empleado_id=? AND visible=1 ORDER BY id DESC',(eid,)).fetchall();c.close()
        if not e:abort(403)
        return page('Mi legajo digital','''<div class="card"><h2>Bienvenido/a, {{e.nombre}}</h2><p>{{e.cargo}} · {{e.departamento}}</p><p><b>Fecha de ingreso:</b> {{e.fecha_ingreso or 'No registrada'}} · <b>Antigüedad:</b> {{antiguedad}}</p><p><a href="/portal/calculadora">Abrir calculadora laboral</a></p><a href="/portal/salir">Cerrar sesión</a></div><div class="card"><h2>Mis documentos</h2><p class="muted">Seleccioná una categoría para consultar tus archivos.</p>'''+TABS+'</div>',e=e,grupos=agrupar(docs),administracion=False,can_edit=False,antiguedad=antiguedad(e['fecha_ingreso']))
    @app.get('/rrhh/portal/archivo/<int:did>')
    def rrhh_portal_archivo(did):
        c=db();r=c.execute('SELECT * FROM rrhh_portal_docs WHERE id=?',(did,)).fetchone();c.close()
        if not r:abort(404)
        if session.get('rrhh_portal_id')==r['empleado_id'] and r['visible']:pass
        elif session.get('user') and perm('VER'):pass
        else:abort(403)
        path=base/Path(r['archivo']).name
        if not path.is_file():abort(404)
        return send_file(path,as_attachment=request.args.get('ver')!='1',download_name=r['nombre'])
    @app.get('/portal/salir')
    def portal_logout():session.clear();return redirect('/portal/login')
    @app.get('/portal/manifest.webmanifest')
    def portal_manifest():
        manifest={"id":"/portal/","name":"Mi Portal Santa Clara","short_name":"Mi Portal Santa Clara","description":"Portal del Funcionario del Centro Médico Santa Clara","start_url":"/portal/login","scope":"/portal","display":"standalone","background_color":"#f2f7f8","theme_color":"#087c8b","icons":[{"src":"/static/portal-icon-192.png","sizes":"192x192","type":"image/png","purpose":"any maskable"},{"src":"/static/portal-icon-512.png","sizes":"512x512","type":"image/png","purpose":"any maskable"}]}
        import json
        return Response(json.dumps(manifest,ensure_ascii=False),mimetype='application/manifest+json',headers={'Cache-Control':'no-cache'})
