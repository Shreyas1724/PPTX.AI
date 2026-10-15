"""Integration tests for Projects Studio using the app's real cookie auth/DB."""
import os
import pytest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from fastapi import HTTPException
from fastapi.testclient import TestClient
from test_identity import setup,signup
from app import core,project_worker,project_ai,project_routes
from app.project_models import ProjectBlueprint,ProjectAnalysisJob
from sqlalchemy import select,create_engine,func
from sqlalchemy.orm import sessionmaker


def new_idea(client,name='Renewable energy tracker'):
    return client.post('/api/v1/idea-projects',json={'title':name,'idea':'Build a low-cost energy monitor for rural schools that measures electricity use and offers savings recommendations.','domain':'IoT','constraints':{'purpose':'college'}})


def test_create_edit_history_restore_and_archive(setup):
    client,codes=setup;signup(client,codes)
    r=new_idea(client);assert r.status_code==201,r.text
    idea=r.json();pid=idea['id'];assert idea['revision']==0
    listed=client.get('/api/v1/idea-projects').json()['items'];assert len(listed)==1
    assert client.get('/api/v1/projects').json()[0]['id']==pid
    patch=client.patch('/api/v1/idea-projects/'+pid,json={'title':'Energy impact','revision':0})
    assert patch.status_code==200,patch.text;assert patch.json()['revision']==1
    assert client.patch('/api/v1/idea-projects/'+pid,json={'title':'stale','revision':0}).status_code==409
    section=client.patch(f'/api/v1/idea-projects/{pid}/sections/overview',json={'revision':1,'content':{'title':'Monitor','problem_statement':'Unexpected energy use'}})
    assert section.status_code==200,section.text
    assert section.json()['sections']['overview']['title']=='Monitor'
    revisions=client.get(f'/api/v1/idea-projects/{pid}/versions').json()
    assert [r['revision'] for r in revisions]==[2,1,0]
    restored=client.post(f'/api/v1/idea-projects/{pid}/versions/restore',json={'revision':1,'expected_revision':2})
    assert restored.status_code==200;assert restored.json()['revision']==3
    assert restored.json()['sections']=={}
    assert client.patch(f'/api/v1/idea-projects/{pid}',json={'archived':True,'revision':3}).status_code==200
    assert not client.get('/api/v1/idea-projects').json()['items']
    assert client.get('/api/v1/idea-projects?archived=true').json()['items'][0]['id']==pid
    assert client.delete(f'/api/v1/idea-projects/{pid}').json()['ok']


def test_no_ai_provider_no_fake_result_and_owner_isolation(setup,monkeypatch):
    client,codes=setup;signup(client,codes)
    pid=new_idea(client).json()['id']
    monkeypatch.delenv('LLM_API_KEY',raising=False)
    response=client.post(f'/api/v1/idea-projects/{pid}/analysis',json={},headers={'Idempotency-Key':'request-one'})
    assert response.status_code==503 and 'not configured' in response.text
    assert client.get('/api/v1/idea-projects/capabilities').json()['ai_configured']==False
    client.post('/api/v1/auth/logout');signup(client,codes,2)
    assert client.get('/api/v1/idea-projects/'+pid).status_code==404
    assert client.patch(f'/api/v1/idea-projects/{pid}',json={'revision':0,'title':'Stolen'}).status_code==404
    assert client.delete(f'/api/v1/idea-projects/{pid}').status_code==404
    assert not client.get('/api/v1/idea-projects').json()['items']


