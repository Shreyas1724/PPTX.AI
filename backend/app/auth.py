"""Verified onboarding, Google Identity Services, and HTTP-only sessions."""
import os, re, time, secrets, hashlib, hmac, smtplib, ssl
from email.message import EmailMessage
from typing import Literal
import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from .core import Session, User, Profile, Registration, GoogleTicket, RateBucket, SessionToken, CreditEvent, hash_password, check_password, new_token
from .activity import record
from .security import csrf
router=APIRouter(prefix='/api/v1/auth',tags=['Authentication'])
COOKIE='pptx_session'

def db():
 with Session() as session: yield session

def current(request:Request,session=Depends(db)):
 # Read-only compatibility with earlier API clients; browsers now use cookies.
 token=request.cookies.get(COOKIE) or request.headers.get('authorization','').removeprefix('Bearer ').strip()
 entry=session.scalar(select(SessionToken).where(SessionToken.token_hash==hashlib.sha256(token.encode()).hexdigest(),SessionToken.revoked==False,SessionToken.expires>int(time.time()))) if token else None
 user=session.get(User,entry.user_id) if entry else None
 if not user: raise HTTPException(401,'Sign in required')
 request.state.user_id=user.id
 return user

def profile_out(session,user):
 p=session.get(Profile,user.id)
 return {'id':user.id,'email':user.email,'credits':user.credits,'name':p.name if p else '', 'mobile':p.phone if p else '', 'role':p.role if p else '', 'email_verified':bool(p and p.email_verified),'mobile_verified':bool(p and p.phone_verified)}

def sign_in(session,user,response):
 token=new_token(session,user)
 response.set_cookie(COOKIE,token,max_age=7*86400,httponly=True,secure=os.getenv('COOKIE_SECURE','false').lower()=='true',samesite='lax',path='/')
 response.set_cookie('pptx_csrf',csrf(token),max_age=7*86400,httponly=False,secure=os.getenv('COOKIE_SECURE','false').lower()=='true',samesite='lax',path='/')
 response.headers['Cache-Control']='no-store'
 return {'user':profile_out(session,user)}

def limit(session,key,maximum=10,window=600):
 # Upsert plus conditional atomic increment works across API processes.
 now=int(time.time()); bucket=now//window
 digest=hashlib.sha256((key+':'+str(bucket)).encode()).hexdigest()
 dialect=session.bind.dialect.name
 if dialect=='postgresql':
  from sqlalchemy.dialects.postgresql import insert
 else:
  from sqlalchemy.dialects.sqlite import insert
 session.execute(insert(RateBucket).values(key=digest,count=0,expires=(bucket+1)*window).on_conflict_do_nothing(index_elements=['key']))
 result=session.execute(update(RateBucket).where(RateBucket.key==digest,RateBucket.count<maximum).values(count=RateBucket.count+1)); session.commit()
 if not result.rowcount: raise HTTPException(429,'Too many attempts. Please try again later.',headers={'Retry-After':str(window-now%window)})

def ip(request):
 # Uvicorn defaults to trusting forwarding headers only from loopback. Behind
 # Docker nginx set FORWARDED_ALLOW_IPS to the trusted proxy address/network.
 return request.client.host if request.client else 'unknown'
def secret():
 value=os.getenv('OTP_SECRET','')
 if len(value)<32: raise HTTPException(503,'Verification is not configured. Contact the site administrator.')
 return value

def code_hash(challenge,channel,code): return hmac.new(secret().encode(),f'{challenge}:{channel}:{code}'.encode(),hashlib.sha256).hexdigest()
def providers_ready():
 return bool(len(os.getenv('OTP_SECRET',''))>=32 and os.getenv('SMTP_HOST') and os.getenv('SMTP_FROM') and os.getenv('TWILIO_ACCOUNT_SID') and os.getenv('TWILIO_AUTH_TOKEN') and os.getenv('TWILIO_FROM'))

