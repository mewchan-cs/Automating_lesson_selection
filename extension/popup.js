"use strict";
const $ = (id) => document.getElementById(id);
const STORAGE_KEY = 'advisor_local_pairing_token';
let currentReport = null;
let currentTranscript = null;

function notify(message, bad = false) {
  $('message').textContent = message;
  $('message').className = bad ? 'error' : 'ok';
}
function fillList(id, values, fmt, empty) {
  const list = $(id);
  list.replaceChildren();
  if (!values.length) {
    const item = document.createElement('li');
    item.textContent = empty;
    list.appendChild(item);
  }
  for (const value of values.slice(0, 30)) {
    const item = document.createElement('li');
    item.textContent = fmt(value);
    list.appendChild(item);
  }
  if (values.length > 30) {
    const item = document.createElement('li');
    item.textContent = `و ${values.length - 30} مورد دیگر در گزارش کامل...`;
    list.appendChild(item);
  }
}
function metric(label, value) {
  const node = document.createElement('div');
  node.className = 'metric';
  const number = document.createElement('strong');
  const description = document.createElement('span');
  number.textContent = value === undefined || value === null ? '—' : new Intl.NumberFormat('fa-IR', {maximumFractionDigits: 2, useGrouping:false}).format(value);
  description.textContent = label;
  node.append(number, description);
  $('metrics').appendChild(node);
}
function showReport(r) {
  $('results').style.display = 'block';
  renderVisualSummary(r.visual_summary);
  renderAcademicReview(r.academic_review);
  renderDetails(r);
  $('student').textContent = `${r.student.full_name || 'دانشجو'} | شماره دانشجویی: ${r.student.student_id || '—'} | ${r.student.major || 'رشته نامشخص'} | چارت: ${r.curriculum}`;
  $('metrics').replaceChildren();
  const o = r.overview;
  metric('نیمسال ثبت‌شده', o.semester_count);
  metric('دفعات اخذ درس', o.course_attempts);
  metric('واحد اخذشده از ردیف‌ها', o.attempted_credits_from_rows);
  metric('واحد قبول‌شده به اعلام سامانه', o.latest_reported_passed_credits);
  metric('معدل کل به اعلام سامانه', o.latest_reported_gpa);
  metric('دفعات منطبق با چارت', o.matched_attempts);
  metric('نمرات کمتر از ۱۰ (صرفاً آماری)', o.observed_grades_below_10);
  metric('دروس تکرارشده', o.repeated_course_count);
  fillList('repeated', r.repeated_courses,
    x => `${x.course_name}: ${x.attempts.map(a => `${a.academic_year_start}-${a.term} (${a.grade === null ? 'بی‌نمره' : a.grade})`).join('؛ ')}`,
    'درسی با بیش از یک بار اخذ شناسایی نشد.');
  fillList('unmatched', r.unmatched_courses,
    x => `${x.course_code} — ${x.course_name} (${x.attempts} بار)`,
    'همه کدهای مشاهده‌شده در چارت انتخابی پیدا شدند.');
  fillList('warnings', r.warnings, x => x, 'هشداری ثبت نشده است.');
}
function selectTranscriptCandidate(results) {
  const candidates=results.map(v=>v.result).filter(v=>v?.found&&v.transcript);
  const unique=[...new Map(candidates.map(v=>[JSON.stringify([v.transcript.student,v.transcript.semesters]),v])).values()];
  if(unique.length>1)throw new Error('چند کارنامه متفاوت باز است؛ فقط کارنامه دانشجوی موردنظر را باز نگه دارید.');
  return unique[0];
}
async function extractFromOpenTab() {
  let [tab] = await chrome.tabs.query({active: true, currentWindow: true});
  if (new URLSearchParams(location.search).has('wide')) {
    const tabs = await chrome.tabs.query({currentWindow:true});
    tab = tabs.filter(t=>t.id === Number(new URLSearchParams(location.search).get('source')))[0];
  }
  if (!tab?.id || !/^https?:\/\//.test(tab.url || '')) {
    throw new Error('ابتدا پرتال دانشگاه را در زبانه فعال باز کنید.');
  }
  // This runs only after user clicks, on already-visible DOM (including available iframes).
  const injected = await chrome.scripting.executeScript({
    target: {tabId: tab.id, allFrames: true},
    files: ['extractor.js']
  });
  const found = selectTranscriptCandidate(injected);
  if (!found) {
    throw new Error('جدول کارنامه در صفحه فعلی پیدا نشد. «اطلاعیه نمرات» را باز کن؛ قالب صفحه مدیر گروه هم ممکن است متفاوت باشد.');
  }
  return found.transcript;
}
async function sendToEngine(transcript, chart, token) {
  const reviewRequested=$('academicReviewEnabled').checked;
  if (reviewRequested) {
    transcript.extraction = {...transcript.extraction,history_complete:$('completeHistory').checked,
                             completeness_source:'user_confirmation_for_this_analysis'};
  }
  const response = await fetch('http://127.0.0.1:8765/analyze', {
    method: 'POST',
    headers: {'Content-Type': 'application/json', 'X-Local-Token': token},
    body: JSON.stringify({chart, transcript,academic_review:reviewRequested,review_mode:'graduation'}),
    cache: 'no-store'
  });
  const payload = await response.json();
  if (!response.ok) {
    if (response.status === 401) throw new Error('کد اتصال اشتباه است. کد نمایش‌داده‌شده در پنجره پایتون را بررسی کن.');
    throw new Error(payload.message || payload.error || `خطای موتور: ${response.status}`);
  }
  if(reviewRequested && payload.academic_review?.mode!=='graduation'){
    throw new Error('موتور قبلی هنوز فعال است. پنجره پایتون قبلی را ببندید و start_server.bat همین بسته جدید را اجرا کنید.');
  }
  return payload;
}
function saveJSON(value, filename) {
  const blob = new Blob([JSON.stringify(value, null, 2)], {type: 'application/json;charset=utf-8'});
  const url = URL.createObjectURL(blob);
  chrome.downloads.download({url, filename, saveAs: true}).then(() => {
    setTimeout(() => URL.revokeObjectURL(url), 30000);
  }).catch(e => {
    URL.revokeObjectURL(url);
    notify(`ذخیره ناموفق: ${e.message}`, true);
  });
}
$('analyze').addEventListener('click', async () => {
  $('analyze').disabled = true;
  $('results').style.display = 'none';
  currentReport = currentTranscript = null;
  try {
    const token = $('token').value.trim();
    const chart = $('chart').value;
    if (!token) throw new Error('کد اتصال موتور پایتون را وارد کن.');
    if (!chart) throw new Error('چارت سال ورودی دانشجو را انتخاب کن.');
    await chrome.storage.session.set({[STORAGE_KEY]: token});
    notify('در حال استخراج کارنامه و ارسال به موتور محلی...');
    const transcript = await extractFromOpenTab();
    const report = await sendToEngine(transcript, chart, token);
    currentTranscript = transcript;
    currentReport = report;
    notify(`تحلیل اولیه کامل شد: ${report.overview.semester_count} نیمسال، ${report.overview.course_attempts} بار اخذ درس. اطلاعات فقط به 127.0.0.1 ارسال شدند.`);
    showReport(report);
  } catch (err) {
    notify(`خطا: ${err?.message || String(err)}\nاگر اتصال رد شد، نخست فایل start_server.bat را اجرا کن.`, true);
  } finally {
    $('analyze').disabled = false;
    $('completeHistory').checked = false;
  }
});
$('academicReviewEnabled').addEventListener('change',()=>{
  $('academicOptions').hidden=!$('academicReviewEnabled').checked;
  $('completeHistory').checked=false;
});
$('download').addEventListener('click', () => {
  if (currentReport) saveJSON(currentReport, 'advisor_report.json');
});
$('downloadTranscript').addEventListener('click', () => {
  if (currentTranscript) saveJSON(currentTranscript, 'extracted_transcript.json');
});
chrome.storage?.session.get(STORAGE_KEY).then(o => {
  $('token').value = o[STORAGE_KEY] || '';
}).catch(() => {});

