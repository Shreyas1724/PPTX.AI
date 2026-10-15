import hashlib,hmac,os,uuid,logging
from fastapi.responses import JSONResponse
LOG=logging.getLogger('pptx.security')
def csrf(token):return hashlib.sha256(('pptx-csrf:'+token).encode()).hexdigest()
class BodyLimit:
 """Enforce the limit even on chunked requests without a Content-Length."""
 def __init__(self,app,maximum=6_000_000):self.app=app;self.maximum=maximum
 async def __call__(self,scope,receive,send):
  if scope['type']!='http':return await self.app(scope,receive,send)
  size=0;chunks=[]
  while True:
   message=await receive()
   if message['type']=='http.disconnect':return
   size+=len(message.get('body',b''))
   if size>self.maximum:return await JSONResponse({'detail':'Request exceeds the 6 MB limit'},status_code=413)(scope,receive,send)
   chunks.append(message)
   if not message.get('more_body'):break
  async def bounded_receive():
   if chunks:return chunks.pop(0)
   return await receive()
  await self.app(scope,bounded_receive,send)

def validate_production():
 if os.getenv('APP_ENV')!='production':return
 if os.getenv('COOKIE_SECURE')!='true':raise RuntimeError('Production requires COOKIE_SECURE=true')
 if len(os.getenv('OTP_SECRET',''))<32:raise RuntimeError('Production requires a strong OTP_SECRET')
 if not os.getenv('DATABASE_URL','').startswith('postgresql'):raise RuntimeError('Production requires PostgreSQL')
 if not all(x.strip().startswith('https://') for x in os.getenv('CORS_ORIGINS','').split(',')):raise RuntimeError('Production requires explicit HTTPS origins')
