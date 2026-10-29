const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const node=(tag='div')=>({tag,textContent:'',children:[],hidden:false,append(...items){this.children.push(...items);},replaceChildren(){this.children=[];}});
const host=node(),context=vm.createContext({Intl,document:{getElementById:()=>host,createElement:node}});
for(const file of ['graduation-report.js','academic-review.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,'../extension/'+file),'utf8'),context);
context.data={mode:'graduation',chart:'1401-1402',title:'واحدها تکمیل نیست',reason:'کسری واحد',
 required_credits:142,counted_passed_credits:90,reported_passed_credits:97,remaining_to_confirm:52,exact_remaining_credits:null,
 categories:[{name:'عمومی',required:22,confirmed:20,remaining_to_confirm:2}],missing_courses:[],groups:[],unresolved_rows:[],passed_not_allocated:[],note:'قبولی ۱۰'};
vm.runInContext('renderAcademicReview(data)',context);
const flat=n=>[n,...n.children.flatMap(flat)],all=flat(host);
assert.ok(all.some(n=>n.tag==='table'));
assert.ok(all.some(n=>n.textContent==='عمومی'));
assert.ok(all.some(n=>n.textContent.includes('۹۰')));
assert.ok(all.some(n=>n.textContent.includes('۵۲')));
assert.ok(!all.some(n=>n.textContent.includes('معدل تابستان')||n.textContent.includes('سقف واحد')||n.textContent.includes('وضعیت: نامشخص')));
console.log('PASS: graduation-only category/credit report; no academic-status or summer-cap messages');
