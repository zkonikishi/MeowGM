// Wire format only. A native account/character ID is never a platform UID.
(function(root){
 'use strict';
 function native(value){
  if(typeof value!=='string'||! /^[1-9][0-9]{0,18}$/.test(value)||BigInt(value)>9223372036854775807n)throw Error('native ID 必须为规范十进制 int64 字符串');
  return value;
 }
 function uid8(value){if(typeof value!=='string'||! /^[0-9]{8}$/.test(value))throw Error('平台 UID 必须为8位ASCII数字字符串');return value;}
 const api=Object.freeze({native,uid8});root.MeowNativeIds=api;
 if(typeof module!=='undefined'&&module.exports)module.exports=api;
})(typeof window!=='undefined'?window:globalThis);
