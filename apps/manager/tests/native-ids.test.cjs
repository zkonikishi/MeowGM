const assert=require('node:assert/strict');
const ids=require('../../admin/native-ids.js');
for(const value of ['9007199254740991','9007199254740992','9007199254740993','9223372036854775807'])assert.equal(ids.native(value),value);
for(const value of ['01','0','-1','+1','1e3','1.0',' 1','9223372036854775808',1,1.0,1e3,9007199254740992,null,true,'١'])assert.throws(()=>ids.native(value));
assert.equal(ids.uid8('00000001'),'00000001');
for(const value of [10000001,'1','000000001','١٢٣٤٥٦٧٨'])assert.throws(()=>ids.uid8(value));
console.log('native-ID and platform UID8 browser boundary tests passed');
