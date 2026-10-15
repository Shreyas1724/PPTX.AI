import json,time,os,hmac,hashlib
from concurrent.futures import ThreadPoolExecutor
import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine,select,func
from sqlalchemy.orm import sessionmaker
from app import core,credits,worker,billing,intelligence
from test_identity import setup,signup

def deck(c):
 p=c.post('/api/v1/projects',json={'name':'Test'}).json()
 return c.post('/api/v1/presentations',json={'project_id':p['id'],'title':'Security'}).json()['id']
def generate(c,d,key='request-1',prompt='Security and privacy'):
 return c.post(f'/api/v1/presentations/{d}/generate',json={'prompt':prompt,'count':5},headers={'Idempotency-Key':key})

def test_reservation_idempotency_settlement_and_refund(setup):
 c,codes=setup;signup(c,codes);d=deck(c)
 a=generate(c,d);assert a.status_code==202,a.text
 b=generate(c,d);assert a.json()['job_id']==b.json()['job_id']
 assert c.get('/api/v1/credits').json()['balance']==28
 assert c.get('/api/v1/credits').json()['reserved']==2
 assert generate(c,d,prompt='different').status_code==409
 worker.process(a.json()['job_id']);worker.process(a.json()['job_id'])
 assert c.get('/api/v1/credits').json()['spent']==2
 assert c.get('/api/v1/credits').json()['reserved']==0
 assert len(c.get('/api/v1/presentations/'+d).json()['slides'])==5
 assert c.get('/api/v1/credits').json()['balance']==28

def test_failed_job_refunds_once_and_conflict_preserves_manual_edit(setup,monkeypatch):
 c,codes=setup;signup(c,codes);d=deck(c);j=generate(c,d).json()['job_id']
 monkeypatch.setattr(worker,'build',lambda *a:(_ for _ in ()).throw(RuntimeError('secret-do-not-leak')))
 worker.process(j);worker.process(j)
 assert c.get('/api/v1/credits').json()['balance']==30
 status=c.get('/api/v1/jobs/'+j).json();assert status['credit_state']=='refunded' and 'secret' not in status['error']
 with core.Session() as s:
  op=s.scalar(select(core.Operation).where(core.Operation.job_id==j));assert not credits.refund(s,op.id);s.commit()
 monkeypatch.setattr(worker,'build',intelligence.build)
 j=generate(c,d,'second-request').json()['job_id']
 c.post('/api/v1/presentations/'+d+'/slides',json={'title':'Keep this edit','body':['User content']})
 worker.process(j)
 assert c.get('/api/v1/credits').json()['balance']==30
 assert c.get('/api/v1/presentations/'+d).json()['slides'][0]['title']=='Keep this edit'

def test_stalled_jobs_refund_and_cannot_later_commit(setup):
 c,codes=setup;signup(c,codes);d=deck(c);j=generate(c,d).json()['job_id']
 with core.Session() as s:
  op=s.scalar(select(core.Operation).where(core.Operation.job_id==j));op.state='running';op.lease_until=int(time.time())-1;s.commit()
 worker.sweep();worker.sweep();worker.process(j)
 assert c.get('/api/v1/credits').json()['balance']==30
 assert c.get('/api/v1/jobs/'+j).json()['credit_state']=='refunded'

def test_concurrent_requests_cannot_overspend(tmp_path):
 engine=create_engine('sqlite:///'+str(tmp_path/'concurrency.db'),connect_args={'timeout':20});core.Base.metadata.create_all(engine);sessions=sessionmaker(bind=engine,expire_on_commit=False)
 with sessions() as s:
  u=core.User(email='concurrent@test.com',password='x',credits=2);s.add(u);s.flush();p=core.Project(owner_id=u.id,name='test');s.add(p);s.flush();d=core.Presentation(project_id=p.id,title='test');s.add(d);s.commit();user_id=u.id;deck_id=d.id
 def reserve(i):
  with sessions() as s:
   try:return credits.reserve(s,user_id,s.get(core.Presentation,deck_id),'generation',{'prompt':'test','count':5},'key-'+str(i)).job_id
   except HTTPException as e:return e.status_code
 with ThreadPoolExecutor(max_workers=6) as pool:results=list(pool.map(reserve,range(6)))
 assert sum(isinstance(x,str) for x in results)==1
 assert results.count(402)==5
 with sessions() as s:
  assert s.get(core.User,user_id).credits==0
  assert s.scalar(select(func.count()).select_from(core.CreditEvent))==1
 engine.dispose()

