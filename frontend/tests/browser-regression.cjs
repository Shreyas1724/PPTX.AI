const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const base=process.env.PPTX_TEST_URL||'http://127.0.0.1:3300';
const email=process.env.PPTX_TEST_EMAIL;
const password=process.env.PPTX_TEST_PASSWORD;
const waitForSignal=(signal,label)=>{let timer;return Promise.race([signal,new Promise((_,reject)=>{timer=setTimeout(()=>reject(new Error('Timed out waiting for '+label)),30000)})]).finally(()=>clearTimeout(timer))};
if(!email||!password)throw new Error('Set PPTX_TEST_EMAIL and PPTX_TEST_PASSWORD');
(async()=>{
 const browser=await chromium.launch({headless:true,args:['--no-sandbox']});
 const context=await browser.newContext();
 const page=await context.newPage();
 const runtimeErrors=[];
 page.on('pageerror',error=>runtimeErrors.push(error.message));
 const api=async(path,method='GET',data)=>{
  const csrf=(await context.cookies(base)).find(cookie=>cookie.name==='pptx_csrf')?.value||'';
  const response=await context.request.fetch(base+'/api/v1'+path,{method,data,headers:{'X-CSRF-Token':decodeURIComponent(csrf)}});
  assert(response.ok(),method+' '+path+' failed '+response.status()+' '+await response.text());
  return response.json();
 };
 const fixtureProjects=[];
 const fixtureDecks=[];
 const fixtureIdeas=[];
 let mobileContext;
 try{
  await api('/auth/login','POST',{email,password});
  const project=await api('/projects','POST',{name:'Frontend regression '+Date.now()});fixtureProjects.push(project.id);
  const deckA=await api('/presentations','POST',{project_id:project.id,title:'Frontend regression A'});fixtureDecks.push(deckA.id);
  const deckB=await api('/presentations','POST',{project_id:project.id,title:'Frontend regression B'});fixtureDecks.push(deckB.id);
  for(let n=1;n<=4;n++)await api('/presentations/'+deckA.id+'/slides','POST',{title:'Slide '+n,body:['Content '+n]});
  await api('/presentations/'+deckB.id+'/slides','POST',{title:'Other deck slide',body:['Other content']});
  await page.goto(base+'/presentation/'+deckA.id);
  await page.locator('.editorBar strong').filter({hasText:'Frontend regression A'}).waitFor();
  assert.equal(await page.locator('.thumbnail').count(),4);

  await page.locator('textarea[name=body]').fill('one\ntwo\nthree\nfour\nfive\nsix\nseven');
  let slidePatches=0;const countPatch=request=>{if(request.method()==='PATCH'&&request.url().includes('/slides/'))slidePatches++};page.on('request',countPatch);
  await page.getByRole('button',{name:'Save slide',exact:true}).click();
  await page.getByRole('alert').filter({hasText:'at most six'}).waitFor();
  assert.equal(slidePatches,0,'Invalid slide must not be silently truncated and saved');
  assert.equal(await page.locator('textarea[name=body]').inputValue(),'one\ntwo\nthree\nfour\nfive\nsix\nseven');
  assert.deepEqual((await api('/presentations/'+deckA.id)).slides[0].body,['Content 1']);
  page.off('request',countPatch);
  await page.locator('textarea[name=body]').fill('Content 1');
  await page.locator('.toast button').click();
  console.log('PASS: excessive slide points preserve unsaved content without sending a PATCH');

  await page.getByRole('button',{name:'Mobile Control',exact:true}).click();
  const createdResponse=page.waitForResponse(response=>response.url().endsWith('/presentation-control/sessions')&&response.request().method()==='POST');
  await page.getByRole('button',{name:'Create pairing QR'}).click();
  const invite=await(await createdResponse).json();
  await page.locator('.liveStatus.connected').waitFor();
  mobileContext=await browser.newContext({viewport:{width:390,height:844}});
  const phone=await mobileContext.newPage();phone.on('pageerror',error=>runtimeErrors.push(error.message));
  await phone.goto(base+'/control'+new URL(invite.pairing_url).hash);
  await phone.locator('.connection.on').waitFor();
  await phone.locator('.mobileStage strong').filter({hasText:'SLIDE 1'}).waitFor();
  await phone.getByRole('button',{name:'Next slide',exact:true}).click();
  await phone.locator('.mobileStage strong').filter({hasText:'SLIDE 2'}).waitFor();
  await phone.getByRole('button',{name:'Next slide',exact:true}).click();
  await phone.locator('.mobileStage strong').filter({hasText:'SLIDE 3'}).waitFor();
  assert.match(await page.locator('.canvasMark').innerText(),/03$/);
  await page.locator('.controlHead .close').click();
  await page.locator('.thumbnail').nth(3).click();
  await phone.locator('.mobileStage strong').filter({hasText:'SLIDE 4'}).waitFor();
  await phone.getByRole('button',{name:'Previous slide',exact:true}).click();
  await phone.locator('.mobileStage strong').filter({hasText:'SLIDE 3'}).waitFor();
  assert.match(await page.locator('.canvasMark').innerText(),/03$/);
  await page.getByRole('button',{name:'Add slide',exact:true}).click();
  await phone.locator('.mobileStage span').filter({hasText:'of 5'}).waitFor();
  await phone.getByRole('button',{name:'Last slide',exact:true}).click();
  await phone.locator('.mobileStage strong').filter({hasText:'SLIDE 5'}).waitFor();
  await page.getByRole('button',{name:'Mobile Control',exact:true}).click();
  await page.getByRole('button',{name:'End session',exact:true}).click();
  await phone.getByText('The host ended this control session.',{exact:true}).waitFor();
  assert(await phone.getByRole('button',{name:'Next slide',exact:true}).isDisabled());
  await page.getByRole('button',{name:'Mobile Control',exact:true}).click();
  await page.getByRole('button',{name:'Create pairing QR'}).waitFor();
  await page.locator('.controlHead .close').click();
  console.log('PASS: real pairing, repeated next, host synchronization, previous, end and fresh-session UI');

  await page.route('**/api/v1/projects',route=>route.request().method()==='GET'?route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({detail:'Simulated project list failure'})}):route.continue());
  await page.goto(base+'/app');
  await page.locator('.studioMain').waitFor();
  await page.getByRole('button',{name:'Sign out',exact:true}).waitFor();
  await page.getByRole('alert').filter({hasText:'Simulated project list failure'}).waitFor();
  assert.equal(await page.locator('.identityPage').count(),0);
  await page.unroute('**/api/v1/projects');
  console.log('PASS: project-list failures retain authenticated workspace');

  let releaseOld;const oldGate=new Promise(resolve=>{releaseOld=resolve});let oldStarted;const started=new Promise(resolve=>{oldStarted=resolve});
  await page.route('**/api/v1/presentations/'+deckA.id,async route=>{oldStarted();await oldGate;await route.continue()});
  await page.goto(base+'/presentation/'+deckA.id,{waitUntil:'domcontentloaded'});
  await waitForSignal(started,'delayed presentation request');
  await page.evaluate(id=>{history.pushState({},'','/presentation/'+id);dispatchEvent(new PopStateEvent('popstate'))},deckB.id);
  await page.locator('.editorBar strong').filter({hasText:'Frontend regression B'}).waitFor();
  releaseOld();
  await page.waitForTimeout(600);
  assert.equal(await page.locator('.editorBar strong').innerText(),'Frontend regression B');
  assert.equal(await page.locator('input[name=title]').inputValue(),'Other deck slide');
  await page.unroute('**/api/v1/presentations/'+deckA.id);
  console.log('PASS: late presentation response cannot overwrite the active deck');

  const ideaA=await api('/idea-projects','POST',{title:'Regression idea A',idea:'Build a practical inventory tracker for a local workshop.'});fixtureIdeas.push(ideaA.id);
  const ideaB=await api('/idea-projects','POST',{title:'Regression idea B',idea:'Build a useful task planner for a small community group.'});fixtureIdeas.push(ideaB.id);
  await page.route('**/api/v1/idea-projects/capabilities',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({ai_configured:true,research_configured:false,analysis_cost:0,mode:'ai'})}));
  await page.route('**/api/v1/idea-projects/'+ideaA.id+'/analysis',route=>route.fulfill({status:202,contentType:'application/json',body:JSON.stringify({job_id:'regression-job',status:'queued',cost:0})}));
  await page.route('**/api/v1/idea-projects/'+ideaA.id+'/analysis/jobs/regression-job',route=>route.fulfill({status:200,contentType:'application/json',body:JSON.stringify({id:'regression-job',status:'completed',cost:0})}));
  await page.goto(base+'/projects');
  await page.locator('.projProjectCard').filter({hasText:'Regression idea A'}).click();
  await page.locator('.projWorkspaceHead h1').filter({hasText:'Regression idea A'}).waitFor();
  let releaseAnalysis;const analysisGate=new Promise(resolve=>{releaseAnalysis=resolve});let analysisFetchStarted;const analysisFetch=new Promise(resolve=>{analysisFetchStarted=resolve});
  await page.route('**/api/v1/idea-projects/'+ideaA.id,async route=>{analysisFetchStarted();await analysisGate;await route.continue()});
  await page.getByRole('button',{name:'Analyze entire project'}).click();
  await waitForSignal(analysisFetch,'delayed analysis refresh');
  await page.getByRole('button',{name:'All projects',exact:true}).click();
  await page.locator('.projProjectCard').filter({hasText:'Regression idea B'}).click();
  await page.locator('.projWorkspaceHead h1').filter({hasText:'Regression idea B'}).waitFor();
  releaseAnalysis();
  await page.waitForTimeout(600);
  assert.equal(await page.locator('.projWorkspaceHead h1').innerText(),'Regression idea B');
  console.log('PASS: late analysis refresh cannot overwrite another project');

  await page.goto(base+'/signup');
  await page.locator('input[name=mobile]').fill('+91 98765 43210');
  assert.equal(await page.locator('input[name=mobile]').evaluate(input=>input.validity.patternMismatch),false);
  await page.locator('input[name=mobile]').fill('invalid phone');
  assert.equal(await page.locator('input[name=mobile]').evaluate(input=>input.validity.patternMismatch),true);
  console.log('PASS: phone pattern enforces a country code with modern browser regex rules');
  assert.deepEqual(runtimeErrors,[],'No unhandled browser errors');
  console.log('PASS: no unhandled browser errors');
 }finally{
  const cleanupErrors=[];
  for(const id of fixtureIdeas.reverse())try{await api('/idea-projects/'+id,'DELETE')}catch(error){cleanupErrors.push(error)}
  for(const id of fixtureDecks.reverse())try{await api('/presentations/'+id,'DELETE')}catch(error){cleanupErrors.push(error)}
  for(const id of fixtureProjects.reverse())try{await api('/projects/'+id,'DELETE')}catch(error){cleanupErrors.push(error)}
  await mobileContext?.close();await browser.close();
  if(cleanupErrors.length)throw new AggregateError(cleanupErrors,'Browser fixture cleanup failed');
 }
})().catch(error=>{console.error(error);process.exitCode=1});
