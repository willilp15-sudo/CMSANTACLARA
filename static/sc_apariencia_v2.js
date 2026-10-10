/* Santa Clara ERP V2: navegación visual sin alterar formularios ni endpoints */
document.addEventListener('DOMContentLoaded',()=>{
 const nav=document.querySelector('.wiltech-sc-layout .erp-menu.wiltech-topbar');if(!nav)return;
 const toggle=document.createElement('button');toggle.type='button';toggle.className='scv2-mobile-toggle';toggle.textContent='☰ Menú';toggle.setAttribute('aria-label','Abrir o cerrar menú');toggle.setAttribute('aria-expanded','false');document.body.appendChild(toggle);
 const close=()=>{document.body.classList.remove('scv2-nav-open');toggle.setAttribute('aria-expanded','false')};
 toggle.addEventListener('click',()=>{const open=document.body.classList.toggle('scv2-nav-open');toggle.setAttribute('aria-expanded',String(open))});
 document.addEventListener('keydown',e=>{if(e.key==='Escape')close()});
 document.addEventListener('click',e=>{if(document.body.classList.contains('scv2-nav-open')&&!nav.contains(e.target)&&e.target!==toggle)close()});
 const groups=[...nav.querySelectorAll('details.erp-main-group')];groups.forEach(g=>g.addEventListener('toggle',()=>{if(g.open)groups.forEach(other=>{if(other!==g)other.open=false})}));
});
