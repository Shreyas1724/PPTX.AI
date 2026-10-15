"""Content-aware layout choices with no fabricated chart values or citations."""
import re
from .slide_spec import SlideSpec

LAYOUT_KEYWORDS=(
 ('references',r'\b(references?|bibliograph(?:y|ies)|citations?|sources)\b'),
 ('conclusion',r'\b(conclusion|recommendation|takeaways?|next steps)\b'),
 ('problem_solution',r'\b(problem.*solution|challenge.*approach)\b'),
 ('architecture',r'\b(architecture|infrastructure|database|systems? design)\b'),
 ('methodology',r'\b(methodology|experiment|research method)\b'),
 ('timeline',r'\b(timeline|milestones?|phases?|roadmap)\b'),
 ('process',r'\b(workflow|pipeline|how it works|process|stages?)\b'),
 ('comparison',r'\b(compar(?:e|ed|es|ing|ison|isons|ative|atively)|versus|vs\.?|pros and cons|alternatives)\b'),
 ('kpi',r'\b(metrics?|results?|performance|numbers|statistics|impact)\b'),
 ('summary',r'\b(summary|overview|executive brief)\b'),
)

def plan_layouts(items:list[SlideSpec])->list[SlideSpec]:
    result=[];previous=''
    for index,slide in enumerate(items):
        if slide.layout:
            chosen=slide.layout
        elif slide.chart:
            chosen='chart'
        elif slide.metrics:
            chosen='kpi'
        elif slide.steps:
            chosen='timeline' if re.search(r'\b(roadmap|timeline|phases?|milestones?)\b',slide.title.lower()) else 'process'
        elif index==0:
            chosen='title'
        elif index==len(items)-1 and re.search(r'\b(questions|thank|wrap|next)\b',slide.title.lower()):
            chosen='conclusion'
        else:
            chosen=next((kind for kind,pattern in LAYOUT_KEYWORDS if re.search(pattern,slide.title.lower())),None)
            if chosen is None:
                chosen=('three_column' if len(slide.body) in (3,6) else 'two_column' if len(slide.body) in (2,4) else 'bullets')
            # Prefer meaningful variation for adjacent general-purpose slides.
            if chosen==previous and chosen in ('bullets','two_column','three_column'):
                chosen='two_column' if previous!='two_column' else 'feature_grid'
        result.append(slide.model_copy(update={'layout':chosen}));previous=chosen
    return result