def test_accept_innovation_and_roadmap_persist(setup):
    client,codes=setup;signup(client,codes);pid=new_idea(client).json()['id']
    edit=client.patch(f'/api/v1/idea-projects/{pid}/sections/innovations',json={'revision':0,'content':[{'id':'idea1','title':'Offline-first capture','benefit':'Rural availability','description':'Support offline data'}]})
    assert edit.status_code==200
    accepted=client.post(f'/api/v1/idea-projects/{pid}/innovations/idea1/decision',json={'status':'accepted','revision':1})
    assert accepted.status_code==200,accepted.text
    assert accepted.json()['sections']['requirements'][0]['id']=='innovation-idea1'
    rejected=client.post(f'/api/v1/idea-projects/{pid}/innovations/idea1/decision',json={'status':'rejected','revision':2})
    assert rejected.status_code==200
    assert rejected.json()['sections']['requirements']==[]
    added=client.post(f'/api/v1/idea-projects/{pid}/innovations',json={'title':'Custom feature','description':'Custom feature description','revision':3})
    assert added.status_code==200 and len(added.json()['sections']['innovations'])==2
    roadmap=client.patch(f'/api/v1/idea-projects/{pid}/sections/roadmap',json={'revision':4,'content':[{'id':'p1','title':'MVP','tasks':[{'id':'task1','title':'Connect sensor','status':'pending'}]}]})
    assert roadmap.status_code==200
    changed=client.patch(f'/api/v1/idea-projects/{pid}/roadmap/tasks/task1',json={'revision':5,'status':'completed'})
    assert changed.status_code==200 and changed.json()['sections']['roadmap'][0]['tasks'][0]['status']=='completed'


def test_async_analysis_fails_and_refunds_without_overwriting(setup,monkeypatch):
    client,codes=setup;signup(client,codes);pid=new_idea(client).json()['id']
    monkeypatch.setenv('LLM_API_KEY','test-provider-key');monkeypatch.setenv('PROJECT_ANALYSIS_COST','3')
    start=client.post(f'/api/v1/idea-projects/{pid}/analysis',json={},headers={'Idempotency-Key':'fakejob1'})
    assert start.status_code==202,start.text
    assert client.post(f'/api/v1/idea-projects/{pid}/analysis',json={},headers={'Idempotency-Key':'fakejob1'}).json()['job_id']==start.json()['job_id']
    assert client.get('/api/v1/credits').json()['balance']==27
    assert client.get('/api/v1/credits').json()['reserved']==3
    assert client.post(f'/api/v1/idea-projects/{pid}/analysis',json={},headers={'Idempotency-Key':'different'}).status_code==409
    def fail(*a,**kw):raise project_ai.AIError('LLM schema invalid')
    monkeypatch.setattr(project_worker,'analyze',fail)
    project_worker.process(start.json()['job_id']);project_worker.process(start.json()['job_id'])
    result=client.get(f'/api/v1/idea-projects/{pid}/analysis/jobs/'+start.json()['job_id']).json()
    assert result['status']=='failed';assert client.get('/api/v1/credits').json()['balance']==30
    assert client.get('/api/v1/credits').json()['reserved']==0
    assert client.get('/api/v1/credits').json()['spent']==0
    assert client.get('/api/v1/idea-projects/'+pid).json()['sections']=={}


def test_analysis_success_and_project_to_presentation_handoff(setup,monkeypatch):
    client,codes=setup;signup(client,codes);pid=new_idea(client).json()['id']
    monkeypatch.setenv('LLM_API_KEY','test-key');monkeypatch.setenv('PROJECT_ANALYSIS_COST','0')
    def generate(*args,**kwargs):return ({'overview':{'title':'Energy monitor','problem_statement':'High electricity bills','objectives':['Reduce waste']},
      'innovations':[{'id':'offline','title':'Offline reports','status':'suggested','description':'Works without Internet'}],
      'requirements':[{'id':'core','title':'Track energy','priority':'must-have'}],
      'roadmap':[{'id':'p1','title':'Prototype','tasks':[{'id':'t1','title':'Connect sensor','status':'pending'}]}],
      'architecture':{'stack':['Python','Microcontroller']},'validation':{'tests':['Power meter accuracy']},
      'analysis':{'mvp':'Basic measurement'},'research':{'state':'not_configured','sources':[]}}, {'model':'test', 'tokens':100})
    monkeypatch.setattr(project_worker,'analyze',generate)
    job=client.post(f'/api/v1/idea-projects/{pid}/analysis',json={},headers={'Idempotency-Key':'good'}).json()['job_id']
    project_worker.process(job)
    blueprint=client.get('/api/v1/idea-projects/'+pid).json();assert blueprint['revision']==1
    assert blueprint['sections']['overview']['title']=='Energy monitor'
    done=client.post(f'/api/v1/idea-projects/{pid}/handoff',json={'format':'college','count':6},headers={'Idempotency-Key':'handoff-1'})
    assert done.status_code==202,done.text
    assert done.json()['cost']==2
    assert client.post(f'/api/v1/idea-projects/{pid}/handoff',json={'format':'college','count':6},headers={'Idempotency-Key':'handoff-1'}).json()['job_id']==done.json()['job_id']
    linked=client.get('/api/v1/idea-projects/'+pid).json()['presentations']
    assert linked and linked[0]['id']==done.json()['presentation_id']
    assert client.delete('/api/v1/idea-projects/'+pid).status_code==409
    # Existing generation queue still owns the job.
    from app import worker
    monkeypatch.delenv('LLM_API_KEY',raising=False)
    worker.process(done.json()['job_id'])
    d=client.get('/api/v1/presentations/'+done.json()['presentation_id']).json()
    assert len(d['slides'])==6
    assert client.get('/api/v1/credits').json()['balance']==28


