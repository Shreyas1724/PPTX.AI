import os, json, hashlib, time, re, io, asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, Header, UploadFile, File, Request, Query
from fastapi.responses import StreamingResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field, StringConstraints
from typing import Annotated
from sqlalchemy.orm import Session
from sqlalchemy import select, func, update
from .core import Base, ENGINE, Session as DBSession, User, Project, Presentation, Version, CreditEvent, Job, Document, SessionToken, hash_password, check_password, new_token
from .engine import render
from .slide_spec import SlideSpec
from .quality import audit_slides
from .auth import router as auth_router, current, db
from .activity import purge, record, RETENTION_SECONDS
from .core import Activity, Operation
from . import credits as credit_service
from .control import router as control_router
from .security import csrf, BodyLimit, validate_production
from .auth import limit as rate_limit
from fastapi.responses import JSONResponse
import hmac, uuid, logging

@asynccontextmanager
async def lifespan(app):
 validate_production()
 Base.metadata.create_all(ENGINE)
 from .manage import recover_legacy
 with DBSession() as session:
  recover_legacy(session)
  purge(session)
 yield
app=FastAPI(title='PPTX.AI API',version='3.0',lifespan=lifespan,docs_url=None if os.getenv('APP_ENV')=='production' else '/api/docs',openapi_url=None if os.getenv('APP_ENV')=='production' else '/api/openapi.json',redoc_url=None)
app.add_middleware(BodyLimit)
app.add_middleware(CORSMiddleware,allow_origins=[x.strip() for x in os.getenv('CORS_ORIGINS','http://localhost:3000').split(',')],allow_credentials=True,allow_methods=['GET','POST','PATCH','DELETE'],allow_headers=['Authorization','Content-Type','Idempotency-Key','X-CSRF-Token'])
def owned_project(pid,user,session):
 p=session.get(Project,pid)
 if not p or p.owner_id!=user.id: raise HTTPException(404,'Project not found')
 return p
def owned_deck(did,user,session):
 p=session.scalar(select(Presentation).where(Presentation.id==did).with_for_update())
 if not p: raise HTTPException(404,'Presentation not found')
 owned_project(p.project_id,user,session); return p
def deck_out(p): return {'id':p.id,'project_id':p.project_id,'title':p.title,'theme':p.theme,'version':p.version,'slides':json.loads(p.slides)}
def snapshot(p,session):
 p.version+=1; session.add(Version(presentation_id=p.id,number=p.version,slides=p.slides,theme=p.theme)); session.commit(); session.refresh(p)
class Credentials(BaseModel):
 email:str; password:str=Field(min_length=8,max_length=128)
class Name(BaseModel): name:str=Field(min_length=1,max_length=120)
class DeckCreate(BaseModel): project_id:str; title:str=Field(min_length=1,max_length=120)
class DeckUpdate(BaseModel): title:str|None=Field(default=None,min_length=1,max_length=120); theme:str|None=Field(default=None,max_length=20)
class Slide(SlideSpec):
 pass
class Generate(BaseModel): prompt:str=Field(min_length=3,max_length=4000); count:int=Field(default=8,ge=1,le=20)
class AgentRequest(BaseModel): presentation_id:str; instruction:str=Field(min_length=3,max_length=2000)
class Restore(BaseModel): version:int
@app.get('/api/v1/health')
def health(): return {'status':'ok','llm':'configured' if os.getenv('LLM_API_KEY') else 'local-outline'}
@app.get('/api/v1/health/ready')
def ready(session:Session=Depends(db)): session.execute(select(User).limit(1)); return {'status':'ready'}
app.include_router(auth_router)
from .billing import router as billing_router
app.include_router(billing_router)
app.include_router(control_router)
from .project_routes import router as project_studio_router
app.include_router(project_studio_router)

