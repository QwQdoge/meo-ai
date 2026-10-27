//! Meo runner: the headless device side of Work.
//!
//! Run it on a computer you own and sign in once. The device then announces itself to the rest of
//! your account ("Run on" in Work), and tasks sent from the web, phone or another desktop run here,
//! in the folder you chose, with the same file and command tools as the desktop app. Nothing listens
//! on the network: the runner only connects out to Meo API. Passwords asked by a command are never
//! typed remotely; a headless runner refuses them.
//!
//!   meo-runner [--name "Studio Mac"] [--folder ~/code/project]

use std::{
    env,
    io::{BufRead, BufReader, Write},
    net::TcpListener,
    sync::{Arc, Mutex},
    time::Duration,
};

use meo_ai_core::cloud::{self, Action, AppCore, FileStorage, OAuthConfig, PlatformHooks};
use serde_json::{json, Value};

struct Hooks {
    callbacks: Mutex<Option<tokio::sync::mpsc::UnboundedSender<String>>>,
}

fn open_browser(url: &str) {
    let (program, args): (&str, Vec<&str>) = if cfg!(target_os = "macos") {
        ("open", vec![url])
    } else if cfg!(target_os = "windows") {
        ("cmd", vec!["/c", "start", "", url])
    } else {
        ("xdg-open", vec![url])
    };
    if std::process::Command::new(program).args(args).spawn().is_err() {
        eprintln!("Open this address in a browser to sign in:\n{url}");
    }
}

/// Waits for the one browser redirect to the loopback callback (RFC 8252).
fn listen_for_callback(sender: tokio::sync::mpsc::UnboundedSender<String>) {
    let listener = match TcpListener::bind(("127.0.0.1", cloud::DESKTOP_LOOPBACK_PORT)) {
        Ok(l) => l,
        Err(e) => {
            eprintln!("The sign-in callback port {} is busy: {e}", cloud::DESKTOP_LOOPBACK_PORT);
            return;
        }
    };
    std::thread::spawn(move || {
        for mut stream in listener.incoming().flatten() {
            let mut line = String::new();
            if BufReader::new(&stream).read_line(&mut line).is_err() {
                continue;
            }
            let path = line.split_whitespace().nth(1).unwrap_or("/").to_owned();
            if !path.starts_with("/callback") {
                let _ = stream.write_all(b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n");
                continue;
            }
            let body = "<!doctype html><meta charset=utf-8><title>Meo runner</title><body style=\"font-family:sans-serif;text-align:center;padding-top:20vh\"><h2>This computer is connected to Meo AI</h2><p>You can close this tab.</p>";
            let _ = write!(
                stream,
                "HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}",
                body.len(),
                body
            );
            let _ = sender.send(format!("http://127.0.0.1:{}{}", cloud::DESKTOP_LOOPBACK_PORT, path));
            break;
        }
    });
}

impl PlatformHooks for Hooks {
    fn changed(&self) {}
    fn open_url(&self, url: &str) {
        if let Some(sender) = self.callbacks.lock().unwrap().clone() {
            listen_for_callback(sender);
        }
        open_browser(url);
    }
}

fn flag(args: &[String], name: &str) -> Option<String> {
    args.iter().position(|a| a == name).and_then(|i| args.get(i + 1)).cloned()
}

fn expand(path: &str) -> String {
    match (path.strip_prefix("~/"), env::var("HOME")) {
        (Some(rest), Ok(home)) => format!("{home}/{rest}"),
        _ => path.to_owned(),
    }
}

#[tokio::main]
async fn main() {
    let args: Vec<String> = env::args().collect();
    // sudo/git/ssh started by a task call this binary to ask for a password; a headless runner refuses.
    if let Some(code) = meo_ai_core::cloud::host::askpass_main(&args) {
        std::process::exit(code);
    }
    if args.iter().any(|a| a == "--help" || a == "-h") {
        println!("meo-runner [--name <device name>] [--folder <work folder>]\nSign in once in the browser; then leave it running. Stop with Ctrl-C.");
        return;
    }

    let (callback_tx, mut callback_rx) = tokio::sync::mpsc::unbounded_channel::<String>();
    let core = AppCore::new(
        OAuthConfig {
            account_origin: env::var("MEO_ACCOUNT_ORIGIN").unwrap_or_else(|_| cloud::ACCOUNT_ORIGIN.into()),
            api_origin: env::var("MEO_API_ORIGIN").unwrap_or_else(|_| cloud::API_ORIGIN.into()),
            client_id: cloud::DESKTOP_CLIENT_ID.into(),
            redirect_uri: cloud::DESKTOP_REDIRECT_URI.into(),
        },
        Arc::new(FileStorage::default_location()),
        Arc::new(Hooks { callbacks: Mutex::new(Some(callback_tx)) }),
    );

    let forwarded = core.clone();
    tokio::spawn(async move {
        while let Some(url) = callback_rx.recv().await {
            forwarded.dispatch(Action::AuthCallback { url }).await;
        }
    });

    let host_locale = env::var("LC_ALL").or_else(|_| env::var("LANG")).unwrap_or_default();
    core.dispatch(Action::SetLocale { locale: host_locale }).await;
    core.dispatch(Action::Start).await;
    if let Some(name) = flag(&args, "--name") {
        core.dispatch(Action::SetSetting { binding: "remote.name".into(), value: json!(name) }).await;
    }
    if let Some(folder) = flag(&args, "--folder") {
        core.dispatch(Action::SetSetting { binding: "work.workspace".into(), value: json!(expand(&folder)) }).await;
    }

    let realtime = core.clone();
    tokio::spawn(async move { realtime.dispatch(Action::Realtime).await });

    let mut announced = false;
    let mut asked_sign_in = false;
    let mut refused_prompt = false;
    println!("Meo runner started. Press Ctrl-C to stop.");
    let mut tick = tokio::time::interval(Duration::from_secs(1));
    loop {
        tokio::select! {
            _ = tokio::signal::ctrl_c() => { println!("Stopped."); return; }
            _ = tick.tick() => {}
        }
        let view: Value = core.view();
        let state = view["auth"]["state"].as_str().unwrap_or("");
        if state == "signed_in" {
            if !announced {
                announced = true;
                println!("Signed in as {}. This computer is ready for Work tasks.", view["auth"]["email"].as_str().unwrap_or(""));
            }
        } else if !asked_sign_in && matches!(state, "signed_out" | "") && view["page"]["kind"] == "sign_in" {
            asked_sign_in = true;
            println!("Sign in with Meo Account in the browser that just opened.");
            core.dispatch(Action::SignIn).await;
        }
        // A command asked for a password: only the person at this computer could answer it.
        let secret = view["dialog"]["input"]["secret"] == true;
        if secret && !refused_prompt {
            refused_prompt = true;
            eprintln!("A command asked for a password; the headless runner refused it.");
            core.dispatch(Action::CancelPassword).await;
        } else if !secret {
            refused_prompt = false;
        }
    }
}
