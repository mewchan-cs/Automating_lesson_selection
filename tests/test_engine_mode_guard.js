const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const src=fs.readFileSync(path.join(__dirname,'../extension/popup.js'),'utf8');
const code=src.slice(src.indexOf('async function sendToEngine('),src.indexOf('function saveJSON('));
let payload={academic_review:{academic_status:{label:'نامشخص'}}},request;
const context=vm.createContext({$:()=>({checked:true}),fetch:async(url,options)=>{request=JSON.parse(options.body);return {ok:true,json:async()=>payload};}});
vm.runInContext(code,context);
(async()=>{
  await assert.rejects(()=>vm.runInContext("sendToEngine({},'1401-1402','TEST')",context),/موتور قبلی/);
  payload={academic_review:{mode:'graduation'}};
  const result=await vm.runInContext("sendToEngine({},'1401-1402','TEST')",context);
  assert.equal(result.academic_review.mode,'graduation');assert.equal(request.review_mode,'graduation');
  console.log('PASS: new app rejects stale academic-mode engine and requests graduation-only mode');
})().catch(error=>{console.error(error);process.exitCode=1;});
