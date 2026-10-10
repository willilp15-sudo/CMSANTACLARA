/* Navegación: solo comportamiento visual, sin tocar formularios ni procesos. */
document.addEventListener('DOMContentLoaded',function(){
  const nav=document.getElementById('sc-primary-nav');if(!nav)return;
  const groups=[...nav.querySelectorAll('details.erp-main-group')];
  groups.forEach(group=>group.addEventListener('toggle',()=>{if(group.open)groups.forEach(other=>{if(other!==group)other.open=false})}));
  document.addEventListener('click',event=>{if(!nav.contains(event.target))groups.forEach(group=>group.open=false)});
  document.addEventListener('keydown',event=>{if(event.key==='Escape'){groups.forEach(group=>group.open=false);if(nav.contains(document.activeElement))document.activeElement.blur()}});
});