const faNumber = new Intl.NumberFormat('fa-IR', {maximumFractionDigits: 2, useGrouping: false});
const shown = value => value == null ? '—' : faNumber.format(value);
const termLabel = t => `${shown(t.academic_year_start)}–${shown(t.academic_year_start + 1)} · ${ {1:'نیمسال اول',2:'نیمسال دوم',3:'تابستان'}[t.term]}`;
function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text != null) node.textContent = text;
  if (className) node.className = className;
  return node;
}
function gradeStatus(c) {
  return c.grade == null ? ['pending','بدون نمره'] : c.grade >= 10 ? ['good','پاس‌شده · ≥۱۰'] : ['bad','افتاده · <۱۰'];
}
function courseTable(courses, includeTerm = true) {
  const wrap = element('div', null, 'table-wrap');
  const table = element('table');
  const head = element('thead'); const hr = element('tr');
  const titles = ['نام درس','کد درس','واحد','نمره','وضعیت نمایشی','تطبیق با چارت'];
  if (includeTerm) titles.push('نیمسال');
  titles.forEach(x => hr.append(element('th', x)));
  head.append(hr); table.append(head); const body = element('tbody');
  for (const c of courses) {
    const row = element('tr');
    row.append(element('td', c.course_name));
    const code = element('td'); code.append(element('code', c.course_code)); row.append(code);
    row.append(element('td', shown(c.credits)), element('td', shown(c.grade), 'grade'));
    const status = gradeStatus(c); const cell = element('td'); cell.append(element('span', status[1], `badge ${status[0]}`)); row.append(cell);
    row.append(element('td', {EXACT_CODE:'منطبق',NOT_IN_CHART:'در چارت نیست',AMBIGUOUS_CODE:'نیازمند بررسی'}[c.matching] || 'نامشخص'));
    if (includeTerm) row.append(element('td', termLabel(c)));
    body.append(row);
  }
  table.append(body); wrap.append(table);
  if (!courses.length) wrap.append(element('p','درسی با این فیلتر پیدا نشد.','empty'));
  return wrap;
}
function filterCourses() {
  if (!currentReport) return;
  const normalize = s => String(s).replace(/ي/g,'ی').replace(/ك/g,'ک').replace(/[۰-۹]/g,c=>String(c.charCodeAt(0)-1776)).toLowerCase();
  const query = normalize($('search').value.trim());
  const status = $('statusFilter').value;
  const rows = currentReport.course_attempts.filter(c => (status === 'all' || gradeStatus(c)[0] === status) && normalize(`${c.course_name} ${c.course_code}`).includes(query));
  $('courses').replaceChildren(courseTable(rows));
  $('courseCount').textContent = `${shown(rows.length)} ردیف از ${shown(currentReport.course_attempts.length)} بار اخذ درس`;
}
function renderDetails(r) {
  const rows = r.course_attempts;
  const terms = [...r.semesters].sort((a,b)=>a.academic_year_start-b.academic_year_start || a.term-b.term);
  $('semesters').replaceChildren(); $('trend').replaceChildren(); $('insights').replaceChildren();
  const graded = rows.filter(c=>c.grade != null);
  const strong = [...graded].sort((a,b)=>b.grade-a.grade)[0];
  const missing = rows.filter(c=>c.grade == null).length;
  const below = rows.filter(c=>c.grade != null && c.grade < 10).length;
  const passed = rows.filter(c=>c.grade != null && c.grade >= 10).length;
  const notes = [`${shown(passed)} بار اخذ با نمره ۱۰ و بیشتر، ${shown(below)} بار با نمره کمتر از ۱۰ و ${shown(missing)} بار بدون نمره ثبت شده است.`];
  if (strong) notes.push(`بالاترین نمره ثبت‌شده: ${strong.course_name} (${strong.course_code}) با نمره ${shown(strong.grade)}.`);
  const gpas = terms.filter(t=>t.reported_term_gpa != null);
  if (gpas.length >= 2) {
    const delta = gpas[gpas.length-1].reported_term_gpa-gpas[gpas.length-2].reported_term_gpa;
    notes.push(`معدل آخرین نیمسال دارای معدل نسبت به نیمسال قبلیِ دارای معدل ${delta > 0 ? shown(delta)+' افزایش' : delta < 0 ? shown(-delta)+' کاهش' : 'تغییری'} داشته است.`);
  }
  notes.push('معدل‌ها و واحدهای قبول‌شده از سامانه نقل شده‌اند؛ نمره‌های تکراری حذف نشده‌اند و معدل رسمی مجدداً محاسبه نمی‌شود.');
  notes.forEach(n=>$('insights').append(element('p',n)));
  for (const t of terms) {
    const courses = rows.filter(c=>c.academic_year_start === t.academic_year_start && c.term === t.term);
    const details = element('details'); const summary = element('summary', `${termLabel(t)} · معدل ${shown(t.reported_term_gpa)} · ${shown(t.attempt_count)} درس`);
    details.append(summary); const content = element('div',null,'term-content'); const stats = element('div',null,'term-stats');
    [`واحد اخذشده: ${shown(t.credits_from_rows)}`, `واحد قبول‌شده سامانه: ${shown(t.reported_passed_credits)}`, `معدل کل تا این ترم: ${shown(t.reported_cumulative_gpa)}`, `نمره زیر ۱۰: ${shown(courses.filter(c=>c.grade != null && c.grade<10).length)}`, `بدون نمره: ${shown(courses.filter(c=>c.grade == null).length)}`].forEach(x=>stats.append(element('span',x)));
    content.append(stats,courseTable(courses,false)); details.append(content); $('semesters').append(details);
    const barItem = element('div',null,'trend-item');
    barItem.title = `${termLabel(t)}: ${shown(t.reported_term_gpa)}`;
    barItem.append(element('strong',shown(t.reported_term_gpa)));
    const bar = element('div',null,'bar'); bar.style.height = `${t.reported_term_gpa == null ? 3 : t.reported_term_gpa * 4}px`;
    barItem.append(bar,element('span',`${shown(t.academic_year_start)}/${shown(t.term)}`)); $('trend').append(barItem);
  }
  $('search').value = ''; $('statusFilter').value = 'all';
  // The report is assigned before rendering by the analysis flow.
  currentReport = r; filterCourses();
}
$('search').addEventListener('input',filterCourses);
$('statusFilter').addEventListener('change',filterCourses);
$('openDashboard').addEventListener('click',async()=> {
  const [source] = await chrome.tabs.query({active:true,currentWindow:true});
  chrome.tabs.create({url:chrome.runtime.getURL(`popup.html?wide=1&source=${source?.id || ''}`)});
});
if (new URLSearchParams(location.search).has('wide')) { document.body.classList.add('wide'); $('openDashboard').hidden = true; }
$('print').addEventListener('click',()=> {
  const closed = [...document.querySelectorAll('#semesters details:not([open])')];
  closed.forEach(d=>d.open=true);
  window.print();
  closed.forEach(d=>d.open=false);
});
