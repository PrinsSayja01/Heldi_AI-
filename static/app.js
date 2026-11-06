const state = { city: localStorage.getItem('heidiCity') || 'Berlin', country: localStorage.getItem('heidiCountry') || 'Germany', leads: [], job: null, pollTimer: null, settings: null, cities: [], token: localStorage.getItem('heidiAccessToken') || '' };
const $ = (id) => document.getElementById(id);
const esc = (v='') => String(v ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const initials = (s='') => String(s).trim().split(/\s+/).slice(0,2).map(x=>x[0]||'').join('').toUpperCase() || 'CO';
const fmt = n => Number(n||0).toLocaleString('en-US');
const api = async (url, opts={}) => { const target = `${window.HEIDI_API_BASE || ''}${url}`; const headers={'Content-Type':'application/json',...(opts.headers||{})}; if(state.token) headers.Authorization=`Bearer ${state.token}`; const r=await fetch(target,{...opts,headers}); if(!r.ok){let msg=`Request failed (${r.status})`;try{const j=await r.json();msg=j.detail||msg}catch{};if(r.status===401) showLogin();throw new Error(msg)}; return r.json(); };
function showLogin(){if(!$('authGate'))return;$('authGate').hidden=false;document.querySelector('.app-shell')?.setAttribute('aria-hidden','true');}
function hideLogin(){if(!$('authGate'))return;$('authGate').hidden=true;document.querySelector('.app-shell')?.removeAttribute('aria-hidden');}
async function authenticate(){if(window.HEIDI_REQUIRE_AUTH!==true){hideLogin();return true}if(!state.token){showLogin();return false}try{await api('/api/auth/me');hideLogin();return true}catch{state.token='';localStorage.removeItem('heidiAccessToken');showLogin();return false}}
let toastTimer;
function toast(msg){const t=$('toast');t.textContent=msg;t.classList.add('show');clearTimeout(toastTimer);toastTimer=setTimeout(()=>t.classList.remove('show'),2600)}
function nav(page){document.querySelectorAll('.page').forEach(x=>x.classList.remove('active'));$('page-'+page)?.classList.add('active');document.querySelectorAll('.nav-item').forEach(x=>x.classList.toggle('active',x.dataset.page===page));const names={overview:'Overview',leads:'Lead explorer',research:'New research',settings:'Model & settings'};$('crumbPage').textContent=names[page]||'Overview';if(page==='leads')loadLeads();if(page==='settings')loadSettings();}
document.querySelectorAll('[data-page]').forEach(b=>b.addEventListener('click',()=>nav(b.dataset.page)));
document.querySelectorAll('[data-goto]').forEach(b=>b.addEventListener('click',()=>nav(b.dataset.goto)));

function leadServices(l){const a=[];if(l.weg_management==='Yes')a.push('WEG');if(l.rental_management==='Yes')a.push('Rental');if(l.special_management==='Yes')a.push('Special');return a.length?a.slice(0,2).map(x=>`<span class="mini-pill">${x}</span>`).join(''):'<span class="small-muted">Not confirmed</span>'}
function tierClass(t){return t==='Tier 1'?'tier-1':t==='Tier 2'?'tier-2':'tier-3'}
function scoreCell(l){return `<div class="score-wrap"><span class="score-num">${fmt(l.score)}</span><span class="score-track"><span style="width:${Math.min(100,Math.max(0,l.score||0))}%"></span></span></div>`}
function renderPriority(items){const rows=items.slice(0,7);$('priorityRows').innerHTML=rows.length?rows.map(l=>`<tr data-lead="${esc(l.id)}"><td><div class="company-cell"><div class="company-avatar">${esc(initials(l.name))}</div><div><div class="company-name">${esc(l.name)}</div><div class="company-domain">${esc(l.domain||l.website||'Website not found')}</div></div></div></td><td><div class="service-pills">${leadServices(l)}</div></td><td><div class="contact-mini">${l.contact_person?`<span class="contact-name">${esc(l.contact_person)}</span>`:'<span class="small-muted">No named contact</span>'}${l.contact_email?`<small>${esc(l.contact_email)}</small>`:''}</div></td><td>${scoreCell(l)}</td><td><span class="status-badge">${esc(l.status||'New')}</span></td></tr>`).join(''):'<tr><td colspan="5" class="empty-state">No leads in this city yet. Run a research scan to get started.</td></tr>';
 $('priorityRows').querySelectorAll('tr[data-lead]').forEach(tr=>tr.addEventListener('click',()=>openLead(tr.dataset.lead)));}
function renderAll(items){state.leads=items;$('allLeadRows').innerHTML=items.length?items.map(l=>`<tr data-lead="${esc(l.id)}"><td><div class="company-cell"><div class="company-avatar">${esc(initials(l.name))}</div><div><div class="company-name">${esc(l.name)}</div><div class="company-domain">${esc(l.domain||'No domain')}</div></div></div></td><td>${esc([l.city,l.country].filter(Boolean).join(', '))}</td><td><div class="service-pills">${leadServices(l)}</div></td><td><div class="contact-mini">${l.contact_person?`<span class="contact-name">${esc(l.contact_person)}</span>`:'<span class="small-muted">No named contact</span>'}${l.contact_email?`<small>${esc(l.contact_email)}</small>`:''}</div></td><td>${scoreCell(l)}<span class="tier-badge ${tierClass(l.tier)}">${esc(l.tier)}</span></td><td><span class="confidence-badge ${(l.confidence||'').toLowerCase()}">${esc(l.confidence||'Low')}</span></td><td><span class="status-badge">${esc(l.status||'New')}</span></td><td><span class="muted">↗</span></td></tr>`).join(''):'<tr><td colspan="8" class="empty-state">No matching leads. Try clearing your filters or running research.</td></tr>';
 $('leadCount').textContent=`${fmt(items.length)} leads`;$('tableFooterText').textContent=`Showing ${fmt(items.length)} leads in ${state.city}`;
 $('allLeadRows').querySelectorAll('tr[data-lead]').forEach(tr=>tr.addEventListener('click',()=>openLead(tr.dataset.lead)));}
async function loadDashboard(){try{const [stats,leadRes,cities]=await Promise.all([api(`/api/stats?city=${encodeURIComponent(state.city)}&country=${encodeURIComponent(state.country)}`),api(`/api/leads?city=${encodeURIComponent(state.city)}&country=${encodeURIComponent(state.country)}&limit=2000`),api('/api/cities')]);state.cities=cities.items||[];$('statTotal').textContent=fmt(stats.total);$('statTier1').textContent=fmt(stats.tier1);$('statContacts').textContent=fmt(stats.named_contacts);$('statEmails').textContent=fmt(stats.emails);$('statResearched').textContent=fmt(stats.researched);$('statNeedsValidation').textContent=fmt(Math.max(0,stats.total-stats.researched));$('navLeadCount').textContent=fmt(stats.total);$('snapshotSub').textContent=`${state.city} market · Local prospect database`;$('citySwitcher').innerHTML='';const saved=[...(state.cities||[])];if(!saved.some(x=>x.city===state.city&&x.country===state.country))saved.unshift({city:state.city,country:state.country});saved.forEach(x=>{const o=document.createElement('option');o.value=`${x.city}|${x.country}`;o.textContent=`${x.city}, ${x.country}`;$('citySwitcher').appendChild(o)});$('citySwitcher').value=`${state.city}|${state.country}`;renderPriority(leadRes.items);renderBars(stats);updateExport();}catch(e){toast(e.message)}}
function renderBars(s){const n3=Math.max(0,s.total-s.tier1-s.tier2);const rows=[['Tier 1',s.tier1,'green'],['Tier 2',s.tier2,'amber'],['Tier 3',n3,'gray']];$('tierBars').innerHTML=rows.map(([name,n,cl])=>`<div class="tier-row"><div class="tier-row-head"><span>${name}</span><b>${fmt(n)} <small style="font-weight:400;color:#a3adba">/ ${fmt(s.total)}</small></b></div><div class="tier-track"><div class="tier-fill ${cl}" style="width:${s.total?100*n/s.total:0}%"></div></div></div>`).join('');}
function renderActivity(jobs){const target=$('recentActivity');if(!target)return;if(!jobs.length){target.innerHTML='<div class="empty-copy">No research runs yet. Start with a city and a target market.</div>';return}target.innerHTML=jobs.slice(0,5).map(j=>`<div class="activity-item"><div><b>${esc(j.city)}, ${esc(j.country)}</b><small>${esc(j.status)} · ${fmt(j.found||0)} saved</small></div><span class="status-badge">${esc(j.progress||0)}%</span></div>`).join('');}
async function loadActivity(){try{const result=await api(`/api/jobs?city=${encodeURIComponent(state.city)}&country=${encodeURIComponent(state.country)}`);renderActivity(result.items||[]);}catch(e){renderActivity([]);}}
function updateExport(){
  const city = encodeURIComponent(state.city);
  const country = encodeURIComponent(state.country);
  const csv = $('exportCsvBtn'); if(csv) csv.href = `/api/export.csv?city=${city}&country=${country}`;
  const xlsx = $('exportXlsxBtn'); if(xlsx) xlsx.href = `/api/export.xlsx?city=${city}&country=${country}`;
  const json = $('exportJsonBtn'); if(json) json.href = `/api/export.json?city=${city}&country=${country}`;
}

async function loadLeads(){
  try{
    const q=$('leadSearch').value.trim(),tier=$('tierFilter').value,status=$('statusFilter').value;
    const service=$('serviceFilter')?.value || '', contact=$('contactFilter')?.value || '';
    const p=new URLSearchParams({city:state.city,country:state.country,limit:'2000'});
    if(q)p.set('q',q);
    if(tier)p.set('tier',tier);
    if(status)p.set('status',status);
    const r=await api('/api/leads?'+p.toString());
    
    // Client-side filtering for service and contact type if selected
    let filtered = r.items;
    if(service === 'weg') filtered = filtered.filter(x => x.weg_management === 'Yes');
    else if(service === 'rental') filtered = filtered.filter(x => x.rental_management === 'Yes');
    else if(service === 'special') filtered = filtered.filter(x => x.special_management === 'Yes');
    
    if(contact === 'named') filtered = filtered.filter(x => !!x.contact_person);
    else if(contact === 'email') filtered = filtered.filter(x => !!x.contact_email);
    else if(contact === 'phone') filtered = filtered.filter(x => !!x.phone);

    renderAll(filtered);
  }catch(e){toast(e.message)}
}
let searchDebounce;
['leadSearch','tierFilter','statusFilter','serviceFilter','contactFilter'].forEach(id=>{
  const el = $(id);
  if(el) el.addEventListener(id==='leadSearch'?'input':'change',()=>{
    clearTimeout(searchDebounce);
    searchDebounce=setTimeout(loadLeads,220);
  });
});

async function openLead(id){try{const l=await api(`/api/leads/${encodeURIComponent(id)}`);$('drawerCompany').textContent=l.name;$('drawerDomain').textContent=l.domain||l.website||'Website not found';const sources=(l.sources||[]).filter(x=>x.url);const evidence=l.evidence||[];const gaps=l.gaps||[];const item=(label,value)=>`<div class="detail-item"><small>${esc(label)}</small><b>${value?esc(value):'Not publicly confirmed'}</b></div>`;
 const breakdown=l.raw?.score_breakdown||{};const scoreLabels=[['service_fit','Service fit',35],['portfolio_scale','Portfolio scale',25],['contact_quality','Contact quality',20],['metering_signal','Metering signal',10],['evidence_quality','Evidence quality',10]];
 $('drawerContent').innerHTML=`<div class="drawer-score-row"><div><b>${fmt(l.score)} / 100</b><span>${esc(l.tier)} · ${esc(l.confidence)} confidence</span></div><div style="text-align:right"><b>${fmt(l.completeness)}%</b><span>Data completeness</span></div></div>
 <div class="drawer-section"><h3>Score breakdown</h3><div class="score-detail-list">${scoreLabels.map(([key,label,max])=>`<div class="score-detail"><span>${label}</span><b>${fmt(breakdown[key]||0)} / ${max}</b></div>`).join('')}</div></div>
 <div class="drawer-section"><h3>Company profile</h3><div class="detail-grid">${item('Address',l.address)}${item('Website',l.website)}${item('WEG management',l.weg_management)}${item('Rental management',l.rental_management)}${item('Special property management',l.special_management)}${item('Portfolio units',l.portfolio_units)}${item('Buildings',l.portfolio_buildings)}${item('Digital portal',l.digital_portal)}${item('Metering signal',l.metering_signal)}${item('VDIV member',l.vdiv_member)}</div></div>
 <div class="drawer-section"><h3>Decision-maker & contact</h3><div class="detail-grid">${item('Contact person',l.contact_person)}${item('Role',l.contact_role)}<div class="detail-item"><small>Published business email</small>${l.contact_email?`<a href="mailto:${esc(l.contact_email)}">${esc(l.contact_email)}</a><div class="small-muted">${esc(l.email_type||'Email type not classified')}</div>`:'<b>Not publicly confirmed</b>'}</div>${item('Phone',l.phone)}</div></div>
 <div class="drawer-section"><h3>Why this lead may fit</h3><p style="font-size:10px;line-height:1.6;color:#78869a">${esc(l.rationale||l.summary||'No AI summary available.')}</p></div>
 <div class="drawer-section"><h3>Evidence (${evidence.length})</h3>${evidence.length?evidence.map(e=>`<div class="evidence-item"><b>${esc(e.field||'Source evidence')}</b><p>${esc(e.quote||e.value||'')}</p><a href="${esc(e.source_url)}" target="_blank" rel="noopener noreferrer">${esc(e.source_url)}</a></div>`).join(''):'<div class="gap-item">No validated source excerpts were captured. Review the listed source pages manually.</div>'}</div>
 <div class="drawer-section"><h3>Research gaps / next questions</h3>${gaps.length?gaps.map(g=>`<div class="gap-item">${esc(g)}</div>`).join(''):'<div class="gap-item">No gaps recorded. Confirm all details before outreach.</div>'}</div>
 <div class="drawer-section"><h3>Source register (${sources.length})</h3>${sources.length?sources.map(s=>`<div class="evidence-item"><b>${esc(s.title||s.type||'Public source')}</b><a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(s.url)}</a><p>${esc(s.snippet||'')}</p></div>`).join(''):'<div class="gap-item">No source URLs stored.</div>'}</div>
 <div class="drawer-section"><h3>Correct / enrich lead record</h3><div class="drawer-edit-grid"><label>Name<input id="editContactName" value="${esc(l.contact_person||'')}" placeholder="Public business contact" /></label><label>Role<input id="editContactRole" value="${esc(l.contact_role||'')}" placeholder="e.g. Geschäftsführer" /></label><label>Business email<input id="editContactEmail" value="${esc(l.contact_email||'')}" placeholder="name@company.de" /></label><label>Email type<select id="editEmailType"><option value="unknown" ${l.email_type==='unknown'?'selected':''}>Unknown / not verified</option><option value="generic" ${l.email_type==='generic'?'selected':''}>Generic inbox</option><option value="personal_work" ${l.email_type==='personal_work'?'selected':''}>Named work email</option></select></label><label>Phone<input id="editContactPhone" value="${esc(l.phone||'')}" placeholder="Published business phone" /></label><label>Managed units<input id="editUnits" type="number" min="0" value="${l.portfolio_units??''}" placeholder="Not disclosed" /></label><label>Buildings<input id="editBuildings" type="number" min="0" value="${l.portfolio_buildings??''}" placeholder="Not disclosed" /></label><label>VDIV member<select id="editVdiv"><option ${l.vdiv_member==='Unknown'?'selected':''}>Unknown</option><option ${l.vdiv_member==='Yes'?'selected':''}>Yes</option><option ${l.vdiv_member==='No'?'selected':''}>No</option></select></label></div><div class="drawer-controls"><select id="editStatus"><option ${l.status==='New'?'selected':''}>New</option><option ${l.status==='Qualified'?'selected':''}>Qualified</option><option ${l.status==='Contacted'?'selected':''}>Contacted</option><option ${l.status==='Meeting'?'selected':''}>Meeting</option><option ${l.status==='Not a fit'?'selected':''}>Not a fit</option><option ${l.status==='Seeded'?'selected':''}>Seeded</option></select><button class="button button-primary" id="saveLead">Save lead</button><textarea id="editNotes" placeholder="Add internal notes…">${esc(l.notes||'')}</textarea></div></div>`;
 $('drawerBackdrop').classList.add('open');$('leadDrawer').classList.add('open');$('saveLead').addEventListener('click',async()=>{try{const toInt=id=>$(id).value.trim()===''?null:Number.parseInt($(id).value,10);await api(`/api/leads/${encodeURIComponent(l.id)}`,{method:'PATCH',body:JSON.stringify({status:$('editStatus').value,notes:$('editNotes').value,contact_person:$('editContactName').value.trim()||null,contact_role:$('editContactRole').value.trim()||null,contact_email:$('editContactEmail').value.trim()||null,email_type:$('editEmailType').value,phone:$('editContactPhone').value.trim()||null,portfolio_units:toInt('editUnits'),portfolio_buildings:toInt('editBuildings'),vdiv_member:$('editVdiv').value})});toast('Lead updated');$('drawerBackdrop').classList.remove('open');$('leadDrawer').classList.remove('open');loadDashboard();if($('page-leads').classList.contains('active'))loadLeads();}catch(e){toast(e.message)}});
 }catch(e){toast(e.message)}}
