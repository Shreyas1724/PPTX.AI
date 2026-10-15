"""Project Studio APIs. All project IDs are checked against authenticated ownership."""
import os, json, time, hashlib
from fastapi import APIRouter, Depends, HTTPException, Header, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select, update, delete, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .auth import current,db, limit as rate_limit
from .core import Project, Presentation, Document, User, CreditEvent, Job, uid
from .project_models import ProjectBlueprint, ProjectBlueprintVersion, ProjectAnalysisJob
from .project_ai import REQUIRED_SECTIONS, validate_section
from . import credits

router=APIRouter(prefix='/api/v1/idea-projects', tags=['Projects Studio'])


def clock():return int(time.time())
def jloads(value):return json.loads(value or '{}')

def owner(pid,user,session):
    p=session.get(Project,pid)
    if p is None or p.owner_id!=user.id:raise HTTPException(404,'Project not found')
    b=session.get(ProjectBlueprint,pid)
    if b is None:raise HTTPException(404,'Project blueprint not found')
    return p,b

def serialized(p,b):
    return {'id':p.id,'title':p.name,'idea':b.idea,'domain':b.domain,
            'constraints':jloads(b.constraints_json),'sections':jloads(b.content_json),
            'status':b.status,'archived':b.archived,'revision':b.revision,
            'created_at':b.created_at,'updated_at':b.updated_at}

def snapshot(session,b):
    session.add(ProjectBlueprintVersion(project_id=b.project_id,revision=b.revision,
        snapshot=json.dumps({'idea':b.idea,'domain':b.domain,'constraints':jloads(b.constraints_json),
                             'sections':jloads(b.content_json),'status':b.status,'title':session.get(Project,b.project_id).name},ensure_ascii=False)))

def bump(session,b):
    revision=b.revision;updated_at=clock()
    # Claim the revision before ORM autoflush can write any pending edits.
    with session.no_autoflush:
        changed=session.execute(update(ProjectBlueprint).where(
            ProjectBlueprint.project_id==b.project_id,ProjectBlueprint.revision==revision
        ).values(revision=revision+1,updated_at=updated_at),execution_options={'synchronize_session':False})
    if not changed.rowcount:
        session.rollback();raise HTTPException(409,'Project changed elsewhere; reload before saving.')
    b.revision=revision+1;b.updated_at=updated_at;snapshot(session,b)

def lock_blueprint(session,b):
    # A no-op write also serializes requests on SQLite, where FOR UPDATE is ignored.
    changed=session.execute(update(ProjectBlueprint).where(ProjectBlueprint.project_id==b.project_id)
        .values(revision=ProjectBlueprint.revision),execution_options={'synchronize_session':False})
    if not changed.rowcount:
        session.rollback();raise HTTPException(404,'Project blueprint not found')
    session.refresh(b)

def valid_size(value):
    if len(json.dumps(value,ensure_ascii=False).encode())>115000:
        raise HTTPException(413,'Project section exceeds the supported size.')

class CreateIdea(BaseModel):
    title:str=Field(default='',max_length=120)
    idea:str=Field(min_length=12,max_length=7000)
    domain:str=Field(default='',max_length=120)
    constraints:dict=Field(default_factory=dict)
    @field_validator('title','idea','domain',mode='before')
    @classmethod
    def stripped_text(cls,value):return value.strip() if isinstance(value,str) else value
class UpdateIdea(BaseModel):
    title:str|None=Field(default=None,min_length=1,max_length=120)
    idea:str|None=Field(default=None,min_length=12,max_length=7000)
    domain:str|None=Field(default=None,max_length=120)
    constraints:dict|None=None
    archived:bool|None=None
    revision:int=Field(ge=0)
    @field_validator('title','idea','domain',mode='before')
    @classmethod
    def stripped_text(cls,value):return value.strip() if isinstance(value,str) else value
class SectionEdit(BaseModel):
    content:dict|list=Field()
    revision:int=Field(ge=0)
class InnovationAction(BaseModel):
    status:str=Field(pattern='^(accepted|rejected|saved|suggested)$')
    revision:int=Field(ge=0)
class CustomInnovation(BaseModel):
    title:str=Field(min_length=3,max_length=140)
    description:str=Field(min_length=5,max_length=1500)
    revision:int=Field(ge=0)
class TaskAction(BaseModel):
    status:str=Field(pattern='^(pending|in_progress|completed|blocked)$')
    revision:int=Field(ge=0)
