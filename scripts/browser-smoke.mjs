// Optional browser QA: npm install --prefix /tmp/mira-browser playwright
// PLAYWRIGHT_MODULE=/tmp/mira-browser/node_modules/playwright/index.mjs node scripts/browser-smoke.mjs
import { mkdir, writeFile } from 'node:fs/promises';
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const browser=await chromium.launch({executablePath:process.env.CHROME_PATH || '/usr/bin/google-chrome',headless:true,args:['--no-sandbox']});
const page=await browser.newPage({viewport:{width:1440,height:1000}});
const errors=[];page.on('pageerror',e=>errors.push(e.message));
const checks=[];
try {
 await mkdir('reports',{recursive:true});
 await page.goto('http://localhost:3000',{waitUntil:'networkidle'});
 await page.screenshot({path:'reports/welcome-desktop.png',fullPage:true});
 checks.push('production_page_loaded');
 async function send(text){await page.getByRole('textbox',{name:'Message Mira'}).fill(text);await page.getByRole('button',{name:'Send message',exact:true}).click();await page.getByRole('textbox',{name:'Message Mira'}).waitFor({state:'visible'});await page.waitForFunction(()=>!document.querySelector('textarea[aria-label="Message Mira"]').disabled,{timeout:60000});}
 const arrival=new Date(Date.now()+120*86400000).toISOString().slice(0,10);
 const departure=new Date(Date.now()+122*86400000).toISOString().slice(0,10);
 await send(`Goa ${arrival} to ${departure} for 2 adults`);
 await page.getByRole('button',{name:'Select',exact:true}).first().waitFor();
 checks.push('database_recommendations_rendered');
 await page.getByRole('button',{name:'Select',exact:true}).first().click();
 await page.getByRole('button',{name:'Confirm temporary hold'}).waitFor();
 await send('Is the pool heated?');
 const unknown=await page.evaluate(async()=>{const s=JSON.parse(localStorage.getItem('mira-session'));return (await fetch('http://localhost:8000/api/sessions/'+s.session_id+'/traces',{headers:{Authorization:'Bearer '+s.token}})).json()});
 if(!unknown.some(t=>t.tool_name==='get_policy'&&t.summary.known===false))throw new Error('Unknown policy was not checked against records');checks.push('unknown_policy_grounded');
 await send('Make it ₹9900 total stay');
 const pending=await page.evaluate(async()=>{const s=JSON.parse(localStorage.getItem('mira-session'));return (await fetch('http://localhost:8000/api/sessions/'+s.session_id,{headers:{Authorization:'Bearer '+s.token}})).json()});
 if(pending.state.negotiation_state.status!=='pending_approval')throw new Error('Offer must require manager review');checks.push('negotiation_pending_review');
 await page.getByRole('button',{name:'Demo manager'}).click();
 await page.getByRole('textbox',{name:'Admin token'}).fill(process.env.DEMO_ADMIN_TOKEN || 'mira-local-review-token');
 await page.getByRole('button',{name:'Load requests'}).click();
 const selectedOffer=pending.state.negotiation_state.id;
 const offerCard=page.getByText(`Offer ${selectedOffer.slice(0,8)} · pending approval`,{exact:true}).locator('..');
 await offerCard.getByRole('button',{name:'Approve',exact:true}).click();
 await offerCard.waitFor({state:'hidden'});
 checks.push('real_manager_approval');
 await page.getByRole('button',{name:'Close manager review'}).click();
 await send('Please confirm the temporary hold using the manager-approved total.');
 await page.getByText('Your temporary hold',{exact:true}).waitFor();checks.push('successful_booking_hold');
 await page.reload({waitUntil:'networkidle'});
 await page.getByText('Your temporary hold',{exact:true}).waitFor();checks.push('state_survives_reload');
 await page.getByRole('button',{name:'Tool activity'}).click();
 await page.getByText('create_booking_hold',{exact:true}).waitFor();checks.push('real_tool_traces_visible');
 await page.screenshot({path:'reports/booking-desktop.png',fullPage:true});
 await page.setViewportSize({width:390,height:844});
 await page.screenshot({path:'reports/booking-mobile.png',fullPage:true});
 const overflow=await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth);
 if(overflow)throw new Error('Mobile viewport has horizontal overflow');
 checks.push('mobile_layout_without_horizontal_overflow');
 await page.getByRole('button',{name:'Cancel temporary hold',exact:true}).click();
 await page.getByText('Hold cancelled',{exact:true}).waitFor({timeout:60000});
 checks.push('hold_cancelled_through_ui');
 await page.reload({waitUntil:'networkidle'});
 await page.getByText('Hold cancelled',{exact:true}).waitFor();checks.push('cancellation_survives_reload');
 if(errors.length)throw new Error(errors.join('\n'));
 await writeFile('reports/browser-smoke.json',JSON.stringify({passed:true,checks,page_errors:errors},null,2));
 console.log(JSON.stringify({passed:true,checks,page_errors:errors}));
} catch(error){await page.screenshot({path:'reports/browser-failure.png',fullPage:true});await writeFile('reports/browser-smoke.json',JSON.stringify({passed:false,checks,page_errors:errors,error:String(error)},null,2));throw error;}finally{await browser.close();}
