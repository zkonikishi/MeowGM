"""Build a local Windows read-only development console; never packages runtime data."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile
from verify_mrad_package import verify

ROOT = Path(__file__).resolve().parents[1]
NAME = 'MeowGM-Mrad-ReadOnly-dev-20261023-r2'


def build(output_root):
    if sys.platform != 'win32':
        raise SystemExit('Build on Windows x64 with Python and PyInstaller 6.22.3.')
    if importlib.metadata.version('pyinstaller') != '6.22.3':
        raise SystemExit('Use the pinned PyInstaller 6.22.3 build environment.')
    dependencies = {}
    for line in (ROOT / 'tools' / 'requirements-mrad-package.txt').read_text().splitlines():
        if not line.strip():
            continue
        name, version = line.split('==')
        dependencies[name] = importlib.metadata.version(name)
        if dependencies[name] != version:
            raise SystemExit('Build dependency differs from requirements-mrad-package.txt: ' + name)
    subprocess.run([sys.executable, '-c',
                    'import sys;sys.path.insert(0,sys.argv[1]);import server,mrad_console_host',
                    str(ROOT / 'services' / 'gateway')], check=True)
    output_root = Path(output_root).resolve()
    destination = output_root / NAME
    archive = output_root / (NAME + '.zip')
    if destination.exists() or archive.exists():
        raise SystemExit('Output already exists; choose a new --output-root. Existing artifacts were preserved.')
    staging = ROOT / '.runtime' / ('package-stage-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f'))
    assets = staging / 'assets' / 'apps' / 'admin'
    assets.mkdir(parents=True)
    for source in sorted((ROOT / 'apps' / 'admin').iterdir()):
        if source.is_file() and not source.is_symlink() and source.suffix.lower() in {'.html', '.js', '.css', '.png', '.txt'}:
            shutil.copy2(source, assets / source.name)
    destination.mkdir(parents=True)
    subprocess.run([
        sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean', '--onefile', '--console',
        '--name', 'MeowGM-Mrad-ReadOnly', '--distpath', str(destination),
        '--workpath', str(staging / 'work'), '--specpath', str(staging),
        '--paths', str(ROOT / 'services' / 'gateway'),
        '--add-data', str(assets) + ';apps/admin',
        str(ROOT / 'tools' / 'start_mrad_console.py'),
    ], cwd=ROOT, check=True, env={**os.environ, 'PYINSTALLER_CONFIG_DIR': str(ROOT / '.runtime' / 'pyinstaller-cache')})
    shutil.copy2(ROOT / 'NOTICE.txt', destination / 'NOTICE.txt')
    shutil.copy2(ROOT / 'apps' / 'admin' / 'UPSTREAM-UI.txt', destination / 'UPSTREAM-UI.txt')
    shutil.copy2(Path(sys.base_prefix) / 'LICENSE.txt', destination / 'PYTHON-LICENSE.txt')
    distribution = importlib.metadata.distribution('pyinstaller')
    for file in distribution.files or []:
        if file.name.lower() == 'copying.txt':
            shutil.copy2(distribution.locate_file(file), destination / 'PYINSTALLER-COPYING.txt')
            break
    for package in ('cryptography', 'cffi', 'pycparser'):
        distribution = importlib.metadata.distribution(package)
        for file in distribution.files or []:
            if 'license' in str(file).lower() and file.suffix in ('.txt', '.rst', '.APACHE', '.BSD', ''):
                source = distribution.locate_file(file)
                if source.is_file():
                    licenses = destination / 'licenses' / package
                    licenses.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(source, licenses / file.name)
    instructions = '''MeowGM · Mrad 本机只读管理开发测试包

双击 MeowGM-Mrad-ReadOnly.exe，自动打开本机浏览器。保持控制台运行；关闭控制台只退出 GM 网页，不停止游戏服务。
进入“只读管理”，使用默认 http://127.0.0.1:7000 或实际本机 HTTP 地址，手动连接后查询账号、角色、角色进度。
本包自带 Python 运行时，不要求另外安装 Python、Rust 或 Go；需要 Windows x64 和可用浏览器。
可用 --no-open 禁止自动打开浏览器，--data 路径指定 GM 自身配置目录，--port 0 使用随机本机端口。
默认配置放在 EXE 旁 data/，不存玩家数据库；移动程序前可自行保留该目录。
窗口 URL 含本机临时窗口参数，不要分享。保存服务地址不会自动连接。

范围：本机连接诊断、账号列表、角色列表、角色进度。无玩家资产写入、远程管理、游戏账号登录、游戏进程启停。
账号内部键精确按 Int64 字符串处理；列表最多 2000 行，达到上限时结果可能不全。
服务实例/数据库/资源变化时须重新连接。角色存档、HTTP 成功、已选角连接均不能证明客户端已进入城镇。
客户端游戏认证、角色界面、选角进入城镇分别显示“未验收”，由真实客户端联调确认。
这是浏览器宿主开发测试包，不是仓库完整 Tauri 发行版；本机验证记录见同目录 VALIDATION.md。
作者、来源和使用声明见 NOTICE.txt / UPSTREAM-UI.txt；Python 与 PyInstaller 声明随包保留。
'''
    (destination / '使用说明.txt').write_text(instructions, encoding='utf-8-sig')
    validation = verify(destination / 'MeowGM-Mrad-ReadOnly.exe')
    (destination / 'VALIDATION.md').write_text(
        '# Development package validation\n\nFrozen executable startup, packaged assets, local window authentication, read-only route boundaries and graceful shutdown passed in an isolated temporary directory.\n'
        'This check did not contact a game server. Game authentication, character screen and town entry remain unverified.\n\n'
        + '```json\n' + json.dumps(validation, indent=2) + '\n```\n', encoding='utf-8')
    manifest = {
        'product': 'MeowGM Mrad Read-only Development Console', 'package': NAME,
        'kind': 'windows-x64-browser-host-development', 'builtAt': datetime.now(timezone.utc).isoformat(),
        'sourceCommit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'includesUncommittedChanges': bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip()), 'fullTauriRelease': False,
        'pythonRuntime': sys.version.split()[0], 'buildDependencies': dependencies,
        'writeEnabled': False, 'gameEntryVerified': False, 'executableValidated': True,
        'validation': validation,
        'files': {path.relative_to(destination).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(destination.rglob('*')) if path.is_file()},
    }
    (destination / 'artifact.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED) as zipped:
        for path in sorted(destination.rglob('*')):
            if path.is_file():
                zipped.write(path, NAME + '/' + path.relative_to(destination).as_posix())
    print(json.dumps({'directory': str(destination), 'archive': str(archive),
                      'sha256': hashlib.sha256(archive.read_bytes()).hexdigest(), 'executableValidated': True}, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-root', type=Path, default=ROOT / 'dist')
    build(parser.parse_args().output_root)