def test_same_request_concurrency_charges_once(tmp_path):
 engine=create_engine('sqlite:///'+str(tmp_path/'same.db'),connect_args={'timeout':20});core.Base.metadata.create_all(engine);sessions=sessionmaker(bind=engine,expire_on_commit=False)
 with sessions() as s:
  u=core.User(email='same@test.com',password='x',credits=2);s.add(u);s.flush();p=core.Project(owner_id=u.id,name='test');s.add(p);s.flush();d=core.Presentation(project_id=p.id,title='test');s.add(d);s.commit();user_id=u.id;deck_id=d.id
 def reserve(_):
  with sessions() as s:return credits.reserve(s,user_id,s.get(core.Presentation,deck_id),'generation',{'prompt':'test','count':5},'same-key').job_id
 with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(reserve,range(4)))
 assert len(set(results))==1
 with sessions() as s:assert s.get(core.User,user_id).credits==0
 engine.dispose()

def test_csrf_and_body_limits(setup):
 c,codes=setup;signup(c,codes)
 assert c.post('/api/v1/projects',json={'name':'bad'},headers={'X-CSRF-Token':''}).status_code==403
 assert c.post('/api/v1/projects',json={'name':'ok'}).status_code==200
 assert c.post('/api/v1/projects',content=b'x'*6_000_001).status_code==413
 assert c.post('/api/v1/auth/logout-all').status_code==200
 assert c.get('/api/v1/auth/me').status_code==401

def test_ai_edit_schema_and_compound_instructions(setup,monkeypatch):
 c,codes=setup;signup(c,codes);d=deck(c)
 c.post('/api/v1/presentations/'+d+'/slides',json={'title':'Intro','body':['one','two','three']})
 j=c.post('/api/v1/agent/chat',json={'presentation_id':d,'instruction':'make slide 1 shorter'},headers={'Idempotency-Key':'edit1'}).json()['job_id'];worker.process(j)
 assert len(c.get('/api/v1/presentations/'+d).json()['slides'][0]['body'])==2
 assert c.get('/api/v1/credits').json()['balance']==29
 called=[]
 def mock_llm(system,user,schema,count=None):
  called.append(user['instruction']);return intelligence.EditIR(slides=[{'title':'Sharper story','body':['A concise point']}],theme='light',summary='Updated content and theme.'),{'model':'test','tokens':5}
 monkeypatch.setattr(intelligence,'llm',mock_llm)
 j=c.post('/api/v1/agent/chat',json={'presentation_id':d,'instruction':'make slide 1 sharper and change theme to light'},headers={'Idempotency-Key':'edit2'}).json()['job_id'];worker.process(j)
 assert called
 assert c.get('/api/v1/presentations/'+d).json()['theme']=='light'
 with pytest.raises(ValueError):intelligence.DeckIR.model_validate({'slides':[{'title':'x','body':['x'*241]}]})

def test_paid_webhook_exactly_once_and_bad_signature(setup,monkeypatch):
 c,codes=setup;user=signup(c,codes).json()['user'];monkeypatch.setenv('STRIPE_WEBHOOK_SECRET','whsec_test')
 with core.Session() as s:
  order=core.Purchase(user_id=user['id'],stripe_session='cs_test_paid',credits=100,amount=50000,currency='inr');s.add(order);s.commit();oid=order.id
 event={'type':'checkout.session.completed','data':{'object':{'id':'cs_test_paid','payment_status':'paid','metadata':{'order_id':oid},'client_reference_id':oid,'amount_total':50000,'currency':'inr'}}}
 raw=json.dumps(event).encode();stamp=str(int(time.time()));sig=hmac.new(b'whsec_test',stamp.encode()+b'.'+raw,hashlib.sha256).hexdigest()
 assert c.post('/api/v1/billing/webhook',content=raw,headers={'stripe-signature':'bad'}).status_code==400
 for _ in range(2):assert c.post('/api/v1/billing/webhook',content=raw,headers={'stripe-signature':f't={stamp},v1={sig}'}).status_code==200
 assert c.get('/api/v1/credits').json()['balance']==130
 with core.Session() as s:assert s.scalar(select(func.count()).select_from(core.CreditEvent).where(core.CreditEvent.reason=='purchase'))==1

