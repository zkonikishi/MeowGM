"""Local catalog test adapter; no provider network, orders, or production grants."""
import importlib.util
import json
import sqlite3
import sys
import threading
import time
from contextlib import contextmanager
from pathlib import Path

class CatalogError(ValueError):pass
class CatalogConflict(CatalogError):pass

class Catalog:
    def __init__(self,data):
        self.path=Path(data)/'meowpay-mock/catalog.sqlite3'
        self.lock=threading.Lock()

    def engine(self):
        if getattr(sys,'frozen',False):source=Path(sys._MEIPASS)/'meowpay-simulator/mock.py'
        else:source=Path(__file__).resolve().parents[4]/'_src/MeowPay/mock.py'
        if not source.is_file():raise CatalogError('MeowPay 模拟组件不可用；没有连接生产支付服务')
        spec=importlib.util.spec_from_file_location('_meowpay_catalog_simulator',source)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        return module.MockPay(),module.Fault

    @contextmanager
    def connect(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        db=sqlite3.connect(self.path)
        db.executescript('CREATE TABLE IF NOT EXISTS catalog(id INTEGER PRIMARY KEY CHECK(id=1),body TEXT NOT NULL);CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,at INTEGER,actor TEXT,revision INTEGER,body TEXT NOT NULL);')
        try:
            with db:yield db
        finally:db.close()

    def load(self,db,engine):
        row=db.execute('SELECT body FROM catalog WHERE id=1').fetchone()
        if row:engine.catalogConfig=json.loads(row[0]);engine.refresh_catalog()

    def read(self):
        with self.lock:
            engine,_=self.engine()
            with self.connect() as db:
                self.load(db,engine)
                audit=[{'id':r[0],'at':r[1],'actor':r[2],'revision':r[3],'catalog':json.loads(r[4])} for r in db.execute('SELECT * FROM audit ORDER BY id DESC LIMIT 50')]
                return {'simulation':True,'frameworkHostIntegrated':False,'productionEntitlementImplemented':False,'catalog':engine.catalogConfig,'regions':engine.regions,'audit':audit}

    def write(self,body,actor):
        required={'revision','pointsPerMinor','monthlyMinor','yearlyMinor','blackDiamondEnabled'}
        if set(body)!=required or type(body['revision']) is not int or not actor:raise CatalogError('模拟商品配置参数不正确')
        with self.lock:
            engine,fault=self.engine()
            with self.connect() as db:
                db.execute('BEGIN IMMEDIATE');self.load(db,engine)
                try:r=engine.configure_catalog(actor,['meowpay.catalog.write'],body['revision'],body['pointsPerMinor'],body['monthlyMinor'],body['yearlyMinor'],body['blackDiamondEnabled'])
                except fault as e:
                    if str(e)=='catalog_conflict':raise CatalogConflict('模拟配置已被修改，请重新读取后再保存')
                    raise CatalogError('模拟商品配置无效或没有配置权限')
                raw=json.dumps(r,ensure_ascii=False)
                db.execute('INSERT OR REPLACE INTO catalog(id,body) VALUES(1,?)',(raw,))
                db.execute('INSERT INTO audit(at,actor,revision,body) VALUES(?,?,?,?)',(int(time.time()),actor,r['revision'],raw))
        return self.read()
