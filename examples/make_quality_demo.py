"""Create an offline, explicitly illustrative presentation-quality fixture."""
from pathlib import Path
import sys,json
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'backend'))
from app.engine import render
from app.quality import audit_pptx
SLIDES=[
 {'title':'The Future of Project Intelligence','layout':'title','subtitle':'A demonstration of editable PPTX.AI slide designs','body':['This deck is an illustrative design fixture, not verified research.']},
 {'title':'Executive Summary','layout':'summary','body':['Ideas become structured requirements','Validation reduces delivery uncertainty','Visual layouts match communication intent','Native content remains editable']},
 {'title':'Problem and Solution','layout':'problem_solution','body':['Problem: lengthy research can be hard to present.','People need to see the central insight.','Solution: plan each slide around a clear claim.','Create native charts and diagrams where useful.']},
 {'title':'Comparison of Approaches','layout':'comparison','body':['Traditional: repeated bullets','Traditional: manual design decisions','Proposed: content-aware slides','Proposed: repeatable quality checks']},
 {'title':'Presentation Generation Workflow','layout':'process','steps':['Understand request','Outline narrative','Choose slide layouts','Render PowerPoint','Check output']},
 {'title':'System Architecture','layout':'architecture','steps':['React application','FastAPI application APIs','Content & layout planner','Native PowerPoint renderer','Quality checks and export']},
 {'title':'MVP Roadmap','layout':'timeline','steps':['Requirements','Core engine','Quality checks','User testing']},
 {'title':'Illustrative Benchmarks','layout':'chart','chart':{'kind':'bar','title':'Example data, not measured','unit':'sample units','points':[{'label':'A','value':12},{'label':'B','value':19},{'label':'C','value':24}]},'notes':'All values are fabricated illustrative fixture data, not actual project benchmark results.'},
 {'title':'Hypothetical Adoption Trend','layout':'chart','chart':{'kind':'line','title':'Illustrative values','unit':'sample users','points':[{'label':'Jan','value':10},{'label':'Feb','value':20},{'label':'Mar','value':30}]},'notes':'Illustrative chart, not factual user data.'},
 {'title':'Illustrative Category Shares','layout':'chart','chart':{'kind':'pie','title':'Sample distribution','unit':'%','points':[{'label':'Education','value':40},{'label':'Business','value':35},{'label':'Other','value':25}]},'notes':'Illustrative values only.'},
 {'title':'Design System Metrics','layout':'kpi','metrics':[{'label':'Layout choices','value':'24','context':'Supported layout identifiers in the design schema'},{'label':'Presentation aspect','value':'16:9','context':'Standard wide presentation'},{'label':'Native charts','value':'3','context':'Bar, line, pie supported'}]},
 {'title':'Technical Priorities','layout':'three_column','body':['Native output','Edit text and charts','Validated content','Use strict schemas','No fabricated sources','Human verification remains necessary']},
 {'title':'Research Methodology','layout':'methodology','steps':['Collect user materials','Separate facts from assumptions','Draft an outline','Validate key claims']},
 {'title':'References and Notes','layout':'references','body':['This demonstration uses example statements only.','No external research was performed for the example presentation.']},
 {'title':'Conclusion','layout':'conclusion','body':['Content-aware layouts and structural checks form a stronger presentation-generation foundation.']},
]
if __name__=='__main__':
 p=Path(__file__).with_name('PPTX_AI_Design_Engine_Demo.pptx')
 b=render('PPTX.AI Example',SLIDES,'midnight');p.write_bytes(b)
 report=audit_pptx(b,verify_external=True)
 Path(__file__).with_name('quality_demo_report.json').write_text(json.dumps(report,indent=2))
 print(p,'size',len(b),'report',report['status'],report['critical_count'],'critical',report['warning_count'],'warnings','pdf',report['independent_render'])
