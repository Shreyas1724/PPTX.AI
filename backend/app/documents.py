"""Parse untrusted documents in a resource-limited subprocess on Linux."""
import io,sys,json,zipfile,subprocess
class DocumentError(Exception):pass

def extract(raw,extension):
 if len(raw)>5_000_000:raise DocumentError('File exceeds 5 MB')
 if extension in ('txt','md','csv'):
  if b'\x00' in raw:raise DocumentError('Text file contains binary data')
  return raw.decode('utf-8')[:200000]
 if extension=='pdf':
  if not raw.startswith(b'%PDF-'):raise DocumentError('Invalid PDF file')
  from pypdf import PdfReader
  reader=PdfReader(io.BytesIO(raw))
  if reader.is_encrypted:raise DocumentError('Encrypted PDFs are not supported')
  chunks=[];length=0
  for page in reader.pages[:50]:
   text=page.extract_text() or '';chunks.append(text[:200000-length]);length+=len(chunks[-1])
   if length>=200000:break
  return '\n'.join(chunks)[:200000]
 if extension=='docx':
  with zipfile.ZipFile(io.BytesIO(raw)) as archive:
   entries=archive.infolist()
   if len(entries)>500 or sum(i.file_size for i in entries)>20_000_000:raise DocumentError('Document expands beyond the allowed size')
   if '[Content_Types].xml' not in archive.namelist() or 'word/document.xml' not in archive.namelist():raise DocumentError('Invalid Word document')
  from docx import Document
  return '\n'.join(p.text for p in Document(io.BytesIO(raw)).paragraphs)[:200000]
 raise DocumentError('Use TXT, MD, CSV, PDF, or DOCX')

def parse(raw,extension):
 if extension not in ('txt','md','csv','pdf','docx'):raise DocumentError('Unsupported document type')
 try:
  result=subprocess.run([sys.executable,'-m','app.documents',extension],input=raw,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=12,check=False)
  if result.returncode!=0:raise DocumentError('Document could not be read within safety limits')
  data=json.loads(result.stdout)
  if 'error' in data:raise DocumentError(data['error'])
  if not data['text'].strip():raise DocumentError('No extractable text. Scanned documents need OCR first.')
  return data['text']
 except subprocess.TimeoutExpired:raise DocumentError('Document processing timed out')

if __name__=='__main__':
 try:
  import resource
  resource.setrlimit(resource.RLIMIT_AS,(768*1024*1024,768*1024*1024))
  resource.setrlimit(resource.RLIMIT_CPU,(8,8))
  raw=sys.stdin.buffer.read(5_000_001)
  text=extract(raw,sys.argv[1]);print(json.dumps({'text':text}))
 except Exception:
  print(json.dumps({'error':'Cannot extract text from this document. Check its format and size.'}))
