"""The operator CLI creates ordinary local identities without weakening auth."""
import io
import pytest
from sqlalchemy import func, select
from app import core, manage
from test_identity import setup


def test_demo_account_uses_real_login_and_balanced_ledger(setup):
 client,_=setup
 password='local-test-password-2026'
 with core.Session() as session:
  user=manage.create_demo_user(session,email=' DEMO@PPTX.TEST ',password=password)
  assert user.password!=password and core.check_password(password,user.password)
  profile=session.get(core.Profile,user.id)
  assert not profile.email_verified and not profile.phone_verified
  assert not manage.audit(session)
  assert session.scalar(select(core.Activity).where(core.Activity.user_id==user.id)).action=='account.created'
 assert client.post('/api/v1/auth/login',json={'email':'demo@pptx.test','password':'incorrect'}).status_code==401
 response=client.post('/api/v1/auth/login',json={'email':'demo@pptx.test','password':password})
 assert response.status_code==200,response.text
 assert 'HttpOnly' in response.headers['set-cookie']
 assert response.json()['user']['credits']==30
 assert client.get('/api/v1/auth/me').json()['email']=='demo@pptx.test'


def test_duplicate_demo_never_resets_password_or_credits(setup):
 with core.Session() as session:
  user=manage.create_demo_user(session,email='demo@pptx.test',password='original-password-2026',credits=12)
  with pytest.raises(ValueError,match='already exists'):
   manage.create_demo_user(session,email='demo@pptx.test',password='replacement-password-2026',credits=99)
  session.refresh(user)
  assert user.credits==12 and core.check_password('original-password-2026',user.password)
  assert session.scalar(select(func.count()).select_from(core.CreditEvent))==1
  assert not manage.audit(session)


@pytest.mark.parametrize('environment',['production','PRODUCTION','staging'])
def test_demo_rejects_nonlocal_environments_before_writes(setup,monkeypatch,environment):
 monkeypatch.setenv('APP_ENV',environment)
 with core.Session() as session:
  with pytest.raises(ValueError,match='restricted'):
   manage.create_demo_user(session,email='demo@pptx.test',password='local-password-2026')
  assert session.scalar(select(func.count()).select_from(core.User))==0


def test_demo_rejects_server_database_before_writes(monkeypatch):
 class Dialect:name='postgresql'
 class Engine:dialect=Dialect()
 class ServerSession:
  def get_bind(self):return Engine()
 monkeypatch.setenv('APP_ENV','development')
 with pytest.raises(ValueError,match='restricted'):
  manage.create_demo_user(ServerSession(),email='demo@pptx.test',password='local-password-2026')


def test_cli_generates_password_once_and_duplicate_does_not_disclose_one(setup,monkeypatch,capsys):
 generated='generated-local-password-2026'
 monkeypatch.setattr(manage.secrets,'token_urlsafe',lambda _:generated)
 monkeypatch.setattr('sys.argv',['manage','create-demo-user'])
 manage.main()
 assert 'Password (shown once): '+generated in capsys.readouterr().out
 with pytest.raises(SystemExit,match='already exists'):manage.main()
 assert generated not in capsys.readouterr().out


def test_cli_stdin_password_is_never_printed_or_in_validation_errors(setup,monkeypatch,capsys):
 monkeypatch.setattr('sys.argv',['manage','create-demo-user','--password-stdin'])
 monkeypatch.setattr('sys.stdin',io.StringIO('local-stdin-password-2026\n'))
 manage.main()
 assert 'local-stdin-password-2026' not in capsys.readouterr().out
 with core.Session() as session:
  user=session.scalar(select(core.User).where(core.User.email=='demo@pptx.test'))
  assert core.check_password('local-stdin-password-2026',user.password)
  with pytest.raises(ValueError) as error:
   manage.create_demo_user(session,email='other@pptx.test',password='short')
  assert 'short' not in str(error.value)


def test_demo_rejects_real_email_address(setup):
 with core.Session() as session:
  with pytest.raises(ValueError,match='reserved .test'):
   manage.create_demo_user(session,email='real@example.com',password='local-password-2026')
  assert session.scalar(select(func.count()).select_from(core.User))==0