$('closeDrawer').addEventListener('click',()=>{$('drawerBackdrop').classList.remove('open');$('leadDrawer').classList.remove('open')});$('drawerBackdrop').addEventListener('click',()=>{$('drawerBackdrop').classList.remove('open');$('leadDrawer').classList.remove('open')});

async function loadRuntime(){
  try{
    const h=await api('/api/health');
    const ai=h.ai||{};
    const groq=ai.groq||{};
    const ollama=ai.ollama||h.ollama||{};
    const dot=$('sidebarOllamaDot');
    
    // Status in sidebar
    const activeProvider = ai.provider_mode === 'auto' ? (groq.configured && !groq.in_cooldown ? 'Groq (Auto)' : 'Ollama (Auto)') : ai.provider_mode === 'groq' ? 'Groq Cloud' : 'Ollama Local';
    const isReady = (ai.provider_mode === 'groq' && groq.configured) || (ai.provider_mode === 'ollama' && ollama.online) || (ai.provider_mode === 'auto' && (groq.configured || ollama.online));
    
    dot.classList.toggle('online', isReady);
    $('sidebarOllamaStatus').textContent = isReady ? 'Ready' : 'Check AI';
    $('sidebarModel').textContent = activeProvider;
    $('runtimeModel').textContent = activeProvider;
    $('runtimeStatus').textContent = isReady ? 'Active' : 'Offline';
    $('runtimeStatus').className = 'runtime-status ' + (isReady ? 'online' : 'offline');
    $('settingsRuntimeStatus').textContent = isReady ? `${activeProvider} Active` : 'Offline';
    $('settingsRuntimeStatus').className = 'runtime-status ' + (isReady ? 'online' : 'offline');
    
    $('runtimeCopy').textContent = `AI mode: ${ai.provider_mode}. Primary: Groq (${groq.model || 'none'}). Fallback: Ollama (${ollama.model || 'none'}). Total failovers: ${ai.telemetry?.total_fallbacks || 0}.`;
    $('modelNotice').innerHTML = isReady 
      ? `<span class="notice-icon">◉</span><span>AI Router active (${activeProvider}). Primary GroqCloud with automatic local Ollama failover.</span><button class="text-button" data-goto="settings">AI Provider settings →</button>`
      : `<span class="notice-icon">!</span><span>AI providers need attention. Configure Groq key or start local Ollama.</span><button class="text-button" data-goto="settings">Settings →</button>`;
    
    document.querySelectorAll('#modelNotice [data-goto]').forEach(b=>b.addEventListener('click',()=>nav('settings')));
    $('searchSourceText').textContent = `Public web search · ${h.search_provider}`;
    return h;
  }catch(e){
    $('runtimeCopy').textContent='Could not read local runtime status.';
    return null;
  }
           api(`/api/stats?city=${encodeURIComponent(state.city)}&country=${encodeURIComponent(state.country)}`),
           api(`/api/leads?city=${encodeURIComponent(state.city)}&country=${encodeURIComponent(state.country)}&limit=2000`),
           api('/api/cities'),
           api('/api/jobs') // Added jobs API call
}

