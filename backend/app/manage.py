"""Operator-only CLI. Never expose this module as an HTTP endpoint."""
import argparse, os, secrets, sys
from sqlalchemy import select,func,update
from sqlalchemy.exc import IntegrityError
from .core import Base,Session,User,Profile,CreditEvent,Job,Operation,hash_password

def create_demo_user(session,*,email,password,name='Demo Tester',mobile='+12025550199',credits=30):
 """Provision a local test identity explicitly; never called by app startup."""
 if os.getenv('APP_ENV','development').strip().lower() not in ('development','test','local') or session.get_bind().dialect.name!='sqlite':
  raise ValueError('Demo accounts are restricted to local SQLite development/test databases.')
 if not 1<=credits<=100000:raise ValueError('Credits must be between 1 and 100000')
 # Share onboarding validation, but never render validation input (passwords).
 from .auth import Signup
 from pydantic import ValidationError
 try:data=Signup(name=name,email=email,mobile=mobile,password=password,role='other')
 except ValidationError:raise ValueError('Enter a valid name, email, international mobile number, and a 10–128 character password.') from None
 if not data.email.endswith('.test'):raise ValueError('Use a reserved .test email address for a demo identity.')
 Base.metadata.create_all(session.get_bind())
 if session.scalar(select(User).where(User.email==data.email)) or session.scalar(select(Profile).where(Profile.phone==data.mobile)):
  raise ValueError('Demo email or mobile already exists; no account or password was changed.')
 try:
  user=User(email=data.email,password=hash_password(password),credits=credits);session.add(user);session.flush()
  # Synthetic contacts have not passed real OTP verification.
  session.add(Profile(user_id=user.id,name=data.name,phone=data.mobile,role=data.role,email_verified=False,phone_verified=False))
  session.add(CreditEvent(user_id=user.id,amount=credits,reason='operator:demo',key='operator:demo:'+user.id))
  from .activity import record
  record(session,user.id,'account.created','Local demo account provisioned by trusted operator')
  session.commit()
 except IntegrityError:
  session.rollback();raise ValueError('Demo email or mobile already exists; no account or password was changed.') from None
 return user

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
 p=argparse.ArgumentParser(description='PPTX.AI trusted-operator administration')
 sub=p.add_subparsers(dest='command',required=True);sub.add_parser('audit-credits')
 grant=sub.add_parser('grant-credits');grant.add_argument('--email',required=True);grant.add_argument('--credits',required=True,type=int);grant.add_argument('--reference',required=True)
 demo=sub.add_parser('create-demo-user',help='Explicitly create a synthetic local SQLite test account')
 demo.add_argument('--email',default='demo@pptx.test');demo.add_argument('--name',default='Demo Tester');demo.add_argument('--mobile',default='+12025550199');demo.add_argument('--credits',default=30,type=int)
 demo.add_argument('--password-stdin',action='store_true',help='Read a password from stdin instead of generating one; never pass passwords as arguments')
 args=p.parse_args()
 with Session() as session:
  if args.command=='create-demo-user':
   password=sys.stdin.readline(131).rstrip('\r\n') if args.password_stdin else secrets.token_urlsafe(24)
   try:user=create_demo_user(session,email=args.email,password=password,name=args.name,mobile=args.mobile,credits=args.credits)
   except ValueError as exc:raise SystemExit(str(exc)) from None
   print('Local demo account created. This account exists only in the configured SQLite database.')
   print('Email: '+user.email)
   if not args.password_stdin:print('Password (shown once): '+password)
   return
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