@app.get('/api/v1/credits')
def credits(user:User=Depends(current),session:Session=Depends(db)): return credit_service.wallet(session,user.id)
@app.get('/api/v1/credits/history')
def credits_history(offset:int=Query(default=0,ge=0),limit:int=Query(default=30,ge=1,le=100),user:User=Depends(current),session:Session=Depends(db)):
 query=select(CreditEvent).where(CreditEvent.user_id==user.id).order_by(CreditEvent.created_at.desc(),CreditEvent.id.desc()).offset(offset).limit(limit+1)
 rows=session.scalars(query).all()
 return {'has_more':len(rows)>limit,'items':[{'id':e.id,'amount':e.amount,'reason':e.reason,'created_at':e.created_at} for e in rows[:limit]]}
@app.get('/api/v1/credits/operations')
def operations(user:User=Depends(current),session:Session=Depends(db)):
 rows=session.scalars(select(Operation).where(Operation.user_id==user.id).order_by(Operation.created_at.desc()).limit(30)).all()
 return [{'id':o.id,'job_id':o.job_id,'kind':o.kind,'cost':o.cost,'state':o.state,'created_at':o.created_at} for o in rows]
@app.get('/api/v1/projects')
def projects(user:User=Depends(current),session:Session=Depends(db)):
 from .project_models import ProjectBlueprint
 ideas=set(session.scalars(select(ProjectBlueprint.project_id).join(Project,Project.id==ProjectBlueprint.project_id).where(Project.owner_id==user.id)).all())
 return [{'id':p.id,'name':p.name,'created_at':p.created_at,'has_blueprint':p.id in ideas}
         for p in session.scalars(select(Project).where(Project.owner_id==user.id).order_by(Project.created_at.desc())).all()]
@app.post('/api/v1/projects')
def create_project(data:Name,user:User=Depends(current),session:Session=Depends(db)):
 p=Project(owner_id=user.id,name=data.name); session.add(p); session.commit(); return {'id':p.id,'name':p.name}
@app.patch('/api/v1/projects/{pid}')
def rename_project(pid:str,data:Name,user:User=Depends(current),session:Session=Depends(db)):
 p=owned_project(pid,user,session); p.name=data.name; session.commit(); return {'id':p.id,'name':p.name}
@app.delete('/api/v1/projects/{pid}')
def delete_project(pid:str,user:User=Depends(current),session:Session=Depends(db)):
 owned_project(pid,user,session)
 if session.scalar(select(Presentation).where(Presentation.project_id==pid)): raise HTTPException(409,'Delete presentations first')
 for doc in session.scalars(select(Document).where(Document.project_id==pid)):session.delete(doc)
 session.delete(session.get(Project,pid)); session.commit(); return {'ok':True}
@app.get('/api/v1/presentations')
def presentations(user:User=Depends(current),session:Session=Depends(db)):
 ids=select(Project.id).where(Project.owner_id==user.id)
 return [deck_out(p) for p in session.scalars(select(Presentation).where(Presentation.project_id.in_(ids)).order_by(Presentation.created_at.desc())).all()]
@app.post('/api/v1/presentations')
def create_deck(data:DeckCreate,user:User=Depends(current),session:Session=Depends(db)):
 owned_project(data.project_id,user,session); p=Presentation(project_id=data.project_id,title=data.title); session.add(p); session.commit(); return deck_out(p)
@app.get('/api/v1/presentations/{did}')
def get_deck(did:str,user:User=Depends(current),session:Session=Depends(db)): return deck_out(owned_deck(did,user,session))
@app.patch('/api/v1/presentations/{did}')
def update_deck(did:str,data:DeckUpdate,user:User=Depends(current),session:Session=Depends(db)):
 p=owned_deck(did,user,session)
 if data.title is not None: p.title=data.title[:120]
 if data.theme is not None:
  if data.theme not in ('midnight','light','aurora'): raise HTTPException(422,'Unknown theme')
  p.theme=data.theme
 snapshot(p,session); return deck_out(p)
