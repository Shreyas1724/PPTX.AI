"""Re-runnable additive Projects Studio migration.

Usage (backup the database first):
    cd backend && python -m app.migrations.projects_20261015

Never drops or alters existing project, deck, credit or authentication tables.
This is intentionally a forward-only migration: roll back the application code,
not the user-owned project data. Tables may be removed only with a separately
reviewed backup-and-data-retention procedure.
"""
from ..core import Base, ENGINE
from ..project_models import ProjectBlueprint, ProjectBlueprintVersion, ProjectAnalysisJob

TABLES = [ProjectBlueprint.__table__, ProjectBlueprintVersion.__table__, ProjectAnalysisJob.__table__]

def upgrade(connection=None):
    if connection is None:
        with ENGINE.begin() as connection:
            Base.metadata.create_all(bind=connection,tables=TABLES,checkfirst=True)
    else:
        Base.metadata.create_all(bind=connection,tables=TABLES,checkfirst=True)

if __name__=='__main__':
    upgrade()
    print('Projects Studio: additive tables checked/created; existing data preserved.')
