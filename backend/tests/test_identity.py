"""OTP transport and Google signature verification mocked; application flows are real."""
import os, time
os.environ['DATABASE_URL']='sqlite://'
os.environ['OTP_SECRET']='test-secret-only-not-for-production-12345678'
from sqlalchemy import create_engine, select
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from app import core, auth, main
from app.activity import purge, RETENTION_SECONDS
import pytest

class SecureClient(TestClient):
 def request(self,*args,**kwargs):
  headers=dict(kwargs.pop('headers',{}) or {})
  if self.cookies.get('pptx_csrf'):headers.setdefault('X-CSRF-Token',self.cookies.get('pptx_csrf'))
  return super().request(*args,headers=headers,**kwargs)

@pytest.fixture
def setup(monkeypatch):
 engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
 core.Session.configure(bind=engine); monkeypatch.setattr(main,'ENGINE',engine)
 for name in ['SMTP_HOST','SMTP_FROM','TWILIO_ACCOUNT_SID','TWILIO_AUTH_TOKEN','TWILIO_FROM','GOOGLE_CLIENT_ID']:
  monkeypatch.setenv(name,'test')
 codes={}
 monkeypatch.setattr(auth,'deliver',lambda channel,destination,code:codes.update({(channel,destination):code}))
 with SecureClient(main.app) as client: yield client,codes
 core.Base.metadata.drop_all(engine); engine.dispose()

def details(n=1):return {'name':'Aarav Sharma','email':f'aarav{n}@gmail.com','mobile':f'+9198765432{n:02d}','password':'strong-password-2026','role':'student'}
def signup(c,codes,n=1,extra=None):
 d=details(n);d.update(extra or {})
 r=c.post('/api/v1/auth/register',json=d);assert r.status_code==200,r.text
 challenge=r.json()['challenge_id']
 for channel,dest in [('email',d['email']),('mobile',d['mobile'])]:
  r=c.post('/api/v1/auth/register/verify',json={'challenge_id':challenge,'channel':channel,'code':codes[('email' if channel=='email' else 'sms',dest)]});assert r.status_code==200,r.text
 r=c.post('/api/v1/auth/register/complete',json={'challenge_id':challenge});assert r.status_code==200,r.text
 return r

def test_registration_requires_both_verifications(setup):
 c,codes=setup;d=details();r=c.post('/api/v1/auth/register',json=d);cid=r.json()['challenge_id']
 assert 'code' not in r.text and 'password' not in r.text
 assert c.post('/api/v1/auth/login',json=d).status_code==401
 assert c.post('/api/v1/auth/register/complete',json={'challenge_id':cid}).status_code==403
 assert c.post('/api/v1/auth/register/verify',json={'challenge_id':cid,'channel':'email','code':codes['email',d['email']]}).status_code==200
 assert c.post('/api/v1/auth/register/complete',json={'challenge_id':cid}).status_code==403
 assert c.post('/api/v1/auth/register/verify',json={'challenge_id':cid,'channel':'mobile','code':codes['sms',d['mobile']]}).status_code==200
 done=c.post('/api/v1/auth/register/complete',json={'challenge_id':cid});assert done.status_code==200
 assert 'HttpOnly' in done.headers['set-cookie']
 assert done.json()['user']['name']==d['name']
 assert done.json()['user']['role']=='student'
 assert c.post('/api/v1/auth/register/complete',json={'challenge_id':cid}).status_code==410
 c.post('/api/v1/auth/logout');assert c.get('/api/v1/auth/me').status_code==401
 assert c.post('/api/v1/auth/login',json={'email':d['email'],'password':d['password']}).status_code==200

def test_wrong_codes_lock_and_resend_does_not_reset_attempts(setup):
 c,codes=setup;d=details();cid=c.post('/api/v1/auth/register',json=d).json()['challenge_id']
 wrong='000000' if codes['email',d['email']]!='000000' else '111111'
 for _ in range(5):assert c.post('/api/v1/auth/register/verify',json={'challenge_id':cid,'channel':'email','code':wrong}).status_code==400
 assert c.post('/api/v1/auth/register/verify',json={'challenge_id':cid,'channel':'email','code':codes['email',d['email']]}).status_code==429
 assert c.post('/api/v1/auth/register/resend',json={'challenge_id':cid,'channel':'email'}).status_code==429

