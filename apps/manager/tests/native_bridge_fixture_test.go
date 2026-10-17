package main

// Runs only in an isolated copy of the pinned upstream gm module.
// All accounts, characters and SQLite files are synthetic; no PVF/game is opened.
import (
 "bytes"
 "context"
 "database/sql"
 "encoding/json"
 "net/url"
 "os"
 "path/filepath"
 "strings"
 "testing"

 "dfolauncher/gm/internal/dbx"
 "dfolauncher/gm/internal/servercompat/storage"
 _ "modernc.org/sqlite"
)

func TestMeowNativeBridgeReadModifyReceipt(t *testing.T) {
 ctx:=context.Background()
 path:=filepath.Join(t.TempDir(),"synthetic.sqlite3")
 schema,err:=os.ReadFile("../../internal/servercompat/storage/testdata/sqlite-schema.sql")
 if err!=nil {t.Fatal(err)}
 seed,err:=sql.Open("sqlite",dbx.SQLiteDSN(path,5000));if err!=nil {t.Fatal(err)}
 defer seed.Close()
 if _,err=seed.Exec(string(schema));err!=nil {t.Fatal(err)}
 if _,err=seed.Exec(`INSERT INTO accounts(username,development_only) VALUES('meow-synthetic',1)`);err!=nil {t.Fatal(err)}
 const identity="c638346fa77a523a77e7022aa19511951d4bb9619c7e0c035d0ff4835a8fc400"
 if _,err=seed.Exec(`INSERT INTO characters(account_id,wire_id,name,profession,create_request,config_version,state) VALUES(1,1,'synthetic-role',11,x'00',?,?)`,identity,[]byte(`{"level":1,"skill_points":[2,3],"technique_points":[0,0],"inventory":{"version":"ordinary-bag-v1","gold":0},"meow_unknown":{"preserve":true}}`));err!=nil {t.Fatal(err)}
 store,err:=storage.Open(ctx,storage.Config{Driver:dbx.DriverSQLite,SQLitePath:path});if err!=nil {t.Fatal(err)}
 defer store.Close()
 s:=&server{store:store,operator:"MeowGM-synthetic",index:&ItemIndex{}}
 read:=func() map[string]json.RawMessage {
  role,err:=s.gmRole(ctx,1,1);if err!=nil {t.Fatal(err)}
  var state map[string]json.RawMessage;if err=json.Unmarshal(role.State,&state);err!=nil {t.Fatal(err)}
  return state
 }
 if string(read()["skill_points"])!="[2,3]" {t.Fatal("unexpected seed")}
 resultRead,err:=s.bridgeCall(bridgeRequest{Method:"character",Query:url.Values{"id":{"1"}}});if err!=nil {t.Fatal(err)}
 if !bytes.Contains(mustFixtureJSON(t,resultRead),[]byte("synthetic-role")) {t.Fatalf("native character read failed: %s",mustFixtureJSON(t,resultRead))}
 body:=json.RawMessage(`{"id":"launcher-meow-fixture-0001","account":1,"character":1,"action":"sp","value":7,"reason":"synthetic acceptance"}`)
 var wire bytes.Buffer
 input:=strings.NewReader(string(mustFixtureJSON(t,bridgeRequest{Method:"character.edit",Body:body}))+"\n"+string(mustFixtureJSON(t,bridgeRequest{Method:"character.edit",Body:body}))+"\n")
 if err=s.serveBridge(input,&wire);err!=nil {t.Fatal(err)}
 decoder:=json.NewDecoder(&wire)
 var greeting map[string]any;if err=decoder.Decode(&greeting);err!=nil {t.Fatal(err)}
 if greeting["ready"]!=true {t.Fatal(greeting)}
 for _,applied:=range []bool{true,false} {
  var reply map[string]any;if err=decoder.Decode(&reply);err!=nil {t.Fatal(err)}
  if reply["ok"]!=true||reply["applied"]!=applied||reply["grant_id"]!="launcher-meow-fixture-0001" {t.Fatal(reply)}
 }
 state:=read();if string(state["skill_points"])!="[9,10]"||string(state["meow_unknown"])!="{\"preserve\":true}" {t.Fatalf("state %s",mustFixtureJSON(t,state))}
 conflict:=bytes.Replace(body,[]byte(`"value":7`),[]byte(`"value":8`),1)
 if _,err=s.bridgeCall(bridgeRequest{Method:"character.edit",Body:conflict});err==nil {t.Fatal("same ID accepted different mutation")}
 wrong:=bytes.Replace(body,[]byte(`"account":1`),[]byte(`"account":2`),1)
 wrong=bytes.Replace(wrong,[]byte("fixture-0001"),[]byte("fixture-0002"),1)
 if _,err=s.bridgeCall(bridgeRequest{Method:"character.edit",Body:wrong});err==nil {t.Fatal("wrong owner accepted")}
 tpRequest:=json.RawMessage(`{"id":"launcher-meow-fixture-tp01","account":1,"character":1,"action":"tp","value":5,"reason":"synthetic TP acceptance"}`)
 if _,err=s.bridgeCall(bridgeRequest{Method:"character.edit",Body:tpRequest});err!=nil {t.Fatal(err)}
 if string(read()["technique_points"])!="[5,5]" {t.Fatal("TP mutation failed")}
 overflow:=bytes.Replace(body,[]byte(`"value":7`),[]byte(`"value":65535`),1)
 overflow=bytes.Replace(overflow,[]byte("fixture-0001"),[]byte("fixture-overflow"),1)
 if _,err=s.bridgeCall(bridgeRequest{Method:"character.edit",Body:overflow});err==nil {t.Fatal("overflow accepted")}
 var count int;var receipt []byte
 if err=seed.QueryRow(`SELECT count(*) FROM admin_grants`).Scan(&count);err!=nil||count!=2 {t.Fatalf("audit count %d err %v",count,err)}
 if err=seed.QueryRow(`SELECT receipt FROM admin_grants WHERE grant_id='launcher-meow-fixture-0001'`).Scan(&receipt);err!=nil {t.Fatal(err)}
 if !json.Valid(receipt)||!bytes.Contains(receipt,[]byte(`"before"`))||!bytes.Contains(receipt,[]byte(`"after"`)) {t.Fatalf("invalid receipt %s",receipt)}
 result,err:=s.bridgeCall(bridgeRequest{Method:"history",Query:url.Values{"account":{"1"}}});if err!=nil {t.Fatal(err)}
 if !bytes.Contains(mustFixtureJSON(t,result),[]byte("launcher-meow-fixture-0001")) {t.Fatal("history missing receipt")}
 if string(read()["skill_points"])!="[9,10]" {t.Fatal("failed operation changed state")}
 t.Log("native stdio dispatch + SP mutation + replay=false + conflict/ownership rejection + receipt/history passed")
}