def test_unpaid_or_mismatched_payments_never_credit(setup):
 c,codes=setup;user=signup(c,codes).json()['user']
 with core.Session() as s:
  order=core.Purchase(user_id=user['id'],stripe_session='cs_test',credits=100,amount=50000,currency='inr');s.add(order);s.commit()
  event={'type':'checkout.session.completed','data':{'object':{'id':'cs_test','payment_status':'unpaid','metadata':{'order_id':order.id},'client_reference_id':order.id,'amount_total':50000,'currency':'inr'}}}
  billing.fulfill(s,event);assert s.get(core.User,user['id']).credits==30
  event['data']['object']['payment_status']='paid';event['data']['object']['amount_total']=1
  with pytest.raises(HTTPException):billing.fulfill(s,event)
  assert s.get(core.User,user['id']).credits==30

@pytest.mark.parametrize('event',[
 [],None,{'type':'checkout.session.completed','data':None},
 {'type':'checkout.session.completed','data':{'object':None}},
 {'type':'checkout.session.completed','data':{'object':{'payment_status':'paid','metadata':None}}},
 {'type':'checkout.session.completed','data':{'object':{'payment_status':'paid','metadata':{'order_id':{}}}}},
])
def test_malformed_signed_webhooks_return_validation_errors(setup,monkeypatch,event):
 c,codes=setup;signup(c,codes);monkeypatch.setenv('STRIPE_WEBHOOK_SECRET','whsec_test')
 raw=json.dumps(event).encode();stamp=str(int(time.time()))
 signature=hmac.new(b'whsec_test',stamp.encode()+b'.'+raw,hashlib.sha256).hexdigest()
 response=c.post('/api/v1/billing/webhook',content=raw,headers={'stripe-signature':f't={stamp},v1={signature}'})
 assert response.status_code==400,response.text
 assert c.get('/api/v1/credits').json()['balance']==30

def test_document_boundaries():
 from app.documents import parse,extract,DocumentError
 assert parse(b'A useful reference','txt')=='A useful reference'
 with pytest.raises(DocumentError):parse(b'not a PDF','pdf')
 with pytest.raises(DocumentError):extract(b'bad\x00binary','txt')
 with pytest.raises(DocumentError):parse(b'','txt')

def test_legacy_schema_upgrade_preserves_accounts(tmp_path):
 engine=create_engine('sqlite:///'+str(tmp_path/'legacy.db'))
 with engine.begin() as conn:
  conn.exec_driver_sql('CREATE TABLE users (id VARCHAR PRIMARY KEY,email VARCHAR UNIQUE NOT NULL,password VARCHAR NOT NULL,credits INTEGER NOT NULL,created_at DATETIME)')
  conn.exec_driver_sql("INSERT INTO users VALUES ('legacy','legacy@example.com','hash',27,CURRENT_TIMESTAMP)")
 core.Base.metadata.create_all(engine)
 with engine.connect() as conn:
  assert conn.exec_driver_sql("SELECT credits FROM users WHERE id='legacy'").scalar()==27
  assert conn.exec_driver_sql('SELECT COUNT(*) FROM operations').scalar()==0
 engine.dispose()

def test_legacy_job_refund_is_idempotent(setup):
 from app.manage import recover_legacy,audit
 c,codes=setup;user=signup(c,codes).json()['user'];d=deck(c)
 with core.Session() as s:
  u=s.get(core.User,user['id']);u.credits-=2
  job=core.Job(user_id=u.id,presentation_id=d,prompt='old job',count=5);s.add(job);s.flush()
  s.add(core.CreditEvent(user_id=u.id,amount=-2,reason=job.id));s.commit()
  recover_legacy(s);recover_legacy(s)
  assert s.get(core.User,user['id']).credits==30
  assert not audit(s)