@app.delete('/api/v1/presentations/{did}')
def delete_deck(did:str,user:User=Depends(current),session:Session=Depends(db)):
 p=owned_deck(did,user,session)
 if session.scalar(select(Job).where(Job.presentation_id==did,Job.status.in_(['queued','running']))):raise HTTPException(409,'Wait for active jobs to finish before deleting this deck.')
 for v in session.scalars(select(Version).where(Version.presentation_id==did)): session.delete(v)
 for j in session.scalars(select(Job).where(Job.presentation_id==did)): session.delete(j)
 session.delete(p); session.commit(); return {'ok':True}
@app.get('/api/v1/presentations/{did}/versions')
def versions(did:str,user:User=Depends(current),session:Session=Depends(db)):
 owned_deck(did,user,session); return [{'number':v.number,'created_at':v.created_at,'theme':v.theme} for v in session.scalars(select(Version).where(Version.presentation_id==did).order_by(Version.number.desc()))]
@app.post('/api/v1/presentations/{did}/restore')
def restore(did:str,data:Restore,user:User=Depends(current),session:Session=Depends(db)):
 p=owned_deck(did,user,session); v=session.scalar(select(Version).where(Version.presentation_id==did,Version.number==data.version))
 if not v: raise HTTPException(404,'Version not found')
 p.slides=v.slides; p.theme=v.theme; snapshot(p,session); return deck_out(p)
@app.get('/api/v1/presentations/{did}/slides')
def slides(did:str,user:User=Depends(current),session:Session=Depends(db)): return json.loads(owned_deck(did,user,session).slides)
@app.post('/api/v1/presentations/{did}/slides')
def add_slide(did:str,data:Slide,user:User=Depends(current),session:Session=Depends(db)):
 p=owned_deck(did,user,session); slides=json.loads(p.slides);
 if len(slides)>=20:raise HTTPException(422,'A presentation can have up to 20 slides.')
 slides.append(data.model_dump()); p.slides=json.dumps(slides); snapshot(p,session); return deck_out(p)
@app.patch('/api/v1/presentations/{did}/slides/{index}')
def edit_slide(did:str,index:int,data:Slide,user:User=Depends(current),session:Session=Depends(db)):
 p=owned_deck(did,user,session); slides=json.loads(p.slides)
 if index<0 or index>=len(slides): raise HTTPException(404,'Slide not found')
 slides[index]=data.model_dump(); p.slides=json.dumps(slides); snapshot(p,session); return deck_out(p)
@app.delete('/api/v1/presentations/{did}/slides/{index}')
def remove_slide(did:str,index:int,user:User=Depends(current),session:Session=Depends(db)):
 p=owned_deck(did,user,session); slides=json.loads(p.slides)
 if index<0 or index>=len(slides): raise HTTPException(404,'Slide not found')
 if len(slides)==1:raise HTTPException(409,'Keep at least one slide in the presentation.')
 slides.pop(index); p.slides=json.dumps(slides); snapshot(p,session); return deck_out(p)
@app.post('/api/v1/presentations/{did}/generate',status_code=202)
def start_generation(did:str,data:Generate,idempotency_key:str=Header(...,min_length=1,max_length=128),user:User=Depends(current),session:Session=Depends(db)):
 rate_limit(session,'generation:'+user.id,20,600)
 p=owned_deck(did,user,session)
 op=credit_service.reserve(session,user.id,p,'generation',data.model_dump(),idempotency_key)
 return {'job_id':op.job_id,'status':session.get(Job,op.job_id).status,'cost':op.cost}
@app.get('/api/v1/jobs/{jid}')
def job_status(jid:str,user:User=Depends(current),session:Session=Depends(db)):
 j=session.get(Job,jid)
 if not j or j.user_id!=user.id: raise HTTPException(404,'Job not found')
 op=session.scalar(select(Operation).where(Operation.job_id==jid))
 return {'id':j.id,'status':j.status,'stage':j.stage,'error':j.error,'presentation_id':j.presentation_id,'cost':op.cost if op else 0,'credit_state':op.state if op else 'legacy','result':json.loads(op.result) if op else {}}
