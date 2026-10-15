"""All credit mutations happen in the same transaction as their ledger entries."""
import hashlib,json,os,time
from fastapi import HTTPException
from sqlalchemy import select,update,func
from sqlalchemy.exc import IntegrityError
from .core import User,CreditEvent,Job,Operation,uid

def prices():
 return {'generation':max(1,int(os.getenv('GENERATION_COST','2'))),'edit':max(1,int(os.getenv('AI_EDIT_COST','1')))}
def reserve(session,user_id,presentation,kind,payload,key):
 if not key or len(key)>128: raise HTTPException(422,'An Idempotency-Key of 1–128 characters is required.')
 canonical=json.dumps({'presentation_id':presentation.id,'kind':kind,'payload':payload},sort_keys=True,separators=(',',':'))
 fingerprint=hashlib.sha256(canonical.encode()).hexdigest()
 def existing():
  op=session.scalar(select(Operation).where(Operation.user_id==user_id,Operation.request_key==key))
  if op and op.fingerprint!=fingerprint: raise HTTPException(409,'This request key was already used for a different operation.')
  return op
 old=existing()
 if old:return old
 cost=prices()[kind]; job_id=uid()
 try:
  # This conditional SQL update prevents concurrent overspending on both databases.
  changed=session.execute(update(User).where(User.id==user_id,User.credits>=cost).values(credits=User.credits-cost))
  if not changed.rowcount:
   session.rollback();old=existing()
   if old:return old
   raise HTTPException(402,'Insufficient credits. Check your wallet before continuing.')
  job=Job(id=job_id,user_id=user_id,presentation_id=presentation.id,prompt=payload.get('prompt',payload.get('instruction','')),count=payload.get('count',len(json.loads(presentation.slides))))
  op=Operation(user_id=user_id,job_id=job_id,request_key=key,fingerprint=fingerprint,kind=kind,payload=json.dumps(payload),cost=cost,base_version=presentation.version)
  session.add_all([job,op,CreditEvent(user_id=user_id,amount=-cost,reason=kind+':reserve',key='reserve:'+job_id)])
  session.commit();return op
 except IntegrityError:
  session.rollback();old=existing()
  if old:return old
  raise

def refund(session,op_id,reason='Operation failed'):
 op=session.get(Operation,op_id)
 if not op:return False
 result=session.execute(update(Operation).where(Operation.id==op_id,Operation.state.in_(['reserved','running'])).values(state='refunded',result=json.dumps({'message':reason})))
 if not result.rowcount:return False
 session.execute(update(User).where(User.id==op.user_id).values(credits=User.credits+op.cost))
 session.add(CreditEvent(user_id=op.user_id,amount=op.cost,reason=op.kind+':refund',key='refund:'+op.job_id))
 job=session.get(Job,op.job_id)
 if job:job.status='failed';job.stage='refunded';job.error=reason
 return True

def wallet(session,user_id):
 from .project_models import ProjectAnalysisJob
 balance=session.scalar(select(User.credits).where(User.id==user_id))
 reserved=session.scalar(select(func.coalesce(func.sum(Operation.cost),0)).where(Operation.user_id==user_id,Operation.state.in_(['reserved','running'])))
 spent=session.scalar(select(func.coalesce(func.sum(Operation.cost),0)).where(Operation.user_id==user_id,Operation.state=='settled'))
 analysis_reserved=session.scalar(select(func.coalesce(func.sum(ProjectAnalysisJob.cost),0)).where(ProjectAnalysisJob.owner_id==user_id,ProjectAnalysisJob.status.in_(['queued','running'])))
 analysis_debits=-session.scalar(select(func.coalesce(func.sum(CreditEvent.amount),0)).where(CreditEvent.user_id==user_id,CreditEvent.reason.in_(['project_analysis:reserve','project_analysis:refund'])))
 reserved+=analysis_reserved
 # The ledger survives project deletion, preserving historical spending.
 spent+=analysis_debits-analysis_reserved
 return {'balance':balance,'reserved':reserved,'spent':spent,'generation_cost':prices()['generation'],'edit_cost':prices()['edit'],'model_mode':'ai' if os.getenv('LLM_API_KEY') else 'local-outline'}
