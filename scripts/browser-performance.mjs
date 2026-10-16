// Production UI regression checks with delayed/mock API responses; no model calls.
// Start a production frontend on port 3001, then run with PLAYWRIGHT_MODULE if needed.
import assert from 'node:assert/strict';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE||'playwright');
const browser=await chromium.launch({executablePath:process.env.CHROME_PATH||'/usr/bin/google-chrome',headless:true,args:['--no-sandbox']});
const page=await browser.newPage({viewport:{width:1440,height:1000}});
const errors=[];
page.on('pageerror',error=>errors.push(error.message));
let version=0,failChat=false,failFlags=false,chatRequests=[],sessionReads=0,traceReads=0;
let releaseChat;
async function completeChat(){
 const deadline=Date.now()+10000;
 while(!releaseChat){
  assert.ok(Date.now()<deadline,'Chat request did not arrive');
  await new Promise(resolve=>setTimeout(resolve,10));
 }
 releaseChat();releaseChat=undefined;
}
const state=()=>({session_id:'performance-session',state_version:version,booking_requirements:{},active_intent:'greeting',latest_recommendations:[],latest_quote_id:null,quote:null,negotiation_state:{},pending_confirmation:false,hold:null,next_action:'respond_to_guest',escalation_status:'none'});
const respond=(route,data,status=200)=>route.fulfill({status,contentType:'application/json',headers:{'Access-Control-Allow-Origin':'*','Access-Control-Allow-Headers':'*'},body:JSON.stringify(data)});
await page.route('http://localhost:8000/**',async route=>{
 const request=route.request(),path=new URL(request.url()).pathname;
 if(request.method()==='OPTIONS')return respond(route,{});
 if(path==='/api/sessions')return respond(route,{session_id:'performance-session',token:'mock-token'});
 if(path==='/api/chat'){
  const body=request.postDataJSON();chatRequests.push(body);
  await new Promise(resolve=>{releaseChat=resolve});
  if(failChat)return respond(route,{error:'Temporary chat outage'},503);
  version++;return respond(route,{state:state(),response:`Reply ${version}`,request_id:`mock-${version}`});
 }
 if(path.endsWith('/flags'))return respond(route,failFlags?{error:'Flags unavailable'}:[],failFlags?503:200);
 if(path.endsWith('/traces')){traceReads++;return respond(route,[])}
 sessionReads++;return respond(route,{state:state(),messages:[],llm_mode:'openai'});
});
try{
 await page.goto(process.env.FRONTEND_URL||'http://127.0.0.1:3001',{waitUntil:'networkidle'});
 const input=page.getByRole('textbox',{name:'Message Mira'}),send=page.getByRole('button',{name:'Send message',exact:true});
 await input.fill('First message');await send.click();
 await page.getByText('First message',{exact:true}).waitFor();
 assert.equal(await input.inputValue(),'');
 assert.equal(await input.isEnabled(),true);
 await input.fill('Draft while waiting');
 await page.waitForFunction(()=>document.body.textContent.includes('Mira is checking'));
 failFlags=true;await completeChat();
 await page.getByText('Reply 1',{exact:true}).waitFor();
 await page.waitForFunction(()=>!document.body.textContent.includes('Mira is checking'));
 assert.equal(await input.inputValue(),'Draft while waiting');
 assert.equal(await send.isEnabled(),true);
 assert.equal(sessionReads,0,'chat must not refetch session/history');
 assert.equal(traceReads,0,'traces load only when requested');
 assert.equal(await page.getByRole('button',{name:'Retry message'}).count(),0,'diagnostic failure must not fail chat');
 await page.getByRole('button',{name:'Tool activity',exact:true}).click();
 await page.waitForFunction(()=>document.body.textContent.includes('Stay activity could not be refreshed'));
 assert.ok(traceReads>0);
 failChat=true;await send.click();
 await completeChat();
 await page.getByRole('button',{name:'Retry message'}).waitFor();
 assert.equal(await input.inputValue(),'Draft while waiting');
 assert.equal(await page.locator('[aria-live="polite"]').getByText('Draft while waiting',{exact:true}).count(),0,'failed optimistic message is removed');
 const retryKey=chatRequests.at(-1).idempotency_key;
 failChat=false;await page.getByRole('button',{name:'Retry message'}).click();
 await completeChat();
 await page.getByText('Reply 2',{exact:true}).waitFor();
 assert.equal(chatRequests.at(-1).idempotency_key,retryKey);
 assert.equal(await page.locator('[aria-live="polite"]').getByText('Draft while waiting',{exact:true}).count(),1);
 assert.deepEqual(errors,[]);
 console.log(JSON.stringify({passed:true,checks:['immediate sent message','composer usable during request','draft preserved','no history refetch after chat','lazy traces','diagnostic failure isolated','failed message rollback','idempotent retry'],chatRequests:chatRequests.length,sessionReads,traceReads}));
}finally{await browser.close()}