def deliver(channel,destination,code):
 """Never return/log codes. Tests replace this function with an in-memory fake."""
 if channel=='email':
  message=EmailMessage(); message['Subject']='Your PPTX.AI verification code'; message['From']=os.environ['SMTP_FROM']; message['To']=destination
  message.set_content(f'Your PPTX.AI code is {code}. It expires with your signup session in 15 minutes. Never share this code. If you did not request this, ignore this email.')
  host=os.environ['SMTP_HOST']; port=int(os.getenv('SMTP_PORT','587'))
  factory=smtplib.SMTP_SSL if os.getenv('SMTP_SECURITY','starttls')=='ssl' else smtplib.SMTP
  with factory(host,port,timeout=15) as smtp:
   if factory is smtplib.SMTP: smtp.starttls(context=ssl.create_default_context())
   if os.getenv('SMTP_USER'): smtp.login(os.environ['SMTP_USER'],os.environ['SMTP_PASSWORD'])
   smtp.send_message(message)
 else:
  sid=os.environ['TWILIO_ACCOUNT_SID']
  with httpx.Client(timeout=15) as client:
   result=client.post(f'https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json',auth=(sid,os.environ['TWILIO_AUTH_TOKEN']),data={'From':os.environ['TWILIO_FROM'],'To':destination,'Body':f'Your PPTX.AI verification code is {code}. Valid for your 15-minute signup session. Do not share it.'})
   result.raise_for_status()

class Signup(BaseModel):
 name:str=Field(min_length=2,max_length=100); email:str=Field(max_length=254)
 mobile:str; password:str=Field(min_length=10,max_length=128)
 role:Literal['student','professional','faculty','entrepreneur','other']
 google_ticket:str|None=None
 @field_validator('name')
 @classmethod
 def name_valid(cls,v):
  v=v.strip()
  if len(v)<2: raise ValueError('Enter your full name')
  return v
 @field_validator('email')
 @classmethod
 def email_valid(cls,v):
  v=v.strip().lower()
  if not re.fullmatch(r'[^@\s\r\n]+@[^@\s\r\n]+\.[^@\s\r\n]+',v): raise ValueError('Enter a valid email address')
  return v
 @field_validator('mobile')
 @classmethod
 def phone_valid(cls,v):
  v=re.sub(r'[\s()-]','',v)
  if not re.fullmatch(r'\+[1-9]\d{7,14}',v): raise ValueError('Use an international number, e.g. +919876543210')
  return v
class Challenge(BaseModel): challenge_id:str=Field(min_length=32,max_length=64)
class Verify(Challenge): channel:Literal['email','mobile']; code:str=Field(pattern=r'^\d{6}$')
class Resend(Challenge): channel:Literal['email','mobile']
class Login(BaseModel): email:str=Field(max_length=254); password:str=Field(min_length=1,max_length=128)
class GoogleCredential(BaseModel): ticket:str=Field(max_length=64); credential:str=Field(max_length=12000)

def challenge(session,identifier):
 row=session.scalar(select(Registration).where(Registration.id==identifier).with_for_update())
 if not row or row.expires<=int(time.time()) or row.consumed: raise HTTPException(410,'This signup session has expired. Please start again.')
 return row

def status(row): return {'challenge_id':row.id,'email_verified':row.email_verified,'mobile_verified':row.phone_verified,'expires_at':row.expires,'email_resend_at':row.email_sent+60,'mobile_resend_at':row.phone_sent+60}

def send_code(session,row,channel):
 attr='phone' if channel=='mobile' else 'email'
 if getattr(row,attr+'_verified'): raise HTTPException(409,'Already verified')
 if getattr(row,attr+'_attempts')>=5: raise HTTPException(429,'Verification attempt limit reached. Start again later.')
 if int(time.time())<getattr(row,attr+'_sent')+60: raise HTTPException(429,'Wait 60 seconds before requesting another code.')
 code=f'{secrets.randbelow(1000000):06d}'
 setattr(row,attr+'_hash',code_hash(row.id,channel,code)); setattr(row,attr+'_sent',int(time.time()))
 session.commit()
 try: deliver('email' if channel=='email' else 'sms',row.email if channel=='email' else row.phone,code)
 except Exception: raise HTTPException(503,'Could not deliver the code. Please try resending after 60 seconds.')

