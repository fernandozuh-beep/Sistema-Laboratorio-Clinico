
const $=s=>document.querySelector(s),ES=['Recepcionado','Procesando','Validación','Entregado'],NEXT={Recepcionado:'Procesando',Procesando:'Validación',Validación:'Entregado'},PL={1:'Crítica',2:'Urgente',3:'Rutina'};
const EDOT={Recepcionado:'#94a3b8',Procesando:'#f59e0b','Validación':'#3b82f6',Entregado:'#22c55e'},AVC=['#0ea5a5','#6366f1','#f59e0b','#ec4899','#22c55e','#8b5cf6'];
let T=sessionStorage.t,U=JSON.parse(sessionStorage.u||'null'),CAT={},F='',O=[],AL=[],ws,idle;
let FP='',FA='',PG=1;const PER=25;
const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const can=(...r)=>r.includes(U?.rol);
const iniciales=n=>String(n||'?').trim().split(/\s+/).slice(0,2).map(w=>w[0]||'').join('').toUpperCase()||'?';
const avColor=s=>{let h=0;for(const c of String(s||''))h=(h*31+c.charCodeAt(0))>>>0;return AVC[h%AVC.length]};
function edadDe(f){if(!f)return null;const n=new Date(f+'T00:00:00'),h=new Date();if(isNaN(n))return null;let a=h.getFullYear()-n.getFullYear();if(h.getMonth()<n.getMonth()||(h.getMonth()==n.getMonth()&&h.getDate()<n.getDate()))a--;return a>=0?a:null}
function rolLine(u){if(!u)return '';switch(u.rol){case 'admin':return 'Administración del sistema';case 'medico':return 'Médico · '+(u.especialidad||'Medicina');case 'quimico':return 'Químico · Laboratorio clínico';case 'recepcion':return 'Recepción · Admisión';default:return u.rol||''}}
function relCorta(iso){const mins=Math.max(0,Math.round((Date.now()-new Date(iso))/6e4));return mins<1?'ahora':mins<60?`hace ${mins} min`:mins<1440?`hace ${Math.floor(mins/60)} h`:`hace ${Math.floor(mins/1440)} d`}
function toast(t,ok){const d=document.createElement('div');d.className='toast'+(ok?' ok':'');d.setAttribute('role',ok?'status':'alert');d.textContent=t;$('#toasts').append(d);setTimeout(()=>d.remove(),ok?3500:12000)}
async function api(p,o={}){const r=await fetch('/api'+p,{...o,headers:{'Content-Type':'application/json',Authorization:'Bearer '+T}});
 if(r.status==401){logout();throw Error('Sesión expirada')}const d=await r.json().catch(()=>({}));
 if(!r.ok){const e=Error(typeof d.detail=='string'?d.detail:'Revisa los datos capturados');e.detail=d.detail;throw e}return d}
$('#lf').onsubmit=async e=>{e.preventDefault();$('#le').textContent='';
 const r=await fetch('/api/auth/login',{method:'POST',body:new URLSearchParams({username:$('#u').value,password:$('#pw').value})});const d=await r.json();
 if(!r.ok)return $('#le').textContent=d.detail;T=d.access_token;U=d;sessionStorage.t=T;sessionStorage.u=JSON.stringify(d);start()};
