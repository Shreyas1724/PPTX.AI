"""Account-scoped task journal. Retention is always a rolling 100 days."""
import time
from sqlalchemy import delete, select
from .core import Session, Activity, Registration, GoogleTicket, RateBucket, SessionToken
RETENTION_SECONDS=100*86400

def record(session,user_id,action,summary,resource_id=None,status='completed'):
 session.add(Activity(user_id=user_id,action=action,summary=summary[:240],resource_id=resource_id,status=status))

def purge(session):
 now=int(time.time())
 for model,condition in [(Activity,Activity.created_at<now-RETENTION_SECONDS),(Registration,Registration.expires<now),(GoogleTicket,GoogleTicket.expires<now),(RateBucket,RateBucket.expires<now),(SessionToken,SessionToken.expires<now)]:
  session.execute(delete(model).where(condition))
 session.commit()

def maintenance():
 while True:
  try:
   from .worker import sweep
   sweep()
   with Session() as session: purge(session)
  except Exception:
   import logging
   logging.getLogger(__name__).exception('Retention cleanup failed')
  time.sleep(3600)

if __name__=='__main__': maintenance()
