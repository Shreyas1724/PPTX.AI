"""Server-priced Checkout and signature-verified, one-time fulfillment."""
import os,json,time,hmac,hashlib
import httpx
from fastapi import APIRouter,Depends,HTTPException,Request
from pydantic import BaseModel,Field
from sqlalchemy import select,update
from .auth import db,current,limit
from .core import Purchase,User,CreditEvent
from .activity import record
router=APIRouter(prefix='/api/v1/billing',tags=['Billing'])

def catalog():
 # No charge is possible until an operator explicitly supplies a price.
 try:
  amount=int(os.getenv('CREDIT_PACK_AMOUNT','0'));credits=int(os.getenv('CREDIT_PACK_CREDITS','100'))
 except ValueError:return []
 currency=os.getenv('BILLING_CURRENCY','inr').lower()
 if amount<=0 or credits<=0 or currency not in ('inr','usd','eur','gbp'):return []
 return [{'id':'studio','credits':credits,'amount':amount,'currency':currency}]
def enabled():return bool(os.getenv('STRIPE_SECRET_KEY') and os.getenv('STRIPE_WEBHOOK_SECRET') and os.getenv('PUBLIC_APP_URL') and catalog())
@router.get('/catalog')
def get_catalog():return {'enabled':enabled(),'packs':catalog() if enabled() else []}
class Checkout(BaseModel): pack_id:str=Field(max_length=40)

def create_checkout(order,email):
 base=os.environ['PUBLIC_APP_URL'].rstrip('/')
 if not base.startswith('https://') and os.getenv('APP_ENV')=='production':raise HTTPException(503,'Checkout requires an HTTPS application URL.')
 data={'mode':'payment','customer_email':email,'client_reference_id':order.id,'metadata[order_id]':order.id,'success_url':base+'/credits?payment=return','cancel_url':base+'/credits?payment=cancelled','line_items[0][price_data][currency]':order.currency,'line_items[0][price_data][unit_amount]':str(order.amount),'line_items[0][price_data][product_data][name]':f'PPTX.AI — {order.credits} credits','line_items[0][quantity]':'1'}
 try:
  with httpx.Client(timeout=20) as client:
   r=client.post('https://api.stripe.com/v1/checkout/sessions',headers={'Authorization':'Bearer '+os.environ['STRIPE_SECRET_KEY'],'Idempotency-Key':'checkout:'+order.id},data=data);r.raise_for_status();return r.json()
 except Exception:raise HTTPException(503,'Checkout is temporarily unavailable. No credits have been added.')
@router.post('/checkout')
def checkout(data:Checkout,user=Depends(current),session=Depends(db)):
 if not enabled():raise HTTPException(503,'Credit purchases have not been configured.')
 limit(session,'checkout:'+user.id,10,600)
 pack=next((p for p in catalog() if p['id']==data.pack_id),None)
 if not pack:raise HTTPException(422,'Unknown credit pack')
 order=Purchase(user_id=user.id,credits=pack['credits'],amount=pack['amount'],currency=pack['currency']);session.add(order);session.commit()
 result=create_checkout(order,user.email)
 if not result.get('url','').startswith('https://checkout.stripe.com/'):raise HTTPException(502,'Payment provider returned an invalid checkout URL.')
 order.stripe_session=result['id'];session.commit();return {'url':result['url'],'order_id':order.id}

def verify_signature(raw,signature):
 secret=os.getenv('STRIPE_WEBHOOK_SECRET','')
 if not secret:raise HTTPException(503,'Webhook not configured')
 try:
  fields=[x.split('=',1) for x in signature.split(',')];stamp=next(v for k,v in fields if k=='t')
  if abs(int(time.time())-int(stamp))>300:raise ValueError()
  expected=hmac.new(secret.encode(),stamp.encode()+b'.'+raw,hashlib.sha256).hexdigest()
  if not any(k=='v1' and hmac.compare_digest(v,expected) for k,v in fields):raise ValueError()
 except Exception:raise HTTPException(400,'Invalid webhook signature')

def fulfill(session,event):
 if not isinstance(event,dict):raise HTTPException(400,'Invalid webhook event')
 if event.get('type') not in ('checkout.session.completed','checkout.session.async_payment_succeeded'):return
 envelope=event.get('data')
 if not isinstance(envelope,dict) or not isinstance(envelope.get('object'),dict):raise HTTPException(400,'Invalid checkout event')
 data=envelope['object']
 if data.get('payment_status')!='paid':return
 metadata=data.get('metadata')
 if not isinstance(metadata,dict) or not isinstance(metadata.get('order_id'),str):raise HTTPException(400,'Invalid order metadata')
 order_id=metadata['order_id'];order=session.get(Purchase,order_id) if order_id else None
 if not order:raise HTTPException(400,'Unknown order')
 if data.get('amount_total')!=order.amount or data.get('currency')!=order.currency or data.get('client_reference_id')!=order.id:raise HTTPException(400,'Payment does not match the order')
 if not order.stripe_session:raise HTTPException(503,'Order is still being initialized; retry delivery')
 if data.get('id')!=order.stripe_session:raise HTTPException(400,'Checkout session does not match')
 changed=session.execute(update(Purchase).where(Purchase.id==order.id,Purchase.state=='pending').values(state='fulfilled'))
 if not changed.rowcount:return
 session.execute(update(User).where(User.id==order.user_id).values(credits=User.credits+order.credits))
 session.add(CreditEvent(user_id=order.user_id,amount=order.credits,reason='purchase',key='purchase:'+order.id))
 record(session,order.user_id,'credits.purchased',f'Purchased {order.credits} credits');session.commit()
@router.post('/webhook')
async def webhook(request:Request,session=Depends(db)):
 raw=await request.body()
 if len(raw)>250000:raise HTTPException(413,'Webhook payload too large')
 verify_signature(raw,request.headers.get('stripe-signature',''))
 try:event=json.loads(raw)
 except ValueError:raise HTTPException(400,'Invalid JSON')
 fulfill(session,event);return {'received':True}