@router.get('/config')
def config(): return {'google_client_id':os.getenv('GOOGLE_CLIENT_ID',''),'verification_available':providers_ready(),'roles':['student','professional','faculty','entrepreneur','other']}
@router.post('/register')
def register(data:Signup,request:Request,session=Depends(db)):
 limit(session,'signup-ip:'+ip(request),10,3600); limit(session,'signup-email:'+data.email,3,3600); limit(session,'signup-phone:'+data.mobile,3,3600)
 if not providers_ready(): raise HTTPException(503,'Email and SMS verification must be configured before creating an account.')
 if session.scalar(select(User).where(User.email==data.email)) or session.scalar(select(Profile).where(Profile.phone==data.mobile)): raise HTTPException(409,'This email or mobile number is already registered. Please log in.')
 subject=None
 if data.google_ticket:
  ticket=session.scalar(select(GoogleTicket).where(GoogleTicket.id==data.google_ticket).with_for_update())
  if not ticket or not ticket.verified or ticket.consumed or ticket.expires<=int(time.time()) or ticket.email!=data.email: raise HTTPException(400,'Google signup expired. Continue with Google again.')
  subject=ticket.subject; ticket.consumed=True
 row=Registration(name=data.name,email=data.email,phone=data.mobile,role=data.role,password=hash_password(data.password),google_sub=subject,expires=int(time.time())+900)
 session.add(row); session.commit()
 # Return the pending session even if either delivery fails, so resend works.
 delivery_errors=[]
 for channel in ('email','mobile'):
  try: send_code(session,row,channel)
  except HTTPException: delivery_errors.append(channel)
 return {**status(row),'delivery_errors':delivery_errors}
@router.post('/register/verify')
def verify(data:Verify,request:Request,session=Depends(db)):
 limit(session,'verify-ip:'+ip(request),50,600)
 row=challenge(session,data.challenge_id); attr='phone' if data.channel=='mobile' else 'email'
 if getattr(row,attr+'_verified'): return status(row)
 attempts=getattr(row,attr+'_attempts')
 if attempts>=5: raise HTTPException(429,'Too many incorrect codes. Start a new signup session later.')
 setattr(row,attr+'_attempts',attempts+1)
 valid=hmac.compare_digest(getattr(row,attr+'_hash') or '',code_hash(row.id,data.channel,data.code))
 if valid: setattr(row,attr+'_verified',True); setattr(row,attr+'_hash',None)
 session.commit()
 if not valid: raise HTTPException(400,'Incorrect verification code.')
 return status(row)
@router.post('/register/resend')
def resend(data:Resend,request:Request,session=Depends(db)):
 limit(session,'resend-ip:'+ip(request),20,3600)
 row=challenge(session,data.challenge_id)
 limit(session,'delivery:'+data.channel+':'+(row.email if data.channel=='email' else row.phone),6,3600)
 row=challenge(session,data.challenge_id); send_code(session,row,data.channel); return status(row)
@router.post('/register/complete')
def complete(data:Challenge,response:Response,session=Depends(db)):
 row=challenge(session,data.challenge_id)
 if not row.email_verified or not row.phone_verified: raise HTTPException(403,'Verify both your email and mobile number first.')
 try:
  user=User(email=row.email,password=row.password); session.add(user); session.flush()
  session.add(Profile(user_id=user.id,name=row.name,phone=row.phone,role=row.role,email_verified=True,phone_verified=True,google_sub=row.google_sub))
  session.add(CreditEvent(user_id=user.id,amount=30,reason='welcome'))
  record(session,user.id,'account.created','Account created and email/mobile verified')
  # Delete password hash and all pending personal details immediately.
  session.delete(row); session.commit()
 except IntegrityError:
  session.rollback(); raise HTTPException(409,'Account already exists. Please log in.')
 return sign_in(session,user,response)
