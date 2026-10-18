use std::env;
use std::net::{IpAddr, SocketAddr};
use std::sync::Arc;
use std::time::Duration;

use meo_ai_core::{
    capability_transport, register_builtin_capabilities, transport, MeoService,
    OpenAiCompatibleProvider, ProviderModel, ServiceConfig,
};
use tokio::net::TcpListener;
use tracing::{info, warn};
use tracing_subscriber::EnvFilter;

fn env_u64(name: &str, default: u64) -> u64 {
    env::var(name)
        .ok()
        .and_then(|value| value.parse::<u64>().ok())
        .unwrap_or(default)
}

fn env_usize(name: &str, default: usize) -> usize {
    env::var(name)
        .ok()
        .and_then(|value| value.parse::<usize>().ok())
        .unwrap_or(default)
}

fn argument_value(name: &str) -> Option<String> {
    let prefix = format!("{name}=");
    let mut args = env::args().skip(1);
    while let Some(argument) = args.next() {
        if argument == name {
            return args.next();
        }
        if let Some(value) = argument.strip_prefix(&prefix) {
            return Some(value.to_owned());
        }
    }
    None
}

fn parse_models(raw: &str) -> Vec<ProviderModel> {
    raw.split(',')
        .map(str::trim)
        .filter(|value| !value.is_empty())
        .map(|model_id| ProviderModel {
            model_id: model_id.to_owned(),
            label: model_id.to_owned(),
            provider: "configured".to_owned(),
            supports_vision: true,
            supports_tools: true,
        })
        .collect()
}

fn service_config() -> ServiceConfig {
    ServiceConfig {
        provider_start_timeout: Duration::from_secs(env_u64(
            "MEO_AI_PROVIDER_START_TIMEOUT_SECONDS",
            30,
        )),
        provider_idle_timeout: Duration::from_secs(env_u64(
            "MEO_AI_PROVIDER_IDLE_TIMEOUT_SECONDS",
            120,
        )),
        request_timeout: Duration::from_secs(env_u64("MEO_AI_REQUEST_TIMEOUT_SECONDS", 30 * 60)),
        retained_terminal_requests: env_usize("MEO_AI_RETAINED_TERMINAL_REQUESTS", 128),
        event_replay_limit: env_usize("MEO_AI_EVENT_REPLAY_LIMIT", 2048),
    }
}

fn build_service() -> Result<MeoService, Box<dyn std::error::Error>> {
    let service = MeoService::with_config(service_config());
    let endpoint = env::var("MEO_AI_PROVIDER_ENDPOINT").unwrap_or_default();
    let models = parse_models(&env::var("MEO_AI_MODELS").unwrap_or_default());

    if endpoint.trim().is_empty() || models.is_empty() {
        warn!(
            "no direct provider configured; Rust AgentService will expose health and conversation APIs but model requests will be unavailable"
        );
        return Ok(service);
    }

    let provider = OpenAiCompatibleProvider::new(
        "configured",
        endpoint,
        env::var("MEO_AI_PROVIDER_API_KEY").unwrap_or_default(),
        models,
    )?;
    service.register_provider(Arc::new(provider));
    Ok(service)
}

fn bind_addr() -> Result<SocketAddr, Box<dyn std::error::Error>> {
    let host = argument_value("--host")
        .or_else(|| env::var("MEO_AI_SERVICE_HOST").ok())
        .unwrap_or_else(|| "127.0.0.1".to_owned());
    let port = argument_value("--port")
        .or_else(|| env::var("MEO_AI_SERVICE_PORT").ok())
        .unwrap_or_else(|| "8765".to_owned())
        .parse::<u16>()?;
    let ip = host.parse::<IpAddr>().map_err(|_| {
        format!("Meo AgentService host must be a loopback IP address, got {host:?}")
    })?;
    if !ip.is_loopback() {
        return Err("Meo AgentService may only bind to loopback".into());
    }
    Ok(SocketAddr::new(ip, port))
}

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    tracing_subscriber::fmt()
        .with_env_filter(
            EnvFilter::try_from_default_env().unwrap_or_else(|_| EnvFilter::new("info")),
        )
        .with_target(false)
        .compact()
        .init();

    let self_check = env::args().any(|arg| arg == "--self-check");
    let mut service = build_service()?;
    if let Ok(file) = env::var("MEO_AI_SETTINGS_FILE") {
        service = service.with_preferences(meo_ai_core::settings::SettingsStore::open(file)?);
    }
    if let Ok(file) = env::var("MEO_AI_MEMORY_FILE") {
        service = service.with_memory(meo_ai_core::memory::MemoryStore::open(file)?);
    }
    let capabilities = service.capability_catalog();
    {
        let mut catalog = capabilities
            .write()
            .expect("capability catalog lock poisoned during startup");
        register_builtin_capabilities(&mut catalog)?;
    }

    if self_check {
        let capability_count = capabilities
            .read()
            .expect("capability catalog lock poisoned during self-check")
            .list()
            .len();
        println!(
            "{}",
            serde_json::json!({
                "agent": service.health_snapshot(),
                "capabilities": capability_count,
            })
        );
        return Ok(());
    }

    let address = bind_addr()?;
    let listener = TcpListener::bind(address).await?;
    let actual = listener.local_addr()?;
    info!(address = %actual, "Meo AgentService Rust runtime listening");

    let app = transport::router(service).merge(capability_transport::router(capabilities));
    axum::serve(listener, app)
        .with_graceful_shutdown(async {
            if tokio::signal::ctrl_c().await.is_err() {
                warn!("failed to install Ctrl-C shutdown handler");
            }
        })
        .await?;
    Ok(())
}
