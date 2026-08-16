const state = { project: null, file: null, evidence: [] };
const $ = (id) => document.getElementById(id);
const panels = { upload: $('upload-panel'), analysis: $('analysis-panel'), planning_review: $('planning-panel'), rfp_review: $('rfp-panel') };

function showBusy(message) { $('busy-text').textContent = message; $('busy').classList.remove('hidden'); }
function hideBusy() { $('busy').classList.add('hidden'); }
function alertUser(message) { $('alert').textContent = message; $('alert').classList.remove('hidden'); window.scrollTo({top: 0, behavior: 'smooth'}); }
function clearAlert() { $('alert').classList.add('hidden'); }

async function api(path, options = {}) {
  const response = await fetch(path, { headers: {'Content-Type':'application/json'}, ...options });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `HTTP ${response.status}`);
  return data;
}

function activate(stage) {
  const target = stage === 'complete' ? 'rfp_review' : stage === 'planning_confirmed' ? 'planning_review' : stage;
  Object.entries(panels).forEach(([key, panel]) => panel.classList.toggle('hidden', key !== target));
  const order = ['upload','analysis','planning_review','rfp_review'];
  const index = order.indexOf(target);
  document.querySelectorAll('.step').forEach((step, i) => {
    step.classList.toggle('active', i === index);
    step.classList.toggle('done', i < index || stage === 'complete');
  });
}

function renderProject(project) {
  state.project = project;
  state.evidence = project.evidence || [];
  renderAnalysis(); renderEvidence();
  $('planning-editor').value = project.planning_markdown || '';
  $('rfp-editor').value = project.rfp_markdown || '';
  const planningDone = project.planning_validation?.completed;
  const rfpDone = project.rfp_validation?.completed;
  setConfirmed('planning', planningDone, project.planning_validation);
  setConfirmed('rfp', rfpDone, project.rfp_validation);
  $('generate-rfp').classList.toggle('hidden', !planningDone || !!project.rfp_markdown);
  $('manifest-download').classList.toggle('hidden', !rfpDone);
  if (rfpDone) $('manifest-download').href = `/api/projects/${project.id}/manifest/provenance`;
  activate(project.stage);
}

function setConfirmed(kind, done, validation) {
  const status = $(`${kind}-status`), download = $(`${kind}-download`), box = $(`${kind}-validation`);
  status.textContent = done ? '검증 완료' : '초안'; status.className = `status-chip ${done ? 'green' : 'amber'}`;
  download.classList.toggle('hidden', !done);
  if (done) download.href = `/api/projects/${state.project.id}/download/${kind}`;
  box.classList.toggle('hidden', !validation);
  if (validation) {
    const zip = validation.zip || {};
    box.textContent = done
      ? `검증 게이트 통과 · Kordoc validate · 왕복 변환 · SVG 렌더 · ZIP ${zip.entries || 0}개 엔트리${validation.warnings?.length ? ` · 경고 ${validation.warnings.length}건` : ''}`
      : '검증이 완료되지 않았습니다.';
  }
}

function renderAnalysis() {
  if (!state.project?.analysis) return;
  const labels = {title:'수요명',classification:'기술분야',period:'개발기간',budget:'예산',objective:'개발목표',contents:'개발내용',trends:'동향',need:'필요성·효과'};
  $('field-grid').replaceChildren(...Object.entries(state.project.analysis.fields).map(([key, field]) => {
    const card = document.createElement('div'); card.className = 'field-card';
    const small = document.createElement('small'); small.textContent = labels[key] || key;
    const strong = document.createElement('strong'); strong.textContent = field.value;
    const tag = document.createElement('i'); tag.textContent = field.provenance === 'source_input' ? 'SOURCE INPUT' : 'UNRESOLVED';
    card.append(small,strong,tag); return card;
  }));
  $('mapping-list').replaceChildren(...state.project.analysis.mapping.map(item => {
    const row = document.createElement('div'); row.className = 'map-row';
    const name = document.createElement('span'); name.textContent = item.report_item;
    const tags = document.createElement('span'); tags.className = 'tags';
    const map = {direct:'① 직접',research_needed:'② 조사',decision_needed:'③ 판단'};
    item.classification.forEach(value => { const tag=document.createElement('span'); tag.className='tag'; tag.textContent=map[value]; tags.append(tag); });
    row.append(name,tags); return row;
  }));
  $('decision-list').replaceChildren(...state.project.analysis.questions.map((item, index) => {
    const row=document.createElement('div'); row.className='decision';
    const num=document.createElement('b'); num.textContent=index+1;
    const label=document.createElement('label'); label.textContent=item.question; label.htmlFor=`decision-${item.key}`;
    const input=document.createElement('input'); input.id=`decision-${item.key}`; input.dataset.key=item.key; input.value=state.project.decisions?.[item.key] || ''; input.placeholder='미입력 시 [추가 결정 필요]';
    row.append(num,label,input); return row;
  }));
}

function renderEvidence() {
  $('evidence-list').replaceChildren(...state.evidence.map((item, index) => {
    const row=document.createElement('div'); row.className='evidence-item';
    row.textContent=`${item.status === 'verified' ? '검증됨' : '미검증'} · ${item.organization || '기관 미입력'} · ${item.title || '자료명 미입력'}`;
    row.title='클릭하여 삭제'; row.addEventListener('click',()=>{state.evidence.splice(index,1);renderEvidence();}); return row;
  }));
}

