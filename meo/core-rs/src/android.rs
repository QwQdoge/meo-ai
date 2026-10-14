use jni::{
    objects::{JClass, JString},
    sys::jstring,
    JNIEnv,
};
use serde_json::json;

use crate::{decode_sse_line, ContentBlock};

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
