const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm'), assert = require('node:assert/strict');
function node(tag='div') {
  return {tag,textContent:'',children:[],open:false,append(...items){this.children.push(...items);},replaceChildren(){this.children=[];}};
}
const host=node();
const context = vm.createContext({document:{getElementById:()=>host,createElement:node}});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../extension/chart-summary.js'),'utf8'),context);
const c = {course_name:'<img src=x>درس نمونه',course_code:'TEST-123',availability:{reasons:[]}};
context.data = {not_taken:[c],option_groups:[{title:'اختیاری',remaining_option_count:1,ready:[c],needs_review:[],waiting:[],previously_taken_count:0}],needs_matching:[],uncertain_visual_courses:[],notice:'نمونه'};
vm.runInContext('renderVisualSummary(data)',context);
const flatten = n => [n,...n.children.flatMap(flatten)];
let all = flatten(host);
assert.ok(all.some(n=>n.tag==='span' && n.textContent===c.course_name));
assert.ok(all.some(n=>n.tag==='code' && n.textContent==='TEST-123'));
assert.equal(all.filter(n=>n.tag==='details').length,1);
context.data.not_taken=[];
context.data.option_groups=[];
vm.runInContext('renderVisualSummary(data)',context);
all=flatten(host);
assert.ok(!all.some(n=>n.textContent===c.course_name));
assert.ok(all.some(n=>n.textContent.includes('پیدا نشد')));
context.data.main_alternatives=[{title:'انقلاب اسلامی / اندیشه سیاسی امام',completion_status:'OPEN',ready:[{course_name:'انقلاب اسلامی ایران',course_code:'272481'}],needs_review:[],waiting:[],retake_options:[]}];
vm.runInContext('renderVisualSummary(data)',context);
assert.ok(host.children.some(n=>n.tag==='h3'&&n.textContent.includes('انقلاب اسلامی')));
assert.ok(flatten(host).some(n=>n.tag==='code'&&n.textContent==='272481'));
console.log('PASS: compact name/code rendering, group options, safe text and stale-result clearing');
