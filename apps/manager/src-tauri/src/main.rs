#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
use std::{io::{BufRead,BufReader},process::{Child,Command,Stdio},sync::Mutex,time::Duration};
use std::os::windows::process::CommandExt;
use sha2::{Digest,Sha256};
use tauri::Manager;

struct UpdateState {updater:meow_launcher_core::update::Updater,data:std::path::PathBuf}
fn manager_update_base()->String {
    let config=std::env::current_exe().ok().and_then(|p|p.parent().map(|d|d.join("manager.public.json")));
    config.and_then(|p|std::fs::read(p).ok()).and_then(|b|serde_json::from_slice::<serde_json::Value>(&b).ok())
        .and_then(|v|v.get("updateBaseUrl").and_then(|s|s.as_str()).map(str::to_owned))
        .filter(|s|meow_launcher_core::update::validate_base(s).is_ok()).unwrap_or_default()
}
#[tauri::command]
fn manager_about()->serde_json::Value {serde_json::json!({"product":"MeowGM","author":env!("CARGO_PKG_AUTHORS"),"version":env!("MEOW_MANAGER_DISPLAY_VERSION"),"edition":"unified","notes":"统一版本 · 手动配置服务器，本机保存连接信息","productMarker":meow_launcher_core::update::Program::Manager.marker()})}
#[tauri::command]
async fn manager_check_update()->meow_launcher_core::Result<meow_launcher_core::update::UpdateStatus> {meow_launcher_core::update::check(&manager_update_base(),env!("CARGO_PKG_VERSION"),"manager-v1",meow_launcher_core::update::Program::Manager).await}
#[tauri::command]
async fn manager_download_update(state:tauri::State<'_,UpdateState>)->meow_launcher_core::Result<meow_launcher_core::update::Downloaded> {state.updater.download(&state.data.join("updates")).await}
#[tauri::command]
fn manager_open_update(state:tauri::State<UpdateState>)->meow_launcher_core::Result<()> {open::that(state.updater.downloaded_directory()?).map_err(|_|meow_launcher_core::error("folder_open","无法打开更新目录。"))}
#[tauri::command]
fn manager_open_publication(state:tauri::State<UpdateState>,id:String)->Result<(),String>{
    if id.len()!=32||!id.bytes().all(|b|b.is_ascii_hexdigit()){return Err("发布编号不正确".into());}
    let root=state.data.join("data/client-publications").canonicalize().map_err(|_|"发布目录不存在")?;
    let path=root.join(id).canonicalize().map_err(|_|"发布目录不存在")?;
    if !path.starts_with(&root)||!path.is_dir(){return Err("发布目录无效".into());}
    open::that(path).map_err(|_|"无法打开发布目录".into())
}
struct Backend(Mutex<Option<Child>>);
impl Drop for Backend { fn drop(&mut self) { if let Ok(slot)=self.0.get_mut() { if let Some(mut child)=slot.take() {let _=child.kill();let _=child.wait();} } } }
#[tauri::command]
async fn choose_package_directory()->Option<String> {
    rfd::AsyncFileDialog::new().set_title("选择待发布客户端目录").pick_folder().await.map(|p|p.path().display().to_string())
}
#[tauri::command]
async fn choose_pvf_file()->Option<String> {
    rfd::AsyncFileDialog::new().set_title("选择 PVF 或加密分发包（仅处理副本）").add_filter("PVF 与分发包", &["pvf", "oopvf"]).pick_file().await.map(|p|p.path().display().to_string())
}
#[tauri::command]
async fn choose_pvf_key()->Option<String> {
    rfd::AsyncFileDialog::new().set_title("选择独立密钥（不会加入分发包）").add_filter("密钥", &["key"]).pick_file().await.map(|p|p.path().display().to_string())
}
#[tauri::command]
fn manager_open_pvf(state:tauri::State<UpdateState>,id:String)->Result<(),String>{
    if id.len()!=32||!id.bytes().all(|b|b.is_ascii_hexdigit()){return Err("处理编号不正确".into());}
    let root=state.data.join("data/pvf-protections").canonicalize().map_err(|_|"副本目录不存在")?;
    let path=root.join(id).canonicalize().map_err(|_|"副本目录不存在")?;
    if !path.starts_with(&root)||!path.is_dir(){return Err("副本目录无效".into());}
    open::that(path).map_err(|_|"无法打开副本目录".into())
}
#[tauri::command]
fn manager_window_action(window:tauri::WebviewWindow,action:String)->Result<(),String> {
    let result=match action.as_str() {
        "close"=>window.close(),
        "minimize"=>window.minimize(),
        "drag"=>window.start_dragging(),
        "maximize"=>match window.is_maximized(){Ok(true)=>window.unmaximize(),Ok(false)=>window.maximize(),Err(e)=>Err(e)},
        _=>return Err("不支持的窗口操作".into()),
    };
    result.map_err(|_|"窗口操作未完成".into())
}
fn main(){
    let mut context=tauri::generate_context!();
    if meow_launcher_core::edition::is_sponsor(){context.config_mut().identifier="com.meow.gm.sponsor".into();}
    // Explicit alternate data roots own separate instances; never focus a different operator profile.
    if let Some(root)=std::env::var_os("OO_MANAGER_DATA") {
        let digest=format!("{:x}",Sha256::digest(root.to_string_lossy().as_bytes()));
        context.config_mut().identifier=format!("com.meowopia.oo-manager.profile-{}",&digest[..16]);
    }
    let app=tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![choose_package_directory,choose_pvf_file,choose_pvf_key,manager_open_pvf,manager_window_action,manager_about,manager_check_update,manager_download_update,manager_open_update,manager_open_publication])
        .plugin(tauri_plugin_single_instance::init(|app,_,_|{if let Some(window)=app.get_webview_window("main"){let _=window.unminimize();let _=window.set_focus();}}))
        .setup(|app|{
            let data=std::env::var_os("OO_MANAGER_DATA").map(std::path::PathBuf::from).unwrap_or(app.path().app_local_data_dir()?);std::fs::create_dir_all(&data)?;
            app.manage(UpdateState{updater:meow_launcher_core::update::Updater::new(&manager_update_base(),meow_launcher_core::update::Program::Manager,"manager-v1",env!("CARGO_PKG_VERSION")),data:data.clone()});
            let payload=include_bytes!("../binaries/oo-manager-host.exe");
            let digest=format!("{:x}",Sha256::digest(payload));
            let runtime=data.join("runtime").join(&digest);std::fs::create_dir_all(&runtime)?;
            let executable=runtime.join("oo-manager-host.exe");
            if !executable.exists() || Sha256::digest(std::fs::read(&executable)?).as_slice()!=Sha256::digest(payload).as_slice(){std::fs::write(&executable,payload)?;}
            let diagnostics=data.join("logs");std::fs::create_dir_all(&diagnostics)?;
            let errors=std::fs::OpenOptions::new().create(true).append(true).open(diagnostics.join("backend-startup.log"))?;
            let mut child=Command::new(executable).env("OO_MANAGER_DATA",data.join("data")).env("OO_MANAGER_PARENT",std::process::id().to_string()).env("MEOW_MANAGER_VERSION",env!("MEOW_MANAGER_DISPLAY_VERSION")).creation_flags(0x08000000).stdin(Stdio::null()).stdout(Stdio::piped()).stderr(Stdio::from(errors)).spawn()?;
            let stdout=child.stdout.take().ok_or("管理服务启动失败")?;
            app.manage(Backend(Mutex::new(Some(child))));
            let (sender,receiver)=std::sync::mpsc::channel();
            std::thread::spawn(move||{let mut line=String::new();let result=BufReader::new(stdout).read_line(&mut line).map(|_|line);let _=sender.send(result);});
            let line=receiver.recv_timeout(Duration::from_secs(45))??;
            let ready:serde_json::Value=serde_json::from_str(&line)?;
            let port=ready["port"].as_u64().filter(|p|*p>0&&*p<=65535).ok_or("管理服务端口无效")?;
            let nonce=ready["setup"].as_str().unwrap_or("");
            let address=format!("http://127.0.0.1:{port}/#setup={nonce}");
            let mut window=tauri::WebviewWindowBuilder::new(app,"main",tauri::WebviewUrl::External(address.parse()?))
                .title("MeowGM · 服务器运营管理器").inner_size(1280.0,900.0).min_inner_size(900.0,650.0).center()
                .decorations(false)
                .data_directory(data.join("webview"))
                .focused(true)
                .on_navigation(move |url|url.scheme()=="http"&&url.host_str()==Some("127.0.0.1")&&url.port()==Some(port as u16));
            if let Ok(arguments)=std::env::var("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"){window=window.additional_browser_args(&arguments);}
            let window=window.build()?;
            window.set_icon(tauri::image::Image::new_owned(include_bytes!("../icons/amoei.rgba").to_vec(),32,32))?;
            Ok(())
        }).build(context).expect("MeowGM 启动失败");
    app.run(|app,event|{if matches!(event,tauri::RunEvent::Exit){if let Some(state)=app.try_state::<Backend>(){if let Ok(mut slot)=state.0.lock(){if let Some(mut child)=slot.take(){let _=child.kill();let _=child.wait();}}}}});
}