function logout(){sessionStorage.clear();location.reload()}$('#out').onclick=logout;
function temaIcon(){const b=$('#themeBtn');if(b)b.textContent=document.documentElement.dataset.theme=='dark'?'☀️':'🌙'}
$('#themeBtn').onclick=()=>{const h=document.documentElement,t=h.dataset.theme=='dark'?'light':'dark';h.dataset.theme=t;try{localStorage.setItem('ocac-theme',t)}catch(e){}temaIcon()};
temaIcon();
$('#navOrd').onclick=()=>{document.querySelectorAll('.nav-it').forEach(n=>n.classList.remove('on'));$('#navOrd').classList.add('on');scrollTo({top:0,behavior:'smooth'})};
function bump(){clearTimeout(idle);idle=setTimeout(()=>{toast('Sesión cerrada por inactividad');setTimeout(logout,1500)},15*60e3)}
['click','keydown'].forEach(e=>addEventListener(e,()=>T&&bump()));
async function start(){if(!T)return;$('#login').hidden=true;$('#app').hidden=false;
 $('#whoName').textContent=U.nombre;$('#whoRol').textContent=rolLine(U);
 $('#whoAv').textContent=$('#sideAv').textContent=iniciales(U.nombre);
 const fl=new Date().toLocaleDateString('es-MX',{weekday:'long',day:'numeric',month:'long',year:'numeric'});$('#fechaLine').textContent='Hospital General · '+fl[0].toUpperCase()+fl.slice(1);
 $('#audBtn').hidden=$('#usrBtn').hidden=!can('admin');$('#nuevo').hidden=!can('admin','medico','recepcion');bump();
 CAT=await api('/catalogo');load();
 ws=new WebSocket(`${location.protocol=='https:'?'wss':'ws'}://${location.host}/ws/alertas?token=${T}`);
 ws.onopen=()=>{$('#liveInd').classList.remove('off');$('#liveTxt').textContent='En vivo'};
 ws.onclose=ws.onerror=()=>{$('#liveInd').classList.add('off');$('#liveTxt').textContent='Sin conexión'};
 ws.onmessage=e=>{const a=JSON.parse(e.data);toast(`⚠ ${a.mensaje} — ${a.paciente} (${a.folio})`);load()};setInterval(load,30000)}
function recibida(x){const d=new Date(x.creado),mins=Math.max(0,Math.round((Date.now()-d)/6e4));
 const rel=mins<1?'ahora':mins<60?`hace ${mins} min`:mins<1440?`hace ${Math.floor(mins/60)} h${mins%60?' '+mins%60+' min':''}`:`hace ${Math.floor(mins/1440)} d`;
 const tarde=x.prioridad==1&&x.estado!='Entregado'&&mins>=120;
 return `${d.toLocaleDateString('es-MX',{day:'2-digit',month:'short'})} ${d.toLocaleTimeString('es-MX',{hour:'2-digit',minute:'2-digit'})}<br>${tarde?`<span class="tag p1">⚠ ${rel}</span>`:`<span class="mut">${rel}</span>`}`}
async function load(){if(!O.length)$('#tb').innerHTML='<tr><td colspan="7" class="empty">Cargando órdenes…</td></tr>';try{const [o0,s,al]=await Promise.all([api(`/ordenes?q=${encodeURIComponent($('#q').value)}&estado=${F=='crit'?'':encodeURIComponent(F)}`),api('/stats'),api('/ordenes')]);const o=F=='crit'?o0.filter(x=>x.prioridad==1&&x.estado!='Entregado'):o0;O=o;AL=al;renderAlertas();
 $('#kpis').innerHTML=`<button class="kpi ${F?'':'on'}" data-f=""><span>Todas</span><b>${s.total}</b></button>`+ES.map(x=>`<button class="kpi ${F==x?'on':''}" data-f="${x}"><span>${x}</span><b>${s.estados[x]||0}</b></button>`).join('')+`<button class="kpi crit ${F=='crit'?'on':''}" data-f="crit"><span>🚨 Críticas abiertas</span><b>${s.criticas}</b></button>`;
 document.querySelectorAll('[data-f]').forEach(b=>b.onclick=()=>{F=b.dataset.f;PG=1;load()});
 if(o.length)render();else{$('#tb').innerHTML='<tr><td colspan="7" class="empty">No hay órdenes con este filtro. Crea una con “Nueva orden”.</td></tr>';$('#pgInfo').textContent='Sin resultados';$('#pgPrev').disabled=$('#pgNext').disabled=true}}catch(e){if(!O.length)$('#tb').innerHTML='<tr><td colspan="7" class="empty">No se pudieron cargar las órdenes. <button class="btn sm sec" onclick="load()">Reintentar</button></td></tr>';toast('No se pudieron cargar las órdenes: '+e.message)}}
