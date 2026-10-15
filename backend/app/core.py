import os, secrets, hashlib, hmac, time, base64, json
from datetime import datetime, timezone
from sqlalchemy import create_engine, Column, String, Integer, ForeignKey, DateTime, Text, Boolean, UniqueConstraint
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL=os.getenv('DATABASE_URL','sqlite:///./pptx.db')
ENGINE=create_engine(DATABASE_URL,connect_args={'check_same_thread':False} if DATABASE_URL.startswith('sqlite') else {},pool_pre_ping=True)
Session=sessionmaker(bind=ENGINE,expire_on_commit=False)
Base=declarative_base()
def now(): return datetime.now(timezone.utc)
def uid(): return secrets.token_hex(16)
class User(Base):
 __tablename__='users'
 id=Column(String,primary_key=True,default=uid); email=Column(String,unique=True,nullable=False,index=True); password=Column(String,nullable=False); credits=Column(Integer,default=30,nullable=False); created_at=Column(DateTime,default=now)
class Project(Base):
 __tablename__='projects'
 id=Column(String,primary_key=True,default=uid); owner_id=Column(String,ForeignKey('users.id'),nullable=False,index=True); name=Column(String,nullable=False); created_at=Column(DateTime,default=now)
class Presentation(Base):
 __tablename__='presentations'
 id=Column(String,primary_key=True,default=uid); project_id=Column(String,ForeignKey('projects.id'),nullable=False,index=True); title=Column(String,nullable=False); theme=Column(String,default='midnight'); version=Column(Integer,default=0); slides=Column(Text,default='[]'); created_at=Column(DateTime,default=now)
class Version(Base):
 __tablename__='versions'
 id=Column(String,primary_key=True,default=uid); presentation_id=Column(String,ForeignKey('presentations.id'),nullable=False,index=True); number=Column(Integer,nullable=False); slides=Column(Text,nullable=False); theme=Column(String,nullable=False); created_at=Column(DateTime,default=now)
 __table_args__=(UniqueConstraint('presentation_id','number'),)
class CreditEvent(Base):
 __tablename__='credit_events'
 id=Column(String,primary_key=True,default=uid); user_id=Column(String,ForeignKey('users.id'),nullable=False,index=True); amount=Column(Integer,nullable=False); reason=Column(String,nullable=False); key=Column(String,unique=True); created_at=Column(DateTime,default=now)
class Job(Base):
 __tablename__='jobs'
 id=Column(String,primary_key=True,default=uid); presentation_id=Column(String,ForeignKey('presentations.id'),nullable=False); user_id=Column(String,ForeignKey('users.id'),nullable=False); status=Column(String,default='queued'); stage=Column(String,default='queued'); prompt=Column(Text,nullable=False); count=Column(Integer,nullable=False); error=Column(Text); created_at=Column(DateTime,default=now)
class Document(Base):
 __tablename__='documents'
 id=Column(String,primary_key=True,default=uid); project_id=Column(String,ForeignKey('projects.id'),nullable=False); filename=Column(String,nullable=False); content=Column(Text,nullable=False); created_at=Column(DateTime,default=now)
class SessionToken(Base):
 __tablename__='sessions'
 id=Column(String,primary_key=True,default=uid); user_id=Column(String,ForeignKey('users.id'),nullable=False); token_hash=Column(String,unique=True,nullable=False); expires=Column(Integer,nullable=False); revoked=Column(Boolean,default=False)
def hash_password(password):
 salt=secrets.token_bytes(16); digest=hashlib.scrypt(password.encode(),salt=salt,n=16384,r=8,p=1); return base64.b64encode(salt+digest).decode()
def check_password(password,stored):
 try:
  value=base64.b64decode(stored); return hmac.compare_digest(hashlib.scrypt(password.encode(),salt=value[:16],n=16384,r=8,p=1),value[16:])
 except Exception: return False
def new_token(db,user):
 token=secrets.token_urlsafe(40); db.add(SessionToken(user_id=user.id,token_hash=hashlib.sha256(token.encode()).hexdigest(),expires=int(time.time())+7*86400)); db.commit(); return token

# Additive v2 tables preserve existing accounts and presentation data.
class Profile(Base):
 __tablename__='profiles'
 user_id=Column(String,ForeignKey('users.id'),primary_key=True)
 name=Column(String(100),nullable=False)
 phone=Column(String(16),unique=True,nullable=False)
 role=Column(String(30),nullable=False)
 email_verified=Column(Boolean,default=False,nullable=False)
 phone_verified=Column(Boolean,default=False,nullable=False)
 google_sub=Column(String(255),unique=True)
class Registration(Base):
 __tablename__='registrations'
 id=Column(String,primary_key=True,default=uid)
 name=Column(String(100),nullable=False); email=Column(String(254),nullable=False,index=True)
 phone=Column(String(16),nullable=False); role=Column(String(30),nullable=False); password=Column(String,nullable=False)
 google_sub=Column(String(255))
 email_hash=Column(String); phone_hash=Column(String)
 email_verified=Column(Boolean,default=False); phone_verified=Column(Boolean,default=False)
 email_attempts=Column(Integer,default=0); phone_attempts=Column(Integer,default=0)
 email_sent=Column(Integer,default=0); phone_sent=Column(Integer,default=0)
 expires=Column(Integer,nullable=False,index=True); consumed=Column(Boolean,default=False)
