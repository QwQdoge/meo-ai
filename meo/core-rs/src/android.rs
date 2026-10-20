use std::{
    panic::{catch_unwind, AssertUnwindSafe},
    sync::Arc,
};

use jni::{
    objects::{GlobalRef, JClass, JObject, JString},
    sys::{jlong, jstring},
    JNIEnv, JavaVM,
};
use serde_json::json;
use tokio::runtime::{Builder, Runtime};

use crate::{
    cloud::{self, Action, AppCore, FileStorage, OAuthConfig, PlatformHooks},
    decode_sse_line, ContentBlock,
};

fn to_java_string(env: &mut JNIEnv<'_>, value: String) -> jstring {
    env.new_string(value)
        .map(|value| value.into_raw())
        .unwrap_or(std::ptr::null_mut())
}

fn java_string(env: &mut JNIEnv<'_>, value: JString<'_>) -> Result<String, String> {
    env.get_string(&value)
        .map(|value| value.into())
        .map_err(|error| error.to_string())
}

#[no_mangle]
pub extern "system" fn Java_org_meo_ai_core_MeoCore_normalizeSseEvent(
    mut env: JNIEnv,
    _class: JClass,
    line: JString,
) -> jstring {
    let result = java_string(&mut env, line)
        .and_then(|line| decode_sse_line(&line).map_err(|error| error.to_string()))
        .and_then(|event| serde_json::to_string(&event).map_err(|error| error.to_string()));

    match result {
        Ok(json) => to_java_string(&mut env, json),
        Err(error) => to_java_string(&mut env, json!({"error": error}).to_string()),
    }
}

#[no_mangle]
pub extern "system" fn Java_org_meo_ai_core_MeoCore_normalizeBlocks(
    mut env: JNIEnv,
    _class: JClass,
    blocks_json: JString,
) -> jstring {
    let result = java_string(&mut env, blocks_json)
        .and_then(|raw| {
            serde_json::from_str::<Vec<ContentBlock>>(&raw).map_err(|error| error.to_string())
        })
        .and_then(|blocks| serde_json::to_string(&blocks).map_err(|error| error.to_string()));

    match result {
        Ok(json) => to_java_string(&mut env, json),
        Err(error) => to_java_string(&mut env, json!({"error": error}).to_string()),
    }
}

// ---- Cloud application core ------------------------------------------------
//
// Kotlin (`org.meo.ai.core.CloudCore`) owns an opaque handle. It renders the
// JSON from `nativeView` and sends action objects back through
// `nativeDispatch`; sign-in, API calls, caching and navigation stay in Rust.

struct Native {
    core: AppCore,
    runtime: Runtime,
    /// `true` once `Action::Start` has finished. A sign-in redirect can launch
    /// the app cold, so the callback must wait for the saved state to load.
    started: tokio::sync::watch::Sender<bool>,
}

/// Calls back into the Kotlin `CloudCoreListener` from any core thread.
struct JavaHooks {
    vm: JavaVM,
    listener: GlobalRef,
}

impl JavaHooks {
    fn call(&self, method: &str, signature: &str, arguments: &[&str]) {
        let Ok(mut env) = self.vm.attach_current_thread() else {
            return;
        };
        let strings: Result<Vec<_>, _> =
            arguments.iter().map(|text| env.new_string(text)).collect();
        let result = match strings {
            Ok(strings) => {
                let values: Vec<jni::objects::JValue> = strings
                    .iter()
                    .map(|s| jni::objects::JValue::Object(s))
                    .collect();
                env.call_method(&self.listener, method, signature, &values)
            }
            Err(error) => Err(error),
        };
        if result.is_err() {
            // Never leave a pending Java exception on a core thread.
            let _ = env.exception_clear();
        }
    }
}

impl PlatformHooks for JavaHooks {
    fn changed(&self) {
        self.call("onChanged", "()V", &[]);
    }

    fn open_url(&self, url: &str) {
        self.call("onOpenUrl", "(Ljava/lang/String;)V", &[url]);
    }

    fn busy(&self, busy: bool) {
        let Ok(mut env) = self.vm.attach_current_thread() else {
            return;
        };
        if env
            .call_method(
                &self.listener,
                "onBusy",
                "(Z)V",
                &[jni::objects::JValue::Bool(busy as u8)],
            )
            .is_err()
        {
            let _ = env.exception_clear();
        }
    }

