"""Durable database queue with atomic claims, a bounded lease, and fenced commits."""
import json,time,logging,os
from sqlalchemy import select,update
from .core import Session,Job,Presentation,Document,Version,Operation
from .activity import record
from .credits import refund
from .intelligence import retrieve,build,edit,AIError
from .engine import render
from .quality import audit_pptx
LOG=logging.getLogger(__name__)
LEASE_SECONDS=300

def process(job_id):
 with Session() as session:
  op=session.scalar(select(Operation).where(Operation.job_id==job_id))
  if not op:return
  claimed=session.execute(update(Operation).where(Operation.id==op.id,Operation.state=='reserved').values(state='running',lease_until=int(time.time())+LEASE_SECONDS))
  if not claimed.rowcount:session.rollback();return
  job=session.get(Job,job_id)
  if not job:
   message='The job no longer exists. Reserved credits were refunded.'
   if refund(session,op.id,message):record(session,op.user_id,op.kind+'.failed',message,status='failed')
   session.commit();return
  job.status='running';job.stage='retrieving';session.commit()
  op_id=op.id
 try:
  with Session() as session:
   op=session.get(Operation,op_id);job=session.get(Job,job_id);p=session.get(Presentation,job.presentation_id)
   if not p:raise AIError('Presentation no longer exists.')
   payload=json.loads(op.payload); instruction=payload.get('prompt',payload.get('instruction',''))
   sources=retrieve(session.scalars(select(Document).where(Document.project_id==p.project_id)).all(),instruction)
   slides=json.loads(p.slides);theme=p.theme;title=p.title
   job.stage='generating' if op.kind=='generation' else 'editing';session.commit()
  if op.kind=='generation':slides,usage=build(instruction,payload['count'],sources);summary='Presentation generated.'
  else:slides,theme,summary,usage=edit(instruction,slides,theme,sources)
  with Session() as session:
   session.execute(update(Job).where(Job.id==job_id,Job.status=='running').values(stage='validating'));session.commit()
  # Render before committing: broken deck generation never consumes reserved credits.
  deck_bytes=render(title,slides,theme)
  quality=audit_pptx(deck_bytes,verify_external=os.getenv('PPTX_VISUAL_QA','0')=='1')
  if quality['critical_count'] or quality['independent_render']['status']=='failed':
   raise AIError('Slide quality checks failed. No credits were charged; revise the request and retry.')
  with Session() as session:
   op=session.get(Operation,op_id);job=session.get(Job,job_id)
   settled=session.execute(update(Operation).where(Operation.id==op_id,Operation.state=='running',Operation.lease_until>int(time.time())).values(state='settled',result=json.dumps({'message':summary,'usage':usage,'quality':{'status':quality['status'],'critical_count':quality['critical_count'],'warning_count':quality['warning_count'],'independent_render':quality['independent_render']},'sources':[{'source_id':s['source_id'],'filename':s['filename'],'chunk':s['chunk']} for s in sources]})))
   if not settled.rowcount:session.rollback();return
   updated=session.execute(update(Presentation).where(Presentation.id==job.presentation_id,Presentation.version==op.base_version).values(slides=json.dumps(slides),theme=theme,version=op.base_version+1))
   if not updated.rowcount:session.rollback();raise AIError('The presentation changed during processing. Your newer edits were preserved; retry this request.')
   session.add(Version(presentation_id=job.presentation_id,number=op.base_version+1,slides=json.dumps(slides),theme=theme))
   job.status='completed';job.stage='completed';job.error=None
   record(session,job.user_id,op.kind+'.completed',summary,job.presentation_id);session.commit()
 except Exception as exc:
  message=str(exc) if isinstance(exc,AIError) else 'Processing failed. Your reserved credits were refunded.'
  LOG.warning('operation_failed',extra={'job_id':job_id,'error_type':type(exc).__name__})
  with Session() as session:
   op=session.get(Operation,op_id)
   if refund(session,op_id,message):record(session,op.user_id,op.kind+'.failed',message,status='failed')
   session.commit()

def sweep():
 with Session() as session:
  now=int(time.time())
  expired=session.scalars(select(Operation).where(((Operation.state=='running')&(Operation.lease_until<now))|((Operation.state=='reserved')&(Operation.created_at<now-900)))).all()
  for op in expired:refund(session,op.id,'The job timed out. Credits were refunded automatically.')
  session.commit()

def run():
 while True:
  try:
   sweep()
   from .project_worker import tick as project_tick
   project_tick()
   with Session() as session:ids=session.scalars(select(Operation.job_id).where(Operation.state=='reserved').order_by(Operation.created_at).limit(5)).all()
   for identifier in ids:process(identifier)
  except Exception:LOG.exception('worker_poll_failed')
  time.sleep(2)
if __name__=='__main__':run()