class GoogleTicket(Base):
 __tablename__='google_tickets'
 id=Column(String,primary_key=True,default=uid); nonce=Column(String,nullable=False)
 subject=Column(String); email=Column(String); name=Column(String)
 expires=Column(Integer,nullable=False); verified=Column(Boolean,default=False); consumed=Column(Boolean,default=False)
class RateBucket(Base):
 __tablename__='rate_buckets'
 key=Column(String,primary_key=True); count=Column(Integer,nullable=False,default=0); expires=Column(Integer,nullable=False,index=True)
class Activity(Base):
 __tablename__='activities'
 id=Column(String,primary_key=True,default=uid); user_id=Column(String,ForeignKey('users.id'),nullable=False,index=True)
 action=Column(String(80),nullable=False); summary=Column(String(240),nullable=False)
 resource_id=Column(String); status=Column(String(20),default='completed',nullable=False)
 created_at=Column(Integer,nullable=False,default=lambda:int(time.time()),index=True)

class Operation(Base):
 __tablename__='operations'
 id=Column(String,primary_key=True,default=uid)
 user_id=Column(String,ForeignKey('users.id'),nullable=False,index=True)
 job_id=Column(String,unique=True,nullable=False)
 request_key=Column(String(128),nullable=False)
 fingerprint=Column(String(64),nullable=False)
 kind=Column(String(30),nullable=False)
 payload=Column(Text,nullable=False)
 cost=Column(Integer,nullable=False)
 state=Column(String(20),nullable=False,default='reserved',index=True)
 base_version=Column(Integer,nullable=False)
 lease_until=Column(Integer,default=0,nullable=False,index=True)
 result=Column(Text,default='{}',nullable=False)
 created_at=Column(Integer,default=lambda:int(time.time()),nullable=False,index=True)
 __table_args__=(UniqueConstraint('user_id','request_key'),)
class Purchase(Base):
 __tablename__='purchases'
 id=Column(String,primary_key=True,default=uid)
 user_id=Column(String,ForeignKey('users.id'),nullable=False,index=True)
 stripe_session=Column(String,unique=True)
 credits=Column(Integer,nullable=False); amount=Column(Integer,nullable=False); currency=Column(String(3),nullable=False)
 state=Column(String(20),default='pending',nullable=False)
 created_at=Column(Integer,default=lambda:int(time.time()),nullable=False)

# Mobile presentation-control records. Tokens are only ever returned once; the
# database stores hashes so a leaked database cannot impersonate a controller.
class ControlSession(Base):
 __tablename__='control_sessions'
 id=Column(String,primary_key=True,default=uid); presentation_id=Column(String,ForeignKey('presentations.id'),nullable=False,index=True)
 owner_user_id=Column(String,ForeignKey('users.id'),nullable=False,index=True); status=Column(String(20),default='waiting',nullable=False,index=True)
 current_slide_index=Column(Integer,default=0,nullable=False); total_slides=Column(Integer,default=0,nullable=False)
 created_at=Column(Integer,default=lambda:int(time.time()),nullable=False); expires_at=Column(Integer,nullable=False,index=True)
 started_at=Column(Integer); last_activity_at=Column(Integer); ended_at=Column(Integer)
class PairingInvitation(Base):
 __tablename__='pairing_invitations'
 id=Column(String,primary_key=True,default=uid); session_id=Column(String,ForeignKey('control_sessions.id'),nullable=False,index=True)
 token_hash=Column(String(64),unique=True,nullable=False); expires_at=Column(Integer,nullable=False,index=True); used_at=Column(Integer); revoked_at=Column(Integer); created_at=Column(Integer,default=lambda:int(time.time()),nullable=False)
class ControllerDevice(Base):
 __tablename__='controller_devices'
 id=Column(String,primary_key=True,default=uid); session_id=Column(String,ForeignKey('control_sessions.id'),nullable=False,index=True)
 user_id=Column(String,ForeignKey('users.id')); label=Column(String(80),nullable=False); token_hash=Column(String(64),unique=True,nullable=False)
 created_at=Column(Integer,default=lambda:int(time.time()),nullable=False); last_seen_at=Column(Integer); revoked_at=Column(Integer)
class ControlCommand(Base):
 __tablename__='control_commands'
 id=Column(String,primary_key=True,default=uid); session_id=Column(String,ForeignKey('control_sessions.id'),nullable=False,index=True); device_id=Column(String,ForeignKey('controller_devices.id'),nullable=False)
 request_id=Column(String(100),nullable=False); command=Column(String(30),nullable=False); payload=Column(Text,default='{}',nullable=False); status=Column(String(20),default='queued',nullable=False); result=Column(Text,default='{}',nullable=False); created_at=Column(Integer,default=lambda:int(time.time()),nullable=False)
 __table_args__=(UniqueConstraint('session_id','request_id'),)
class ControlAuditEvent(Base):
 __tablename__='control_audit_events'
 id=Column(String,primary_key=True,default=uid); session_id=Column(String,ForeignKey('control_sessions.id'),nullable=False,index=True); actor_user_id=Column(String,ForeignKey('users.id')); event_type=Column(String(50),nullable=False); event_metadata=Column('metadata',Text,default='{}',nullable=False); created_at=Column(Integer,default=lambda:int(time.time()),nullable=False,index=True)