async function loadSettings(){
  try{
    const s=await api('/api/settings');
    state.settings=s;
    const ai=s.ai||{};
    const groq=ai.groq||{};
    const ollama=ai.ollama||{};
    
    if($('aiProviderMode')) $('aiProviderMode').value = s.ai_provider || 'auto';
    if($('aiFallbackEnabled')) $('aiFallbackEnabled').checked = s.ai_fallback_enabled !== false;
    if($('groqKeyStatus')) $('groqKeyStatus').value = groq.masked_key || 'Not configured in .env';
    if($('groqModel')) $('groqModel').value = s.groq_model || 'openai/gpt-oss-120b';
    
    $('ollamaUrl').value = s.ollama_base_url;
    $('ollamaModel').innerHTML = '';
    const models = ollama.available_models || [];
    const options = [...new Set([s.ollama_model, ...models].filter(Boolean))];
    options.forEach(m => {
      const o = document.createElement('option');
      o.value = m;
      o.textContent = m + (models.includes(m) ? '' : ' · not installed');
      $('ollamaModel').appendChild(o);
    });
    $('ollamaModel').value = s.ollama_model;

    // Update Telemetry
    if($('groqReqCount')) $('groqReqCount').textContent = fmt(groq.stats?.requests || 0);
    if($('groqTokens')) $('groqTokens').textContent = `${fmt(groq.stats?.total_tokens || 0)} tokens (${groq.stats?.last_latency_ms || 0}ms)`;
    if($('ollamaReqCount')) $('ollamaReqCount').textContent = fmt(ollama.stats?.requests || 0);
    if($('ollamaTokens')) $('ollamaTokens').textContent = `${fmt(ollama.stats?.total_tokens || 0)} tokens (${ollama.stats?.last_latency_ms || 0}ms)`;

    // Update Fallback Events Log
    const events = ai.telemetry?.recent_fallback_events || [];
    if($('fallbackEventLog')) {
      if(events.length === 0) {
        $('fallbackEventLog').innerHTML = '<span class="small-muted">No failover events recorded. Primary provider operating normally.</span>';
      } else {
        $('fallbackEventLog').innerHTML = events.map(e => `
          <div style="border-bottom:1px solid #f0f2f5; padding:4px 0;">
            <b>${esc(e.at)}</b>: Switched from <span class="mini-pill">${esc(e.from)}</span> to <span class="mini-pill">${esc(e.to)}</span><br>
            <small style="color:#b67b20;">Reason: ${esc(e.reason)}</small>
          </div>
        `).join('');
      }
    }

    await loadRuntime();
  }catch(e){toast(e.message)}
}

