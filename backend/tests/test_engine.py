from app.engine import local_slides, render

def test_export():
 slides=local_slides('Cybersecurity',5)
 assert len(slides)==5
 assert render('Cybersecurity',slides,'midnight')[:2]==b'PK'
