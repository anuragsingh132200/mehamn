// Paid live-model UI probe. Uses the same Playwright setup as browser-smoke.mjs.
import {mkdir,writeFile} from 'node:fs/promises';
const {chromium}=await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const browser=await chromium.launch({executablePath:process.env.CHROME_PATH || '/usr/bin/google-chrome',headless:true,args:['--no-sandbox']});
const page=await browser.newPage({viewport:{width:1440,height:1000}});
const errors=[],checks=[];
page.on('pageerror',e=>errors.push(e.message));
try{
 await mkdir('reports',{recursive:true});
 await page.goto('http://localhost:3000',{waitUntil:'networkidle'});
 await page.getByRole('button',{name:'Plan a three-day Goa itinerary'}).click();
 const card=page.getByRole('region',{name:'Your demo itinerary'});
 await card.waitFor({timeout:90000});
 if(await card.locator('article').count()!==3)throw Error('Expected three day cards');
 await card.getByText('FICTIONAL DEMO ITINERARY',{exact:true}).waitFor();
 checks.push('live itinerary displayed with three days and demo label');
 await page.screenshot({path:'reports/itinerary-desktop.png',fullPage:true});
 await page.reload({waitUntil:'networkidle'});
 await card.waitFor();
 if(await card.locator('article').count()!==3)throw Error('Plan not restored');
 checks.push('saved itinerary restored after reload');
 await page.setViewportSize({width:390,height:844});
 await page.screenshot({path:'reports/itinerary-mobile.png',fullPage:true});
 if(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth))throw Error('Mobile horizontal overflow');
 checks.push('mobile layout without horizontal overflow');
 if(errors.length)throw Error(errors.join('; '));
 checks.push('no browser runtime errors');
 await writeFile('reports/browser-itinerary.json',JSON.stringify({status:'passed',checks,errors},null,2));
 console.log(JSON.stringify({status:'passed',checks}));
}catch(e){await writeFile('reports/browser-itinerary.json',JSON.stringify({status:'failed',checks,errors,error:e.message},null,2));throw e;}
finally{await browser.close();}