$('refreshModels')?.addEventListener('click',async()=>{
  try{
    const s=await api('/api/ollama/models');
    const sel=$('ollamaModel');
    const selected=sel.value;
    sel.innerHTML='';
    const models = s.available_models || s.models || [];
    [...new Set([selected,...models].filter(Boolean))].forEach(m=>{
      const o=document.createElement('option');
      o.value=m;
      o.textContent=m+(models.includes(m)?'':' · not installed');
      sel.appendChild(o);
    });
    toast(s.online?`${models.length} local models found`:'Ollama is offline');
  }catch(e){toast(e.message)}
});

$('saveSettings')?.addEventListener('click',async()=>{
  try{
    const payload = {
      ai_provider: $('aiProviderMode').value,
      ai_fallback_enabled: $('aiFallbackEnabled').checked,
      groq_model: $('groqModel').value.trim(),
      ollama_base_url: $('ollamaUrl').value.trim(),
      ollama_model: $('ollamaModel').value
    };
    const s=await api('/api/settings',{method:'PUT',body:JSON.stringify(payload)});
    toast('AI Provider settings saved');
    $('connectionResult').textContent = `Settings saved. Active mode: ${s.ai_provider}. Primary: ${s.groq_model}.`;
    await loadSettings();
  }catch(e){toast(e.message)}
});

