/* Small addition to the original 0.3 view. All portal text stays text content. */
function renderVisualSummary(data) {
  const host = document.getElementById('visualSummary');
  host.replaceChildren();
  if (!data) return;
  const make = (tag,text,className) => {
    const node = document.createElement(tag);
    if (text != null) node.textContent = text;
    if (className) node.className = className;
    return node;
  };
  function courses(rows) {
    const list = make('ul',null,'visual-course-list');
    for (const c of rows) {
      const li = make('li');
      li.append(make('span',c.course_name),make('code',c.course_code || 'کد تأیید نشده'));
      li.title = (c.availability?.reasons || []).join('؛ ');
      list.append(li);
    }
    return list;
  }
  host.append(make('h2','درس‌های اخذنشدهٔ چارت تصویری'));
  if (data.not_taken.length) host.append(courses(data.not_taken));
  else host.append(make('p','درس اخذنشدهٔ قابل تطبیقی در تصویر پیدا نشد.','muted'));
  for(const group of data.main_alternatives || []){
    host.append(make('h3',`${group.title} — گذراندن یکی از گزینه‌ها`));
    if(group.completion_status==='UNKNOWN')host.append(make('p','تکمیل این گروه به‌علت نمره یا تطبیق نامطمئن هنوز قطعی نیست.','muted'));
    const options=[...group.ready,...group.needs_review,...group.waiting];
    if(options.length)host.append(courses(options));
    if(group.retake_options?.length){
      const prior=make('details');prior.append(make('summary','گزینه‌های قبلاً اخذشده با قبولی احرازنشده'),courses(group.retake_options));host.append(prior);
    }
  }
  host.append(make('h2','گزینه‌های خانه‌های اختیاری، تخصصی و تمرکز'));
  for (const group of data.option_groups) {
    if(group.show_in_main)continue; // Already visible above; completed one-of groups need no new choice.
    const box = make('details');
    box.open = group.ready.length > 0;
    box.append(make('summary',`${group.title} · ${group.remaining_option_count} گزینهٔ اخذنشده`));
    const content = make('div',null,'term-content');
    if (group.ready.length) {
      content.append(make('p','قابل پیشنهاد از نظر پیش‌نیازهای ثبت‌شده:'),courses(group.ready));
    }
    const review = [...group.needs_review,...group.waiting];
    if (review.length) {
      const pending = make('details');
      pending.append(make('summary',`نیازمند بررسی یا پیش‌نیاز (${review.length})`),courses(review));
      content.append(pending);
    }
    if (!group.remaining_option_count) content.append(make('p','گزینهٔ اخذنشدهٔ قابل تطبیق باقی نمانده است.'));
    if (group.previously_taken_count) content.append(make('p',`${group.previously_taken_count} گزینه قبلاً اخذ شده؛ تعداد انتخاب لازمِ باقی‌مانده نیازمند تعیین سهم گروه است.`,'muted'));
    if (group.note) content.append(make('p',group.note,'muted'));
    box.append(content); host.append(box);
  }
  if (data.needs_matching.length || data.uncertain_visual_courses.length) {
    const box = make('details');
    box.append(make('summary','تطبیق‌های نامطمئن'));
    const content = make('div',null,'term-content');
    content.append(make('p','این موارد بدون تأیید هم‌ارزی، اخذنشده یا گذرانده‌شده فرض نشده‌اند.','muted'));
    content.append(courses(data.uncertain_visual_courses));
    for (const row of data.needs_matching) content.append(make('p',`${row.course_name} — ${row.course_code || 'کد موجود نیست'}`,'muted'));
    box.append(content);host.append(box);
  }
  host.append(make('p',data.notice,'muted'));
  if (data.code_notice) host.append(make('p',data.code_notice,'muted'));
}