class RestoreVersion(BaseModel):
    revision:int=Field(ge=0)
    expected_revision:int=Field(ge=0)
class Handoff(BaseModel):
    format:str=Field(default='full',pattern='^(full|pitch|college|hackathon|architecture|research|investor|custom)$')
    sections:list[str]=Field(default_factory=list,max_length=9)
    count:int=Field(default=8,ge=1,le=20)
    theme:str=Field(default='midnight',pattern='^(midnight|light|aurora)$')
class AnalysisStart(BaseModel):
    section:str|None=None

@router.get('/capabilities')
def capabilities(user:User=Depends(current)):
    return {'ai_configured':bool(os.getenv('LLM_API_KEY')),
            'research_configured':bool(os.getenv('PROJECT_RESEARCH_BRAVE_API_KEY')),
            'analysis_cost':max(0,int(os.getenv('PROJECT_ANALYSIS_COST','0'))),
            'mode':'configured' if os.getenv('LLM_API_KEY') else 'configuration_required'}

@router.get('')
def list_ideas(search:str='',archived:bool=False,limit:int=Query(default=30,ge=1,le=100),
               offset:int=Query(default=0,ge=0),user:User=Depends(current),session:Session=Depends(db)):
    query=select(Project,ProjectBlueprint).join(ProjectBlueprint,Project.id==ProjectBlueprint.project_id).where(Project.owner_id==user.id,ProjectBlueprint.archived==archived)
    if search.strip():query=query.where(func.lower(Project.name).like('%'+search[:100].lower().replace('%','\\%').replace('_','\\_')+'%',escape='\\'))
    rows=session.execute(query.order_by(ProjectBlueprint.updated_at.desc()).offset(offset).limit(limit+1)).all()
    return {'items':[serialized(p,b) for p,b in rows[:limit]],'has_more':len(rows)>limit}

@router.post('',status_code=201)
def create_idea(data:CreateIdea,user:User=Depends(current),session:Session=Depends(db)):
    valid_size(data.constraints)
    p=Project(owner_id=user.id,name=(data.title.strip() or data.idea.strip().splitlines()[0][:120]))
    session.add(p);session.flush()
    b=ProjectBlueprint(project_id=p.id,idea=data.idea.strip(),domain=data.domain.strip(),
                       constraints_json=json.dumps(data.constraints),content_json='{}',status='draft',revision=0,archived=False,created_at=clock(),updated_at=clock())
    session.add(b);snapshot(session,b);session.commit()
    return serialized(p,b)

@router.get('/{pid}')
def get_idea(pid:str,user:User=Depends(current),session:Session=Depends(db)):
    p,b=owner(pid,user,session)
    answer=serialized(p,b)
    answer['presentations']=[{'id':d.id,'title':d.title,'version':d.version} for d in session.scalars(select(Presentation).where(Presentation.project_id==pid))]
    return answer

@router.post('/{pid}/duplicate',status_code=201)
def duplicate_idea(pid:str,user:User=Depends(current),session:Session=Depends(db)):
    p,b=owner(pid,user,session)
    new=Project(owner_id=user.id,name=(p.name[:110]+' (copy)')[:120])
    session.add(new);session.flush()
    clone=ProjectBlueprint(project_id=new.id,idea=b.idea,domain=b.domain,
        constraints_json=b.constraints_json,content_json=b.content_json,status='edited',revision=0,
        archived=False,created_at=clock(),updated_at=clock())
    session.add(clone);snapshot(session,clone);session.commit()
    return serialized(new,clone)

@router.patch('/{pid}')
def update_idea(pid:str,data:UpdateIdea,user:User=Depends(current),session:Session=Depends(db)):
    p,b=owner(pid,user,session)
    if data.revision!=b.revision:raise HTTPException(409,'Project changed elsewhere; reload before saving.')
    if data.title is not None:p.name=data.title.strip()
    if data.idea is not None:b.idea=data.idea.strip()
    if data.domain is not None:b.domain=data.domain.strip()
    if data.constraints is not None:valid_size(data.constraints);b.constraints_json=json.dumps(data.constraints)
    if data.archived is not None:b.archived=data.archived
    bump(session,b);session.commit();return serialized(p,b)