@router.post('/login')
def login(data:Login,request:Request,response:Response,session=Depends(db)):
 email=data.email.strip().lower(); limit(session,'login-ip:'+ip(request),30,600); limit(session,'login-email:'+email,10,600)
 user=session.scalar(select(User).where(User.email==email))
 if not user or not check_password(data.password,user.password): raise HTTPException(401,'Email or password is incorrect.')
 record(session,user.id,'account.login','Logged in with email and password'); session.commit()
 return sign_in(session,user,response)
@router.get('/me')
def me(user=Depends(current),session=Depends(db)): return profile_out(session,user)
@router.post('/logout')
def logout(request:Request,response:Response,user=Depends(current),session=Depends(db)):
 token=request.cookies.get(COOKIE) or request.headers.get('authorization','').removeprefix('Bearer ').strip()
 entry=session.scalar(select(SessionToken).where(SessionToken.token_hash==hashlib.sha256(token.encode()).hexdigest()))
 if entry: entry.revoked=True
 record(session,user.id,'account.logout','Signed out'); session.commit(); response.delete_cookie(COOKIE,path='/'); response.delete_cookie('pptx_csrf',path='/'); return {'ok':True}
@router.post('/google/start')
def google_start(request:Request,session=Depends(db)):
 if not os.getenv('GOOGLE_CLIENT_ID'): raise HTTPException(503,'Google sign-in is not configured.')
 limit(session,'google-start:'+ip(request),30,600)
 row=GoogleTicket(nonce=secrets.token_urlsafe(32),expires=int(time.time())+600); session.add(row); session.commit()
 return {'ticket':row.id,'nonce':row.nonce}

def google_claims(credential):
 from google.oauth2 import id_token
 from google.auth.transport.requests import Request as GoogleRequest
 try: return id_token.verify_oauth2_token(credential,GoogleRequest(),os.environ['GOOGLE_CLIENT_ID'])
 except Exception: raise HTTPException(401,'Google could not verify your sign-in. Please try again.')
@router.post('/google')
def google_login(data:GoogleCredential,request:Request,response:Response,session=Depends(db)):
 limit(session,'google-login:'+ip(request),20,600)
 if not os.getenv('GOOGLE_CLIENT_ID'): raise HTTPException(503,'Google sign-in is not configured.')
 ticket=session.scalar(select(GoogleTicket).where(GoogleTicket.id==data.ticket).with_for_update())
 if not ticket or ticket.verified or ticket.consumed or ticket.expires<=int(time.time()): raise HTTPException(401,'Google sign-in expired. Please try again.')
 claims=google_claims(data.credential)
 if not claims.get('email_verified') or claims.get('nonce')!=ticket.nonce or not claims.get('sub'): raise HTTPException(401,'Invalid Google identity.')
 ticket.verified=True; ticket.subject=claims['sub']; ticket.email=claims['email'].lower(); ticket.name=claims.get('name','')[:100]
 profile=session.scalar(select(Profile).where(Profile.google_sub==ticket.subject))
 if profile:
  ticket.consumed=True; user=session.get(User,profile.user_id); record(session,user.id,'account.login','Logged in with Google'); session.commit(); return sign_in(session,user,response)
 if session.scalar(select(User).where(User.email==ticket.email)):
  ticket.consumed=True; session.commit(); raise HTTPException(409,'This email already has a password account. Log in with your registered email and password.')
 session.commit()
 return {'onboarding_required':True,'google_ticket':ticket.id,'email':ticket.email,'name':ticket.name}


@router.post('/logout-all')
def logout_all(response:Response,user=Depends(current),session=Depends(db)):
 session.execute(update(SessionToken).where(SessionToken.user_id==user.id).values(revoked=True))
 record(session,user.id,'account.logout','Signed out of all devices');session.commit()
 response.delete_cookie(COOKIE,path='/');response.delete_cookie('pptx_csrf',path='/');return {'ok':True}
