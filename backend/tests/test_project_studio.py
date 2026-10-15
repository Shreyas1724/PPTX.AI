"""Integration tests for Projects Studio using the app's real cookie auth/DB."""
import os
from fastapi.testclient import TestClient
from test_identity import setup,signup
from app import core,project_worker,project_ai
from sqlalchemy import select


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
    assert client.post(f'/api/v1/idea-projects/{pid}/analysis',json={},headers={'Idempotency-Key':'different'}).status_code==409
    def fail(*a,**kw):raise project_ai.AIError('LLM schema invalid')
    monkeypatch.setattr(project_worker,'analyze',fail)
    project_worker.process(start.json()['job_id']);project_worker.process(start.json()['job_id'])
    result=client.get(f'/api/v1/idea-projects/{pid}/analysis/jobs/'+start.json()['job_id']).json()
    assert result['status']=='failed';assert client.get('/api/v1/credits').json()['balance']==30
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