@router.delete('/{pid}')
def delete_idea(pid:str,user:User=Depends(current),session:Session=Depends(db)):
    p,b=owner(pid,user,session)
    lock_blueprint(session,b)
    if session.scalar(select(Presentation.id).where(Presentation.project_id==pid).limit(1)):
        raise HTTPException(409,'This project has presentations. Archive it instead to preserve your decks.')
    if session.scalar(select(ProjectAnalysisJob.id).where(ProjectAnalysisJob.project_id==pid,ProjectAnalysisJob.status.in_(['queued','running'])).limit(1)):
        raise HTTPException(409,'Wait for the active analysis to finish.')
    # These models have no ORM relationships: execute child removals before
    # deleting either parent so foreign-key checks succeed on PostgreSQL.
    for model in (ProjectAnalysisJob,ProjectBlueprintVersion,Document):
        session.execute(delete(model).where(model.project_id==pid))
    session.execute(delete(ProjectBlueprint).where(ProjectBlueprint.project_id==pid))
    session.execute(delete(Project).where(Project.id==pid))
    session.commit();return {'ok':True}

@router.patch('/{pid}/sections/{section}')
def update_section(pid:str,section:str,data:SectionEdit,user:User=Depends(current),session:Session=Depends(db)):
    if section not in (*REQUIRED_SECTIONS,'research'):raise HTTPException(404,'Unknown section')
    p,b=owner(pid,user,session)
    if data.revision!=b.revision:raise HTTPException(409,'Reload this project; another change was saved.')
    valid_size(data.content)
    try:validate_section(section,data.content)
    except ValueError as exc:raise HTTPException(422,str(exc)) from exc
    sections=jloads(b.content_json);sections[section]=data.content
    b.content_json=json.dumps(sections,ensure_ascii=False);b.status='edited'
    bump(session,b);session.commit();return serialized(p,b)

@router.post('/{pid}/innovations')
def add_innovation(pid:str,data:CustomInnovation,user:User=Depends(current),session:Session=Depends(db)):
    p,b=owner(pid,user,session)
    if data.revision!=b.revision:raise HTTPException(409,'Reload before modifying innovations.')
    sections=jloads(b.content_json);items=sections.setdefault('innovations',[])
    if not isinstance(items,list):raise HTTPException(409,'Innovation section has an invalid structure.')
    items.append({'id':uid(),'title':data.title,'description':data.description,'status':'suggested','category':'custom','source':'user'})
    b.content_json=json.dumps(sections);b.status='edited';bump(session,b);session.commit();return serialized(p,b)

@router.post('/{pid}/innovations/{iid}/decision')
def decision(pid:str,iid:str,data:InnovationAction,user:User=Depends(current),session:Session=Depends(db)):
    p,b=owner(pid,user,session)
    if data.revision!=b.revision:raise HTTPException(409,'Reload before modifying innovations.')
    sections=jloads(b.content_json)
    target=next((v for v in sections.get('innovations',[]) if str(v.get('id'))==iid),None)
    if target is None:raise HTTPException(404,'Innovation not found')
    target['status']=data.status
    requirements=sections.setdefault('requirements',[])
    if isinstance(requirements,list):
        derived='innovation-'+iid
        requirements[:]=[x for x in requirements if x.get('id')!=derived]
        if data.status=='accepted':
            requirements.append({'id':derived,'title':str(target.get('title','Innovation'))[:140],
              'priority':'should-have','purpose':str(target.get('description',''))[:1200],
              'benefit':str(target.get('benefit',''))[:1200],
              'acceptance_criteria':'Define acceptance criteria before implementation',
              'source':'accepted_innovation'})
    b.content_json=json.dumps(sections);b.status='edited';bump(session,b);session.commit();return serialized(p,b)

@router.patch('/{pid}/roadmap/tasks/{tid}')
def task_status(pid:str,tid:str,data:TaskAction,user:User=Depends(current),session:Session=Depends(db)):
    p,b=owner(pid,user,session)
    if data.revision!=b.revision:raise HTTPException(409,'Reload before updating tasks.')
    sections=jloads(b.content_json);found=False
    for phase in sections.get('roadmap',[]):
        for task in phase.get('tasks',[]):
            if str(task.get('id'))==tid:
                task['status']=data.status;found=True;break
    if not found:raise HTTPException(404,'Task not found')
    b.content_json=json.dumps(sections);b.status='edited';bump(session,b);session.commit();return serialized(p,b)

