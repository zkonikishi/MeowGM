import unittest
from native_ids import native_id_from_request,native_id_to_wire,platform_uid8,response_ids_to_wire,MAX_NATIVE_ID

class NativeIdTests(unittest.TestCase):
 def test_exact_int64_strings_and_safe_legacy_number_policy(self):
  for number in [2**53-1,2**53,2**53+1,MAX_NATIVE_ID]:
   self.assertEqual(native_id_from_request(str(number)),number)
   self.assertEqual(native_id_to_wire(number),str(number))
  self.assertEqual(native_id_from_request(2**53-1),2**53-1)
  for number in [2**53,2**53+1,MAX_NATIVE_ID]:
   with self.assertRaises(ValueError):native_id_from_request(number)
 def test_reject_noncanonical_native_ids(self):
  for value in ['01','0','-1','+1','1e3','1.0',' 1','1 ','١','９','9223372036854775808',-1,0,1.0,1e3,True,None]:
   with self.subTest(value=value),self.assertRaises(ValueError):native_id_from_request(value)
 def test_uid8_is_separate_preserves_leading_zero_and_does_not_accept_number(self):
  self.assertEqual(platform_uid8('00000001'),'00000001')
  for value in [10000001,'1','000000001','١٢٣٤٥٦٧٨',None]:
   with self.assertRaises(ValueError):platform_uid8(value)
  with self.assertRaises(ValueError):native_id_from_request('00000001')
 def test_native_read_and_history_responses_do_not_round(self):
  value=2**53+1
  result=response_ids_to_wire('character',{'account':value,'character':{'id':MAX_NATIVE_ID,'wire_id':1},'summary':{'level':1}})
  self.assertEqual(result['account'],str(value));self.assertEqual(result['character']['id'],str(MAX_NATIVE_ID));self.assertEqual(result['character']['wire_id'],1)
  history=response_ids_to_wire('history',{'history':[{'character_id':MAX_NATIVE_ID,'request':{'account_id':value,'character_id':MAX_NATIVE_ID}}]})
  self.assertEqual(history['history'][0]['request']['account_id'],str(value))
