(() => {
  const root = document.getElementById('dns-campus');
  const main = root.querySelector('#ds-main');
  const boot = JSON.parse(document.getElementById('campus-config').textContent);
  let page = boot.page || 'home', step = 0;
  let assessment = boot.result || null, busy = false, submitting = false;
  const recordFilters = {student_id:'', tier:'', cohort_year:''};
  const tiers = ["You're doing ok", 'Worth a check-in', 'Please reach out'];
  let recordsRequest = 0, searchTimer;
  const survey = boot.survey;
  const questions = Object.fromEntries(survey.questions.map(q=>[q.key,q]));
  const answers = Object.fromEntries(survey.questions.map(q=>[q.key,null]));
  Object.assign(answers,{student_id:'',feelings_text:''});
  const chapters = survey.sections.map(section=>section.title);
  const reviewStep = chapters.length;
  const escape = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function plant(g=1){return `<div class="ds-plant" aria-hidden="true" style="--grow:${g}"><div class="ds-stem"><div class="ds-leaf"></div><div class="ds-leaf r"></div><div class="ds-leaf s"></div></div><div class="ds-pot"></div></div>`}
function home(){main.innerHTML=`<section class="ds-hero-video"><video class="ds-video" autoplay muted loop playsinline poster="/static/video/poster.jpg"><source src="/static/video/hero.mp4" type="video/mp4"></video><div class="ds-video-overlay"><div class="ds-video-content"><p class="ds-kicker">Student wellbeing</p><h1>A private stress check-in for SIT students.</h1><p>Notice how stress, sleep, study load and support are affecting you. Get a structured summary and a few practical next steps. Not a diagnosis.</p><div class="ds-actions"><button class="ds-primary" data-action="start">Start check-in</button><a class="ds-secondary" href="mailto:SITCounselling@SingaporeTech.edu.sg">Talk to SIT Counselling</a></div><p class="ds-note">11 validated questions · about 3 minutes · your student ID is never sent to the AI</p></div></div></section><section class="ds-hero"><div><p class="ds-kicker">What this offers</p><h2>Early support, grounded in research.</h2><p>Validated questions on stress, sleep, study load, finances and support. A structured summary and practical next steps. Wellbeing guidance only.</p></div><aside class="ds-aside"><h2>What you can expect</h2><ol class="ds-steps"><li><strong>Private answers</strong><span>Research-based questions on stress, rest, study, finances and support.</span></li><li><strong>Clear summary</strong><span>A structured score, tier and suggestions. Wellbeing guidance only.</span></li><li><strong>Support nearby</strong><span>SIT Counselling and national helplines are always one tap away.</span></li></ol></aside></section><section class="ds-bottom"><article class="ds-feature"><span class="ds-num">01</span><h3>Early check-in</h3><p>Spot building stress before it affects studies, sleep or wellbeing.</p></article><article class="ds-feature"><span class="ds-num">02</span><h3>Research-based</h3><p>Questions adapted from PSS-4, PSQI, PAS, IFDFW and MSPSS instruments.</p></article><article class="ds-feature"><span class="ds-num">03</span><h3>Privacy first</h3><p>Your ID stays with SIT staff. It is never included in the AI request.</p></article></section><section class="ds-research"><h2>Grounded in validated instruments</h2><p>Results are adapted scores for guidance, not clinical PSS-4, PSQI or MSPSS diagnoses.</p><p class="ds-sources">Sources: Cohen et al. (1983); Buysse et al. (1989); Bedewy & Gabriel (2015); Prawitz et al. (2006); Zimet et al. (1988).</p></section>`}
  function field(label, id, control, help='') {
    return `<div class="ds-field"><label class="ds-label" for="${id}">${label}</label>${control}<div class="ds-help">${help}</div></div>`;
  }
  function answerText(key, value=answers[key]) {
    if(value===null || value===undefined || value==='')return 'Not shared';
    const q=questions[key];
    if(!q)return String(value);
    if(q.options)return `${value} · ${q.options[+value-q.min]}`;
    return `${value} ${q.unit}`;
  }
  function questionControl(q) {
    if(q.kind==='slider' && answers[q.key]===null) answers[q.key]=q.default;
    const value=answers[q.key];
    const helpId=q.key+'-help';
    const title=`<h3 class="ds-q-title" id="${q.key}-title">${q.kind==='slider'?`<label for="${q.key}">${escape(q.prompt)}</label>`:escape(q.prompt)}</h3>`;
    if(q.kind==='slider'){
      const shown=escape(answerText(q.key, value));
      return `<div class="ds-question" id="question-${q.key}">
      ${title}
      <div class="ds-big-value"><output id="${q.key}-value" for="${q.key}" aria-live="polite">${shown}</output></div>
      <input type="range" id="${q.key}" min="${q.min}" max="${q.max}" step="${q.step}" value="${value}" ${q.key==='fin_stress'?`aria-describedby="${helpId}"`:''} aria-valuetext="${shown}">
      <div class="ds-ends"><span>${q.min} · ${escape(q.low)}</span><span>${q.max} · ${escape(q.high)}</span></div>
      ${q.key==='fin_stress'?`<p id="${helpId}" class="ds-help">Higher numbers mean more financial stress.</p>`:''}
      </div>`;
    }
    return `<div class="ds-question" id="question-${q.key}" role="group" aria-labelledby="${q.key}-title">${title}
      <div class="ds-answer-options">${q.options.map((label,i)=>`<label class="ds-answer"><input type="radio" name="${q.key}" value="${i+q.min}" ${answers[q.key]===i+q.min?'checked':''}><span><b>${i+q.min}</b>${escape(label)}</span></label>`).join('')}</div>
      </div>`;
  }
  function safetyPrompt() {
    return `<div class="ds-support ds-support-urgent" role="status"><h3>Please reach out</h3><p>If your words reflect how you feel right now, you deserve support. This basic word check cannot determine your safety.</p><p><a href="tel:65922030">SIT Counselling 24-hour helpline 6592 2030</a><br><a href="tel:1767">Samaritans of Singapore 1767</a><br><a href="tel:1771">National mindline 1771</a></p><a href="mailto:SITCounselling@SingaporeTech.edu.sg">SITCounselling@SingaporeTech.edu.sg</a></div>`;
  }
  function reflectionSafety() {
    const text=answers.feelings_text.toLowerCase().replaceAll('’',"'");
    return survey.safetyPatterns.some(pattern=>new RegExp(pattern,'i').test(text));
  }
  function checkin() {
    let content;
    if(step<reviewStep) {
      const section=survey.sections[step];
      content=`<span class="ds-pill">${escape(section.period)}</span><h2 tabindex="-1" id="ds-step-heading">${escape(section.heading)}</h2><p>${escape(section.intro)}</p>
        <div class="ds-why"><strong>Why this matters</strong><p>${escape(section.why)}</p></div>
        ${step===0?field('Student ID','student_id','<input class="ds-input" id="student_id" inputmode="numeric" maxlength="7" autocomplete="off" placeholder="e.g. 2605581">','7 digits starting with 2. Only SIT wellbeing staff can see your ID, and it\'s never sent to the AI.'):''}
        ${section.keys.map(key=>questionControl(questions[key])).join('')}
        ${step===5?field('Anything on your mind about school or life lately? (Optional)','feelings_text','<textarea class="ds-input" id="feelings_text" rows="4" maxlength="2000" placeholder="A space to reflect, if you want it."></textarea>','This space is just for you. It isn\'t scored or saved. If anything you write suggests you might need support right away, we\'ll show you who to contact.'):''}
        <div id="ds-safety">${reflectionSafety()?safetyPrompt():''}</div>`;
    } else {
      content=`<span class="ds-pill">✦ Your check-in, together</span><h2 tabindex="-1" id="ds-step-heading">A moment to look back.</h2><p>Check the time periods and answers below. You can edit any chapter before continuing.</p>
      <p><strong>Student ID:</strong> ${escape(answers.student_id)}</p>
      ${survey.sections.map((section,index)=>`<section class="ds-review-block"><div class="ds-actions"><h3>${escape(section.title)}</h3><button class="ds-link" data-edit-step="${index}">Edit</button></div><p class="ds-help">${escape(section.period)}</p>
      <dl class="ds-summary">${section.keys.map(key=>`<div><dt>${escape(questions[key].prompt)}</dt><dd>${escape(answerText(key))}</dd></div>`).join('')}${index===5?`<div><dt>Reflection</dt><dd>${answers.feelings_text?'Written for you only. It isn\'t scored or saved.':'Skipped'}</dd></div>`:''}</dl></section>`).join('')}
      ${reflectionSafety()?safetyPrompt():''}
      <div class="ds-why"><strong>What happens next</strong><p>After you submit, we'll look at your answers and share a few suggestions that may help. Only SIT wellbeing staff can see your ID, and it's never sent to the AI. Anything you write in the reflection box is not stored. This check-in isn't a diagnosis.</p></div>`;
    }
    main.innerHTML=`<div class="ds-journey"><aside class="ds-rail"><div class="ds-kicker">Chapters</div>
      ${chapters.map((title,i)=>`<div class="ds-stop ${i===step?'current':i<step?'done':''}"><b>${i<step?'✓':i+1}</b><span>${escape(title)}</span></div>`).join('')}
      <div class="ds-progress-note"><strong>${Math.round(step/reviewStep*100)}%</strong><span>complete</span></div></aside>
      <section><div class="ds-kicker">${step===reviewStep?'Review your check-in':`Chapter ${step+1} of ${reviewStep} · ${escape(chapters[step])}`}</div>
      <div class="ds-track" role="progressbar" aria-label="Chapters completed" aria-valuemin="0" aria-valuemax="${reviewStep}" aria-valuenow="${step}"><div style="width:${step/reviewStep*100}%"></div></div>
      ${content}<div class="ds-error" role="alert" id="ds-error"></div><div id="ds-failure-support"></div>
      <div class="ds-form-foot"><button class="ds-secondary" data-action="back">← ${step===0?'Home':'Back'}</button><button class="ds-primary" data-action="next">${step===reviewStep?'Get my check-in':step===reviewStep-1?'Review my check-in':'Continue'} →</button></div></section></div>`;
    if(step===0)main.querySelector('#student_id').value=answers.student_id;
    if(step===5)main.querySelector('#feelings_text').value=answers.feelings_text;
  }
  function supportPanel(advisor) {
    // URLs are constructed from the existing I/O contact fields, never model text.
    const email = String(advisor.email || '');
    const phone = String(advisor.helpline || '').replace(/[^+0-9]/g, '');
    const sos = String(advisor.sos || '1767').replace(/[^+0-9]/g, '');
    const mindline = String(advisor.mindline || '1771').replace(/[^+0-9]/g, '');
    const contacts = [
      ['Email', `mailto:${email}`, email],
      ['SIT Counselling 24-hour helpline', `tel:${phone}`, advisor.helpline || ''],
      ['Samaritans of Singapore', `tel:${sos}`, advisor.sos || '1767'],
      ['National mindline', `tel:${mindline}`, advisor.mindline || '1771'],
    ];
    return `<div class="ds-support ${advisor.prominence==='high'?'ds-support-urgent':''}"><h3>${escape(advisor.heading)}</h3>
      <p>${escape(advisor.body)}</p>
      <ul class="ds-contacts">${contacts.map(([label,href,value])=>`<li><span class="ds-contact-label">${escape(label)}</span><a href="${escape(href)}">${escape(value)}</a></li>`).join('')}</ul></div>`;
  }
  function result() {
    if (!assessment) {page='checkin';checkin();return;}
    main.innerHTML = `<span class="ds-pill">✦ Check-in complete</span><div class="ds-result"><section>
      <h2>You don't have to do<br>everything at once.</h2><p>A little perspective, a few suggestions, and support if you want it.</p>
      <div class="ds-result-hero" data-risk="${riskClass(assessment.insights?.risk_category)}"><div class="ds-kicker">Your check-in</div><h2>${escape(assessment.soft.heading)}</h2>
      <p>${escape(assessment.soft.body)}</p><div class="ds-note">Wellbeing guidance, not a medical diagnosis. Your ID was not sent to the AI.</div></div>
      ${insightsPanel()}
      <h3>${escape(assessment.tips.heading)}</h3><p>A few ideas that might help.</p>
      <ul class="ds-suggestions">${assessment.tips.items.map(tip=>`<li>${escape(tip.text)}</li>`).join('')}</ul>
      <p class="ds-save-note">Your answers are saved so SIT wellbeing staff can follow up if needed. Anything you wrote in the reflection box is not stored.</p>
      <button class="ds-link" data-action="new">Back to homepage</button></section>
      <aside><div class="ds-mini ds-companion">${plant()}<span class="ds-pill">Check-in complete</span><h3>You made space for you.</h3>
      <p>Taking a moment to check in is a good step. Come back whenever you need to.</p></div>
      ${supportPanel(assessment.advisor)}</aside></div>`;
  }
  function pathFor(next) {
    if(next==='result')return boot.resultUrl;
    if(next==='records')return boot.recordsPageUrl;
    return boot.homeUrl;
  }
  function remember(next) {
    const path=pathFor(next);
    if(!path)return;
    const state={page:next};
    if(location.pathname===path)history.replaceState(state,'',path);
    else history.pushState(state,'',path);
  }
  function render() {
    if(page==='records' && !boot.isAdmin){
      page='home';
      if(boot.homeUrl&&location.pathname!==boot.homeUrl)history.replaceState({page:'home'},'',boot.homeUrl);
    }
    root.querySelectorAll('[data-nav]').forEach(button => {
      if(button.dataset.nav===(page==='result'?'checkin':page))button.setAttribute('aria-current','page');
      else button.removeAttribute('aria-current');
    });
    ({home,checkin,result,records}[page] || home)();
  }
  function riskClass(value) {
    return {Low:'low',Moderate:'moderate',High:'high'}[value] || 'unknown';
  }
  function insightsPanel() {
    const info=assessment.insights;
    if(!info)return '';
    const factors=(info.factors||[]).map(factor=>`<article class="ds-factor ${factor.flagged?'is-flagged':''}"><div class="ds-actions"><h3>${escape(factor.title)}</h3>${factor.flagged?'<span class="ds-pill ds-pill-gentle">Worth some attention</span>':''}</div><strong>${escape(factor.value)}</strong><p>${escape(factor.text)}</p></article>`).join('');
    const section=factors?`<section class="ds-factor-section"><h3>How the pieces fit together</h3><p>These factors provide context and guide your next steps. They do not prove what caused your stress.</p><div class="ds-factor-grid">${factors}</div></section>`:'';
    return section+(info.safety_flag?safetyPrompt():'');
  }
  function records() {
    if(!boot.isAdmin){page='home';home();return;}
    const columns=[
      ['Student ID','id'],
      ['Stress score (/5)','eq'],
      ['Tier','tier'],
      ['Control','eq','pss_1'],
      ['Coping','eq','pss_2'],
      ['Going well','eq','pss_3'],
      ['Piling up','eq','pss_4'],
      ['Sleep (hours)','eq'],
      ['Sleep quality','eq'],
      ['Workload','eq'],
      ['Catch-up','eq'],
      ['Finances','eq'],
      ['Friends','eq'],
      ['Family','eq'],
      ['Status','status'],
      ['Date saved','date'],
    ];
    const heads=columns.map(([label,kind,key])=>{
      const title=key?` title="${escape(key+': '+questions[key].prompt)}"`:'';
      return `<th scope="col"${kind==='eq'?' class="ds-eq"':''}${title}>${label}</th>`;
    }).join('');
    const colgroup=`<colgroup>${columns.map(([,kind])=>`<col class="ds-col-${kind}">`).join('')}</colgroup>`;
    main.innerHTML=`<section><span class="ds-pill">Staff view</span><h2>Saved student check-ins.</h2><p>For SIT wellbeing staff. Search by student ID, tier, or cohort. Student IDs are visible here only and are never sent to the AI.</p>
      <div class="ds-records-toolbar">
      <div class="ds-record-filters">
        <label>Student ID<input class="ds-input" id="ds-record-search" type="search" inputmode="numeric" placeholder="Search all or part of an ID" value="${escape(recordFilters.student_id)}"></label>
        <label>Tier<select class="ds-input" id="ds-record-tier"><option value="">All tiers</option>${tiers.map(name=>`<option value="${escape(name)}"${name===recordFilters.tier?' selected':''}>${escape(name)}</option>`).join('')}</select></label>
        <label>Cohort year<select class="ds-input" id="ds-record-cohort"><option value="">All cohorts</option>${recordFilters.cohort_year?`<option value="${escape(recordFilters.cohort_year)}" selected>20${escape(recordFilters.cohort_year)}</option>`:''}</select></label>
        <button class="ds-secondary" data-action="clear-filters">Clear Filters</button>
      </div>
      <p id="ds-record-status" role="status" aria-live="polite"></p>
      </div>
      <div class="ds-record-table" role="region" aria-label="Saved check-ins table" tabindex="0">
      <table><caption>All saved student check-ins</caption>${colgroup}<thead><tr>${heads}</tr></thead><tbody id="ds-record-rows"></tbody></table></div>
      <p class="ds-record-note">Answers are on a 1–5 scale, where 1 is the lowest. Sleep is shown in hours. All times are in Singapore time (SGT).</p>
      <button class="ds-link" data-action="refresh-records">Refresh records</button></section>`;
    loadRecords();
  }
  function savedDate(value) {
    if(!value)return '—';
    const date=new Date(value);
    if(Number.isNaN(date.getTime()))return 'Unknown date';
    return new Intl.DateTimeFormat('en-SG',{timeZone:'Asia/Singapore',dateStyle:'medium',timeStyle:'short'}).format(date);
  }
  async function loadRecords() {
    if(!boot.isAdmin)return;
    const requestId=++recordsRequest;
    const status=main.querySelector('#ds-record-status');
    if(!status)return;
    status.textContent='Loading records…';
    main.querySelector('#ds-record-rows').innerHTML='';
    try {
      const params=new URLSearchParams(recordFilters);
      const response=await fetch(boot.recordsUrl+'?'+params.toString(),{cache:'no-store'});
      const data=await response.json();
      if(page!=='records'||requestId!==recordsRequest)return;
      if(response.status===401||response.status===403){
        main.querySelector('#ds-record-rows').innerHTML='';
        status.textContent='Your admin session has ended. Please sign in again.';
        location.replace(boot.adminLoginUrl);return;
      }
      if(!response.ok)throw new Error('load');
      const cohort=main.querySelector('#ds-record-cohort');
      cohort.innerHTML='<option value="">All cohorts</option>'+data.cohorts.map(year=>`<option value="${escape(year)}">20${escape(year)}</option>`).join('');
      cohort.value=recordFilters.cohort_year;
      status.textContent=`Showing ${data.matching} of ${data.total} check-ins`;
      const cell=value=>escape(value===null||value===undefined||value===''?'—':value);
      const answerCell=(key,value)=>{
        if(value===null||value===undefined||value==='')return '<td class="ds-num ds-eq">—</td>';
        const q=questions[key];
        const shown=typeof value==='number'?String(value):String(value);
        let title=shown;
        if(q&&Array.isArray(q.options)){
          const label=q.options[+value-q.min];
          if(label)title=`${shown} · ${label}`;
        }else if(q&&q.unit)title=`${shown} ${q.unit}`;
        return `<td class="ds-num ds-eq" title="${escape(title)}">${escape(shown)}</td>`;
      };
      const tierName=row=>row.soft_label||{Low:"You're doing ok",Moderate:'Worth a check-in',High:'Please reach out'}[row.risk_category]||'—';
      const answersFor=row=>['pss_1','pss_2','pss_3','pss_4','sleep_hours_avg','sleep_quality','pas_workload','pas_catchup','fin_stress','mspss_friends','mspss_family'].map(key=>answerCell(key,row[key])).join('');
      main.querySelector('#ds-record-rows').innerHTML=data.records.length?data.records.map(row=>`<tr data-risk="${riskClass(row.risk_category)}"><td>${cell(row.student_id)}</td><td class="ds-num ds-eq">${cell(row.stress_score)}</td><td><span class="ds-risk ds-risk-${riskClass(row.risk_category)}">${escape(tierName(row))}</span></td>${answersFor(row)}<td>${cell(row.status)}</td><td class="ds-date">${escape(savedDate(row.saved_at))}</td></tr>`).join(''):'<tr><td colspan="16" class="ds-empty">No records found</td></tr>';

    }catch(error){if(page==='records'&&requestId===recordsRequest){status.textContent='Could not load saved records. Use Refresh records to try again.';main.querySelector('#ds-record-rows').innerHTML='';}}
  }
  function valid() {
    let message='', focus;
    if(step===0&&!/^2[0-9]{6}$/.test(answers.student_id.trim())){message='Enter a 7-digit student ID starting with 2.';focus=main.querySelector('#student_id');}
    for(const key of survey.sections[step]?.keys||[]) {
      const q=questions[key], value=answers[key];
      if(value===null||value===''||!Number.isFinite(+value)||+value<q.min||+value>q.max||!Number.isInteger(+value/q.step)) {
        if(!message){message=`Please answer “${q.label}” using the available choices.`;focus=main.querySelector(`#question-${key} input`);}
      }
    }
    main.querySelector('#ds-error').textContent=message;
    if(focus)focus.focus();
    return !message;
  }
  function setBusy(value) {
    busy=value;root.setAttribute('aria-busy',String(value));
    root.querySelectorAll('button,input,textarea,select').forEach(control=>control.disabled=value);
  }
  async function post(url,body) {
    const response=await fetch(url,{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':boot.csrfToken},body:JSON.stringify(body)});
    const data=await response.json();return {response,data};
  }
  async function submit() {
    // Set before any await so a second click cannot start another request.
    if(submitting)return;
    submitting=true;
    const submitButton=main.querySelector('button[data-action="next"]');
    if(submitButton)submitButton.disabled=true;
    setBusy(true);
    const showError=text=>{const box=main.querySelector('#ds-error');if(box)box.textContent=text;};
    try {
      showError('Taking a moment to understand your check-in…');
      const support=main.querySelector('#ds-failure-support');
      if(support)support.innerHTML='';
      assessment=null;
      const {response,data}=await post(boot.submitUrl,{...answers,student_id:answers.student_id.trim(),feelings_text:answers.feelings_text.trim()});
      if(!response.ok) {
        if(data.errors){const key=Object.keys(data.errors)[0];step=key==='student_id'?0:key==='feelings_text'?5:Math.max(0,survey.sections.findIndex(section=>section.keys.includes(key)));render();}
        const calm=data.message||'We could not complete your check-in right now. Your answers are still here; please try again.';
        showError(data.errors?Object.values(data.errors).join(' '):calm);
        if(data.advisor){
          const panel=main.querySelector('#ds-failure-support');
          if(panel)panel.innerHTML=(data.safety_flag?safetyPrompt():'')+supportPanel(data.advisor);
        }
        return;
      }
      assessment=data.result;page='result';remember('result');render();
    } catch(error) {showError('Could not connect. Your answers are still here; please try again.');}
    finally {setBusy(false);submitting=false;}
  }
  root.addEventListener('input',event=>{
    const {id,value}=event.target;
    if(id==='ds-record-search'){recordFilters.student_id=value;clearTimeout(searchTimer);recordsRequest++;searchTimer=setTimeout(()=>{if(page==='records')loadRecords();},200);return;}
    if(questions[id]?.kind==='slider') {
      answers[id]=+value;
      const shown=answerText(id);
      const out=main.querySelector('#'+id+'-value');if(out)out.textContent=shown;
      event.target.setAttribute('aria-valuetext',shown);
    } else if(id==='student_id'||id==='feelings_text') {
      answers[id]=value;
      if(id==='feelings_text')main.querySelector('#ds-safety').innerHTML=reflectionSafety()?safetyPrompt():'';
    }
  });
  root.addEventListener('change',event=>{
    if(questions[event.target.name]&&event.target.type==='radio')answers[event.target.name]=+event.target.value;
    if(event.target.id==='ds-record-tier'){recordFilters.tier=event.target.value;loadRecords();}
    if(event.target.id==='ds-record-cohort'){recordFilters.cohort_year=event.target.value;loadRecords();}
  });
  root.addEventListener('click',async event=>{
    const button=event.target.closest('button');if(!button||busy||submitting)return;
    if(button.dataset.editStep!==undefined){step=+button.dataset.editStep;checkin();main.querySelector('#ds-step-heading').focus();return;}
    if(button.dataset.nav){
      const next=button.dataset.nav;
      if(next==='records'&&!boot.isAdmin)return;
      page=next;remember(page);render();return;
    }
    switch(button.dataset.action){
      case 'clear-filters':clearTimeout(searchTimer);Object.keys(recordFilters).forEach(key=>recordFilters[key]='');records();return;
      case 'refresh-records':loadRecords();return;
      case 'start':page='checkin';break;
      case 'back':if(step===0)page='home';else step--;break;
      case 'next':if(!valid())return;if(step<reviewStep)step++;else{button.disabled=true;await submit();return;}break;
      case 'new':location.assign(boot.homeUrl);return;
      default:return;
    }
    remember(page);
    render();
    if(page==='checkin')main.querySelector('#ds-step-heading')?.focus();
  });
  // Clear sensitive table rows before a page can enter the back/forward cache.
  window.addEventListener('pagehide',()=>{
    if(page==='records'){recordsRequest++;main.querySelector('#ds-record-rows').innerHTML='';}
  });
  window.addEventListener('pageshow',event=>{
    if(event.persisted&&boot.isAdmin)location.reload();
  });
  document.addEventListener('visibilitychange',()=>{
    if(page==='records'&&!document.hidden)loadRecords();
  });
  window.addEventListener('popstate',event=>{
    const next=event.state&&event.state.page;
    if(!next)return;
    if((next==='records'&&!boot.isAdmin)||(next==='result'&&!assessment)){
      page='home';
      if(boot.homeUrl)history.replaceState({page:'home'},'',boot.homeUrl);
      render();
      return;
    }
    page=next;render();
  });
  history.replaceState({page},'',location.pathname);
  render();
})();