function renderAlertas(){const list=[];
 for(const x of AL){if(x.estado=='Entregado')continue;for(const [k,p] of Object.entries(x.analisis||{})){if(p.flag==='crítico'&&p.valor!=null)list.push({x,k,p})}}
 const el=$('#alertList');if(!el)return;
 if(!list.length){el.innerHTML='<div class="okbox">✓ Sin alertas. El panel se actualiza en tiempo real cuando un analizador reporta un valor crítico.</div>';return}
 el.innerHTML=list.map(({x,k,p})=>`<div class="alert"><b>${esc(k)}</b> <span class="v">${p.valor} ${esc(p.u)}</span><small>${esc(x.paciente)} · ${esc(x.folio)} · ${relCorta(x.creado)}${x.solicitante?' · '+esc(x.solicitante):''}</small><button class="go" onclick="atender(${x.id})">Atender ahora →</button></div>`).join('')}
function atender(id){if(!O.find(o=>o.id==id)){const x=AL.find(o=>o.id==id);if(x)O.unshift(x)}res(id)}
function fila(x){const hayM=(can('admin','medico','recepcion')&&x.estado!='Entregado')||['Validación','Entregado'].includes(x.estado)||can('admin');const ed=edadDe(x.fecha_nac);
 return `<tr class="${x.critico||(x.prioridad==1&&x.estado!='Entregado')?'c':''}"><td><div class="who"><span class="av2" style="background:${avColor(x.paciente)}">${esc(iniciales(x.paciente))}</span><span class="pac"><b>${esc(x.paciente)}</b><small>${esc(x.expediente)}${ed!=null?' · '+ed+' años':''}</small></span></div></td><td class="folio">${esc(x.folio)}</td><td>${esc(x.tipo_analisis)}<br><span class="mut">${esc(x.area)}</span></td>
 <td><span class="tag p${x.prioridad}">${PL[x.prioridad]}</span></td><td><span class="st"><i style="background:${EDOT[x.estado]||'#94a3b8'}"></i>${x.estado}</span></td><td>${recibida(x)}</td><td><div class="acts">
 <button class="b2" onclick="res(${x.id})">${can('admin','quimico')&&x.estado!='Entregado'?'Resultados':'Ver'}</button>
 ${can('admin','quimico')&&NEXT[x.estado]?`<button class="b1" onclick="avanzar(${x.id},'${NEXT[x.estado]}')">→ ${NEXT[x.estado]}</button>`:''}
 ${hayM?`<button class="b3" aria-haspopup="menu" aria-expanded="false" aria-label="Más acciones para ${esc(x.folio)}" onclick="toggleMenu(event,${x.id})">⋯</button>`:''}</div></td></tr>`}
var menuEl=null,menuBtn=null;
function closeMenu(){if(menuEl){menuEl.remove();menuEl=null}if(menuBtn){menuBtn.setAttribute('aria-expanded','false');menuBtn=null}}
function toggleMenu(ev,id){const b=ev.currentTarget,was=menuBtn===b;closeMenu();if(was)return;
 const x=O.find(o=>o.id==id);if(!x)return;const items=[];
 if(can('admin','medico','recepcion')&&x.estado!='Entregado')items.push(`<button role="menuitem" onclick="closeMenu();formOrden(${id})">Editar</button>`);
 if(['Validación','Entregado'].includes(x.estado))items.push(`<button role="menuitem" onclick="closeMenu();pdf(${id})">PDF</button>`,`<button role="menuitem" onclick="closeMenu();fhir(${id})">FHIR</button>`);
 if(can('admin'))items.push(`<button role="menuitem" class="danger" onclick="closeMenu();del(${id})">Eliminar</button>`);
 if(!items.length)return;
 const m=document.createElement('div');m.className='menu';m.setAttribute('role','menu');m.innerHTML=items.join('');document.body.append(m);
 const r=b.getBoundingClientRect();m.style.left=Math.max(8,Math.min(r.right-m.offsetWidth,innerWidth-m.offsetWidth-8))+'px';
 m.style.top=(r.bottom+4+m.offsetHeight>innerHeight?Math.max(8,r.top-m.offsetHeight-4):r.bottom+4)+'px';
 b.setAttribute('aria-expanded','true');menuEl=m;menuBtn=b;const f=m.querySelector('button');if(f)f.focus()}