def test_expiry_and_missing_provider_fail_closed(setup,monkeypatch):
 c,codes=setup;cid=c.post('/api/v1/auth/register',json=details()).json()['challenge_id']
 with core.Session() as s:
  row=s.get(core.Registration,cid);row.expires=int(time.time())-1;s.commit()
 assert c.post('/api/v1/auth/register/complete',json={'challenge_id':cid}).status_code==410
 monkeypatch.delenv('TWILIO_AUTH_TOKEN')
 assert c.post('/api/v1/auth/register',json=details(2)).status_code==503

def test_resend_invalidates_old_code(setup):
 c,codes=setup;d=details();cid=c.post('/api/v1/auth/register',json=d).json()['challenge_id'];old=codes['email',d['email']]
 assert c.post('/api/v1/auth/register/resend',json={'challenge_id':cid,'channel':'email'}).status_code==429
 with core.Session() as s:
  row=s.get(core.Registration,cid);row.email_sent=0;s.commit()
 assert c.post('/api/v1/auth/register/resend',json={'challenge_id':cid,'channel':'email'}).status_code==200
 if old!=codes['email',d['email']]:assert c.post('/api/v1/auth/register/verify',json={'challenge_id':cid,'channel':'email','code':old}).status_code==400

def test_history_ownership_retention_and_task_capture(setup):
 c,codes=setup;u=signup(c,codes).json()['user'];pid=c.post('/api/v1/projects',json={'name':'My project'}).json()['id']
 did=c.post('/api/v1/presentations',json={'project_id':pid,'title':'Pitch'}).json()['id']
 assert c.post(f'/api/v1/presentations/{did}/slides',json={'title':'Intro','body':['Hello']}).status_code==200
 assert c.get(f'/api/v1/presentations/{did}/export').status_code==200
 with core.Session() as s:
  s.add(core.Activity(user_id=u['id'],action='slide.edited',summary='expired',created_at=int(time.time())-RETENTION_SECONDS-10));s.commit()
 history=c.get('/api/v1/history').json();assert not any(i['summary']=='expired' for i in history['items'])
 assert {'project.created','presentation.created','slide.created','presentation.exported'}<=set(i['action'] for i in history['items'])
 assert c.get('/api/v1/history?category=slide').json()['total']==1
 assert c.get('/api/v1/history?limit=1').json()['has_more']
 with core.Session() as s:
  purge(s);assert not s.scalar(select(core.Activity).where(core.Activity.summary=='expired'))
 c.post('/api/v1/auth/logout');signup(c,codes,2)
 assert not any(i['action']=='slide.created' for i in c.get('/api/v1/history').json()['items'])
 assert c.get(f'/api/v1/presentations/{did}').status_code==404

def test_google_onboarding_nonce_replay_and_returning_login(setup,monkeypatch):
 c,codes=setup;ticket=c.post('/api/v1/auth/google/start').json()
 claims={'sub':'google-user-1','email':'aarav1@gmail.com','name':'Aarav','email_verified':True,'nonce':ticket['nonce']}
 monkeypatch.setattr(auth,'google_claims',lambda credential:claims)
 result=c.post('/api/v1/auth/google',json={'ticket':ticket['ticket'],'credential':'verified-test-token'})
 assert result.status_code==200 and result.json()['onboarding_required']
 assert c.post('/api/v1/auth/google',json={'ticket':ticket['ticket'],'credential':'verified-test-token'}).status_code==401
 signup(c,codes,extra={'google_ticket':result.json()['google_ticket']});c.post('/api/v1/auth/logout')
 t=c.post('/api/v1/auth/google/start').json();claims['nonce']=t['nonce']
 assert c.post('/api/v1/auth/google',json={'ticket':t['ticket'],'credential':'verified-test-token'}).json()['user']['email']=='aarav1@gmail.com'
 c.post('/api/v1/auth/logout');t=c.post('/api/v1/auth/google/start').json();claims['nonce']='wrong'
 assert c.post('/api/v1/auth/google',json={'ticket':t['ticket'],'credential':'verified-test-token'}).status_code==401

def test_cross_site_requests_and_login_rate_limit(setup):
 c,codes=setup
 assert c.post('/api/v1/auth/login',headers={'Origin':'https://evil.example'},json={'email':'a@b.com','password':'no'}).status_code==403
 for _ in range(10):assert c.post('/api/v1/auth/login',json={'email':'x@y.com','password':'wrong'}).status_code==401
 assert c.post('/api/v1/auth/login',json={'email':'x@y.com','password':'wrong'}).status_code==429
