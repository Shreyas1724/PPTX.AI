"""Offline structural coverage matrix; synthetic topic prompts, no LLM calls.

Do not treat these numbers as an evaluation of content or aesthetics.
"""
import json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.engine import render,local_slides
from app.quality import audit_pptx

categories={'academic':'A literature review of machine learning methods',
 'business':'A company process improvement initiative',
 'finance':'Financial performance reporting with verified data only',
 'startup':'An early stage SaaS product investor overview',
 'technical':'An API and database architecture proposal',
 'education':'A classroom lesson on renewable energy'}
results=[]
for name,prompt in categories.items():
 for count in (5,10,20):
  slides=local_slides(prompt,count)
  result=audit_pptx(render('Fixture '+name,slides,'light'))
  results.append({'category':name,'slide_count':count,'reopens':True,
                  'critical_geometry_findings':result['critical_count'],
                  'text_fit_warnings':result['warning_count']})
report={'note':'Deterministic local placeholder outlines; tests validate shape geometry only, NOT factual or artistic quality.',
        'cases':len(results),'failed_structural_cases':sum(x['critical_geometry_findings']>0 for x in results),'results':results}
Path(__file__).with_name('coverage_matrix.json').write_text(json.dumps(report,indent=2))
print('Structural fixture cases:',report['cases'],'failures:',report['failed_structural_cases'])