document.addEventListener('click',e=>{if(menuEl&&!menuEl.contains(e.target)&&menuBtn&&!menuBtn.contains(e.target))closeMenu()});
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&menuEl){const b=menuBtn;closeMenu();if(b)b.focus()}});
addEventListener('scroll',()=>closeMenu(),true);
function render(){if(!O.length)return;closeMenu();
 const rows=O.filter(x=>(!FP||x.prioridad==+FP)&&(!FA||x.area==FA));
 const pages=Math.max(1,Math.ceil(rows.length/PER));if(PG>pages)PG=pages;
 const as=$('#fArea'),set=new Set(O.map(x=>x.area));if(FA)set.add(FA);
 as.innerHTML='<option value="">Todas</option>'+[...set].sort().map(a=>`<option ${a==FA?'selected':''}>${esc(a)}</option>`).join('');
 const page=rows.slice((PG-1)*PER,PG*PER);
 $('#tb').innerHTML=page.length?page.map(fila).join(''):'<tr><td colspan="7" class="empty">Ninguna orden coincide con la prioridad o el área elegidas.</td></tr>';
 $('#pgInfo').textContent=rows.length?`Página ${PG} de ${pages} · ${rows.length} ${rows.length==1?'orden':'órdenes'}`:'Sin resultados';
 $('#pgPrev').disabled=PG<=1;$('#pgNext').disabled=PG>=pages}
$('#fPri').onchange=e=>{FP=e.target.value;PG=1;render()};
$('#fArea').onchange=e=>{FA=e.target.value;PG=1;render()};
$('#pgPrev').onclick=()=>{if(PG>1){PG--;render()}};
$('#pgNext').onclick=()=>{if(O.length){PG++;render()}};
$('#q').oninput=()=>{clearTimeout(window.dq);window.dq=setTimeout(()=>{PG=1;load()},300)};
function cerrar(){$('#dlg').close()}
async function act(fn,msg){if(act.busy)return;act.busy=true;try{await fn();toast(msg,1);cerrar();load()}catch(e){toast(e.message)}finally{act.busy=false}}
function avanzar(id,e){act(()=>api(`/ordenes/${id}/estado`,{method:'PUT',body:JSON.stringify({estado:e})}),'Estado actualizado: '+e)}
function del(id){const x=O.find(o=>o.id==id);if(!x)return;
 $('#dlg').innerHTML=`<h2 style="margin:0">Eliminar orden</h2><p>¿Eliminar la orden <b>${esc(x.folio)}</b> de ${esc(x.paciente)}?<br><span class="mut">Quedará registrada en la bitácora.</span></p>
 <div class="foot"><button class="btn sec" onclick="cerrar()">Cancelar</button><button class="btn red" id="delOk">Eliminar</button></div>`;
 $('#delOk').onclick=()=>act(()=>api('/ordenes/'+id,{method:'DELETE'}),'Orden eliminada');
 $('#dlg').showModal()}
function erroresCampo(e){const mapa={expediente:'e',nombre:'n',sexo:'s',fecha_nac:'f',tipo_analisis:'t',prioridad:'p',solicitante:'m',observaciones:'o'};let n=0;
 const poner=(campo,msg)=>{const suf=mapa[campo],p=suf&&document.getElementById('fe_'+suf);if(!p)return;const inp=document.getElementById('f_'+suf);if(inp)inp.setAttribute('aria-invalid','true');p.textContent=msg;p.hidden=false;n++};
 if(Array.isArray(e.detail))e.detail.forEach(d=>{const loc=Array.isArray(d.loc)?String(d.loc[d.loc.length-1]):'';poner(loc,d.msg||'Dato inválido')});
 else if(typeof e.detail=='string'){const s=e.detail.toLowerCase();Object.keys(mapa).forEach(c=>{if(s.includes(c))poner(c,e.detail)})}
 return n>0}
