"""SQLite must preserve edits and one-time pairing across competing requests."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker

from app import control, core, main
from test_identity import setup, signup


def test_stale_deck_edit_returns_conflict_and_preserves_first_edit(setup):
    client, codes = setup
    user_id = signup(client, codes).json()['user']['id']
    pid = client.post('/api/v1/projects', json={'name': 'Concurrency'}).json()['id']
    did = client.post('/api/v1/presentations', json={'project_id': pid, 'title': 'Original'}).json()['id']
    with core.Session() as first, core.Session() as second:
        user = second.get(core.User, user_id)
        stale = main.owned_deck(did, user, second)
        saved = main.update_deck(did, main.DeckUpdate(title='Saved title', theme='light'), first.get(core.User, user_id), first)
        assert saved['version'] == 1
        with pytest.raises(HTTPException) as error:
            main.update_deck(did, main.DeckUpdate(title='Stale title', theme='aurora'), user, second)
        assert error.value.status_code == 409
    deck = client.get('/api/v1/presentations/' + did).json()
    assert (deck['title'], deck['theme'], deck['version']) == ('Saved title', 'light', 1)
    assert len(client.get(f'/api/v1/presentations/{did}/versions').json()) == 1


def test_concurrent_pairing_invitation_can_only_create_one_controller(tmp_path):
    engine = create_engine('sqlite:///' + str(tmp_path / 'pairing.db'), connect_args={'timeout': 20})
    core.Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    token = 'pc_' + 'a' * 40
    with sessions() as session:
        user = core.User(email='pairing@example.com', password='unused')
        session.add(user); session.flush()
        project = core.Project(owner_id=user.id, name='Pairing')
        session.add(project); session.flush()
        deck = core.Presentation(project_id=project.id, title='Pairing')
        session.add(deck); session.flush()
        row = core.ControlSession(presentation_id=deck.id, owner_user_id=user.id,
                                  total_slides=1, expires_at=control.ts() + 300)
        session.add(row); session.flush()
        session.add(core.PairingInvitation(session_id=row.id, token_hash=control.digest(token), expires_at=control.ts() + 120))
        session.commit()

    barrier = Barrier(2)

    def pair(index):
        with sessions() as session:
            original_scalar = session.scalar

            def synchronized_scalar(statement, *args, **kwargs):
                result = original_scalar(statement, *args, **kwargs)
                if isinstance(result, core.PairingInvitation):
                    barrier.wait(timeout=10)
                return result

            session.scalar = synchronized_scalar
            try:
                return control.exchange(control.Pairing(token=token, device_label=f'Phone {index}'), session)
            except HTTPException as error:
                return error.status_code

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(pair, range(2)))
        assert sum(isinstance(result, dict) for result in results) == 1
        assert results.count(410) == 1
        with sessions() as session:
            assert session.scalar(select(func.count()).select_from(core.ControllerDevice)) == 1
    finally:
        engine.dispose()
