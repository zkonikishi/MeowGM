fn main() {
    println!("cargo:rerun-if-changed=../version.json");
    let metadata: serde_json::Value = serde_json::from_str(
        &std::fs::read_to_string("../version.json").expect("GM version metadata")
    ).expect("GM version JSON");
    let display = metadata["version"].as_str().expect("GM display version");
    assert_eq!(metadata["semver"].as_str().unwrap(), std::env::var("CARGO_PKG_VERSION").unwrap(), "GM version mapping differs");
    println!("cargo:rustc-env=MEOW_MANAGER_DISPLAY_VERSION={display}");
    tauri_build::try_build(tauri_build::Attributes::new().windows_attributes(
        tauri_build::WindowsAttributes::new().window_icon_path("icons/amoei.ico")
    )).expect("manager Windows resources");
}
