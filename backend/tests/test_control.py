"""Pairing invitations are single-use and controller commands are idempotent."""
import os
os.environ.setdefault('DATABASE_URL','sqlite://')
os.environ.setdefault('OTP_SECRET','test-secret-only-not-for-production-12345678')
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool
from fastapi.testclient import TestClient
from app import core, main, auth

def test_pairing_exchange_and_command(monkeypatch):
 engine=create_engine('sqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool); core.Session.configure(bind=engine); main.ENGINE=engine
 with engine.connect() as connection:connection.exec_driver_sql('PRAGMA foreign_keys=ON')
 for n in ['SMTP_HOST','SMTP_FROM','TWILIO_ACCOUNT_SID','TWILIO_AUTH_TOKEN','TWILIO_FROM']: monkeypatch.setenv(n,'test')
 codes={}; monkeypatch.setattr(auth,'deliver',lambda ch,dest,code: codes.update({(ch,dest):code}))
 class C(TestClient):
  def request(self,*a,**kw):
   h=dict(kw.pop('headers',{}) or {});
   if self.cookies.get('pptx_csrf'): h.setdefault('X-CSRF-Token',self.cookies.get('pptx_csrf'))
   return super().request(*a,headers=h,**kw)
 with C(main.app) as c:
  d={'name':'Control User','email':'control@example.com','mobile':'+919876543299','password':'strong-password-2026','role':'student'}; cid=c.post('/api/v1/auth/register',json=d).json()['challenge_id']
  c.post('/api/v1/auth/register/verify',json={'challenge_id':cid,'channel':'email','code':codes['email',d['email']]}); c.post('/api/v1/auth/register/verify',json={'challenge_id':cid,'channel':'mobile','code':codes['sms',d['mobile']]}); assert c.post('/api/v1/auth/register/complete',json={'challenge_id':cid}).status_code==200
  pid=c.post('/api/v1/projects',json={'name':'control'}).json()['id']; did=c.post('/api/v1/presentations',json={'project_id':pid,'title':'Deck'}).json()['id']; c.post(f'/api/v1/presentations/{did}/slides',json={'title':'Slide','body':['one']})
  session=c.post('/api/v1/presentation-control/sessions',json={'presentation_id':did}).json(); raw=session['pairing_url'].split('invite=',1)[1]; exchanged=c.post('/api/v1/presentation-control/pairing/exchange',json={'token':raw,'device_label':'Phone'}); assert exchanged.status_code==200
  assert c.post('/api/v1/presentation-control/pairing/exchange',json={'token':raw,'device_label':'Replay'}).status_code==410
  token=exchanged.json()['controller_token']; payload={'request_id':'request-1234','command':'SLIDE_GOTO','slide_index':0}; assert c.post('/api/v1/presentation-control/controllers/'+token+'/command',json=payload).json()['accepted']; assert c.post('/api/v1/presentation-control/controllers/'+token+'/command',json=payload).json()['duplicate']
