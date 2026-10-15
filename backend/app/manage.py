"""Operator-only CLI. Never expose this module as an HTTP endpoint."""
import argparse
from sqlalchemy import select,func,update
from sqlalchemy.exc import IntegrityError
from .core import Session,User,CreditEvent,Job,Operation

def recover_legacy(session):
 # v2 used Job + CreditEvent directly. Do not abandon old paid queued jobs.
 rows=session.scalars(select(Job).where(Job.status.in_(['queued','running']),~Job.id.in_(select(Operation.job_id)))).all()
 for job in rows:
  changed=session.execute(update(Job).where(Job.id==job.id,Job.status.in_(['queued','running'])).values(status='failed',stage='migration',error='Job interrupted by upgrade. Please retry.'))
  if not changed.rowcount:continue
  debit=session.scalar(select(CreditEvent).where(CreditEvent.user_id==job.user_id,CreditEvent.reason==job.id,CreditEvent.amount<0))
  if debit:
   session.execute(update(User).where(User.id==job.user_id).values(credits=User.credits-debit.amount))
   session.add(CreditEvent(user_id=job.user_id,amount=-debit.amount,reason='legacy:refund',key='legacy-refund:'+job.id))
 session.commit()

def audit(session):
 discrepancies=[]
 for user in session.scalars(select(User)):
  ledger=session.scalar(select(func.coalesce(func.sum(CreditEvent.amount),0)).where(CreditEvent.user_id==user.id))
  if ledger!=user.credits:discrepancies.append({'user_id':user.id,'balance':user.credits,'ledger':ledger})
 return discrepancies

def main():
 p=argparse.ArgumentParser(description='PPTX.AI trusted-operator credit administration')
 sub=p.add_subparsers(dest='command',required=True);sub.add_parser('audit-credits')
 grant=sub.add_parser('grant-credits');grant.add_argument('--email',required=True);grant.add_argument('--credits',required=True,type=int);grant.add_argument('--reference',required=True)
 args=p.parse_args()
 with Session() as session:
  if args.command=='audit-credits':
   import json
   problems=audit(session);print(json.dumps({'discrepancies':problems},indent=2));raise SystemExit(1 if problems else 0)
  if args.credits<=0 or args.credits>100000:raise SystemExit('Credits must be between 1 and 100000')
  if not 1<=len(args.reference)<=100:raise SystemExit('Reference must be between 1 and 100 characters')
  user=session.scalar(select(User).where(User.email==args.email.strip().lower()))
  if not user:raise SystemExit('Account not found')
  key='operator:'+args.reference
  if session.scalar(select(CreditEvent).where(CreditEvent.key==key)):raise SystemExit('Reference already used; no credits added')
  try:
   session.execute(update(User).where(User.id==user.id).values(credits=User.credits+args.credits))
   session.add(CreditEvent(user_id=user.id,amount=args.credits,reason='operator:grant',key=key));session.commit()
  except IntegrityError:session.rollback();raise SystemExit('Reference already used; no credits added')
  print('Credit grant recorded.')
if __name__=='__main__':main()
