"""Optional PVF integration. Missing tooling never prevents the GM from starting."""
import importlib
import hashlib
import uuid
from pathlib import Path


class ProtectionError(ValueError):
    pass


def provider():
    try:
        return importlib.import_module('pvf_protection')
    except ImportError:
        return None


def capabilities():
    module = provider()
    if module:
        return module.capabilities()
    return {'available': False, 'huazhiGameEncryption': False, 'modes': [],
            'message': 'PVF 保护模块未随当前版本提供；仅支持读取文件大小和校验值。'}


def inspect_file(value):
    if not isinstance(value, str) or not value.strip():
        raise ProtectionError('请选择本机 PVF 文件')
    path = Path(value)
    if not path.is_absolute() or not path.is_file():
        raise ProtectionError('文件不存在或不是绝对路径')
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return {'path': str(path), 'size': path.stat().st_size, 'sha256': digest.hexdigest(),
            'format': 'unverified', 'headerValidated': False, 'capabilities': capabilities()}


def execute(action, body, data):
    module = provider()
    if action == 'inspect':
        if set(body) != {'path'}: raise ProtectionError('检测参数不正确')
        return module.inspect(body['path']) if module else inspect_file(body['path'])
    if not module:
        raise ProtectionError('PVF 保护模块尚未提供，当前不能加密、解密或生成密钥；原文件未修改。')
    parent = Path(data) / 'pvf-protections'
    parent.mkdir(parents=True, exist_ok=True)
    if action == 'protect': return module.protect(body, parent)
    if action == 'unprotect': return module.unprotect(body, parent)
    if action == 'key':
        if body: raise ProtectionError('密钥生成不接受自定义参数')
        keys = Path(data) / 'pvf-keys'
        keys.mkdir(parents=True, exist_ok=True)
        path = keys / (uuid.uuid4().hex + '.key')
        module.generate_key(path)
        return {'path': str(path), 'keyIncluded': False, 'message': '密钥单独保存在本机，请另行备份；勿上传到官网或加入玩家包。'}
    raise ProtectionError('不支持的 PVF 操作')