$('testGroqBtn')?.addEventListener('click', async()=>{
  const btn = $('testGroqBtn');
  btn.disabled = true;
  btn.textContent = 'Testing Groq…';
  try {
    const res = await api('/api/ai/test-groq', { method: 'POST' });
    if(res.success) {
      toast('GroqCloud test succeeded');
      $('connectionResult').textContent = `GroqCloud inference succeeded with ${res.model} in ${res.latency_ms}ms. Tokens: ${res.usage?.total_tokens || 'N/A'}.`;
    } else {
      toast('GroqCloud test failed');
      $('connectionResult').textContent = `GroqCloud failed: ${res.error}`;
    }
    await loadSettings();
  } catch(e) {
    toast(e.message);
    $('connectionResult').textContent = `Groq Error: ${e.message}`;
  } finally {
    btn.disabled = false;
    btn.textContent = 'Test Groq';
  }
});

$('testOllamaBtn')?.addEventListener('click', async()=>{
  const btn = $('testOllamaBtn');
  btn.disabled = true;
  btn.textContent = 'Testing Ollama…';
  try {
    const res = await api('/api/ai/test-ollama', { method: 'POST' });
    if(res.success) {
      toast('Local Ollama test succeeded');
      $('connectionResult').textContent = `Ollama inference succeeded with ${res.model} in ${res.latency_ms}ms. Response: ${JSON.stringify(res.response)}`;
    } else {
      toast('Ollama prompt failed');
      $('connectionResult').textContent = `Ollama failed: ${res.error}`;
    }
    await loadSettings();
  } catch(e) {
    toast(e.message);
    $('connectionResult').textContent = `Ollama Error: ${e.message}`;
  } finally {
    btn.disabled = false;
    btn.textContent = 'Test Ollama';
  }
});