function formOrden(id){const x=id?O.find(o=>o.id==id):{sexo:'M',prioridad:3,solicitante:U.nombre,observaciones:''};
 const areas={};Object.entries(CAT).forEach(([k,v])=>{const a=v.area||'Sin área';(areas[a]=areas[a]||[]).push(k)});
 $('#dlg').innerHTML=`<h2 style="margin:0">${id?'Editar orden '+esc(x.folio):'Nueva orden de análisis'}</h2><div class="g2">
 <div><label for="f_e">Expediente *</label><input id="f_e" required value="${esc(x.expediente)}" ${id?'readonly':''} placeholder="EXP-0007"><p class="ferr" id="fe_e" hidden></p></div>
 <div><label for="f_n">Nombre del paciente *</label><input id="f_n" required value="${esc(x.paciente)}"><p class="ferr" id="fe_n" hidden></p></div>
 <div><label for="f_s">Sexo</label><select id="f_s"><option value="M" ${x.sexo=='M'?'selected':''}>Masculino</option><option value="F" ${x.sexo=='F'?'selected':''}>Femenino</option></select></div>
 <div><label for="f_f">Fecha de nacimiento</label><input id="f_f" type="date" value="${x.fecha_nac||''}"><p class="mut" id="f_edad" style="margin:2px 0 0"></p><p class="ferr" id="fe_f" hidden></p></div>
 <div><label for="f_t">Análisis *</label><select id="f_t" required>${Object.entries(areas).map(([a,ks])=>`<optgroup label="${esc(a)}">${ks.map(k=>`<option ${x.tipo_analisis==k?'selected':''}>${esc(k)}</option>`).join('')}</optgroup>`).join('')}</select><p class="ferr" id="fe_t" hidden></p></div>
 <div><label for="f_p">Prioridad</label><select id="f_p">${[1,2,3].map(p=>`<option value="${p}" ${x.prioridad==p?'selected':''}>${PL[p]}</option>`).join('')}</select></div></div>
 <label for="f_m">Médico solicitante</label><input id="f_m" value="${esc(x.solicitante)}"><label for="f_o">Observaciones clínicas</label><textarea id="f_o" rows="2">${esc(x.observaciones)}</textarea>
 <div class="foot"><button class="btn sec" onclick="cerrar()">Cancelar</button><button class="btn" id="sv">Guardar orden</button></div>`;
 const edad=()=>{const el=$('#f_edad'),v=$('#f_f').value;if(!v){el.textContent='';return}const a=edadDe(v);el.textContent=a==null?'':'Edad: '+a+(a==1?' año':' años')};
 $('#f_f').addEventListener('input',edad);edad();
 $('#sv').onclick=async()=>{const btn=$('#sv');if(btn.disabled)return;btn.disabled=true;
  document.querySelectorAll('.ferr').forEach(p=>{p.hidden=true;p.textContent=''});document.querySelectorAll('#dlg [aria-invalid]').forEach(i=>i.removeAttribute('aria-invalid'));
  const b={expediente:$('#f_e').value.trim(),nombre:$('#f_n').value.trim(),sexo:$('#f_s').value,fecha_nac:$('#f_f').value||null,tipo_analisis:$('#f_t').value,prioridad:+$('#f_p').value,solicitante:$('#f_m').value,observaciones:$('#f_o').value};
  try{await api(id?'/ordenes/'+id:'/ordenes',{method:id?'PUT':'POST',body:JSON.stringify(b)});toast(id?'Orden actualizada':'Orden creada',1);cerrar();load()}catch(e){if(!erroresCampo(e))toast(e.message)}finally{btn.disabled=false}};
 $('#dlg').showModal()}
$('#nuevo').onclick=()=>can('admin','medico','recepcion')?formOrden():toast('Tu rol no puede crear órdenes');
function flagDe(v,p){if(v==null||!p)return null;if((p.cmin!=null&&v<p.cmin)||(p.cmax!=null&&v>p.cmax))return 'crítico';return v<p.min?'bajo':v>p.max?'alto':'normal'}
function deltaTag(d,p){const fv=flagDe(d.actual,p),serio=fv&&fv!=='normal';
 return ` <span class="tag ${serio?'f-crítico':'f-alto'}" title="${serio?'Cambio brusco y el valor actual está fuera de rango':'Cambio brusco, pero el valor actual sigue dentro de rango'}">Δ ${d.pct>0?'+':''}${d.pct}% vs ${new Date(d.fecha).toLocaleDateString('es-MX')}</span>`}
