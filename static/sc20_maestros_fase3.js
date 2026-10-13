/* Santa Clara ERP 2.0 Fase 3: búsqueda local no destructiva en tablas de maestros. */
(function(){'use strict';
 const paths=['/patients','/products','/providers','/thirdparties'];
 function init(){
   const path=window.location.pathname.toLowerCase();
   if(!paths.some(p=>path===p||path.startsWith(p+'/')))return;
   document.querySelectorAll('table').forEach((table,index)=>{
     if(table.dataset.sc20Search==='1'||table.closest('.sc20-form-tools'))return;
     const body=table.tBodies&&table.tBodies[0];if(!body||body.rows.length<3)return;
     const host=document.createElement('div');host.className='sc20-form-tools';
     const label=document.createElement('label');const id='sc20-search-'+index;label.htmlFor=id;label.textContent='Buscar en registros visibles';
     const input=document.createElement('input');input.id=id;input.type='search';input.placeholder='Filtrar esta tabla';input.autocomplete='off';
     const count=document.createElement('span');count.className='sc20-count';count.setAttribute('aria-live','polite');
     const clear=document.createElement('button');clear.type='button';clear.textContent='Limpiar';
     function filter(){const q=input.value.trim().toLocaleLowerCase();let shown=0;Array.from(body.rows).forEach(row=>{const ok=!q||row.textContent.toLocaleLowerCase().includes(q);row.classList.toggle('sc20-hidden-row',!ok);if(ok)shown++;});count.textContent=shown+' de '+body.rows.length+' filas cargadas';}
     input.addEventListener('input',filter);clear.addEventListener('click',()=>{input.value='';filter();input.focus();});
     host.append(label,input,clear,count);table.parentNode.insertBefore(host,table);table.dataset.sc20Search='1';filter();
   });
 }
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