function suggestedKeywords(){const lang=$('searchLanguage').value;const country=$('researchCountry').value.trim().toLowerCase();const german=lang==='de'||(lang==='auto'&&['germany','de','deutschland'].includes(country));$('researchKeywords').value=german?'Hausverwaltung, WEG-Verwaltung, Mietverwaltung, Immobilienverwaltung':'property management company, residential property management, building management, rental property management';}
$('searchLanguage').addEventListener('change',suggestedKeywords);
$('researchCountry').addEventListener('change',()=>{if($('searchLanguage').value==='auto')suggestedKeywords()});
$('startResearch').addEventListener('click',async()=>{const city=$('researchCity').value.trim(),country=$('researchCountry').value.trim();if(city.length<2||country.length<2){toast('Enter a city and country');return}const terms=$('researchKeywords').value.split(',').map(x=>x.trim()).filter(Boolean);const vertical=$('researchVertical').value.trim();if(vertical)terms.unshift(vertical);const max=Number($('maxCompanies').value);try{$('startResearch').disabled=true;$('startResearch').textContent='Starting…';const r=await api('/api/research',{method:'POST',body:JSON.stringify({city,country,max_companies:max,keywords:[...new Set(terms)],use_local_model:$('useLocalModel').checked})});state.job=r.job_id;state.city=city;state.country=country;localStorage.setItem('heidiCity',city);localStorage.setItem('heidiCountry',country);$('citySwitcher').innerHTML='';const activeOpt=document.createElement('option');activeOpt.value=`${city}|${country}`;activeOpt.textContent=`${city}, ${country}`;$('citySwitcher').appendChild(activeOpt);$('citySwitcher').value=`${city}|${country}`;updateExport();renderRunEmpty(false);pollJob(r.job_id);toast(`Research started for ${city}`);}catch(e){toast(e.message)}finally{$('startResearch').disabled=false;$('startResearch').innerHTML='Start research <span>→</span>'}});
function renderRunEmpty(show=true){if(!show)return;}
function renderRun(job){
  const logs=job.logs||[];
  const pct=job.progress||0;
  const terminal=job.status==='completed'||job.status==='failed'||job.status==='cancelled';
  const isRunning = job.status==='running'||job.status==='queued'||job.status==='cancelling';
  
  $('runPanel').innerHTML=`
    <div class="run-active">
      <div class="run-active-head">
        <div>
          <h3>${job.status==='completed'?'Research completed':job.status==='failed'?'Research stopped':job.status==='cancelled'?'Research cancelled':`Researching ${esc(job.city)}, ${esc(job.country)}`}</h3>
          <p>${job.current_step?esc(job.current_step):'Starting the discovery workflow…'}</p>
        </div>
        <div style="display:flex;align-items:center;gap:12px;">
          ${isRunning ? `<button class="button button-danger" id="cancelJobBtn" style="padding:6px 10px;font-size:10px;">Cancel run</button>` : ''}
          <div class="progress-percent">${pct}%</div>
        </div>
      </div>
      <div class="progress-track"><span style="width:${pct}%"></span></div>
      <div class="run-stat-row">
        <span><b>${fmt(job.found||0)}</b> leads saved</span>
        <span><b>${fmt(job.processed||0)}</b> processed</span>
        <span><b>${terminal?'Done': isRunning ? 'Running' : job.status}</b> status</span>
      </div>
      <div class="log-box">
        ${logs.map(x=>`<div class="log-line"><time>${esc(x.at||'')}</time><span>${esc(x.message||'')}</span></div>`).join('')}
        ${job.error?`<div class="log-line">${esc(job.error)}</div>`:''}
      </div>
      ${terminal?`
        <div style="display:flex;justify-content:space-between;align-items:center;margin-top:12px">
          <span class="small-muted">${job.status==='completed'?'New prospects have been saved to your local database.':job.status==='cancelled'?'Run cancelled. Validated prospects were preserved.':'Review the error above, then retry with fewer companies.'}</span>
          <button class="button button-secondary" id="viewNewLeads">View leads →</button>
        </div>`:''}
    </div>
  `;
  if(terminal){
    $('viewNewLeads')?.addEventListener('click',()=>nav('leads'));
  }
  if(isRunning){
    $('cancelJobBtn')?.addEventListener('click', async()=>{
      try {
        $('cancelJobBtn').disabled = true;
        $('cancelJobBtn').textContent = 'Cancelling…';
        await api(`/api/jobs/${job.id}/cancel`, { method: 'POST' });
        toast('Cancellation requested');
      } catch(e) {
        toast(e.message);
      }
    });
  }
}
async function pollJob(id){
  clearTimeout(state.pollTimer);
  try{
    const j=await api(`/api/jobs/${id}`);
    renderRun(j);
    if(j.status==='completed'||j.status==='failed'||j.status==='cancelled'){
      state.job=null;
      loadDashboard();
      if($('page-leads').classList.contains('active'))loadLeads();
      return;
    }
    state.pollTimer=setTimeout(()=>pollJob(id),1600);
  }catch(e){toast(e.message)}
}
$('citySwitcher').addEventListener('change',()=>{const [city,country]=$('citySwitcher').value.split('|');if(!city||!country)return;state.city=city;state.country=country;localStorage.setItem('heidiCity',city);localStorage.setItem('heidiCountry',country);$('researchCity').value=city;$('researchCountry').value=country;loadDashboard();if($('page-leads').classList.contains('active'))loadLeads()});
$('refreshDashboard').addEventListener('click',()=>{loadDashboard();loadRuntime();toast('Dashboard refreshed')});

