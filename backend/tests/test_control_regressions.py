from test_identity import setup, signup
import pytest
from starlette.websockets import WebSocketDisconnect
from app import main


def make_deck(client):
    pid = client.post('/api/v1/projects', json={'name': 'Control regression'}).json()['id']
    return client.post('/api/v1/presentations', json={'project_id': pid, 'title': 'Deck'}).json()['id']


def test_mobile_control_requires_slides(setup):
    client, codes = setup
    signup(client, codes)
    did = make_deck(client)
    response = client.post('/api/v1/presentation-control/sessions', json={'presentation_id': did})
    assert response.status_code == 409


def test_host_updates_slide_count_and_bad_messages_do_not_break_connection(setup):
    client, codes = setup
    signup(client, codes)
    did = make_deck(client)
    slide = {'title': 'Slide', 'body': ['Content']}
    client.post(f'/api/v1/presentations/{did}/slides', json=slide)
    sid = client.post('/api/v1/presentation-control/sessions', json={'presentation_id': did}).json()['session_id']
    with client.websocket_connect(f'/api/v1/presentation-control/ws/{sid}?role=host') as socket:
        assert socket.receive_json()['type'] == 'SESSION_STATE'
        assert socket.receive_json()['type'] == 'HOST_CONNECTED'
        socket.send_json([])
        assert socket.receive_json()['type'] == 'ERROR'
        socket.send_json({'type': 'HOST_STATE', 'slide_index': 'invalid'})
        assert socket.receive_json()['type'] == 'ERROR'
        socket.send_json({'type': 'COMMAND_RESULT', 'request_id': {}})
        assert socket.receive_json()['type'] == 'ERROR'
        client.post(f'/api/v1/presentations/{did}/slides', json=slide)
        socket.send_json({'type': 'HOST_STATE', 'slide_index': 1})
        state = socket.receive_json()
        assert state['type'] == 'SLIDE_STATE_CHANGED'
        assert state['slide_index'] == 1
        assert state['total_slides'] == 2
        saved = client.get(f'/api/v1/presentation-control/sessions/{sid}').json()
        assert saved['current_slide_index'] == 1
        assert saved['total_slides'] == 2


def test_end_closes_live_socket_before_deck_deletion(setup):
    client, codes = setup
    signup(client, codes)
    did = make_deck(client)
    client.post(f'/api/v1/presentations/{did}/slides', json={'title': 'Slide'})
    sid = client.post('/api/v1/presentation-control/sessions', json={'presentation_id': did}).json()['session_id']
    with client.websocket_connect(f'/api/v1/presentation-control/ws/{sid}?role=host') as socket:
        socket.receive_json()
        socket.receive_json()
        assert client.post(f'/api/v1/presentation-control/sessions/{sid}/end').status_code == 200
        assert socket.receive_json()['type'] == 'SESSION_ENDED'
        with pytest.raises(WebSocketDisconnect):
            socket.receive_json()
        assert client.delete('/api/v1/presentations/' + did).status_code == 200


def test_revocation_closes_controller_socket(setup):
    client, codes = setup
    signup(client, codes)
    did = make_deck(client)
    client.post(f'/api/v1/presentations/{did}/slides', json={'title': 'Slide'})
    control = client.post('/api/v1/presentation-control/sessions', json={'presentation_id': did}).json()
    sid = control['session_id']
    pair = client.post('/api/v1/presentation-control/pairing/exchange', json={
        'token': control['pairing_url'].split('invite=', 1)[1],
    }).json()
    with client.websocket_connect(f"/api/v1/presentation-control/ws/{sid}?token={pair['controller_token']}") as socket:
        socket.receive_json()
        assert client.post(f"/api/v1/presentation-control/sessions/{sid}/revoke/{pair['device_id']}").status_code == 200
        with pytest.raises(WebSocketDisconnect) as error:
            socket.receive_json()
        assert error.value.code == 4403


def test_activity_failure_does_not_mask_committed_mutation(setup, monkeypatch):
    client, codes = setup
    signup(client, codes)
    def unavailable(*args, **kwargs):
        raise RuntimeError('Journal unavailable')
    monkeypatch.setattr(main, 'record', unavailable)
    result = client.post('/api/v1/projects', json={'name': 'Saved successfully'})
    assert result.status_code == 200
    assert client.get('/api/v1/projects').json()[0]['name'] == 'Saved successfully'
