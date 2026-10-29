function renderGraduationReport(data){
  const host=document.getElementById('academicReview');host.replaceChildren();host.hidden=false;
  const make=(tag,text)=>{const n=document.createElement(tag);if(text!=null)n.textContent=text;return n;};
  const show=n=>n==null?'—':new Intl.NumberFormat('fa-IR',{maximumFractionDigits:2}).format(n);
  host.append(make('h2','گزارش تکمیل دروس و واحدهای فارغ‌التحصیلی'),make('strong',data.title),make('p',data.reason));
  host.append(make('p',`چارت ورودی: ${data.chart} · کل واحد برنامه: ${show(data.required_credits)} · قبولی تخصیص‌یافته به الزامات: ${show(data.counted_passed_credits)} · قبولی اعلام‌شدهٔ سامانه: ${show(data.reported_passed_credits)}`));
  host.append(make('p',data.exact_remaining_credits!=null?`واحد باقی‌ماندهٔ قابل محاسبه از کارنامه: ${show(data.exact_remaining_credits)}`:`واحدی که هنوز برای تکمیل سهم‌ها احراز نشده: ${show(data.remaining_to_confirm)}`));
  if(data.categories.length){
    const wrap=make('div'),table=make('table'),head=make('tr');wrap.className='table-wrap';
    ['دسته درس','لازم طبق چارت','قبولی تخصیص‌یافته','مانده برای احراز'].forEach(x=>head.append(make('th',x)));table.append(head);
    for(const c of data.categories){const row=make('tr');[c.name,show(c.required),show(c.confirmed),show(c.remaining_to_confirm)].forEach(x=>row.append(make('td',x)));table.append(row);}
    wrap.append(table);host.append(wrap);
  }
  const status={NOT_TAKEN:'سابقه اخذ پیدا نشد',FAILED:'قبولی ندارد',GRADE_PENDING:'نمره قطعی نیست',MATCH_REQUIRED:'کد نیازمند تطبیق است'};
  if(data.missing_courses.length){
    const box=make('details');box.append(make('summary',`درس‌های الزامی با قبولی احرازنشده (${data.missing_courses.length})`));
    for(const c of data.missing_courses)box.append(make('p',`${c.course_name} — ${c.course_code||'کد موجود نیست'} — ${show(c.credits)} واحد · ${status[c.completion_status]||''}`));host.append(box);
  }
  if(data.groups.length){
    const box=make('details');box.append(make('summary','تکمیل سهم عمومی، اختیاری و تمرکز'));
    for(const g of data.groups){const group=make('details');group.append(make('summary',`${g.name}: ${show(g.confirmed)} از ${show(g.required)} واحد؛ مانده ${show(g.remaining)}`));
      for(const c of g.choices||[])group.append(make('p',`${c.course_name} — ${c.course_code||'کد موجود نیست'} — ${show(c.credits)} واحد`));box.append(group);}
    host.append(box);
  }
  if(data.unresolved_rows.length){
    const box=make('details');box.append(make('summary',`موارد مؤثر در شمارش واحد (${data.unresolved_rows.length})`));
    for(const c of data.unresolved_rows)box.append(make('p',`${c.course_name} — ${c.course_code||'کد موجود نیست'} · ${c.reason}`));host.append(box);
  }
  if(data.passed_not_allocated.length){
    const box=make('details');box.append(make('summary','قبولی‌هایی که به سهم این برنامه تخصیص نیافتند'));
    for(const c of data.passed_not_allocated)box.append(make('p',`${c.course_name} — ${c.course_code||'کد موجود نیست'} — ${show(c.credits)} واحد`));host.append(box);
  }
  const note=make('p',data.note);note.className='muted';host.append(note);
}