@router.get('/{pid}/versions')
def versions(pid:str,user:User=Depends(current),session:Session=Depends(db)):
    owner(pid,user,session)
    return [{'revision':r.revision,'created_at':r.created_at} for r in session.scalars(select(ProjectBlueprintVersion).where(ProjectBlueprintVersion.project_id==pid).order_by(ProjectBlueprintVersion.revision.desc()).limit(50))]

@router.post('/{pid}/versions/restore')
def restore_version(pid:str,data:RestoreVersion,user:User=Depends(current),session:Session=Depends(db)):
    p,b=owner(pid,user,session)
    if data.expected_revision!=b.revision:raise HTTPException(409,'Reload before restoring a previous version.')
    v=session.scalar(select(ProjectBlueprintVersion).where(ProjectBlueprintVersion.project_id==pid,ProjectBlueprintVersion.revision==data.revision))
    if not v:raise HTTPException(404,'Revision not found')
    restored=jloads(v.snapshot)
    p.name=str(restored.get('title',restored.get('sections',{}).get('overview',{}).get('title',p.name)))[:120] or p.name
    b.idea=restored['idea'];b.domain=restored['domain']
    b.constraints_json=json.dumps(restored['constraints']);b.content_json=json.dumps(restored['sections'])
    b.status='edited';bump(session,b);session.commit();return serialized(p,b)

@router.post('/{pid}/analysis',status_code=202)
def start_analysis(pid:str,data:AnalysisStart,idempotency_key:str=Header(...,min_length=1,max_length=128),user:User=Depends(current),session:Session=Depends(db)):
    p,b=owner(pid,user,session)
    if b.archived:raise HTTPException(409,'Unarchive this project before running analysis.')
    section=data.section
    if section is not None and section not in REQUIRED_SECTIONS:raise HTTPException(422,'Unknown analysis section')
    old=session.scalar(select(ProjectAnalysisJob).where(ProjectAnalysisJob.owner_id==user.id,ProjectAnalysisJob.request_key==idempotency_key))
    if old:
        if old.project_id!=pid or old.section!=section:raise HTTPException(409,'Idempotency key already used for another request.')
        return {'job_id':old.id,'status':old.status,'cost':old.cost}
    if not os.getenv('LLM_API_KEY'):raise HTTPException(503,'Project AI is not configured. Add LLM_API_KEY to enable genuine analysis.')
    rate_limit(session,'projects_analysis:'+user.id,12,3600)
    lock_blueprint(session,b)
    if b.archived:raise HTTPException(409,'Unarchive this project before running analysis.')
    fingerprint=hashlib.sha256(json.dumps({'pid':pid,'revision':b.revision,'section':section},sort_keys=True).encode()).hexdigest()
    # Recheck after acquiring the project lock: another request may have queued
    # the same operation while the rate-limit transaction was being committed.
    old=session.scalar(select(ProjectAnalysisJob).where(ProjectAnalysisJob.owner_id==user.id,ProjectAnalysisJob.request_key==idempotency_key))
    if old:
        if old.project_id!=pid or old.section!=section:raise HTTPException(409,'Idempotency key already used for another request.')
        return {'job_id':old.id,'status':old.status,'cost':old.cost}
    if session.scalar(select(ProjectAnalysisJob.id).where(ProjectAnalysisJob.project_id==pid,ProjectAnalysisJob.status.in_(['queued','running'])).limit(1)):
        raise HTTPException(409,'This project already has a running analysis.')
    cost=max(0,int(os.getenv('PROJECT_ANALYSIS_COST','0')))
    if cost:
        changed=session.execute(update(User).where(User.id==user.id,User.credits>=cost).values(credits=User.credits-cost))
        if not changed.rowcount:session.rollback();raise HTTPException(402,'Insufficient credits for project analysis.')
    job=ProjectAnalysisJob(project_id=pid,owner_id=user.id,request_key=idempotency_key,
        fingerprint=fingerprint,mode='section' if section else 'all',section=section,
        base_revision=b.revision,cost=cost)
    try:
        session.add(job);session.flush()
        if cost:session.add(CreditEvent(user_id=user.id,amount=-cost,reason='project_analysis:reserve',key='project-reserve:'+job.id))
        session.commit()
    except IntegrityError:
        session.rollback()
        duplicate=session.scalar(select(ProjectAnalysisJob).where(ProjectAnalysisJob.owner_id==user.id,ProjectAnalysisJob.request_key==idempotency_key))
        if duplicate and duplicate.project_id==pid and duplicate.section==section:return {'job_id':duplicate.id,'status':duplicate.status,'cost':duplicate.cost}
        raise HTTPException(409,'Concurrent analysis request. Refresh and try again.')
    return {'job_id':job.id,'status':job.status,'cost':job.cost}

