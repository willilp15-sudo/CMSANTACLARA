import json, os, time, threading, tkinter as tk
from urllib.request import Request, urlopen
from urllib.parse import urlencode
try:
 import pyttsx3
except Exception:
 pyttsx3=None
BASE_DIR=os.path.dirname(os.path.abspath(__file__))
CONFIG=os.path.join(BASE_DIR,'llamador_config.json')
DEFAULT={"url":"https://santa-clara-erp.onrender.com","token":"CAMBIAR_TOKEN","dispositivo":"LLAMADOR-PRINCIPAL","sector":"Sala de espera","intervalo":3}
if not os.path.exists(CONFIG):
 open(CONFIG,'w',encoding='utf-8').write(json.dumps(DEFAULT,indent=2,ensure_ascii=False))
cfg=json.load(open(CONFIG,encoding='utf-8'))
root=tk.Tk();root.title('Llamador Santa Clara');root.attributes('-fullscreen',True);root.configure(bg='white')
head=tk.Label(root,text='CENTRO MÉDICO SANTA CLARA',font=('Arial',28,'bold'),bg='white');head.pack(pady=30)
patient=tk.Label(root,text='LLAMADA EN ESPERA',font=('Arial',42,'bold'),bg='white',wraplength=1200);patient.pack(pady=40)
detail=tk.Label(root,text=cfg.get('sector','Sala de espera'),font=('Arial',28),bg='white',wraplength=1200);detail.pack(pady=20)
status=tk.Label(root,text='Conectando con el ERP...',font=('Arial',14),bg='white');status.pack(side='bottom',pady=20)
root.bind('<Escape>',lambda e: root.attributes('-fullscreen',False))
engine=pyttsx3.init() if pyttsx3 else None

def call(path,method='GET',body=None):
 base=cfg['url'].rstrip('/');headers={'X-Llamador-Token':cfg['token']}
 data=json.dumps(body).encode() if body is not None else None
 if data:headers['Content-Type']='application/json'
 req=Request(base+path,data=data,headers=headers,method=method)
 return json.loads(urlopen(req,timeout=20).read().decode())

def ui_call(x):
 patient.config(text=x.get('paciente','PACIENTE').upper());detail.config(text='Dirigirse al CONSULTORIO '+str(x.get('consultorio_numero') or '')+'\n'+str(x.get('medico') or ''));root.update()
 if engine:
  engine.say(x.get('texto') or '');engine.runAndWait()
 else:
  try: import winsound;winsound.MessageBeep()
  except Exception: pass
 try:call('/api/llamador/%s/confirmar'%x['id'],'POST',{'dispositivo':cfg['dispositivo']})
 except Exception:pass

def worker():
 while True:
  try:
   q=urlencode({'dispositivo':cfg['dispositivo'],'sector':cfg.get('sector','Sala de espera')});call('/api/llamador/ping?'+q);r=call('/api/llamador/pendientes?'+urlencode({'dispositivo':cfg['dispositivo']}));root.after(0,lambda:status.config(text='CONECTADO AL ERP · '+cfg['dispositivo']))
   if r.get('llamada'):root.after(0,ui_call,r['llamada'])
  except Exception as e:root.after(0,lambda e=e:status.config(text='ERROR DE CONEXIÓN: '+str(e)))
  time.sleep(max(2,int(cfg.get('intervalo',3))))
threading.Thread(target=worker,daemon=True).start();root.mainloop()