def test_duplicate_and_cancel_refunds_once(setup,monkeypatch):
    c,codes=setup;signup(c,codes);pid=new_idea(c).json()['id']
    clone=c.post(f'/api/v1/idea-projects/{pid}/duplicate').json()
    assert clone['id']!=pid and clone['idea']==c.get('/api/v1/idea-projects/'+pid).json()['idea']
    assert len(c.get('/api/v1/idea-projects').json()['items'])==2
    monkeypatch.setenv('LLM_API_KEY','configured');monkeypatch.setenv('PROJECT_ANALYSIS_COST','4')
    j=c.post(f'/api/v1/idea-projects/{pid}/analysis',json={},headers={'Idempotency-Key':'cancel-first'}).json()['job_id']
    assert c.get('/api/v1/credits').json()['balance']==26
    cancelled=c.post(f'/api/v1/idea-projects/{pid}/analysis/jobs/{j}/cancel')
    assert cancelled.status_code==200 and cancelled.json()['status']=='cancelled'
    c.post(f'/api/v1/idea-projects/{pid}/analysis/jobs/{j}/cancel')
    project_worker.process(j)
    assert c.get('/api/v1/credits').json()['balance']==30
    assert c.get(f'/api/v1/idea-projects/{pid}/analysis/jobs/{j}').json()['status']=='cancelled'


def test_whitespace_project_text_is_validated_before_saving(setup):
    c,codes=setup;signup(c,codes)
    assert c.post('/api/v1/idea-projects',json={'idea':' '*20}).status_code==422
    pid=new_idea(c).json()['id']
    for changes in ({'title':'   '},{'idea':' '*20}):
        response=c.patch(f'/api/v1/idea-projects/{pid}',json={'revision':0,**changes})
        assert response.status_code==422,response.text
    assert c.get(f'/api/v1/idea-projects/{pid}').json()['revision']==0


@pytest.mark.parametrize('tasks',[None,'invalid',[None],['invalid']])
def test_roadmap_rejects_tasks_that_would_break_updates(setup,tasks):
    c,codes=setup;signup(c,codes);pid=new_idea(c).json()['id']
    response=c.patch(f'/api/v1/idea-projects/{pid}/sections/roadmap',json={
        'revision':0,'content':[{'id':'phase1','tasks':tasks}]})
    assert response.status_code==422,response.text
    assert c.get(f'/api/v1/idea-projects/{pid}').json()['sections']=={}


def test_stale_session_cannot_overwrite_a_committed_project_edit(setup):
    c,codes=setup;user=signup(c,codes).json()['user'];pid=new_idea(c).json()['id']
    with core.Session() as first,core.Session() as second:
        u1=first.get(core.User,user['id']);u2=second.get(core.User,user['id'])
        old_project,old_blueprint=project_routes.owner(pid,u2,second)
        project_routes.update_idea(pid,project_routes.UpdateIdea(revision=0,title='Saved title',domain='Energy'),u1,first)
        with pytest.raises(HTTPException) as error:
            project_routes.update_idea(pid,project_routes.UpdateIdea(revision=0,title='Stale title',domain='Lost update'),u2,second)
        assert error.value.status_code==409
    saved=c.get(f'/api/v1/idea-projects/{pid}').json()
    assert (saved['title'],saved['domain'],saved['revision'])==('Saved title','Energy',1)