// --- Import Modal Logic ---
let stagedImport = null;
const modalBackdrop = $('importModalBackdrop');
const importModal = $('importModal');

function openImportDialog() {
  $('importCity').value = state.city;
  $('importCountry').value = state.country;
  $('selectedFileName').textContent = 'No file selected yet';
  $('importPreviewArea').style.display = 'none';
  $('commitImportBtn').disabled = true;
  stagedImport = null;
  modalBackdrop?.classList.add('show');
  importModal?.classList.add('show');
}

function closeImportDialog() {
  modalBackdrop?.classList.remove('show');
  importModal?.classList.remove('show');
  stagedImport = null;
}

$('openImportBtn')?.addEventListener('click', openImportDialog);
$('closeImportModal')?.addEventListener('click', closeImportDialog);
$('cancelImportBtn')?.addEventListener('click', closeImportDialog);
modalBackdrop?.addEventListener('click', closeImportDialog);

$('fileDropArea')?.addEventListener('click', () => $('importFileInput').click());
$('importFileInput')?.addEventListener('change', async (e) => {
  const file = e.target.files[0];
  if(!file) return;
  $('selectedFileName').textContent = file.name;
  
  const form = new FormData();
  form.append('file', file);
  const city = encodeURIComponent($('importCity').value.trim() || state.city);
  const country = encodeURIComponent($('importCountry').value.trim() || state.country);
  
  try {
    const res = await fetch(`/api/import/preview?city=${city}&country=${country}`, {
      method: 'POST',
      body: form
    });
    if(!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Import preview failed');
    }
    const data = await res.json();
    stagedImport = data;
    
    $('previewTotal').textContent = `${fmt(data.total_parsed)} rows parsed`;
    $('previewNew').textContent = `${fmt(data.new_count)} new`;
    $('previewDupes').textContent = `${fmt(data.duplicate_count)} duplicates`;
    
    const rows = data.preview_items || [];
    $('previewRows').innerHTML = rows.map(r => `
      <tr style="${r._is_duplicate ? 'background:#fff8ed;' : ''}">
        <td><b>${esc(r.name)}</b>${r._is_duplicate ? '<br><small style="color:#b67b20">Duplicate match</small>' : ''}</td>
        <td>${esc(r.domain || r.website || 'No website')}</td>
        <td>${esc([r.weg_management==='Yes'?'WEG':'', r.rental_management==='Yes'?'Rental':''].filter(Boolean).join(', ') || 'None')}</td>
        <td><span class="status-badge">${esc(r.status || 'New')}</span></td>
      </tr>
    `).join('');
    
    $('importPreviewArea').style.display = 'block';
    $('commitImportBtn').disabled = (data.total_parsed === 0);
  } catch(err) {
    toast(`Failed to preview: ${err.message}`);
  }
});

