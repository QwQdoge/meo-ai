//! Meo Account OAuth 2.1 (authorization code + PKCE) for public clients.

use base64::{engine::general_purpose::URL_SAFE_NO_PAD, Engine};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};
use thiserror::Error;
use url::Url;

use super::now_secs;

pub const SCOPES: &str = "openid email profile offline_access meo:read meo:write";

#[derive(Debug, Error)]
pub enum AuthError {
    #[error("sign-in was cancelled or denied: {0}")]
    Denied(String),
    #[error("sign-in response did not match this request")]
    StateMismatch,
    #[error("sign-in response is missing the authorization code")]
    MissingCode,
    #[error("Meo Account returned HTTP {status}: {code}")]
    Status { status: u16, code: String },
    #[error("network request failed: {0}")]
    Http(#[from] reqwest::Error),
    #[error("invalid Meo Account response: {0}")]
    Invalid(String),
}

#[derive(Debug, Clone)]
pub struct OAuthConfig {
    pub account_origin: String,
    pub api_origin: String,
    pub client_id: String,
    pub redirect_uri: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Session {
    pub access_token: String,
    pub refresh_token: String,
    pub expires_at: i64,
    #[serde(default)]
    pub email: String,
    #[serde(default)]
    pub sub: String,
}

impl Session {
    pub fn needs_refresh(&self) -> bool {
        now_secs() >= self.expires_at - 60
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PendingAuthorization {
    pub state: String,
    pub verifier: String,
    pub url: String,
}

pub(crate) fn random_token(bytes: usize) -> String {
    let mut buffer = vec![0u8; bytes];
    getrandom::getrandom(&mut buffer).expect("system random source unavailable");
    URL_SAFE_NO_PAD.encode(buffer)
}

pub fn code_challenge(verifier: &str) -> String {
    URL_SAFE_NO_PAD.encode(Sha256::digest(verifier.as_bytes()))
}

pub fn begin(config: &OAuthConfig) -> PendingAuthorization {
    let verifier = random_token(48);
    let state = random_token(24);
    let mut url = Url::parse(&format!(
        "{}/v1/auth/oauth2/authorize",
        config.account_origin
    ))
    .expect("account origin is a valid URL");
    url.query_pairs_mut()
        .append_pair("response_type", "code")
        .append_pair("client_id", &config.client_id)
        .append_pair("redirect_uri", &config.redirect_uri)
        .append_pair("scope", SCOPES)
        .append_pair("state", &state)
        .append_pair("code_challenge", &code_challenge(&verifier))
        .append_pair("code_challenge_method", "S256")
        .append_pair("resource", &config.api_origin);
    PendingAuthorization {
        state,
        verifier,
        url: url.into(),
    }
}

/// Validates a redirect such as `meoai://auth/callback?code=..&state=..`.
pub fn parse_callback(callback: &str, expected_state: &str) -> Result<String, AuthError> {
    let url = Url::parse(callback).map_err(|e| AuthError::Invalid(e.to_string()))?;
    let get = |key: &str| {
        url.query_pairs()
            .find(|(k, _)| k == key)
            .map(|(_, v)| v.into_owned())
    };
    if let Some(error) = get("error") {
        return Err(AuthError::Denied(error));
    }
    if get("state").as_deref() != Some(expected_state) {
        return Err(AuthError::StateMismatch);
    }
    get("code")
        .filter(|c| !c.is_empty())
        .ok_or(AuthError::MissingCode)
}

pub async fn exchange(
    http: &reqwest::Client,
    config: &OAuthConfig,
    code: &str,
    verifier: &str,
) -> Result<Session, AuthError> {
    let mut session = token_request(
        http,
        config,
        &[
            ("grant_type", "authorization_code"),
            ("code", code),
            ("code_verifier", verifier),
            ("redirect_uri", &config.redirect_uri),
            ("client_id", &config.client_id),
            ("resource", &config.api_origin),
        ],
        None,
    )
    .await?;
    if let Ok((sub, email)) = user_info(http, config, &session.access_token).await {
        session.sub = sub;
        session.email = email;
    }
    Ok(session)
}

pub async fn refresh(
    http: &reqwest::Client,
    config: &OAuthConfig,
    previous: &Session,
) -> Result<Session, AuthError> {
    let mut session = token_request(
        http,
        config,
        &[
            ("grant_type", "refresh_token"),
            ("refresh_token", &previous.refresh_token),
            ("client_id", &config.client_id),
            ("resource", &config.api_origin),
        ],
        Some(&previous.refresh_token),
    )
    .await?;
    session.email = previous.email.clone();
    session.sub = previous.sub.clone();
    Ok(session)
}

async fn token_request(
    http: &reqwest::Client,
    config: &OAuthConfig,
    form: &[(&str, &str)],
    fallback_refresh: Option<&str>,
) -> Result<Session, AuthError> {
    let response = http
        .post(format!("{}/v1/auth/oauth2/token", config.account_origin))
        .form(form)
        .send()
        .await?;
    let status = response.status().as_u16();
    let body: Value = response.json().await.unwrap_or(Value::Null);
    if !(200..300).contains(&status) {
        let code = body
            .get("error")
            .and_then(|e| e.as_str().or_else(|| e.get("code").and_then(Value::as_str)))
            .unwrap_or("token_request_failed")
            .to_owned();
        return Err(AuthError::Status { status, code });
    }
    let access_token = body["access_token"]
        .as_str()
        .ok_or_else(|| AuthError::Invalid("missing access_token".into()))?
        .to_owned();
    let refresh_token = body["refresh_token"]
        .as_str()
        .or(fallback_refresh)
        .ok_or_else(|| AuthError::Invalid("missing refresh_token".into()))?
        .to_owned();
    let expires_at = body["expires_at"]
        .as_i64()
        .filter(|t| *t > now_secs())
        .unwrap_or_else(|| now_secs() + body["expires_in"].as_i64().unwrap_or(3600));
    Ok(Session {
        access_token,
        refresh_token,
        expires_at,
        email: String::new(),
        sub: String::new(),
    })
}

async fn user_info(
    http: &reqwest::Client,
    config: &OAuthConfig,
    token: &str,
) -> Result<(String, String), AuthError> {
    let body: Value = http
        .get(format!("{}/v1/auth/oauth2/userinfo", config.account_origin))
        .bearer_auth(token)
        .send()
        .await?
        .json()
        .await?;
    Ok((
        body["sub"].as_str().unwrap_or_default().to_owned(),
        body["email"].as_str().unwrap_or_default().to_owned(),
    ))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn config() -> OAuthConfig {
        OAuthConfig {
            account_origin: "https://account.example".into(),
            api_origin: "https://api.example".into(),
            client_id: "client".into(),
            redirect_uri: "meoai://auth/callback".into(),
        }
    }

    #[test]
    fn pkce_challenge_matches_rfc7636_example() {
        assert_eq!(
            code_challenge("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk"),
            "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM"
        );
    }

    #[test]
    fn authorize_url_carries_pkce_state_and_resource() {
        let pending = begin(&config());
        let url = Url::parse(&pending.url).unwrap();
        let q: std::collections::HashMap<_, _> = url.query_pairs().into_owned().collect();
        assert_eq!(q["code_challenge"], code_challenge(&pending.verifier));
        assert_eq!(q["state"], pending.state);
        assert_eq!(q["resource"], "https://api.example");
        assert_eq!(q["code_challenge_method"], "S256");
    }

    #[test]
    fn callback_rejects_wrong_state_and_errors() {
        assert!(matches!(
            parse_callback("meoai://auth/callback?code=x&state=bad", "good"),
            Err(AuthError::StateMismatch)
        ));
        assert!(matches!(
            parse_callback(
                "meoai://auth/callback?error=access_denied&state=good",
                "good"
            ),
            Err(AuthError::Denied(_))
        ));
        assert_eq!(
            parse_callback("meoai://auth/callback?code=abc&state=good", "good").unwrap(),
            "abc"
        );
    }
}
