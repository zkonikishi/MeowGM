"""Read-only resource inventory. Presence never means a native operation is ready."""
import hashlib
import json
from pathlib import Path

def resources(environment,client_directory):
    config=environment.read()
    result={'scope':'local-resource-inventory','refine':{'state':'unavailable','operationEnabled':False,'message':'锻造发放尚未开放'},'images':{'state':'unavailable','previewVerified':False,'message':'未检测到 ImagePacks2；不能显示物品图像'},'names':{'state':'native-or-partial-translation','message':'显示名以当前原生 GM 资源返回为准；未补译名称保留原文，不保证全部中文'}}
    if config['mode']!='local' or not config['root']:return result
    try:
        root=Path(config['root']).resolve(strict=True);path=root/'server/work/dfo-lan/configs/refine.json'
        if not path.is_file():result['refine']['message']='所选服务端缺少 configs/refine.json；锻造不可用'
        elif path.is_symlink() or not path.resolve().is_relative_to(root) or path.stat().st_size>65536:result['refine']['message']='锻造规则路径或大小不符合读取要求'
        else:
            raw=path.read_bytes();value=json.loads(raw)
            if not isinstance(value,dict) or type(value.get('version')) is not int or value['version']!=1 or any(k in value and type(value[k]) is not int for k in ('max_level','record_offset')):raise ValueError('锻造规则结构不符合版本1')
            result['refine'].update(state='parsed',sha256=hashlib.sha256(raw).hexdigest(),maxLevel=value.get('max_level'),recordOffset=value.get('record_offset'),message='已读取所选服务端规则结构；锻造发放仍未开放，未校准实际游戏效果')
    except (OSError,ValueError,TypeError):result['refine']['message']='锻造规则无法读取或结构无效；未使用默认规则代替'
    try:
        if not client_directory or not Path(client_directory).is_absolute():return result
        client=Path(client_directory).resolve(strict=True);images=client/'ImagePacks2'
        if not images.is_dir():return result
        if images.is_symlink() or getattr(images,'is_junction',lambda:False)() or not images.resolve().is_relative_to(client):raise ValueError()
        count=0
        for path in images.iterdir():
            if path.is_file() and not path.is_symlink() and path.suffix.lower()=='.npk':count+=1
            if count>=10000:break
        result['images'].update(state='present' if count else 'unavailable',npkCount=count,countCapped=count==10000,message='发现 NPK 文件；仅成功解码指定物品后才确认该物品预览可用' if count else 'ImagePacks2 中未发现 NPK 文件')
    except (OSError,ValueError):pass
    return result