func mustFixtureJSON(t *testing.T,v any) []byte {t.Helper();b,e:=json.Marshal(v);if e!=nil {t.Fatal(e)};return b}

func TestMeowNativeBridgeInt64Identifiers(t *testing.T) {
 ctx:=context.Background();path:=filepath.Join(t.TempDir(),"synthetic-int64.sqlite3")
 schema,err:=os.ReadFile("../../internal/servercompat/storage/testdata/sqlite-schema.sql");if err!=nil {t.Fatal(err)}
 seed,err:=sql.Open("sqlite",dbx.SQLiteDSN(path,5000));if err!=nil {t.Fatal(err)};defer seed.Close()
 if _,err=seed.Exec(string(schema));err!=nil {t.Fatal(err)}
 const account int64=9223372036854775807
 const roleID int64=9007199254740993
 if _,err=seed.Exec(`INSERT INTO accounts(id,username,development_only) VALUES(?,'int64-fixture',1)`,account);err!=nil {t.Fatal(err)}
 if _,err=seed.Exec(`INSERT INTO characters(id,account_id,wire_id,name,profession,create_request,config_version,state) VALUES(?,?,1,'int64-role',11,x'00',?,?)`,roleID,account,"c638346fa77a523a77e7022aa19511951d4bb9619c7e0c035d0ff4835a8fc400",[]byte(`{"level":1,"skill_points":[2,3],"inventory":{"version":"ordinary-bag-v1","gold":0}}`));err!=nil {t.Fatal(err)}
 store,err:=storage.Open(ctx,storage.Config{Driver:dbx.DriverSQLite,SQLitePath:path});if err!=nil {t.Fatal(err)};defer store.Close()
 s:=&server{store:store,operator:"MeowGM-int64-synthetic",index:&ItemIndex{}}
 read,err:=s.bridgeCall(bridgeRequest{Method:"character",Query:url.Values{"id":{"9007199254740993"}}});if err!=nil {t.Fatal(err)}
 wire:=mustFixtureJSON(t,read)
 if !bytes.Contains(wire,[]byte(`"account":9223372036854775807`))||!bytes.Contains(wire,[]byte(`"id":9007199254740993`)) {t.Fatalf("native wire identity changed: %s",wire)}
 body:=mustFixtureJSON(t,map[string]any{"id":"launcher-native-int64-fixture-01","account":account,"character":roleID,"action":"sp","value":7,"reason":"isolated int64 acceptance"})
 result,err:=s.bridgeCall(bridgeRequest{Method:"character.edit",Body:body});if err!=nil {t.Fatal(err)}
 if !bytes.Contains(mustFixtureJSON(t,result),[]byte(`"applied":true`)) {t.Fatal(result)}
 role,err:=s.gmRole(ctx,account,roleID);if err!=nil {t.Fatal(err)}
 var state struct {Points [2]uint16 `json:"skill_points"`}
 if err=json.Unmarshal(role.State,&state);err!=nil||state.Points!=[2]uint16{9,10} {t.Fatalf("wrong native role mutation: %+v %v",state,err)}
 var idType string;if err=seed.QueryRow(`SELECT typeof(id) FROM accounts WHERE id=?`,account).Scan(&idType);err!=nil||idType!="integer" {t.Fatal(idType,err)}
 t.Log("MaxInt64 account and >2^53 character native read/write preserved exact integer IDs")
}
