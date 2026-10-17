import tempfile
import unittest
from pathlib import Path
from operations import Operations, OperationError, AdminTransport
from unittest.mock import Mock

class OperationsTests(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'ops.db';self.calls=[]
    def tearDown(self):self.tmp.cleanup()
    def transport(self,body):
        self.calls.append(body.copy())
        if len(self.calls)==1:raise OperationError('lost response')
        return {'ok':True,'operation_id':body['operation_id'],'uid':body['uid'],'status':'banned'}
    def test_uncertain_and_restart_keep_original_operation(self):
        ops=Operations(self.path,self.transport);r=ops.create({'uid':'10000001','action':'ban','reason':'test'})
        self.assertEqual(r['state'],'uncertain')
        ops=Operations(self.path,self.transport);r=ops.execute(r['id']);self.assertEqual(r['state'],'completed')
        ops.execute(r['id']);self.assertEqual(len(self.calls),2);self.assertEqual(self.calls[0],self.calls[1])
    def test_not_configured_and_invalid_uid(self):
        with self.assertRaises(OperationError):Operations(self.path,None).create({'uid':'10000001','action':'ban','reason':'test'})
        ops=Operations(self.path,self.transport)
        with self.assertRaises(OperationError):ops.create({'uid':' 10000001','action':'ban','reason':'test'})
        self.assertEqual(ops.list(),[])
    def test_opposite_status_receipt_is_uncertain(self):
        import io
        import json
        transport=AdminTransport('https://platform.example','k'*32)
        body={'operation_id':'request','uid':'10000001','action':'ban','reason':'test'}
        response=io.BytesIO(json.dumps({'ok':True,'operation_id':'request','uid':'10000001','status':'active'}).encode())
        response.status=200
        transport.opener=Mock();transport.opener.open.return_value=response
        with self.assertRaises(OperationError):transport(body)
