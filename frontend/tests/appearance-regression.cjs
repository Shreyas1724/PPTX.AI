const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const base=process.env.PPTX_TEST_URL||'http://127.0.0.1:3300';
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 const errors=[];const context=await browser.newContext({viewport:{width:1440,height:1000}});
 let logged=false;
 await context.route('**/api/v1/**',async route=>{
  const path=new URL(route.request().url()).pathname.replace('/api/v1','');
  const user={id:'u1',name:'Aarav User',credits:30,email:'demo@example.com'};
  let data={};let status=200;
  if(path==='/auth/me'){data=logged?user:{detail:'Unauthorized'};status=logged?200:401}
  else if(path==='/auth/login'){logged=true;data={user}}
  else if(path==='/auth/logout'){logged=false;data={}}
  else if(path==='/auth/config')data={google_client_id:'',verification_available:true};
  else if(path==='/credits')data={balance:30,reserved:0,generation_cost:2,edit_cost:1,model_mode:'ai'};
  else if(path==='/projects')data=[];
  else if(path==='/presentations/d1')data={id:'d1',project_id:'p1',title:'A real presentation',theme:'midnight',version:1,slides:[{title:'Hello',body:['World']}]};
  else if(path==='/presentations/d1/jobs')data=[];
  else if(path==='/presentations')data=[{id:'d1',title:'A real presentation',theme:'midnight',version:1,slides:[{title:'Hello',body:['World']}]}];
  else if(path.startsWith('/history'))data={items:[]};
  else if(path==='/project-ideas')data=[];
  else if(path.includes('/capabilities'))data={ai_configured:false,research_configured:false,analysis_cost:2,mode:'outline'};
  await route.fulfill({status,contentType:'application/json',body:JSON.stringify(data)});
 });
 const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
 await page.goto(base+'/');await page.locator('.entrySwatches button').last().waitFor();
 assert.equal(await page.locator('.entryWheel [role=option]').count(),8);
 assert.equal(await page.locator('.entrySwatches button').count(),8);
 const palette=[];const buttons=[];
 for(const button of await page.locator('.entrySwatches button').all()){
  await button.click();palette.push(await page.locator('.entryPage').evaluate(el=>getComputedStyle(el).backgroundColor));
  buttons.push(await page.locator('.entryPrimary').evaluate(el=>getComputedStyle(el).backgroundColor));
  assert.equal(await button.getAttribute('aria-pressed'),'true');
 }
 assert.equal(new Set(palette).size,8);assert.equal(new Set(buttons).size,8);
 await page.reload();assert.equal(await page.locator('html').getAttribute('data-appearance'),'rose');
 await page.locator('.entryWheel ol').getByRole('button',{name:'Ocean',exact:true}).click();
 assert.equal(await page.locator('html').getAttribute('data-appearance'),'ocean');
 await page.waitForFunction(()=>getComputedStyle(document.querySelector('.entryWheel ol button')).color==='rgb(238, 250, 255)');
 await page.screenshot({path:'/tmp/entry-desktop.png'});
 await page.getByRole('button',{name:'Log in',exact:true}).click();
 await page.locator('input[name=email]').fill('demo@example.com');await page.locator('input[name=password]').fill('password');
 await page.getByRole('button',{name:'Log in to my workspace'}).click();await page.locator('.fluxora').waitFor();
 assert.equal(new URL(page.url()).pathname,'/app');
 assert.equal(await page.locator('html').getAttribute('data-appearance'),'ocean');
 await page.locator('.fx-stat__value').nth(1).filter({hasText:'30'}).waitFor();
 await page.locator('.fx-hero__video').evaluate(video=>new Promise((resolve,reject)=>{if(video.readyState>=2)resolve();else{video.addEventListener('loadeddata',resolve,{once:true});setTimeout(()=>reject(new Error('Video failed to load')),12000)}}));
 assert.equal(await page.locator('.fx-hero__video').evaluate(v=>v.paused),false);
 for(const theme of ['nature','ocean','space','aurora','minimal','cyberpunk','rose','sunset']){
  await page.locator('.appearance-picker select').selectOption(theme);
  assert.equal(await page.locator('html').getAttribute('data-appearance'),theme);
 }
 await page.screenshot({path:'/tmp/fluxora-desktop.png'});
 await page.locator('.featureDock').getByRole('button',{name:'AI Create'}).click();await page.waitForURL('**/create');
 await page.goto(base+'/app');await page.locator('.fluxora').waitFor();
 await page.locator('.featureDock').getByRole('button',{name:'My decks'}).click();await page.locator('.studioDeck').waitFor();
 assert.equal(await page.locator('.studioDeckMeta strong').textContent(),'A real presentation');
 await page.locator('.studioSearch input').fill('missing');await page.getByRole('heading',{name:'No matching presentations'}).waitFor();
 await page.goto(base+'/presentation/d1');await page.locator('.slideCanvas').waitFor();
 await page.locator('.appearance-picker select').selectOption('minimal');
 assert.equal(await page.locator('.slideCanvas').evaluate(el=>getComputedStyle(el).color),'rgb(245, 243, 255)','A dark presentation keeps light text under the Minimal screen theme');
 await page.locator('.appearance-picker select').selectOption('sunset');
 for(const size of [{width:390,height:844},{width:768,height:1024}]){
  await page.setViewportSize(size);await page.goto(base+'/');await page.locator('.entrySwatches').waitFor();
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Entry overflow '+size.width);
  await page.screenshot({path:'/tmp/entry-'+size.width+'.png'});
  await page.goto(base+'/app');await page.locator('.fluxora').waitFor();
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),'Home overflow '+size.width);
  await page.getByRole('button',{name:'Open menu',exact:true}).click();await page.locator('#fluxora-menu').waitFor();
  await page.keyboard.press('Escape');assert.equal(await page.locator('#fluxora-menu').count(),0);
  await page.screenshot({path:'/tmp/fluxora-'+size.width+'.png'});
 }
 await page.emulateMedia({reducedMotion:'reduce'});await page.reload();await page.locator('.fx-hero__video').waitFor();
 assert.equal(await page.locator('.fx-hero__video').evaluate(v=>v.paused),true);
 assert.deepEqual(errors,[]);
 console.log('PASS: eight themes, palette changes, persistence, ring selection, login → Fluxora, local video playback, real stats, Create route, deck search, mobile/tablet layout, menu/Escape and reduced motion. API calls mocked; no live backend verified.');
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