async function res(id){const x=O.find(o=>o.id==id);if(!x)return;const edit=can('admin','quimico')&&x.estado!='Entregado';
 const rid=k=>'r_'+k.replace(/[^a-zA-Z0-9_-]/g,'_');
 $('#dlg').innerHTML=`<h2 style="margin:0">${esc(x.tipo_analisis)}</h2><p class="mut">${esc(x.paciente)} · ${esc(x.folio)} · ${x.estado}${x.observaciones?'<br>Nota: '+esc(x.observaciones):''}</p>
 ${Object.entries(x.analisis).map(([k,p])=>{const crit=(p.cmin!=null||p.cmax!=null)?`<br><span class="mut">Crítico: ${[p.cmin!=null?'&lt; '+p.cmin:null,p.cmax!=null?'&gt; '+p.cmax:null].filter(Boolean).join(' o ')}</span>`:'';
 return `<div class="row"><label style="margin:0" for="${rid(k)}">${esc(k)}<br><span class="mut">Ref. ${p.min}–${p.max} ${esc(p.u)}</span>${crit}</label>
 <input id="${rid(k)}" data-k="${esc(k)}" type="number" step="any" value="${p.valor??''}" ${edit?'':'disabled'}><span>${p.flag?`<span class="tag f-${p.flag}">${p.flag.toUpperCase()}</span>`:'<span class="mut">Pendiente</span>'}</span></div>`}).join('')}
 <div class="foot"><button class="btn sec" onclick="cerrar()">Cerrar</button>${edit?'<button class="btn" id="sr">Guardar resultados</button>':''}</div>`;
 if(edit)$('#sr').onclick=()=>{const r={};document.querySelectorAll('[data-k]').forEach(i=>{if(i.value!=='')r[i.dataset.k]=+i.value});
  act(()=>api(`/ordenes/${id}/resultados`,{method:'PUT',body:JSON.stringify({resultados:r})}),'Resultados guardados')};
 $('#dlg').showModal();
 const f=$('#dlg .foot');
 if(x.estado!='Recepcionado')f.insertAdjacentHTML('afterbegin',`<button class="btn sec" onclick="pdf(${id})">PDF</button><button class="btn sec" onclick="fhir(${id})">FHIR</button>`);
 try{const h=await api(`/ordenes/${id}/historial`),P=CAT[x.tipo_analisis].params;
  const t=Object.entries(h.series).filter(([k,s])=>s.length>1).map(([k,s])=>{const d=h.delta[k],last=s[s.length-1];
  return `<div style="margin-top:10px"><b>${esc(k)}</b> <span class="mut">${s.length} resultados · ${esc(P[k].u)}</span>${d?deltaTag(d,P[k]):''}<br><span class="mut">Último: <b>${last.valor} ${esc(P[k].u)}</b> · ${new Date(last.fecha).toLocaleDateString('es-MX')}</span>${spark(s,P[k])}</div>`}).join('');
  if(t)f.insertAdjacentHTML('beforebegin',`<h3 style="margin:16px 0 0">Tendencia del paciente</h3>${t}`)}catch(e){}}
$('#audBtn').onclick=async()=>{const a=await api('/auditoria');$('#dlg').innerHTML=`<h2 style="margin:0">Bitácora de auditoría</h2><div style="max-height:60vh;overflow:auto"><table style="min-width:0">${a.map(r=>`<tr><td class="mut">${new Date(r.fecha).toLocaleString('es-MX')}</td><td>${esc(r.usuario)}</td><td>${esc(r.accion)} ${esc(r.folio||'')}</td></tr>`).join('')}</table></div><div class="foot"><button class="btn sec" onclick="cerrar()">Cerrar</button></div>`;$('#dlg').showModal()};
const nav=performance.getEntriesByType('navigation')[0];
if(nav&&nav.type==='back_forward'&&sessionStorage.t){sessionStorage.clear();T=null;U=null}
addEventListener('pageshow',e=>{if(e.persisted&&T)logout()});
if(T)start();


