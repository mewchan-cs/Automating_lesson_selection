function renderAcademicReview(data) {
  if(data?.mode==='graduation')return renderGraduationReport(data);
  let host=document.getElementById('academicReview');host.replaceChildren();host.hidden=!data;
  if (!data) return;
  const make=(tag,text)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;return n;};
  const show=n=>n==null?'نامشخص':new Intl.NumberFormat('fa-IR',{maximumFractionDigits:2}).format(n);
  const state=data.academic_status,limit=data.credit_limit,g=data.graduation;
  if(data.decision){
    host.append(make('h2','نتیجهٔ بررسی'),make('p',data.decision.text));
    if(data.decision.detail)host.append(make('p',data.decision.detail));
    const details=make('details');details.append(make('summary','جزئیات و دلیل نتیجه'));host.append(details);host=details;
  }
  host.append(make('h2','وضعیت آموزشی و فارغ‌التحصیلی'));
  host.append(make('p',`آخرین نیمسال: ${data.last_term.semester} · معدل رسمی: ${show(data.last_term.gpa)} · وضعیت: ${state.label}`));
  if(state.status!=='CONFIRMED') host.append(make('p',state.reason));
  if(limit.final_term_exception) host.append(make('p',`ترم آخر: ${show(limit.recommended_credits)} واحد باقی‌مانده؛ تا سقف ${show(limit.maximum)} واحد، بدون شرط الف بودن و با معافیت پیش‌نیاز و هم‌نیاز برای دروس باقی‌ماندهٔ مصوب.`));
  else if(limit.maximum!=null) host.append(make('p',`سقف واحد پیشنهادی: ${show(limit.maximum)} واحد${limit.conditional_maximum!=null?`؛ تا ${show(limit.conditional_maximum)} با تأیید گروه`:''}`));
  else host.append(make('p',limit.conditional_maximum!=null?`سقف مشروط به تأیید: ${show(limit.conditional_maximum)} واحد`:`سقف واحد: نامشخص — ${limit.reason}`));
  host.append(make('p',`فارغ‌التحصیلی: ${g.label}`),make('p',g.reason));
  host.append(make('p',`واحد قبولیِ احرازشده در چارت: ${show(g.confirmed_passed_chart_credits)} · واحد مصوب لازم: ${show(g.required_total)} · باقی‌ماندهٔ قطعی: ${show(g.exact_remaining_credits)}`));
  if(g.missing_required.length){const box=make('details');box.append(make('summary','درس‌های الزامیِ قبولی‌احرازنشده'));for(const c of g.missing_required)box.append(make('p',`${c.course_name} — ${c.course_code||'کد نامشخص'}`));host.append(box);}
  if(g.groups.length){const box=make('details');box.append(make('summary','سهم گروه‌ها'));for(const group of g.groups)box.append(make('p',`${group.name}: ${show(group.confirmed)} احراز شده از ${show(group.required)}؛ مانده ${show(group.remaining)}`));host.append(box);}
  const audit=make('details');audit.append(make('summary',`درستی اخذ دروس: ${data.audit_summary.confirmed} مورد احرازشده، ${data.audit_summary.needs_review} مورد نیازمند بررسی`));
  for(const item of data.course_audit){const row=make('details');row.append(make('summary',`${item.course_name} — ${item.course_code||'کد نامشخص'} · ${item.status==='CONFIRMED'?'احرازشده':'نیازمند بررسی'}`));for(const c of item.checks)row.append(make('p',c.reason));audit.append(row);}host.append(audit);
  host.append(make('p',`مبنای محاسبه: ${data.policy_source||'قاعده قابل اعمال ثبت نشده است'}`));
}