def test_analysis_snapshot_restores_the_project_title(setup,monkeypatch):
    c,codes=setup;signup(c,codes);pid=new_idea(c,'Original title').json()['id']
    monkeypatch.setenv('LLM_API_KEY','configured');monkeypatch.setenv('PROJECT_ANALYSIS_COST','3')
    monkeypatch.setattr(project_worker,'analyze',lambda *args:({'overview':{'title':'AI report title'}},{}))
    job=c.post(f'/api/v1/idea-projects/{pid}/analysis',json={},headers={'Idempotency-Key':'snapshot-title'}).json()['job_id']
    project_worker.process(job)
    wallet=c.get('/api/v1/credits').json()
    assert (wallet['balance'],wallet['reserved'],wallet['spent'])==(27,0,3)
    retried=c.post(f'/api/v1/idea-projects/{pid}/analysis',json={},headers={'Idempotency-Key':'snapshot-title'})
    assert retried.status_code==202,retried.text
    assert retried.json()['job_id']==job
    assert retried.json()['status']=='completed'
    assert c.post(f'/api/v1/idea-projects/{pid}/analysis',json={'section':'roadmap'},headers={'Idempotency-Key':'snapshot-title'}).status_code==409
    assert c.patch(f'/api/v1/idea-projects/{pid}',json={'revision':1,'title':'Later title'}).status_code==200
    restored=c.post(f'/api/v1/idea-projects/{pid}/versions/restore',json={'revision':1,'expected_revision':2})
    assert restored.status_code==200,restored.text
    assert restored.json()['title']=='Original title'
    assert c.delete(f'/api/v1/idea-projects/{pid}').status_code==200
    assert c.get('/api/v1/credits').json()['spent']==3


def test_ai_roadmap_nested_structure_is_validated(monkeypatch):
    monkeypatch.setenv('LLM_API_KEY','configured')
    monkeypatch.setattr(project_ai,'brave_search',lambda query:([],'not_configured'))
    monkeypatch.setattr(project_ai,'llm',lambda *args:(project_ai.SingleSection(content=[{'id':'phase','tasks':['broken']}]),{}))
    with pytest.raises(project_ai.AIError):
        project_ai.analyze('A sufficiently detailed project idea',{}, {}, [],'roadmap')


def test_analysis_completion_preserves_an_edit_between_read_and_commit(setup,monkeypatch):
    c,codes=setup;user=signup(c,codes).json()['user'];pid=new_idea(c).json()['id']
    monkeypatch.setenv('LLM_API_KEY','configured');monkeypatch.setenv('PROJECT_ANALYSIS_COST','3')
    monkeypatch.setattr(project_worker,'analyze',lambda *args:({'overview':{'title':'AI output'}},{}))
    job=c.post(f'/api/v1/idea-projects/{pid}/analysis',json={},headers={'Idempotency-Key':'edit-race'}).json()['job_id']
    factory=core.Session;calls=0
    def racing_session():
        nonlocal calls
        calls+=1;session=factory()
        if calls==3:
            original_get=session.get
            def get(model,identifier,*args,**kwargs):
                value=original_get(model,identifier,*args,**kwargs)
                if model is ProjectBlueprint:
                    with factory() as editor:
                        project_routes.update_idea(pid,project_routes.UpdateIdea(revision=0,title='Manual title',domain='Manual domain'),editor.get(core.User,user['id']),editor)
                return value
            session.get=get
        return session
    monkeypatch.setattr(project_worker,'Session',racing_session)
    project_worker.process(job)
    saved=c.get(f'/api/v1/idea-projects/{pid}').json()
    assert (saved['title'],saved['domain'],saved['revision'])==('Manual title','Manual domain',1)
    assert saved['sections']=={}
    assert c.get(f'/api/v1/idea-projects/{pid}/analysis/jobs/{job}').json()['status']=='failed'
    assert c.get('/api/v1/credits').json()['balance']==30


def isolated_project(tmp_path):
    engine=create_engine('sqlite:///'+str(tmp_path/'project-concurrency.db'),connect_args={'timeout':20})
    core.Base.metadata.create_all(engine);sessions=sessionmaker(bind=engine,expire_on_commit=False)
    with sessions() as session:
        user=core.User(email='projects@example.com',password='hash');session.add(user);session.flush()
        project=core.Project(owner_id=user.id,name='Concurrency');session.add(project);session.flush()
        session.add(ProjectBlueprint(project_id=project.id,idea='Build a useful project for schools',content_json='{"overview":{"title":"Project"}}'))
        session.commit();ids=(user.id,project.id)
    return engine,sessions,ids