@app.get('/api/v1/presentations/{did}/quality')
def presentation_quality(did:str,user:User=Depends(current),session:Session=Depends(db)):
 rate_limit(session,'quality:'+user.id,12,600)
 p=owned_deck(did,user,session)
 raw=json.loads(p.slides)
 if not raw:raise HTTPException(409,'Presentation has no slides')
 return audit_slides(p.title,raw,p.theme,verify_external=os.getenv('PPTX_VISUAL_QA','0')=='1')

@app.get('/api/v1/presentations/{did}/export')
def export(did:str,user:User=Depends(current),session:Session=Depends(db)):
 rate_limit(session,'export:'+user.id,30,600)
 p=owned_deck(did,user,session); slides=json.loads(p.slides)
 if not slides: raise HTTPException(409,'Presentation has no slides')
 content=render(p.title,slides,p.theme)
 return Response(content,media_type='application/vnd.openxmlformats-officedocument.presentationml.presentation',headers={'Content-Disposition':f'attachment; filename="presentation-{p.id}.pptx"'})
@app.post('/api/v1/projects/{pid}/documents')
async def upload(pid:str,file:UploadFile=File(...),user:User=Depends(current),session:Session=Depends(db)):
 rate_limit(session,'upload:'+user.id,15,600)
 owned_project(pid,user,session)
 raw=await file.read(5_000_001)
 if len(raw)>5_000_000: raise HTTPException(413,'File too large')
 name=(file.filename or 'document').split('/')[-1].split('\\')[-1]
 ext=name.rsplit('.',1)[-1].lower()
 from .documents import parse,DocumentError
 try:content=await asyncio.to_thread(parse,raw,ext)
 except DocumentError as exc:raise HTTPException(422,str(exc))
 if not content.strip(): raise HTTPException(422,'No extractable text')
 d=Document(project_id=pid,filename=name[:200],content=content[:200000]); session.add(d); session.commit(); return {'id':d.id,'filename':d.filename,'characters':len(d.content)}
@app.get('/api/v1/projects/{pid}/documents')
def documents(pid:str,user:User=Depends(current),session:Session=Depends(db)):
 owned_project(pid,user,session); return [{'id':d.id,'filename':d.filename} for d in session.scalars(select(Document).where(Document.project_id==pid))]
@app.post('/api/v1/agent/chat',status_code=202)
def agent(data:AgentRequest,idempotency_key:str=Header(...,min_length=1,max_length=128),user:User=Depends(current),session:Session=Depends(db)):
 rate_limit(session,'agent:'+user.id,30,600)
 p=owned_deck(data.presentation_id,user,session)
 op=credit_service.reserve(session,user.id,p,'edit',{'instruction':data.instruction},idempotency_key)
 return {'job_id':op.job_id,'status':session.get(Job,op.job_id).status,'cost':op.cost}

