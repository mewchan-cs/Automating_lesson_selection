const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const node=(tag='div')=>({tag,textContent:'',children:[],hidden:false,append(...x){this.children.push(...x);},replaceChildren(){this.children=[];}});
const host=node(),context=vm.createContext({Intl,document:{getElementById:()=>host,createElement:node}});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../extension/academic-review.js'),'utf8'),context);
context.data={last_term:{semester:'1402-1',gpa:17},academic_status:{status:'CONFIRMED',label:'الف'},
  credit_limit:{maximum:24,final_term_exception:false},graduation:{label:'نیازمند بررسی',reason:'نمونه',confirmed_passed_chart_credits:3,required_total:null,exact_remaining_credits:null,missing_required:[],groups:[]},
  audit_summary:{confirmed:1,needs_review:0},course_audit:[],policy_source:'قواعد کاربر'};
const flat=n=>[n,...n.children.flatMap(flat)];
vm.runInContext('renderAcademicReview(data)',context);
assert.equal(host.hidden,false);
assert.ok(flat(host).some(n=>n.textContent.includes('الف')));
assert.ok(flat(host).some(n=>n.textContent.includes('۲۴')));
context.data.credit_limit={maximum:24,final_term_exception:true,recommended_credits:18};
vm.runInContext('renderAcademicReview(data)',context);
assert.ok(flat(host).some(n=>n.textContent.includes('ترم آخر')&&n.textContent.includes('۱۸')));
vm.runInContext('renderAcademicReview(null)',context);
assert.equal(host.hidden,true);assert.equal(host.children.length,0);
context.data.decision={text:'عادی — سقف انتخاب واحد 20 واحد',detail:null};
vm.runInContext('renderAcademicReview(data)',context);
assert.equal(host.children.filter(n=>n.tag==='details').length,1);
assert.ok(host.children.some(n=>n.textContent===context.data.decision.text));
assert.ok(!host.children.some(n=>n.textContent.includes('نیازمند بررسی')));
console.log('PASS: academic state, credit cap, final-term exception and opt-out clearing');
