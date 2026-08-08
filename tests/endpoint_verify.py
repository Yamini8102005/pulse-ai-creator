from fastapi.testclient import TestClient
from app.main import create_app
from datetime import datetime

# Create an app with an in-memory DB to avoid using any on-disk legacy DB
app = create_app(start_scheduler=False, database_url='sqlite+aiosqlite:///:memory:')

with TestClient(app) as client:
    resp = client.post('/api/agent/init', json={'persona':{'name':'Test Agent','domain':'test'}})
    print('post_status', resp.status_code)
    print('post_json', resp.json())
    assert resp.status_code == 200
    agent_id = resp.json().get('agentId')
    assert isinstance(agent_id, str) and len(agent_id) > 0

    feed = client.get('/api/agent/feed', params={'agentId':agent_id})
    print('feed_status', feed.status_code)
    print('feed_json', feed.json())
    assert feed.status_code == 200
    j = feed.json()
    assert 'posts' in j and isinstance(j['posts'], list)
    if j['posts']:
        p = j['posts'][0]
        required = {'id','createdAt','text','rationale','sources','whyNow'}
        assert required.issubset(p.keys())
        ca = p['createdAt']
        try:
            if ca.endswith('Z'):
                datetime.fromisoformat(ca.replace('Z','+00:00'))
            else:
                datetime.fromisoformat(ca)
        except Exception as e:
            raise AssertionError('createdAt not ISO8601') from e
    print('endpoint_verify OK')
