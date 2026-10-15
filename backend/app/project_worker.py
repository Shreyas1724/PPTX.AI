"""Project-analysis worker reusing the existing worker process and DB queue."""
import os, time, json, logging
from sqlalchemy import select, update
from .core import Session, User, CreditEvent, Document
from .project_models import ProjectBlueprint, ProjectBlueprintVersion, ProjectAnalysisJob
from .project_ai import analyze
from .activity import record
from .core import uid

LOG=logging.getLogger(__name__)
LEASE=240

def refund(session,j,message):
    """Called once under a claimed terminal-state transition."""
    success=session.execute(update(ProjectAnalysisJob).where(ProjectAnalysisJob.id==j.id,ProjectAnalysisJob.status.in_(['queued','running'])).values(status='failed',error=message[:800],updated_at=int(time.time())))
    if success.rowcount and j.cost:
        session.execute(update(User).where(User.id==j.owner_id).values(credits=User.credits+j.cost))
        session.add(CreditEvent(user_id=j.owner_id,amount=j.cost,reason='project_analysis:refund',key='project-refund:'+j.id))
    return bool(success.rowcount)

def process(job_id):
    with Session() as session:
        claimed=session.execute(update(ProjectAnalysisJob).where(ProjectAnalysisJob.id==job_id,ProjectAnalysisJob.status=='queued').values(status='running',updated_at=int(time.time()),lease_until=int(time.time())+LEASE))
        if not claimed.rowcount:session.rollback();return
        job=session.get(ProjectAnalysisJob,job_id);session.commit()
    try:
        with Session() as session:
            job=session.get(ProjectAnalysisJob,job_id)
            b=session.get(ProjectBlueprint,job.project_id)
            if not b or b.revision!=job.base_revision:raise ValueError('Project changed while analysis was queued; previous edits were preserved.')
            idea=b.idea;constraints=json.loads(b.constraints_json);existing=json.loads(b.content_json)
            docs=session.scalars(select(Document).where(Document.project_id==b.project_id)).all()
            # Avoid session-bound lazy access outside connection.
            references=[type('Doc',(),{'id':d.id,'filename':d.filename,'content':d.content}) for d in docs]
            section=job.section
        generated,usage=analyze(idea,constraints,existing,references,section)
        with Session() as session:
            job=session.get(ProjectAnalysisJob,job_id)
            b=session.get(ProjectBlueprint,job.project_id)
            if not b or b.revision!=job.base_revision:raise ValueError('Project was edited during analysis. AI results were discarded to protect newer work.')
            sections=json.loads(b.content_json)
            # Preserve accepted decisions and task completion when matching IDs survive regeneration.
            previous_innovations={str(v.get('id')):v.get('status') for v in sections.get('innovations',[]) if v.get('status') in ('accepted','rejected','saved')}
            previous_tasks={str(t.get('id')):t.get('status') for phase in sections.get('roadmap',[]) for t in phase.get('tasks',[])}
            for key,value in generated.items():
                if key=='innovations':
                    for i,item in enumerate(value):
                        item['id']=str(item.get('id') or 'innovation-'+str(i))[:90]
                        if item['id'] in previous_innovations:item['status']=previous_innovations[item['id']]
                if key=='roadmap':
                    for phase in value:
                        for task in phase.get('tasks',[]):
                            if str(task.get('id')) in previous_tasks:task['status']=previous_tasks[str(task.get('id'))]
                sections[key]=value
            # Keep approved innovations in the active requirement plan after
            # regenerating any section, even when the model reissues that list.
            innovations=sections.get('innovations',[])
            requirements=sections.get('requirements',[])
            if isinstance(innovations,list) and isinstance(requirements,list):
                for innovation in innovations:
                    if innovation.get('status')!='accepted':continue
                    derived='innovation-'+str(innovation.get('id',''))
                    if not any(r.get('id')==derived for r in requirements):
                        requirements.append({'id':derived,'title':str(innovation.get('title','Innovation'))[:140],
                            'priority':'should-have','purpose':str(innovation.get('description',''))[:1200],
                            'benefit':str(innovation.get('benefit',''))[:1200],
                            'acceptance_criteria':'Confirm acceptance criteria','source':'accepted_innovation'})
            if len(json.dumps(sections).encode())>250000:raise ValueError('AI project report exceeded storage limits.')
            success=session.execute(update(ProjectAnalysisJob).where(ProjectAnalysisJob.id==job_id,ProjectAnalysisJob.status=='running',ProjectAnalysisJob.lease_until>=int(time.time())).values(status='completed',updated_at=int(time.time()),result_json=json.dumps({'usage':usage,'sections':list(generated)})))
            if not success.rowcount:session.rollback();return
            b.content_json=json.dumps(sections,ensure_ascii=False);b.status='analyzed';b.revision+=1;b.updated_at=int(time.time())
            session.add(ProjectBlueprintVersion(project_id=b.project_id,revision=b.revision,
                snapshot=json.dumps({'idea':b.idea,'domain':b.domain,'constraints':json.loads(b.constraints_json),'sections':sections,'status':b.status},ensure_ascii=False)))
            record(session,job.owner_id,'project.analysis.completed','Project blueprint analyzed',b.project_id)
            session.commit()
    except Exception as exc:
        LOG.warning('project_analysis_failed',extra={'job_id':job_id,'error_type':type(exc).__name__})
        # Do not include traceback, API credentials, or raw provider replies.
        reason=str(exc) if isinstance(exc,ValueError) or exc.__class__.__name__=='AIError' else 'AI analysis failed; any charged credits were refunded.'
        with Session() as session:
            j=session.get(ProjectAnalysisJob,job_id)
            if j and refund(session,j,reason):
                record(session,j.owner_id,'project.analysis.failed',reason[:220],j.project_id,status='failed')
            session.commit()

def sweep():
    with Session() as session:
        t=int(time.time())
        ids=session.scalars(select(ProjectAnalysisJob.id).where(((ProjectAnalysisJob.status=='running')&(ProjectAnalysisJob.lease_until<t))|((ProjectAnalysisJob.status=='queued')&(ProjectAnalysisJob.created_at<t-900))).limit(30)).all()
        for jid in ids:
            j=session.get(ProjectAnalysisJob,jid)
            if j:refund(session,j,'Project analysis timed out; reserved credits were refunded.')
        session.commit()

def tick():
    sweep()
    with Session() as session:
        ids=session.scalars(select(ProjectAnalysisJob.id).where(ProjectAnalysisJob.status=='queued').order_by(ProjectAnalysisJob.created_at).limit(3)).all()
    for jid in ids:process(jid)