async function blob(p){const r=await fetch(p,{headers:{Authorization:'Bearer '+T}});if(!r.ok){const d=await r.json().catch(()=>({}));throw Error(d.detail||'No se pudo generar')}return r.blob()}
async function pdf(id){const w=window.open('','_blank');try{w.location=URL.createObjectURL(await blob(`/api/ordenes/${id}/pdf`))}catch(e){w.close();toast(e.message)}}
async function fhir(id){try{const a=document.createElement('a');a.href=URL.createObjectURL(await blob(`/api/ordenes/${id}/fhir`));a.download='fhir-orden-'+id+'.json';a.click()}catch(e){toast(e.message)}}
function spark(pts,p){const W=300,H=64,v=pts.map(x=>x.valor),lo=Math.min(...v,p.min),hi=Math.max(...v,p.max),r=(hi-lo)||1,y=n=>H-6-(n-lo)/r*(H-12),x=i=>pts.length>1?8+i*(W-16)/(pts.length-1):W/2;
 return `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Tendencia"><rect x="0" y="${y(p.max)}" width="${W}" height="${Math.max(2,y(p.min)-y(p.max))}" fill="#7dd3fc" opacity=".25"/><polyline fill="none" stroke="#4f46e5" stroke-width="2" points="${pts.map((q,i)=>x(i)+','+y(q.valor)).join(' ')}"/>${pts.map((q,i)=>`<circle cx="${x(i)}" cy="${y(q.valor)}" r="${i==pts.length-1?5:3}" fill="#4f46e5"><title>${q.valor} · ${new Date(q.fecha).toLocaleDateString('es-MX')}</title></circle>`).join('')}</svg>`}
$('#usrBtn').onclick=users;
async function users(){const L=await api('/usuarios');window.UL=L;
 $('#dlg').innerHTML=`<h2 style="margin:0">Usuarios del sistema</h2><table style="min-width:0">${L.map(x=>`<tr><td><b>${esc(x.nombre)}</b><br><span class="mut">${esc(x.username)} · ${x.rol}${x.especialidad?' · '+esc(x.especialidad):''}${x.activo?'':' · inactivo'}</span></td><td><button class="btn sm sec" onclick="uform(${x.id})">Editar</button></td></tr>`).join('')}</table><div class="foot"><button class="btn sec" onclick="cerrar()">Cerrar</button><button class="btn" onclick="uform()">+ Nuevo usuario</button></div>`;
 if(!$('#dlg').open)$('#dlg').showModal()}
function uform(id){const x=id?UL.find(u=>u.id==id):{rol:'medico',activo:true,especialidad:''};
 $('#dlg').innerHTML=`<h2 style="margin:0">${id?'Editar usuario':'Nuevo usuario'}</h2><label>Usuario (minúsculas, sin espacios)</label><input id="u_u" value="${esc(x.username)}" ${id?'readonly':''}><label>Nombre completo</label><input id="u_n" value="${esc(x.nombre)}"><label>Rol</label><select id="u_r">${['medico','quimico','recepcion','admin'].map(r=>`<option ${x.rol==r?'selected':''}>${r}</option>`).join('')}</select><label>Especialidad</label><input id="u_e" value="${esc(x.especialidad||'')}" placeholder="Ej. Medicina interna (solo aplica a médicos)"><label>${id?'Nueva contraseña (vacío = no cambiar)':'Contraseña (mínimo 8 caracteres)'}</label><input id="u_p" type="password" autocomplete="new-password"><label style="display:flex;gap:8px;align-items:center"><input id="u_a" type="checkbox" style="width:auto" ${x.activo?'checked':''}>Cuenta activa</label><div class="foot"><button class="btn sec" onclick="users()">Volver</button><button class="btn" id="u_s">Guardar usuario</button></div>`;
 $('#u_s').onclick=async()=>{try{await api(id?'/usuarios/'+id:'/usuarios',{method:id?'PUT':'POST',body:JSON.stringify({username:$('#u_u').value.trim(),nombre:$('#u_n').value.trim(),rol:$('#u_r').value,especialidad:$('#u_e').value.trim(),password:$('#u_p').value||null,activo:$('#u_a').checked})});toast('Usuario guardado',1);users()}catch(e){toast(e.message)}}}