function collectDecisions() {
  return Object.fromEntries([...document.querySelectorAll('.decision input')].map(input => [input.dataset.key,input.value.trim()]).filter(([,value])=>value));
}

async function saveReview() {
  state.project = await api(`/api/projects/${state.project.id}/review`, {method:'PATCH', body:JSON.stringify({decisions:collectDecisions(),evidence:state.evidence})});
  renderProject(state.project); return state.project;
}

$('file-input').addEventListener('change', event => { state.file=event.target.files[0]; $('file-name').textContent=state.file?.name || ''; $('upload-button').disabled=!state.file; });
['dragenter','dragover'].forEach(name=>$('dropzone').addEventListener(name,event=>{event.preventDefault();$('dropzone').classList.add('drag');}));
['dragleave','drop'].forEach(name=>$('dropzone').addEventListener(name,event=>{event.preventDefault();$('dropzone').classList.remove('drag');}));
$('dropzone').addEventListener('drop', event=>{ const file=event.dataTransfer.files[0]; if(file){state.file=file;$('file-name').textContent=file.name;$('upload-button').disabled=false;} });
$('upload-button').addEventListener('click', async()=>{ clearAlert(); showBusy('원본 HWPX를 파싱하고 있습니다'); try { const buffer=await state.file.arrayBuffer(); const bytes=new Uint8Array(buffer); let binary=''; const step=0x8000; for(let i=0;i<bytes.length;i+=step) binary+=String.fromCharCode(...bytes.subarray(i,i+step)); const project=await api('/api/projects',{method:'POST',body:JSON.stringify({filename:state.file.name,content_base64:btoa(binary)})}); renderProject(project); } catch(error){alertUser(error.message);} finally{hideBusy();} });
$('add-evidence').addEventListener('click',()=>{ state.evidence.push({organization:$('ev-org').value,title:$('ev-title').value,date:$('ev-date').value,url:$('ev-url').value,claim:$('ev-claim').value,status:$('ev-verified').checked?'verified':'unverified'}); ['ev-org','ev-title','ev-date','ev-url','ev-claim'].forEach(id=>$(id).value=''); $('ev-verified').checked=false; renderEvidence(); });
$('save-review').addEventListener('click',async()=>{try{await saveReview();}catch(e){alertUser(e.message);}});
$('generate-planning').addEventListener('click',async()=>{showBusy('기획보고서 초안을 구성하고 있습니다');try{await saveReview();renderProject(await api(`/api/projects/${state.project.id}/planning`,{method:'POST',body:'{}'}));}catch(e){alertUser(e.message);}finally{hideBusy();}});
$('save-planning').addEventListener('click',async()=>{try{renderProject(await api(`/api/projects/${state.project.id}/planning`,{method:'PUT',body:JSON.stringify({markdown:$('planning-editor').value})}));}catch(e){alertUser(e.message);}});
$('confirm-planning').addEventListener('click',async()=>{showBusy('Kordoc으로 기획보고서를 생성·검증하고 있습니다');try{await api(`/api/projects/${state.project.id}/planning`,{method:'PUT',body:JSON.stringify({markdown:$('planning-editor').value})});renderProject(await api(`/api/projects/${state.project.id}/planning/confirm`,{method:'POST',body:'{}'}));}catch(e){alertUser(e.message);}finally{hideBusy();}});
$('generate-rfp').addEventListener('click',async()=>{showBusy('확정된 기획보고서를 RFP 명세로 전환하고 있습니다');try{renderProject(await api(`/api/projects/${state.project.id}/rfp`,{method:'POST',body:'{}'}));}catch(e){alertUser(e.message);}finally{hideBusy();}});
$('save-rfp').addEventListener('click',async()=>{try{renderProject(await api(`/api/projects/${state.project.id}/rfp`,{method:'PUT',body:JSON.stringify({markdown:$('rfp-editor').value})}));}catch(e){alertUser(e.message);}});
$('confirm-rfp').addEventListener('click',async()=>{showBusy('Kordoc으로 RFP를 생성·검증하고 있습니다');try{await api(`/api/projects/${state.project.id}/rfp`,{method:'PUT',body:JSON.stringify({markdown:$('rfp-editor').value})});renderProject(await api(`/api/projects/${state.project.id}/rfp/confirm`,{method:'POST',body:'{}'}));}catch(e){alertUser(e.message);}finally{hideBusy();}});
$('resume-toggle').addEventListener('click',async()=>{try{const result=await api('/api/projects');$('project-list').classList.toggle('hidden');$('project-list').replaceChildren(...result.projects.map(project=>{const button=document.createElement('button');button.className='project-link';button.textContent=`${project.title || '제목 미확정'} · ${project.stage}`;button.addEventListener('click',async()=>renderProject(await api(`/api/projects/${project.id}`)));return button;}));}catch(e){alertUser(e.message);}});
document.querySelectorAll('.step').forEach(step=>step.addEventListener('click',()=>{if(state.project || step.dataset.stage==='upload') activate(step.dataset.stage);}));
