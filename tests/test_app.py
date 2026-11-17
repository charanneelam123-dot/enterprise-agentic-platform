import os,tempfile
os.environ['DATA_DIR']=tempfile.mkdtemp(prefix='agents-test-')
import unittest
from fastapi.testclient import TestClient
from app import app
from workflow import run_graph


class AgentTests(unittest.TestCase):
    def setUp(self):self.client=TestClient(app)
    def start(self):return self.client.post('/api/runs',json={'workflow':'vendor-onboarding','task':'Review demo-001 and draft the appropriate request.'}).json()
    def test_ten_registered_workflows(self):self.assertEqual(len(self.client.get('/api/workflows').json()),10)
    def test_graph_pauses_with_checked_evidence(self):
        run=self.start();self.assertEqual(run['status'],'pending_review');self.assertEqual(len(run['evidence']),2)
        self.assertTrue(run['report']['findings']);self.assertIsNone(run['result'])
    def test_record_read_requires_its_capability(self):
        run=self.start();self.assertEqual(self.client.get('/api/runs/'+run['id']).status_code,404)
    def test_resume_after_reopening_sqlite_checkpointer(self):
        run=self.start();headers={'X-Run-Token':run['token']}
        result=self.client.post('/api/runs/'+run['id']+'/decision',headers=headers,json={'choice':'approve','reason':'Reviewed evidence','version':run['version']})
        self.assertEqual(result.status_code,200);self.assertEqual(result.json()['status'],'complete')
        self.assertFalse(result.json()['result']['external_action_executed'])
    def test_duplicate_decision_rejected(self):
        run=self.start();path='/api/runs/'+run['id']+'/decision';headers={'X-Run-Token':run['token']};body={'choice':'reject','reason':'Need more information','version':run['version']}
        self.assertEqual(self.client.post(path,headers=headers,json=body).status_code,200)
        self.assertEqual(self.client.post(path,headers=headers,json=body).status_code,409)
    def test_stale_version_rejected(self):
        run=self.start();result=self.client.post('/api/runs/'+run['id']+'/decision',headers={'X-Run-Token':run['token']},json={'choice':'approve','reason':'Reviewed evidence','version':0})
        self.assertEqual(result.status_code,409)
    def test_live_requires_operator(self):
        self.assertEqual(self.client.post('/api/runs',json={'workflow':'vendor-onboarding','task':'Review the vendor','live':True}).status_code,403)
    def test_all_workflows_reach_review(self):
        for workflow in self.client.get('/api/workflows').json():
            result=self.client.post('/api/runs',json={'workflow':workflow['id'],'task':'Review demo-001 against the policy.'})
            self.assertEqual(result.status_code,201,workflow['id'])
            self.assertEqual(result.json()['proposal']['kind'],workflow['action'])


if __name__=='__main__':unittest.main()
