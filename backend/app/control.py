"""Secure, short-lived mobile control plane for the real presentation viewer."""
import asyncio, hashlib, json, os, secrets, time
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field
from sqlalchemy import select,update
from sqlalchemy.orm import Session
from .core import Session as DBSession, User, Project, Presentation, ControlSession, PairingInvitation, ControllerDevice, ControlCommand, ControlAuditEvent
from .auth import current, db

router=APIRouter(prefix='/api/v1/presentation-control',tags=['Presentation control'])
FRONTEND=os.getenv('FRONTEND_URL',os.getenv('CORS_ORIGINS','http://localhost:3000').split(',')[0].strip()).rstrip('/')
SESSION_TTL=int(os.getenv('CONTROL_SESSION_TTL','7200')); INVITE_TTL=int(os.getenv('CONTROL_PAIRING_TTL','120'))
controller_connections:dict[str,set[WebSocket]]={}
connections:dict[str,set[WebSocket]]={}; host_connections:dict[str,WebSocket]={}; locks:dict[str,asyncio.Lock]={}
def ts(): return int(time.time())
def digest(v:str): return hashlib.sha256(v.encode()).hexdigest()
def audit(s,session_id,event,actor=None,metadata=None): s.add(ControlAuditEvent(session_id=session_id,actor_user_id=actor,event_type=event,event_metadata=json.dumps(metadata or {},separators=(',',':'))))
def owner(s,sid,user):
 row=s.get(ControlSession,sid)
 if not row or row.owner_user_id!=user.id: raise HTTPException(404,'Control session not found')
 if row.expires_at<=ts() and row.status!='ended': row.status='expired'; s.commit(); raise HTTPException(410,'Control session expired')
 return row
class CreateSession(BaseModel): presentation_id:str
class Pairing(BaseModel): token:str=Field(min_length=20,max_length=200); device_label:str=Field(default='Mobile controller',min_length=1,max_length=80)
class Command(BaseModel): request_id:str=Field(min_length=8,max_length=100); command:Literal['SLIDE_NEXT','SLIDE_PREVIOUS','SLIDE_GOTO','PING']; slide_index:int|None=Field(default=None,ge=0,le=200)

def invitation(s,row):
 for old in s.scalars(select(PairingInvitation).where(PairingInvitation.session_id==row.id,PairingInvitation.used_at.is_(None),PairingInvitation.revoked_at.is_(None))): old.revoked_at=ts()
 raw='pc_'+secrets.token_urlsafe(32); s.add(PairingInvitation(session_id=row.id,token_hash=digest(raw),expires_at=ts()+INVITE_TTL)); s.commit()
 url=f'{FRONTEND}/control#invite={raw}'; result={'pairing_url':url,'expires_at':ts()+INVITE_TTL}
 try:
  import qrcode
  import qrcode.image.svg
  raw_svg=qrcode.make(url,image_factory=qrcode.image.svg.SvgPathImage).to_string(); result['qr_svg']=raw_svg.decode() if isinstance(raw_svg,bytes) else raw_svg
 except Exception:
  # The URL remains usable when the optional renderer is unavailable; Docker
  # installs qrcode from the locked backend requirements.
  result['qr_svg']=''
 return result

@router.post('/sessions')
def create(data:CreateSession,user:User=Depends(current),s:Session=Depends(db)):
 p=s.get(Presentation,data.presentation_id); project=s.get(Project,p.project_id) if p else None
 if not p or not project or project.owner_id!=user.id: raise HTTPException(404,'Presentation not found')
 count=len(json.loads(p.slides or '[]'))
 if not count:raise HTTPException(409,'Add slides before starting mobile control.')
 row=ControlSession(presentation_id=p.id,owner_user_id=user.id,total_slides=count,current_slide_index=0,expires_at=ts()+SESSION_TTL,last_activity_at=ts()); s.add(row); s.commit(); s.refresh(row)
 result=invitation(s,row); audit(s,row.id,'SESSION_CREATED',user.id,{'presentation_id':p.id}); s.commit()
 return {'session_id':row.id,'status':row.status,'total_slides':count,'current_slide_index':0,**result}

@router.post('/sessions/{sid}/pairing')
def regenerate(sid:str,user:User=Depends(current),s:Session=Depends(db)): return invitation(s,owner(s,sid,user))
@router.post('/sessions/{sid}/pairing/regenerate')
def regenerate_alias(sid:str,user:User=Depends(current),s:Session=Depends(db)): return invitation(s,owner(s,sid,user))

