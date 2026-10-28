/* The value of this IIFE is the result returned by chrome.scripting.executeScript.
 * Only read DOM rendered in the currently opened document/frame.
 * No page credentials, cookies, network calls or automatic navigation.
 */
(() => {
  "use strict";
  const normalize = (s) => String(s == null ? "" : s)
    .replace(/[۰-۹]/g, c => String(c.charCodeAt(0) - 0x06F0))
    .replace(/[٠-٩]/g, c => String(c.charCodeAt(0) - 0x0660))
    .replace(/\u200c/g, " ").replace(/\s+/g, " ").trim();
  const text = (element) => normalize(element?.textContent || "");
  const numerical = (value) => {
    const cleaned = normalize(value).replace(/٫/g, ".").replace(/[٬,]/g, "");
    return /^-?\d+(?:\.\d+)?$/.test(cleaned) ? Number(cleaned) : null;
  };
  const summaries = {
    term_attempted_credits: /واحد\s*اخذ\s*شده\s*ترم\s*:\s*([\d.]+)/,
    term_passed_credits: /واحد\s*قبول\s*شده\s*ترم\s*:\s*([\d.]+)/,
    term_gpa: /معدل\s*ترم\s*:\s*([\d.]+)/,
    cumulative_attempted_credits: /واحد\s*اخذ\s*شده\s*کل\s*:\s*([\d.]+)/,
    cumulative_passed_credits: /واحد\s*قبول\s*شده\s*کل\s*:\s*([\d.]+)/,
    cumulative_gpa: /معدل\s*کل\s*:\s*([\d.]+)/
  };
  const headings = ["ردیف", "شماره درس", "نام درس", "واحد", "نمره"];
  const tables = [...document.querySelectorAll("table")].filter(table => {
    const first = table.rows[0];
    if (!first) return false;
    const cells = [...first.cells].map(text);
    return cells.length === 5 && cells.every((val, index) => val === headings[index]);
  });
  if (!tables.length) return {found: false, url: location.origin + location.pathname};

  const warnings = [];
  const fields = {
    "شماره دانشجو": "student_id",
    "نام و نام خانوادگی": "full_name",
    "رشته": "major",
    "مقطع": "degree",
    "دانشکده": "faculty",
    "دوره": "education_program"
  };
  const student = {
    student_id: null, full_name: null, major: null,
    degree: null, faculty: null, education_program: null,
    entry_year: null, inferred_entry_year: null
  };
  for (const table of document.querySelectorAll("table")) {
    const values = [...table.querySelectorAll("td")].map(text);
    if (!values.some(v => /^شماره دانشجو\s*:/.test(v))) continue;
    for (let i = 0; i < values.length - 1; i += 2) {
      const key = values[i].replace(/\s*:\s*$/, "").trim();
      if (Object.prototype.hasOwnProperty.call(fields, key)) {
        student[fields[key]] = values[i+1] || null;
      }
    }
    break;
  }
  if (!student.student_id) warnings.push("شماره دانشجویی در صفحه یافت نشد.");
  const semesters = [];
  const keys = new Set();

  for (const table of tables) {
    // In the university page the semester link immediately precedes its table.
    // Walk siblings only, to avoid assigning the wrong semester across tables.
    let anchor = table.previousElementSibling;
    while (anchor && anchor.tagName !== "TABLE" && !(anchor.tagName === "A" && /spawn\s*\(/i.test(anchor.getAttribute("href") || ""))) {
      anchor = anchor.previousElementSibling;
    }
    const match = anchor?.getAttribute("href")?.match(/spawn\s*\(\s*(\d{4})\s*,\s*([123])\s*\)/i);
    if (!match) {
      warnings.push("جدول درس بدون شناسه نیمسال پیدا شد؛ داده آن وارد خروجی نشد.");
      continue;
    }
    const year = Number(match[1]), term = Number(match[2]);
    const key = `${year}-${term}`;
    if (keys.has(key)) warnings.push(`نیمسال تکراری: ${key}`);
    keys.add(key);
    const yearContext = normalize(anchor.previousSibling?.textContent || "");
    const labelMatch = yearContext.match(/سال\s*:\s*(\d{4})\s*-\s*(\d{4})/);
    const semester = {
      academic_year_start: year,
      academic_year_label: labelMatch ? `${labelMatch[1]}-${labelMatch[2]}` : `${year + 1}-${year}`,
      term,
      term_name: {1: "اول", 2: "دوم", 3: "تابستانی"}[term],
      courses: [],
      reported_summary: null
    };
    for (const [i, row] of [...table.rows].slice(1).entries()) {
      const cells = [...row.cells].map(text);
      if (!cells.length) continue;
      if (cells.length !== 5) {
        warnings.push(`${key}: ردیف ${i + 1} تعداد ستون غیرمنتظره دارد.`);
        continue;
      }
      const code = cells[1], credits = numerical(cells[3]), grade = numerical(cells[4]);
      if (!code || credits === null || credits <= 0 || (cells[4] && grade === null)) {
        warnings.push(`${key}: ردیف ${i + 1} کد، واحد یا نمره نامعتبر دارد؛ حذف نشد.`);
      }
      if (grade !== null && (grade < 0 || grade > 20)) warnings.push(`${key}: نمره خارج از بازه: ${grade}`);
      semester.courses.push({
        course_code: code || null,
        course_id: null,
        course_name: cells[2],
        credits,
        grade,
        grade_raw: cells[4],
        status: "UNDETERMINED"
      });
    }
    let cursor = table.nextElementSibling;
    while (cursor && !["B", "TABLE"].includes(cursor.tagName)) cursor = cursor.nextElementSibling;
    if (cursor?.tagName === "B") {
      const summaryText = text(cursor);
      semester.reported_summary = {};
      for (const [field, pattern] of Object.entries(summaries)) {
        const m = summaryText.match(pattern);
        semester.reported_summary[field] = m ? numerical(m[1]) : null;
        if (!m) warnings.push(`${key}: مقدار ${field} پیدا نشد.`);
      }
    } else warnings.push(`${key}: خلاصه نیمسال پیدا نشد.`);
    const totalCredits = semester.courses.reduce((sum, course) => sum + (course.credits || 0), 0);
    if (semester.reported_summary?.term_attempted_credits != null &&
      Math.abs(totalCredits - semester.reported_summary.term_attempted_credits) > 0.0001) {
      warnings.push(`${key}: مجموع واحدهای جدول (${totalCredits}) با مجموع اعلام‌شده سامانه مغایرت دارد.`);
    }
    semesters.push(semester);
  }
  if (!semesters.length) return {found: false, url: location.origin + location.pathname};
  const years = semesters.map(s => s.academic_year_start);
  student.inferred_entry_year = Math.min(...years);
  warnings.push("سال ورودی فقط از اولین نیمسال موجود تخمین زده شده و باید با مشخصات دانشجو تطبیق شود.");

  const lastSummary = semesters[semesters.length - 1].reported_summary;
  return {
    found: true,
    transcript: {
      schema_version: "1.0",
      source_type: "unofficial_grade_notice_html",
      source_page: location.origin + location.pathname,
      student,
      semesters,
      extraction: {
        semester_count: semesters.length,
        attempt_count: semesters.reduce((sum, semester) => sum + semester.courses.length, 0),
        latest_reported_summary: lastSummary,
        warnings
      }
    }
  };
})();
