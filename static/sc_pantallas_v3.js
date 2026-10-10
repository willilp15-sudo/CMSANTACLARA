/* Santa Clara ERP V3: progressive enhancement; no form submission or backend changes */
(function(){'use strict';
function setup(){const main=document.querySelector('.erp-workspace');if(!main)return;
// Only wrap data tables. Leave tables inside forms untouched to avoid changing dynamic controls.
main.querySelectorAll('table').forEach(function(t){if(t.closest('.sc3-table-scroll')||t.closest('form')||t.closest('[contenteditable]'))return;
const wrap=document.createElement('div');wrap.className='sc3-table-scroll';t.parentNode.insertBefore(wrap,t);wrap.appendChild(t);
const body=t.tBodies&&t.tBodies[0];if(!body||!t.tHead||body.rows.length<5||t.dataset.sc3NoFilter!==undefined)return;
const toolbar=document.createElement('div');toolbar.className='sc3-page-tools';const count=document.createElement('span');count.className='sc3-table-count';const search=document.createElement('input');search.type='search';search.className='sc3-table-search';search.placeholder='Filtrar registros visibles';search.setAttribute('aria-label','Filtrar registros visibles de esta tabla');
function update(){const q=search.value.trim().toLocaleLowerCase('es');let shown=0;Array.from(body.rows).forEach(function(row){if(row.dataset.sc3Empty==='1')return;const ok=!q||row.textContent.toLocaleLowerCase('es').includes(q);row.hidden=!ok;row.style.display=ok?'':'none';if(ok)shown++});count.textContent=shown+' registros visibles';}
search.addEventListener('input',update);toolbar.append(search,count);wrap.parentNode.insertBefore(toolbar,wrap);update();
});
main.querySelectorAll('form').forEach(function(f){if(f.dataset.sc3Enhanced==='1')return;f.dataset.sc3Enhanced='1';const required=f.querySelectorAll('input[required],select[required],textarea[required]');if(required.length&&f.querySelectorAll('input,select,textarea').length>5){const note=document.createElement('div');note.className='sc3-required-legend';note.textContent='Los campos obligatorios deben completarse antes de guardar.';f.insertBefore(note,f.firstChild);}});
}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',setup);else setup();
})();