@router.post('/pairing/exchange')
def exchange(data:Pairing,s:Session=Depends(db)):
 inv=s.scalar(select(PairingInvitation).where(PairingInvitation.token_hash==digest(data.token)).with_for_update())
 if not inv or inv.used_at or inv.revoked_at or inv.expires_at<=ts(): raise HTTPException(410,'This pairing invitation is invalid or expired')
 claimed=s.execute(update(PairingInvitation).where(PairingInvitation.id==inv.id,
  PairingInvitation.used_at.is_(None),PairingInvitation.revoked_at.is_(None),PairingInvitation.expires_at>ts()
 ).values(used_at=ts()),execution_options={'synchronize_session':False})
 if not claimed.rowcount:
  s.rollback();raise HTTPException(410,'This pairing invitation is invalid or expired')
 row=s.scalar(select(ControlSession).where(ControlSession.id==inv.session_id).with_for_update().execution_options(populate_existing=True))
 if not row or row.status in ('ended','expired') or row.expires_at<=ts():
  s.rollback();raise HTTPException(410,'Control session is no longer active')
 raw='ct_'+secrets.token_urlsafe(32); device=ControllerDevice(session_id=row.id,label=data.device_label.strip(),token_hash=digest(raw),last_seen_at=ts()); s.add(device); row.status='connected'; row.last_activity_at=ts(); audit(s,row.id,'DEVICE_PAIRED',None,{'device_label':device.label}); s.commit()
 return {'controller_token':raw,'device_id':device.id,'session_id':row.id,'total_slides':row.total_slides,'current_slide_index':row.current_slide_index,'expires_at':row.expires_at}

@router.get('/sessions/{sid}')
def state(sid:str,user:User=Depends(current),s:Session=Depends(db)):
 row=owner(s,sid,user); devices=s.scalars(select(ControllerDevice).where(ControllerDevice.session_id==sid,ControllerDevice.revoked_at.is_(None))).all()
 return {'session_id':sid,'status':row.status,'current_slide_index':row.current_slide_index,'total_slides':row.total_slides,'expires_at':row.expires_at,'devices':[{'id':d.id,'label':d.label,'last_seen_at':d.last_seen_at} for d in devices]}
@router.get('/sessions/{sid}/state')
def state_alias(sid:str,user:User=Depends(current),s:Session=Depends(db)): return state(sid,user,s)
@router.post('/sessions/{sid}/revoke/{device_id}')
async def revoke(sid:str,device_id:str,user:User=Depends(current),s:Session=Depends(db)):
 row=owner(s,sid,user); d=s.scalar(select(ControllerDevice).where(ControllerDevice.id==device_id,ControllerDevice.session_id==sid))
 if not d: raise HTTPException(404,'Device not found')
 d.revoked_at=ts(); audit(s,sid,'DEVICE_REVOKED',user.id,{'device_id':device_id}); s.commit()
 for socket in list(controller_connections.get(device_id,set())):
  try:await socket.close(code=4403)
  except (RuntimeError,WebSocketDisconnect):pass
 return {'ok':True}
@router.post('/sessions/{sid}/end')
async def end(sid:str,user:User=Depends(current),s:Session=Depends(db)):
 row=owner(s,sid,user); row.status='ended'; row.ended_at=ts(); audit(s,sid,'SESSION_ENDED',user.id); s.commit(); await broadcast(sid,{'type':'SESSION_ENDED'})
 for socket in list(connections.get(sid,set())):
  try:await socket.close(code=1000)
  except (RuntimeError,WebSocketDisconnect):pass
 return {'ok':True}

def device_for(s,token):
 d=s.scalar(select(ControllerDevice).where(ControllerDevice.token_hash==digest(token),ControllerDevice.revoked_at.is_(None)))
 if not d: raise HTTPException(401,'Controller authorization expired')
 row=s.get(ControlSession,d.session_id)
 if not row or row.status in ('ended','expired') or row.expires_at<=ts(): raise HTTPException(410,'Control session is no longer active')
 d.last_seen_at=ts(); row.last_activity_at=ts(); s.commit(); return d,row

@router.post('/controllers/{token}/command')
async def command(token:str,data:Command,s:Session=Depends(db)):
 d,row=device_for(s,token)
 old=s.scalar(select(ControlCommand).where(ControlCommand.session_id==row.id,ControlCommand.request_id==data.request_id))
 if old: return {'accepted':True,'duplicate':True,'status':old.status,'result':json.loads(old.result or '{}')}
 if data.command=='SLIDE_GOTO' and (data.slide_index is None or data.slide_index>=row.total_slides): raise HTTPException(422,'Slide index is outside this presentation')
 c=ControlCommand(session_id=row.id,device_id=d.id,request_id=data.request_id,command=data.command,payload=json.dumps({'slide_index':data.slide_index})); s.add(c); audit(s,row.id,'COMMAND_QUEUED',d.user_id,{'command':data.command}); s.commit()
 await broadcast(row.id,{'type':'COMMAND','request_id':data.request_id,'command':data.command,'slide_index':data.slide_index})
 return {'accepted':True,'duplicate':False,'status':'queued','request_id':data.request_id}

