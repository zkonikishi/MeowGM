"""115US SQLite inspection, read-only and explicit. No migrations or game starts."""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from native_ids import native_id_to_wire,MAX_NATIVE_ID

class Read115Error(ValueError):pass
class Read115:
    def __init__(self,environment):self.environment=environment
    @contextmanager
    def database(self):
        config=self.environment.read()
        if config['profile']!='115us' or config['mode']!='local' or not config['root']:
            raise Read115Error('请先选择本地 115US 整合包目录；云端玩家读取尚未接通。')
        root=Path(config['root']).resolve(strict=True)
        config_path=root/'server/work/dfo-lan/runtime/storage/local.json'
        if config_path.is_symlink() or not config_path.is_file() or config_path.stat().st_size>65536:
            raise Read115Error('缺少 115US 的 server/work/dfo-lan/runtime/storage/local.json；未创建或修改存档。')
        try:
            settings=json.loads(config_path.read_text(encoding='utf-8-sig'))
            value=settings.get('sqlite_path')
            if not isinstance(value,str) or not value:raise ValueError()
            database=Path(value)
            if not database.is_absolute():raise ValueError()
            resolved=database.resolve(strict=True)
            if not resolved.is_relative_to(root) or database.is_symlink() or not resolved.is_file():raise ValueError()
        except (ValueError,OSError):raise Read115Error('SQLite 路径无效或越出所选环境；请核对 115US 配置。') from None
        connection=sqlite3.connect(resolved.as_uri()+'?mode=ro',uri=True,timeout=3)
        connection.row_factory=sqlite3.Row
        try:
            connection.execute('PRAGMA query_only=ON')
            accounts={r[1] for r in connection.execute('PRAGMA table_info(accounts)')}
            characters={r[1] for r in connection.execute('PRAGMA table_info(characters)')}
            if not {'id','username'}<=accounts or not {'id','account_id','name','profession','state','deleted_at'}<=characters:
                raise Read115Error('存档结构与 115US 查询契约不匹配，已停止读取。')
            yield connection
        except sqlite3.Error:raise Read115Error('115US 存档只读查询失败，可能被占用或版本不兼容；未执行迁移。') from None
        finally:connection.close()
    def accounts(self):
        with self.database() as db:
            rows=db.execute('SELECT a.id,a.username,COUNT(c.id) count FROM accounts a LEFT JOIN characters c ON c.account_id=a.id AND c.deleted_at IS NULL GROUP BY a.id,a.username ORDER BY a.id LIMIT 1001').fetchall()
            if len(rows)>1000:raise Read115Error('账号超过1000条，需要分页接口后再读取；未截断为完整清单。')
            return {'profile':'115us','readOnly':True,'nativeIdEncoding':'decimal-int64-string','canonicalMappingVerified':None,'accounts':[{'accountId':native_id_to_wire(r['id']),'name':r['username'],'characterCount':r['count']} for r in rows]}
    def characters(self,account):
        if type(account) is not int or not 0<account<=MAX_NATIVE_ID:raise Read115Error('请选择有效账号')
        with self.database() as db:
            rows=db.execute('SELECT id,name,profession,state FROM characters WHERE account_id=? AND deleted_at IS NULL ORDER BY id LIMIT 201',(account,)).fetchall()
            if len(rows)>200:raise Read115Error('角色数量超出只读查询上限')
            result=[]
            for row in rows:
                try:state=json.loads(row['state'])
                except (ValueError,TypeError):state={}
                level=state.get('level') if isinstance(state,dict) else None
                result.append({'accountId':native_id_to_wire(account),'characterId':native_id_to_wire(row['id']),'name':row['name'],'jobName':'职业 '+str(row['profession']),'level':level if type(level) is int else '未知'})
            return {'profile':'115us','readOnly':True,'nativeIdEncoding':'decimal-int64-string','canonicalMappingVerified':None,'characters':result}