@router.post('/{pid}/analysis/jobs/{jid}/cancel')
def cancel_job(pid:str,jid:str,user:User=Depends(current),session:Session=Depends(db)):
    owner(pid,user,session)
    j=session.get(ProjectAnalysisJob,jid)
    if not j or j.project_id!=pid or j.owner_id!=user.id:raise HTTPException(404,'Analysis job not found')
    changed=session.execute(update(ProjectAnalysisJob).where(ProjectAnalysisJob.id==j.id,ProjectAnalysisJob.status.in_(['queued','running'])).values(
        status='cancelled',error='Cancelled by the user; any charged credits were refunded.',updated_at=clock()))
    if changed.rowcount and j.cost:
        session.execute(update(User).where(User.id==j.owner_id).values(credits=User.credits+j.cost))
        session.add(CreditEvent(user_id=j.owner_id,amount=j.cost,reason='project_analysis:refund',key='project-refund:'+j.id))
    session.commit()
    return {'job_id':j.id,'status':'cancelled' if changed.rowcount else j.status}

@router.get('/{pid}/analysis/jobs/{jid}')
def get_job(pid:str,jid:str,user:User=Depends(current),session:Session=Depends(db)):
    owner(pid,user,session);job=session.get(ProjectAnalysisJob,jid)
    if not job or job.project_id!=pid or job.owner_id!=user.id:raise HTTPException(404,'Analysis job not found')
    return {'id':job.id,'status':job.status,'section':job.section,'cost':job.cost,
            'error':job.error,'result':jloads(job.result_json),'updated_at':job.updated_at}

@router.post('/{pid}/handoff',status_code=202)
def handoff(pid:str,data:Handoff,idempotency_key:str=Header(...,min_length=1,max_length=128),user:User=Depends(current),session:Session=Depends(db)):
    p,b=owner(pid,user,session)
    lock_blueprint(session,b)
    if b.archived:raise HTTPException(409,'Unarchive before generating a presentation.')
    sections=jloads(b.content_json)
    if not sections.get('overview'):raise HTTPException(409,'Analyze or manually fill the project overview before generating slides.')
    choices=data.sections or ['overview','analysis','requirements','innovations','architecture','roadmap','validation','research']
    if any(x not in (*REQUIRED_SECTIONS,'research') for x in choices):raise HTTPException(422,'Unknown blueprint section')
    # Existing credit reservation, worker, presentation rendering and versioning.
    from .core import Operation
    content={name:sections[name] for name in choices if name in sections}
    if not content:raise HTTPException(409,'Selected blueprint sections are empty.')
    # Distribute the existing 4k-character generation input budget across the
    # selected sections rather than truncating away the roadmap and validation.
    per_section=max(180, min(2600, 3300//len(content)))
    fragments=[f'{name.upper()}: '+json.dumps(value,ensure_ascii=False)[:per_section] for name,value in content.items()]
    prompt=('Create a '+data.format+' PPT about '+p.name+'. Use ONLY the approved facts; '
            'disclose uncertainty and do not invent research citations.\n'+'\n'.join(fragments))[:4000]
    payload={'prompt':prompt,'count':data.count,'origin_project_id':pid,'origin_revision':b.revision,
             'format':data.format,'theme':data.theme}
    old=session.scalar(select(Operation).where(Operation.user_id==user.id,Operation.request_key==idempotency_key))
    if old:
        j=session.get(Job,old.job_id)
        old_deck=session.get(Presentation,j.presentation_id) if j else None
        if old.kind!='generation' or not old_deck or old_deck.project_id!=pid or json.loads(old.payload)!=payload:
            raise HTTPException(409,'Idempotency key already used for a different generation request.')
        return {'presentation_id':old_deck.id,'job_id':old.job_id,'status':'existing','cost':old.cost}
    deck=Presentation(project_id=pid,title=p.name[:120],theme=data.theme)
    session.add(deck);session.flush()
    try:
        op=credits.reserve(session,user.id,deck,'generation',payload,idempotency_key)
    except Exception:
        session.rollback();raise
    return {'presentation_id':deck.id,'job_id':op.job_id,'status':'queued','cost':op.cost}