    fn notify(&self, title: &str, text: &str) {
        self.call(
            "onNotify",
            "(Ljava/lang/String;Ljava/lang/String;)V",
            &[title, text],
        );
    }
}

fn build_native(
    env: &mut JNIEnv<'_>,
    data_dir: JString<'_>,
    client_id: JString<'_>,
    listener: JObject<'_>,
) -> Result<Native, String> {
    let data_dir = java_string(env, data_dir)?;
    let client_id = java_string(env, client_id)?;
    let hooks = JavaHooks {
        vm: env.get_java_vm().map_err(|e| e.to_string())?,
        listener: env.new_global_ref(listener).map_err(|e| e.to_string())?,
    };
    let runtime = Builder::new_multi_thread()
        .worker_threads(2)
        .enable_all()
        .build()
        .map_err(|e| e.to_string())?;
    let core = AppCore::new(
        OAuthConfig {
            account_origin: cloud::ACCOUNT_ORIGIN.into(),
            api_origin: cloud::API_ORIGIN.into(),
            client_id: if client_id.trim().is_empty() {
                cloud::ANDROID_CLIENT_ID.into()
            } else {
                client_id
            },
            redirect_uri: cloud::ANDROID_REDIRECT_URI.into(),
        },
        Arc::new(FileStorage::new(data_dir)),
        Arc::new(hooks),
    );
    Ok(Native {
        core,
        runtime,
        started: tokio::sync::watch::channel(false).0,
    })
}

/// Returns an opaque handle, or 0 when the core could not be created.
#[no_mangle]
pub extern "system" fn Java_org_meo_ai_core_CloudCore_nativeCreate(
    mut env: JNIEnv,
    _class: JClass,
    data_dir: JString,
    client_id: JString,
    listener: JObject,
) -> jlong {
    catch_unwind(AssertUnwindSafe(|| {
        match build_native(&mut env, data_dir, client_id, listener) {
            Ok(native) => Box::into_raw(Box::new(native)) as jlong,
            Err(_) => 0,
        }
    }))
    .unwrap_or(0)
}

/// # Safety
/// `handle` must come from `nativeCreate` and not yet have been destroyed;
/// the Kotlin wrapper guarantees both.
unsafe fn native<'a>(handle: jlong) -> Option<&'a Native> {
    (handle != 0).then(|| &*(handle as *const Native))
}

#[no_mangle]
pub extern "system" fn Java_org_meo_ai_core_CloudCore_nativeView(
    mut env: JNIEnv,
    _class: JClass,
    handle: jlong,
) -> jstring {
    let view = catch_unwind(AssertUnwindSafe(|| {
        unsafe { native(handle) }
            .map(|n| n.core.view().to_string())
            .unwrap_or_else(|| "{}".into())
    }))
    .unwrap_or_else(|_| "{}".into());
    to_java_string(&mut env, view)
}

#[no_mangle]
pub extern "system" fn Java_org_meo_ai_core_CloudCore_nativeDispatch(
    mut env: JNIEnv,
    _class: JClass,
    handle: jlong,
    action: JString,
) {
    let Ok(action) = java_string(&mut env, action) else {
        return;
    };
    let _ = catch_unwind(AssertUnwindSafe(|| {
        let Some(native) = (unsafe { native(handle) }) else {
            return;
        };
        match serde_json::from_str::<Action>(&action) {
            Ok(action) => {
                let core = native.core.clone();
                let started = native.started.clone();
                native.runtime.spawn(async move {
                    match action {
                        Action::Start => {
                            core.dispatch(action).await;
                            started.send_replace(true);
                        }
                        Action::AuthCallback { .. } => {
                            let mut ready = started.subscribe();
                            let _ = ready.wait_for(|started| *started).await;
                            core.dispatch(action).await;
                        }
                        action => core.dispatch(action).await,
                    }
                });
            }
            Err(error) => tracing::warn!(%error, "ignored unknown action"),
        }
    }));
}

#[no_mangle]
pub extern "system" fn Java_org_meo_ai_core_CloudCore_nativeDestroy(
    _env: JNIEnv,
    _class: JClass,
    handle: jlong,
) {
    if handle != 0 {
        let native = unsafe { Box::from_raw(handle as *mut Native) };
        native.runtime.shutdown_background();
    }
}