$('commitImportBtn')?.addEventListener('click', async () => {
  if(!stagedImport || !stagedImport.all_items) return;
  const btn = $('commitImportBtn');
  btn.disabled = true;
  btn.textContent = 'Importing…';
  
  try {
    const overwrite = $('overwriteDupes').checked;
    const res = await api('/api/import/commit', {
      method: 'POST',
      body: JSON.stringify({
        items: stagedImport.all_items,
        overwrite_duplicates: overwrite
      })
    });
    toast(`Imported ${res.inserted} new leads (${res.updated} updated, ${res.skipped} skipped)`);
    closeImportDialog();
    loadDashboard();
    if($('page-leads').classList.contains('active')) loadLeads();
  } catch(err) {
    toast(`Import commit failed: ${err.message}`);
  } finally {
    btn.disabled = false;
    btn.textContent = 'Commit import';
  }
});

async function init(){try{if(!(await authenticate()))return;await loadRuntime();await loadDashboard();const s=await api('/api/settings');$('researchCity').value=state.city;$('researchCountry').value=state.country;}catch(e){console.error(e);toast(e.message)}}
init();
loadActivity();

$('loginForm')?.addEventListener('submit',async event=>{event.preventDefault();$('loginError').textContent='';try{const result=await fetch(`${window.HEIDI_API_BASE||''}/api/auth/login`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email:$('loginEmail').value,password:$('loginPassword').value})});if(!result.ok)throw new Error((await result.json()).detail||'Sign-in failed');const data=await result.json();state.token=data.access_token;localStorage.setItem('heidiAccessToken',state.token);hideLogin();await loadRuntime();await loadDashboard();await loadActivity();}catch(error){$('loginError').textContent=error.message;}});