@app.middleware('http')
async def security_and_activity(request:Request,call_next):
 # Same-origin browser writes; API clients may send bearer tokens without Origin.
 request_id=uuid.uuid4().hex
 origin=request.headers.get('origin')
 allowed={x.strip() for x in os.getenv('CORS_ORIGINS','http://localhost:3000').split(',')}
 if request.method not in ('GET','HEAD','OPTIONS'):
  if (origin and origin not in allowed) or request.headers.get('sec-fetch-site')=='cross-site':
   return JSONResponse({'detail':'Request origin is not allowed'},status_code=403)
  token=request.cookies.get('pptx_session')
  if token and not hmac.compare_digest(request.headers.get('x-csrf-token',''),csrf(token)):
   return JSONResponse({'detail':'Refresh the page and retry. Security token is missing or invalid.'},status_code=403)
 try:
  response=await call_next(request)
 except Exception as exc:
  logging.getLogger('pptx.api').error('request_failed',extra={'request_id':request_id,'error_type':type(exc).__name__})
  return JSONResponse({'detail':'An unexpected error occurred. Please retry.','request_id':request_id},status_code=500)
 response.headers['X-Request-ID']=request_id
 response.headers['X-Frame-Options']='DENY'
 response.headers['Permissions-Policy']='camera=(), microphone=(), geolocation=()'
 if os.getenv('APP_ENV')=='production':response.headers['Strict-Transport-Security']='max-age=31536000; includeSubDomains'

 response.headers['X-Content-Type-Options']='nosniff'
 response.headers['Referrer-Policy']='strict-origin-when-cross-origin'
 if request.url.path.startswith('/api/'):
  response.headers['Cache-Control']='no-store'
 user_id=getattr(request.state,'user_id',None)
 path=request.url.path; action=None; resource=None
 if user_id and not path.startswith('/api/v1/auth'):
  parts=path.split('/'); resource=parts[4] if len(parts)>4 else None
  if path.endswith('/export'): action=('presentation.exported','Exported PowerPoint presentation')
  elif request.method in ('POST','PATCH','DELETE'):
   if '/agent/' in path: action=('agent.requested','Requested an assistant edit')
   elif '/documents' in path: action=('document.uploaded','Uploaded reference material')
   elif '/generate' in path: action=('generation.requested','Requested presentation generation')
   elif '/restore' in path: action=('version.restored','Restored a presentation version')
   elif '/slides' in path: action=('slide.'+{'POST':'created','PATCH':'edited','DELETE':'deleted'}[request.method],'Slide '+{'POST':'added','PATCH':'edited','DELETE':'deleted'}[request.method])
   elif '/presentations' in path: action=('presentation.'+{'POST':'created','PATCH':'edited','DELETE':'deleted'}[request.method],'Presentation '+{'POST':'created','PATCH':'updated','DELETE':'deleted'}[request.method])
   elif '/projects' in path: action=('project.'+{'POST':'created','PATCH':'edited','DELETE':'deleted'}[request.method],'Project '+{'POST':'created','PATCH':'renamed','DELETE':'deleted'}[request.method])
  if action:
   with DBSession() as session:
    record(session,user_id,action[0],action[1],resource,status='completed' if response.status_code<400 else 'failed'); session.commit()
 return response

@app.get('/api/v1/history',tags=['History'])
def history(q:str=Query(default='',max_length=100),category:str=Query(default='',pattern='^(|account|project|presentation|slide|generation|document|version|agent)$'),offset:int=Query(default=0,ge=0),limit:int=Query(default=30,ge=1,le=100),user:User=Depends(current),session:Session=Depends(db)):
 cutoff=int(time.time())-RETENTION_SECONDS
 # Read-side expiry makes stale rows invisible even if maintenance is delayed.
 conditions=[Activity.user_id==user.id,Activity.created_at>=cutoff]
 if q: conditions.append(Activity.summary.contains(q,autoescape=True))
 if category: conditions.append(Activity.action.startswith(category+'.'))
 total=session.scalar(select(func.count()).select_from(Activity).where(*conditions))
 rows=session.scalars(select(Activity).where(*conditions).order_by(Activity.created_at.desc(),Activity.id.desc()).offset(offset).limit(limit)).all()
 return {'retention_days':100,'total':total,'offset':offset,'has_more':offset+len(rows)<total,'items':[{'id':a.id,'action':a.action,'summary':a.summary,'resource_id':a.resource_id,'status':a.status,'created_at':a.created_at} for a in rows]}


@app.get('/api/v1/presentations/{did}/jobs')
def deck_jobs(did:str,user:User=Depends(current),session:Session=Depends(db)):
 owned_deck(did,user,session)
 rows=session.scalars(select(Job).where(Job.presentation_id==did,Job.user_id==user.id).order_by(Job.created_at.desc()).limit(1)).all()
 return [{'id':j.id,'presentation_id':did,'status':j.status,'stage':j.stage,'error':j.error} for j in rows]