async def broadcast(sid,message):
 dead=[]
 for ws in list(connections.get(sid,set())):
  try: await ws.send_json(message)
  except Exception: dead.append(ws)
 for ws in dead: connections.get(sid,set()).discard(ws)

def cookie_owner(ws,s):
 token=(ws.headers.get('cookie','').split('pptx_session=',1)[1].split(';',1)[0] if 'pptx_session=' in ws.headers.get('cookie','') else '')
 from .core import SessionToken
 entry=s.scalar(select(SessionToken).where(SessionToken.token_hash==digest(token),SessionToken.revoked.is_(False),SessionToken.expires>ts())) if token else None
 return s.get(User,entry.user_id) if entry else None

@router.websocket('/ws/{sid}')
async def websocket(ws:WebSocket,sid:str,role:str='controller',token:str=''):
 await ws.accept(); s=DBSession(); row=s.get(ControlSession,sid); device=None
 try:
  if not row or row.expires_at<=ts() or row.status in ('ended','expired'): await ws.close(code=4404); return
  device=None
  if role=='host':
   u=cookie_owner(ws,s)
   if not u or u.id!=row.owner_user_id: await ws.close(code=4403); return
   host_connections[sid]=ws; row.status='connected'; row.last_activity_at=ts()
  else:
   device=s.scalar(select(ControllerDevice).where(ControllerDevice.token_hash==digest(token),ControllerDevice.session_id==sid,ControllerDevice.revoked_at.is_(None)))
   if not device: await ws.close(code=4403); return
  if device:controller_connections.setdefault(device.id,set()).add(ws)
  connections.setdefault(sid,set()).add(ws); s.commit(); await ws.send_json({'type':'SESSION_STATE','session_id':sid,'current_slide_index':row.current_slide_index,'total_slides':row.total_slides,'status':row.status})
  if role=='host': await broadcast(sid,{'type':'HOST_CONNECTED'})
  async for message in ws.iter_json():
   row=s.get(ControlSession,sid,populate_existing=True)
   if not row:
    await ws.close(code=4404); break
   if row.expires_at<=ts() or row.status in ('ended','expired'):
    await ws.send_json({'type':'SESSION_ENDED'}); await ws.close(code=4404); break
   if device:
    device=s.get(ControllerDevice,device.id,populate_existing=True)
    if not device or device.revoked_at:
     await ws.close(code=4403); break
   if not isinstance(message,dict):
    await ws.send_json({'type':'ERROR','error':'Control messages must be objects.'}); continue
   kind=message.get('type')
   if kind=='HOST_STATE' and role=='host':
    idx=message.get('slide_index',0)
    if not isinstance(idx,int) or isinstance(idx,bool):
     await ws.send_json({'type':'ERROR','error':'Slide index must be an integer.'}); continue
    deck=s.get(Presentation,row.presentation_id,populate_existing=True)
    row.total_slides=len(json.loads(deck.slides or '[]')) if deck else 0
    if 0<=idx<row.total_slides:
     row.current_slide_index=idx; row.last_activity_at=ts(); s.commit(); await broadcast(sid,{'type':'SLIDE_STATE_CHANGED','slide_index':idx,'total_slides':row.total_slides,'source':'host'})
   elif kind=='COMMAND_RESULT' and role=='host':
    if not isinstance(message.get('request_id'),str) or not 8<=len(message['request_id'])<=100:
     await ws.send_json({'type':'ERROR','error':'Command request ID must be a bounded string.'}); continue
    c=s.scalar(select(ControlCommand).where(ControlCommand.session_id==sid,ControlCommand.request_id==message.get('request_id')))
    if c:
     c.status='completed' if message.get('ok') else 'failed'; c.result=json.dumps({'slide_index':message.get('slide_index'),'error':message.get('error')});
     idx=message.get('slide_index')
     if message.get('ok') and isinstance(idx,int) and not isinstance(idx,bool) and 0<=idx<row.total_slides:row.current_slide_index=idx
     s.commit(); await broadcast(sid,{'type':'COMMAND_RESULT','request_id':c.request_id,'ok':c.status=='completed','slide_index':row.current_slide_index,'error':message.get('error')})
   elif kind=='PING': await ws.send_json({'type':'PONG','at':ts()})
 except (ValueError,TypeError):
  await ws.close(code=1003)
 finally:
  connections.get(sid,set()).discard(ws)
  if not connections.get(sid):connections.pop(sid,None);locks.pop(sid,None)
  if device:
   controller_connections.get(device.id,set()).discard(ws)
   if not controller_connections.get(device.id):controller_connections.pop(device.id,None)
  if host_connections.get(sid) is ws: host_connections.pop(sid,None)
  s.close()
