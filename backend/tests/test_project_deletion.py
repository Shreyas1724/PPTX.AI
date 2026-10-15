from test_identity import setup, signup
from app import core
from sqlalchemy import select, text


def test_legacy_delete_keeps_blueprint_and_history(setup):
    client, codes = setup
    signup(client, codes)
    project = client.post('/api/v1/idea-projects', json={
        'title': 'Energy monitor',
        'idea': 'Measure electricity consumption in rural classrooms.',
    }).json()
    pid = project['id']
    response = client.delete('/api/v1/projects/' + pid)
    assert response.status_code == 409
    assert client.get('/api/v1/idea-projects/' + pid).status_code == 200
    assert client.get(f'/api/v1/idea-projects/{pid}/versions').json()[0]['revision'] == 0
    assert client.delete('/api/v1/idea-projects/' + pid).status_code == 200


def test_legacy_delete_still_removes_plain_workspace(setup):
    client, codes = setup
    signup(client, codes)
    pid = client.post('/api/v1/projects', json={'name': 'Workspace'}).json()['id']
    assert client.delete('/api/v1/projects/' + pid).status_code == 200
    assert client.get('/api/v1/projects').json() == []


def test_delete_paired_deck_requires_end_and_removes_control_records(setup):
    client, codes = setup
    with core.Session() as session:
        session.execute(text('PRAGMA foreign_keys=ON'))
    signup(client, codes)
    pid = client.post('/api/v1/projects', json={'name': 'Workspace'}).json()['id']
    did = client.post('/api/v1/presentations', json={'project_id': pid, 'title': 'Deck'}).json()['id']
    client.post(f'/api/v1/presentations/{did}/slides', json={'title': 'Slide', 'body': ['One']})
    control = client.post('/api/v1/presentation-control/sessions', json={'presentation_id': did}).json()
    sid = control['session_id']
    invitation = control['pairing_url'].split('invite=', 1)[1]
    pairing = client.post('/api/v1/presentation-control/pairing/exchange', json={'token': invitation}).json()
    client.post('/api/v1/presentation-control/controllers/' + pairing['controller_token'] + '/command',
                json={'request_id': 'audit-command-123', 'command': 'SLIDE_NEXT'})
    assert client.delete('/api/v1/presentations/' + did).status_code == 409
    assert client.post(f'/api/v1/presentation-control/sessions/{sid}/end').status_code == 200
    assert client.delete('/api/v1/presentations/' + did).status_code == 200
    with core.Session() as session:
        for model in (core.ControlSession, core.ControlCommand, core.ControllerDevice,
                      core.PairingInvitation, core.ControlAuditEvent):
            column = model.id if model is core.ControlSession else model.session_id
            assert session.scalar(select(model).where(column == sid)) is None
