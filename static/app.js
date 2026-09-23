document.querySelectorAll('.transaction').forEach(f=>{const mon=f.querySelector('.moneda'),tc=f.querySelector('.tc'),date=f.querySelector('[name=fecha]');if(date&&!date.value)date.value=new Date().toISOString().slice(0,10);async function load(){if(mon.value==='PYG'){tc.value=1;tc.readOnly=true;return}tc.readOnly=false;if(!date.value)return;try{let r=await fetch('/api/tc?fecha='+encodeURIComponent(date.value)+'&moneda='+encodeURIComponent(mon.value));let j=await r.json();if(j.tipo)tc.value=j.tipo}catch(e){}}mon.addEventListener('change',load);date.addEventListener('change',load);load()});
function filtrarTabla(q,id){q=(q||'').toLowerCase().trim();document.querySelectorAll('#'+id+' tr').forEach((r,i)=>{if(i===0)return;r.style.display=!q||r.innerText.toLowerCase().includes(q)?'':'none'})}


// V13.4.2 - control del menú lateral
(function(){
  const body=document.body, sidebar=document.getElementById('sidebar');
  const toggle=document.getElementById('menuToggle'), close=document.getElementById('menuClose');
  const overlay=document.getElementById('sidebarOverlay');
  if(!sidebar||!toggle) return;
  const mobile=()=>window.matchMedia('(max-width:900px)').matches;
  function setAria(open){toggle.setAttribute('aria-expanded',open?'true':'false')}
  function openMenu(){if(mobile()){body.classList.add('sidebar-open')}else{body.classList.remove('sidebar-collapsed');localStorage.setItem('sc_sidebar','open')}setAria(true)}
  function closeMenu(){if(mobile()){body.classList.remove('sidebar-open')}else{body.classList.add('sidebar-collapsed');localStorage.setItem('sc_sidebar','closed')}setAria(false)}
  toggle.addEventListener('click',()=>{const open=mobile()?body.classList.contains('sidebar-open'):!body.classList.contains('sidebar-collapsed');open?closeMenu():openMenu()});
  if(close) close.addEventListener('click',closeMenu);
  if(overlay) overlay.addEventListener('click',closeMenu);
  sidebar.querySelectorAll('a').forEach(a=>a.addEventListener('click',()=>{if(mobile()) closeMenu()}));
  document.addEventListener('keydown',e=>{if(e.key==='Escape') closeMenu()});
  function init(){body.classList.remove('sidebar-open');if(mobile()){body.classList.remove('sidebar-collapsed');setAria(false)}else{const saved=localStorage.getItem('sc_sidebar');body.classList.toggle('sidebar-collapsed',saved==='closed');setAria(saved!=='closed')}}
  window.addEventListener('resize',init); init();
})();
