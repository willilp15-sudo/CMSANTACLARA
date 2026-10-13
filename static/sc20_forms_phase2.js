/* Santa Clara 2.0: mejora progresiva sin cambiar endpoints ni datos */
(()=>{'use strict';
 const marker='data-sc20-enhanced';
 function enhanceForm(form){
  if(form.hasAttribute(marker)||form.closest('.erp-menu,nav'))return;
  form.setAttribute(marker,'1');
  const fields=Array.from(form.querySelectorAll('input,select,textarea'));
  const required=fields.filter(el=>el.required && !el.disabled && el.type!=='hidden');
  if(required.length){
   const note=document.createElement('span');note.className='sc20-required-note';note.textContent='* Campos obligatorios';
   const tools=document.createElement('div');tools.className='sc20-form-tools';tools.appendChild(note);
   const status=document.createElement('span');status.className='sc20-form-status';status.setAttribute('aria-live','polite');tools.appendChild(status);
   form.insertBefore(tools,form.firstChild);
   fields.forEach(el=>{
    if(!el.required||el.type==='hidden')return;
    const id=el.id;
    if(id){const label=form.querySelector('label[for="'+CSS.escape(id)+'"]');if(label&&!label.textContent.includes('*'))label.append(' *')}
    el.addEventListener('input',()=>{el.classList.remove('sc20-form-invalid');status.textContent='';status.removeAttribute('role')});
    el.addEventListener('change',()=>el.classList.remove('sc20-form-invalid'));
   });
   form.addEventListener('invalid',ev=>{if(ev.target&&ev.target.matches('input,select,textarea')){ev.target.classList.add('sc20-form-invalid');status.textContent='Revisá los campos obligatorios o inválidos.';status.setAttribute('role','alert')}},true);
  }
 }
 function enhanceTables(root){root.querySelectorAll('table').forEach(t=>{if(t.closest('.sc20-table-scroll')||t.closest('form')||t.closest('nav'))return;const wrap=document.createElement('div');wrap.className='sc20-table-scroll';t.parentNode.insertBefore(wrap,t);wrap.appendChild(t)})}
 function run(root=document){root.querySelectorAll('form').forEach(enhanceForm);enhanceTables(root)}
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',()=>run());else run();
})();
