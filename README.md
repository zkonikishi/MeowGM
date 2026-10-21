# MeowGM

项目维护及本项目改动作者：**zkonikishi**。原作者署名与许可证保持原样。

当前源码：**26.1-snapshot-1 开发候选**（内部 SemVer：26.1.0-snapshot-1）。本次仅同步源码，没有新 EXE 或稳定版发布。

新增客户端 MOD 清单与启停配置、离线部署指纹检查、公钥有效期/区服/撤销校验，以及 MeowScope 能力投影。部署执行仍未支持；可信宿主管理会话/RBAC 未接通时所有开发者执行请求返回 503。签名草稿通过验证不等于真实宿主兼容或生产验收。

面向 86s4a21 / 115US 客户端的 **GM 管理与网关工具套件**：GM 管理器（Rust + Tauri 2 + WebView2）、管理后台、Python 网关服务，以及与 MeowLauncher 共用的核心库副本。

> **使用声明**：本项目仅供免费技术交流与个人学习研究使用，严禁倒卖、收费传播或任何形式的商业牟利。
> 游戏内容及相关知识产权归原权利人所有。本仓库不包含游戏客户端、服务端程序或游戏资源文件。
> 完整声明见 [NOTICE.txt](NOTICE.txt)。

## 组成

| 目录 | 内容 |
| --- | --- |
| `apps/manager` | MeowGM GM 管理器（Tauri 2 桌面端），编译期内嵌 `binaries/oo-manager-host.exe` |
| `apps/admin` | GM 管理后台静态页面 |
| `services/gateway` | MeowGate 网关服务（Python）：GM 通道、准入、远端部署与隧道 |
| `packages/launcher-core` | 与 MeowLauncher 共用的核心库（账号、传输、更新、CN115 环回桥等） |
| `tools` | GM 构建 / 联调 / 打包脚本 |
| `docs` | 验收与设计记录 |

## 环境要求

- Windows 10/11 x64
- [Rust](https://rustup.rs) stable（MSVC toolchain）
- Microsoft Edge WebView2 Runtime（Win11 内置）
- MSVC BuildTools（链接管理器时必需）
- Python 3.11+（网关服务与重建内嵌宿主时需要）

## 构建

### 管理器（MeowGM.exe）

```powershell
# 直接编译管理器主程序（使用仓库内预构建的 oo-manager-host.exe）
cargo build -p meow-manager --release

# 完整发行流程：后台静态页 + 网关打包 + 内嵌宿主重建 + 管理器编译
pwsh -File tools\build-manager.ps1
```

> `apps/manager/src-tauri/src/main.rs` 通过 `include_bytes!("../binaries/oo-manager-host.exe")` 在编译期内嵌宿主程序，
> 该二进制必须存在；仓库已附带预构建版本。若需从源码重建，需要上游 Go 源码（`MEOW_UPSTREAM_DIR` 指向含
> `cmd/modkit` 与 `gm/cmd/gmtool` 的目录）以及 `tools/requirements-manager-build.txt` 中的 Python 依赖。
> `tools/build-manager.ps1` 内的 `C:/rust-toolchain`、`C:/dev-toolchain` 等为工具链占位路径，请按本机环境调整。

### 网关（Python）

```powershell
pip install -r tools\requirements-manager-build.txt
python tools\package-services.py    # 打包网关服务
pwsh -File tools\Start-Manager.ps1  # 启动本地 GM 服务
```

### 联调冒烟

```powershell
node tools\gateway-ui-smoke.cjs     # 需要本地网关已启动
node tools\manager-native-smoke.cjs
node tools\pvf-ui-smoke.cjs
pwsh -File tools\test-manager-native.ps1
```

## 测试

```powershell
cargo test -p meow-launcher-core --locked
```

## 数据与配置

- 本仓库不内置任何真实服务器地址；连接参数在界面中填写或由部署环境提供。
- 远端 GM 通道需要目标主机上的网关服务与 SSH 访问（见 `services/gateway/deploy/managed_remote.py`、`manager_ssh.py`）。
- 网关运行期数据目录已在 `.gitignore` 中排除（`services/gateway/data/`、`*.sqlite`）。

## 脱敏说明

本仓库为**脱敏版本**：不包含任何真实服务器地址、IP、域名、证书或私钥；与线上服务相关的端点均为不可路由的
占位符（`launcher.invalid`、`203.0.113.10`）。`packages/launcher-core` 是 MeowLauncher 核心库的同步副本；
开发辅助脚本中的 `C:/workspace`、`upstream/` 等为占位路径，请按本机环境调整。

## 参考与致谢

- 实现参考了上游 115 启动器项目 [`gitgud.io/yh9/115us-dfolauncher`](https://gitgud.io/yh9/115us-dfolauncher)。该上游仓库未声明开源许可证；本仓库不包含其源码副本，仅在接口形态与实现思路上参考。
- 编译期内嵌的宿主程序由上游 Go 工程构建（`MEOW_UPSTREAM_DIR` 指向的上游仓库，GPL-3.0）；若重新分发该内嵌二进制，需同时履行上游 GPL-3.0 的源码提供义务。

## 许可

本仓库未附开源许可证，默认保留所有权利（All rights reserved）。
在遵守 [NOTICE.txt](NOTICE.txt) 使用声明的前提下，可自由下载、编译、用于个人学习研究。
