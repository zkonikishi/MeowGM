"""GM wire identifiers. Native int64 IDs are not canonical/platform UIDs."""
import re

MAX_NATIVE_ID=9223372036854775807
MAX_SAFE_JSON_INTEGER=9007199254740991

def native_id_from_request(value):
    # Older clients may send exact safe JSON integers, never floats or unsafe numbers.
    if type(value) is int:
        if 0<value<=MAX_SAFE_JSON_INTEGER:return value
        raise ValueError('数值型 native ID 超过安全范围，请用规范十进制字符串')
    if not isinstance(value,str) or not re.fullmatch(r'[1-9][0-9]{0,18}',value):raise ValueError('native ID 必须为无前导零的正十进制 int64 字符串')
    number=int(value)
    if number>MAX_NATIVE_ID:raise ValueError('native ID 超过 int64 范围')
    return number

def native_id_to_wire(value):
    # This branch is for trusted SQLite/native JSON integers, parsed exactly by Python.
    if type(value) is int:
        if 0<value<=MAX_NATIVE_ID:return str(value)
        raise ValueError('原生返回了无效的账号或角色 ID')
    return str(native_id_from_request(value))

def platform_uid8(value):
    # Only the existing platform UID8 contract; universal local_uid format is not frozen.
    if not isinstance(value,str) or not re.fullmatch(r'[0-9]{8}',value):raise ValueError('平台 UID 必须为8位ASCII数字字符串')
    return value

def response_ids_to_wire(method,result):
    if method=='character':
        if 'account' in result:result['account']=native_id_to_wire(result['account'])
        if isinstance(result.get('character'),dict) and 'id' in result['character']:result['character']['id']=native_id_to_wire(result['character']['id'])
    if method in ('prepare','overview','characters'):
        for collection in ('accounts','characters'):
            for row in result.get(collection,[]):
                if isinstance(row,dict) and 'id' in row:row['id']=native_id_to_wire(row['id'])
    if method=='history':
        for row in result.get('history',[]):
            if 'character_id' in row:row['character_id']=native_id_to_wire(row['character_id']) if row['character_id'] else None
            if isinstance(row.get('request'),dict):
                for key in ('account_id','character_id'):
                    if row['request'].get(key):row['request'][key]=native_id_to_wire(row['request'][key])
    return result