@pytest.mark.parametrize('same_key',[False,True])
def test_parallel_analysis_requests_queue_and_charge_once(tmp_path,monkeypatch,same_key):
    engine,sessions,(user_id,pid)=isolated_project(tmp_path)
    monkeypatch.setenv('LLM_API_KEY','configured');monkeypatch.setenv('PROJECT_ANALYSIS_COST','3')
    barrier=Barrier(2)
    monkeypatch.setattr(project_routes,'rate_limit',lambda *args:barrier.wait(timeout=10))
    def start(index):
        with sessions() as session:
            try:
                key='same-key' if same_key else 'key-'+str(index)
                return project_routes.start_analysis(pid,project_routes.AnalysisStart(),key,session.get(core.User,user_id),session)
            except HTTPException as exc:return exc.status_code
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(start,range(2)))
        if same_key:assert results[0]['job_id']==results[1]['job_id']
        else:assert sum(result==409 for result in results)==1
        with sessions() as session:
            assert session.get(core.User,user_id).credits==27
            assert session.scalar(select(func.count()).select_from(ProjectAnalysisJob))==1
            assert session.scalar(select(func.count()).select_from(core.CreditEvent))==1
    finally:engine.dispose()


def test_parallel_handoff_retries_create_a_single_deck(tmp_path,monkeypatch):
    engine,sessions,(user_id,pid)=isolated_project(tmp_path)
    original_owner=project_routes.owner;barrier=Barrier(2)
    def synchronized_owner(*args):
        result=original_owner(*args);barrier.wait(timeout=10);return result
    monkeypatch.setattr(project_routes,'owner',synchronized_owner)
    def start(_):
        with sessions() as session:
            return project_routes.handoff(pid,project_routes.Handoff(),'same-handoff',session.get(core.User,user_id),session)
    try:
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(start,range(2)))
        assert results[0]['job_id']==results[1]['job_id']
        assert results[0]['presentation_id']==results[1]['presentation_id']
        with sessions() as session:
            assert session.get(core.User,user_id).credits==28
            assert session.scalar(select(func.count()).select_from(core.Presentation))==1
            assert session.scalar(select(func.count()).select_from(core.Operation))==1
    finally:engine.dispose()


def test_delete_analyzed_project_removes_children_and_preserves_credit_history(setup,monkeypatch):
    c,codes=setup;signup(c,codes);pid=new_idea(c).json()['id']
    uploaded=c.post(f'/api/v1/projects/{pid}/documents',files={'file':('reference.txt',b'Known facts about school energy usage.','text/plain')})
    assert uploaded.status_code==200,uploaded.text
    monkeypatch.setenv('LLM_API_KEY','configured');monkeypatch.setenv('PROJECT_ANALYSIS_COST','3')
    monkeypatch.setattr(project_worker,'analyze',lambda *args:({'overview':{'title':'Energy monitor'}},{}))
    job=c.post(f'/api/v1/idea-projects/{pid}/analysis',json={},headers={'Idempotency-Key':'delete-finished-project'}).json()['job_id']
    project_worker.process(job)
    assert c.get(f'/api/v1/idea-projects/{pid}/analysis/jobs/{job}').json()['status']=='completed'
    deleted=c.delete(f'/api/v1/idea-projects/{pid}')
    assert deleted.status_code==200,deleted.text
    with core.Session() as session:
        assert session.get(core.Project,pid) is None
        assert session.get(ProjectBlueprint,pid) is None
        assert session.get(ProjectAnalysisJob,job) is None
        assert session.get(core.Document,uploaded.json()['id']) is None
        assert session.scalar(select(func.count()).select_from(project_routes.ProjectBlueprintVersion).where(project_routes.ProjectBlueprintVersion.project_id==pid))==0
        assert session.scalar(select(core.CreditEvent).where(core.CreditEvent.key=='project-reserve:'+job)) is not None
    wallet=c.get('/api/v1/credits').json()
    assert (wallet['balance'],wallet['reserved'],wallet['spent'])==(27,0,3)
