// Runs the actual extraction script with a small DOM contract. Not a Chrome integration test.
const fs = require('node:fs'), vm = require('node:vm'), assert = require('node:assert/strict');
const source = fs.readFileSync(require('node:path').join(__dirname,'../extension/extractor.js'),'utf8');
const cells = values => values.map(textContent=>({textContent}));
const anchor = {tagName:'A', getAttribute:()=> 'javascript:spawn(1402,3)', previousSibling:{textContent:'سال: 1403-1402'}};
const summary = {tagName:'B', textContent:'واحد اخذ شده ترم: 6 واحد قبول شده ترم: 0 معدل ترم: 0 واحد اخذ شده کل: 6 واحد قبول شده کل: 0 معدل کل: 0'};
const table = {tagName:'TABLE', rows:[{cells:cells(['ردیف','شماره درس','نام درس','واحد','نمره'])},
  {cells:cells(['۱','۲۱۰۱','ریاضی','۳','۰'])}, {cells:cells(['۲','','بدون کد','۳',''])}],
  previousElementSibling:anchor,nextElementSibling:summary,querySelectorAll:()=>[]};
const run = tables => vm.runInNewContext(source, {document:{querySelectorAll:()=>tables},location:{origin:'https://portal.example',pathname:'/grades'}});
assert.equal(run([]).found,false);
const result = run([table]);
assert.equal(result.found,true);
assert.equal(result.transcript.semesters[0].term,3);
assert.equal(result.transcript.semesters[0].courses[0].grade,0);
assert.equal(result.transcript.semesters[0].courses[0].course_code,'2101');
assert.equal(result.transcript.semesters[0].courses[1].course_code,null);
assert.equal(result.transcript.semesters[0].courses[1].grade,null);
assert.equal(result.transcript.extraction.attempt_count,2);
assert.ok(result.transcript.extraction.warnings.length);
console.log('PASS: actual extractor / Persian digits, zero, missing code, summer, empty frame (DOM contract only)');
