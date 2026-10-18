package org.meo.ai.network

import org.json.JSONArray
import org.json.JSONObject
import org.meo.ai.model.AiModel
import org.meo.ai.model.ConsentPreview
import org.meo.ai.model.Conversation
import org.meo.ai.model.Credential
import org.meo.ai.model.OAuthSession
import org.meo.ai.model.UiMessage
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder
import java.time.Instant

class ApiException(
    val status: Int,
    val code: String,
    message: String = code,
) : Exception(message)

class MeoApiClient {
    fun exchangeCode(clientId: String, code: String, verifier: String): OAuthSession {
        val form = mapOf(
            "grant_type" to "authorization_code",
            "code" to code,
            "code_verifier" to verifier,
            "redirect_uri" to REDIRECT_URI,
            "client_id" to clientId,
            "resource" to API_BASE,
        )
        return tokenRequest(form)
    }

    fun refreshTokens(clientId: String, refreshToken: String): OAuthSession {
        return tokenRequest(
            mapOf(
                "grant_type" to "refresh_token",
                "refresh_token" to refreshToken,
                "client_id" to clientId,
                "resource" to API_BASE,
            ),
        )
    }

    fun userInfo(accessToken: String): Pair<String, String> {
        val data = requestJson(
            method = "GET",
            url = "$ACCOUNT_BASE/v1/auth/oauth2/userinfo",
            token = accessToken,
        )
        return data.optString("sub") to data.optString("email")
    }

    // Shared cloud personalization API. This is the transport adapter only;
    // Compose owns the platform-specific UI and local preference storage.
    fun getAiSettings(accessToken: String): JSONObject =
        requestJson("GET", "$API_BASE/v1/ai/settings", accessToken).getJSONObject("settings")

    fun saveAiSettings(
        accessToken: String,
        expectedVersion: Int,
        personalInstructions: String,
        memoryEnabled: Boolean,
    ): JSONObject {
        require(expectedVersion >= 0)
        val data = JSONObject()
            .put("expectedVersion", expectedVersion)
            .put("personalInstructions", personalInstructions)
            .put("memoryEnabled", memoryEnabled)
        return requestJson("PATCH", "$API_BASE/v1/ai/settings", accessToken, data)
            .getJSONObject("settings")
    }

    fun listPersonalMemories(accessToken: String, archived: Boolean = false): JSONArray {
        val suffix = if (archived) "?archived=true" else ""
        return requestJson("GET", "$API_BASE/v1/ai/memories$suffix", accessToken)
            .optJSONArray("memories") ?: JSONArray()
    }

    fun addPersonalMemory(accessToken: String, kind: String, content: String): JSONObject {
        val input = JSONObject().put("kind", kind).put("content", content)
        return requestJson("POST", "$API_BASE/v1/ai/memories", accessToken, input)
            .getJSONObject("memory")
    }

    fun updatePersonalMemory(
        accessToken: String,
        id: String,
        expectedVersion: Int,
        enabled: Boolean? = null,
        archived: Boolean? = null,
    ): JSONObject {
        val input = JSONObject().put("expectedVersion", expectedVersion)
        if (enabled != null) input.put("enabled", enabled)
        if (archived != null) input.put("archived", archived)
        return requestJson(
            "PATCH",
            "$API_BASE/v1/ai/memories/${encodePath(id)}",
            accessToken,
            input,
        ).getJSONObject("memory")
    }

    fun listConversations(accessToken: String): List<Conversation> {
        val data = requestJson("GET", "$API_BASE/v1/conversations", accessToken)
        val rows = data.optJSONArray("conversations") ?: JSONArray()
        return buildList {
            for (index in 0 until rows.length()) {
                val row = rows.optJSONObject(index) ?: continue
                val id = row.optString("id")
                if (id.isBlank()) continue
                add(
                    Conversation(
                        id = id,
                        title = row.optString("title").ifBlank { "New chat" },
                        updatedAt = row.optString("updated_at"),
                    ),
                )
            }
        }
    }

    fun createConversation(accessToken: String, title: String): Conversation {
        val data = requestJson(
            "POST",
            "$API_BASE/v1/conversations",
            accessToken,
            JSONObject().put("title", title.take(200)),
        )
        val row = data.getJSONObject("conversation")
        return Conversation(
            id = row.getString("id"),
            title = row.optString("title").ifBlank { "New chat" },
            updatedAt = row.optString("updated_at"),
        )
    }

    fun listMessages(accessToken: String, conversationId: String): List<UiMessage> {
        val data = requestJson(
            "GET",
            "$API_BASE/v1/conversations/${encodePath(conversationId)}/messages",
            accessToken,
        )
        val rows = data.optJSONArray("messages") ?: JSONArray()
        return buildList {
            for (index in 0 until rows.length()) {
                val row = rows.optJSONObject(index) ?: continue
                val role = row.optString("role")
                if (role != "user" && role != "assistant") continue
                val content = row.opt("content")
                val text = extractText(content)
                if (text.isBlank()) continue
                if (role == "user") {
                    add(UiMessage.user(text))
                } else {
                    val blocks = when (content) {
                        is JSONArray -> normalizeBlocks(content, text)
                        else -> null
                    }
                    add(UiMessage(role = "assistant", text = text, blocksJson = blocks ?: org.meo.ai.model.markdownBlocks(text)))
                }
            }
        }
    }

    fun appendMessage(accessToken: String, conversationId: String, role: String, content: String) {
        requestJson(
            "POST",
            "$API_BASE/v1/conversations/${encodePath(conversationId)}/messages",
            accessToken,
            JSONObject().put("role", role).put("content", content),
        )
    }

    fun listCredentials(accessToken: String): List<Credential> {
        val data = broker(accessToken, JSONObject().put("action", "list_credentials"))
        val rows = data.optJSONArray("credentials") ?: JSONArray()
        return buildList {
            for (index in 0 until rows.length()) {
                val row = rows.optJSONObject(index) ?: continue
                if (!row.optBoolean("enabled", true)) continue
                val id = row.optString("id")
                if (id.isBlank()) continue
                add(
                    Credential(
                        id = id,
                        provider = row.optString("provider"),
                        displayName = row.optString("displayName").ifBlank { row.optString("provider") },
                        defaultModel = row.optString("defaultModel"),
                        enabled = row.optBoolean("enabled", true),
                    ),
                )
            }
        }
    }

    fun listModels(accessToken: String, credentialId: String): List<AiModel> {
        val data = broker(
            accessToken,
            JSONObject()
                .put("action", "list_models")
                .put("credentialId", credentialId),
        )
        if (!data.optBoolean("supported", false)) return emptyList()
        val rows = data.optJSONArray("models") ?: JSONArray()
        return buildList {
            for (index in 0 until rows.length()) {
                val row = rows.optJSONObject(index) ?: continue
                val id = row.optString("id")
                if (id.isBlank()) continue
                add(
                    AiModel(
                        id = id,
                        name = row.optString("name").ifBlank { id },
                        description = row.optString("description"),
                    ),
                )
            }
        }
    }

    /** Chat context and consent are assembled by Meo API, never by Android. */
    fun prepareInference(
        accessToken: String,
        clientId: String,
        credentialId: String,
        model: String,
        userPrompt: String,
        dataCategories: List<String>,
        conversationId: String? = null,
    ): ConsentPreview {
        val payload = JSONObject()
            .put("credentialId", credentialId)
            .put("model", model)
            .put("prompt", userPrompt)
        if (conversationId != null) payload.put("conversationId", conversationId)
        val data = requestJson("POST", "$API_BASE/v1/chat/prepare", accessToken, payload)
        val consent = data.getJSONObject("consent")
        return ConsentPreview(
            requestId = consent.getString("requestId"),
            payloadSha256 = consent.getString("payloadSha256"),
            expiresAt = consent.optString("expiresAt"),
            provider = consent.optString("provider"),
            providerName = consent.optString("providerName").ifBlank { consent.optString("provider") },
            destination = consent.optString("destination"),
            model = consent.optString("model").ifBlank { model },
        )
    }

    fun streamInference(
        accessToken: String,
        clientId: String,
        credentialId: String,
        model: String,
        userPrompt: String,
        dataCategories: List<String>,
        consent: ConsentPreview,
        conversationId: String? = null,
        onDelta: (String) -> Unit,
    ) {
        val body = JSONObject()
            .put("credentialId", credentialId)
            .put("model", model)
            .put("prompt", userPrompt)
            .put("consent", JSONObject()
                .put("requestId", consent.requestId)
                .put("payloadSha256", consent.payloadSha256)
                .put("confirmationVersion", 1))
        if (conversationId != null) body.put("conversationId", conversationId)
        val connection = openConnection("$API_BASE/v1/chat/stream", "POST", accessToken)
        connection.setRequestProperty("Content-Type", "application/json; charset=utf-8")
        connection.setRequestProperty("Accept", "text/event-stream")
        connection.doOutput = true
        connection.outputStream.bufferedWriter(Charsets.UTF_8).use { it.write(body.toString()) }
        val status = connection.responseCode
        if (status !in 200..299) {
            val raw = connection.errorStream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
            connection.disconnect()
            throw apiError(status, raw)
        }

        var event = ""
        val dataLines = mutableListOf<String>()
        var providerError: String? = null
        fun dispatch() {
            if (dataLines.isEmpty()) {
                event = ""
                return
            }
            val raw = dataLines.joinToString("\n")
            when (event) {
                "delta" -> {
                    val payload = runCatching { JSONObject(raw) }.getOrNull()
                    val text = payload?.optString("text").orEmpty()
                    if (text.isNotEmpty()) onDelta(text)
                }
                "error" -> {
                    val payload = runCatching { JSONObject(raw) }.getOrNull()
                    providerError = payload?.optString("message").orEmpty().ifBlank { "AI provider stream failed" }
                }
            }
            event = ""
            dataLines.clear()
        }

        try {
            BufferedReader(InputStreamReader(connection.inputStream, Charsets.UTF_8)).use { reader ->
                while (true) {
                    val line = reader.readLine() ?: break
                    when {
                        line.startsWith("event:") -> event = line.substringAfter("event:").trim()
                        line.startsWith("data:") -> dataLines += line.substringAfter("data:").trim()
                        line.isBlank() -> dispatch()
                    }
                }
                dispatch()
            }
        } finally {
            connection.disconnect()
        }
        if (!providerError.isNullOrBlank()) throw ApiException(502, "stream_failed", providerError!!)
    }

    private fun tokenRequest(form: Map<String, String>): OAuthSession {
        val encoded = form.entries.joinToString("&") {
            "${urlEncode(it.key)}=${urlEncode(it.value)}"
        }
        val connection = openConnection("$ACCOUNT_BASE/v1/auth/oauth2/token", "POST", null)
        connection.setRequestProperty("Content-Type", "application/x-www-form-urlencoded")
        connection.doOutput = true
        connection.outputStream.bufferedWriter(Charsets.UTF_8).use { it.write(encoded) }
        val status = connection.responseCode
        val raw = responseText(connection, status)
        connection.disconnect()
        if (status !in 200..299) throw apiError(status, raw)
        val data = JSONObject(raw)
        val now = Instant.now().epochSecond
        val expiresAt = data.optLong("expires_at", 0L).takeIf { it > now }
            ?: now + data.optLong("expires_in", 3600L)
        return OAuthSession(
            accessToken = data.getString("access_token"),
            refreshToken = data.getString("refresh_token"),
            expiresAtEpochSeconds = expiresAt,
        )
    }

    private fun inferenceBody(
        action: String,
        clientId: String,
        credentialId: String,
        model: String,
        userPrompt: String,
        dataCategories: List<String>,
    ): JSONObject {
        return JSONObject()
            .put("action", action)
            .put("credentialId", credentialId)
            .put("clientId", clientId)
            .put("purpose", "meo_ai_android_chat")
            .put("dataCategories", JSONArray(dataCategories))
            .put("model", model)
            .put("userPrompt", userPrompt)
            .put("temperature", 0.7)
            .put("maxOutputTokens", 4096)
    }

    private fun broker(accessToken: String, body: JSONObject): JSONObject {
        return requestJson(
            "POST",
            "$API_BASE/v1/ai/provider-broker",
            accessToken,
            body,
        )
    }

    private fun requestJson(
        method: String,
        url: String,
        token: String?,
        body: JSONObject? = null,
    ): JSONObject {
        val connection = openConnection(url, method, token)
        if (body != null) {
            connection.setRequestProperty("Content-Type", "application/json; charset=utf-8")
            connection.doOutput = true
            connection.outputStream.bufferedWriter(Charsets.UTF_8).use { it.write(body.toString()) }
        }
        val status = connection.responseCode
        val raw = responseText(connection, status)
        connection.disconnect()
        if (status !in 200..299) throw apiError(status, raw)
        if (raw.isBlank()) return JSONObject()
        return runCatching { JSONObject(raw) }.getOrElse {
            throw ApiException(502, "invalid_server_response", "Meo API returned invalid JSON")
        }
    }

    private fun openConnection(url: String, method: String, token: String?): HttpURLConnection {
        return (URL(url).openConnection() as HttpURLConnection).apply {
            requestMethod = method
            connectTimeout = 15_000
            readTimeout = 130_000
            instanceFollowRedirects = false
            setRequestProperty("Accept", "application/json")
            setRequestProperty("Cache-Control", "no-store")
            setRequestProperty("User-Agent", "MeoAI-Android/0.1")
            if (!token.isNullOrBlank()) setRequestProperty("Authorization", "Bearer $token")
        }
    }

    private fun responseText(connection: HttpURLConnection, status: Int): String {
        val stream = if (status in 200..299) connection.inputStream else connection.errorStream
        return stream?.bufferedReader(Charsets.UTF_8)?.use { it.readText() }.orEmpty()
    }

    private fun apiError(status: Int, raw: String): ApiException {
        val payload = runCatching { JSONObject(raw) }.getOrNull()
        val error = payload?.opt("error")
        val code = when (error) {
            is JSONObject -> error.optString("code").ifBlank { "http_$status" }
            is String -> error.ifBlank { "http_$status" }
            else -> "http_$status"
        }
        val message = when (error) {
            is JSONObject -> error.optString("message").ifBlank { code }
            is String -> error
            else -> code
        }
        return ApiException(status, code, message)
    }

    private fun extractText(content: Any?): String {
        return when (content) {
            is JSONArray -> buildList {
                for (index in 0 until content.length()) {
                    val block = content.optJSONObject(index) ?: continue
                    val type = block.optString("type")
                    if (type == "text" || type == "markdown") {
                        block.optString("text").takeIf { it.isNotBlank() }?.let(::add)
                    }
                }
            }.joinToString("\n\n")
            is JSONObject -> content.optString("text")
            is String -> content
            else -> ""
        }
    }

    private fun normalizeBlocks(content: JSONArray, fallbackText: String): String? {
        var recognized = false
        val normalized = JSONArray()
        for (index in 0 until content.length()) {
            val block = content.optJSONObject(index) ?: continue
            when (block.optString("type")) {
                "markdown", "code", "table", "chart", "plugin", "html", "image", "tool_activity" -> {
                    recognized = true
                    normalized.put(block)
                }
                "text" -> {
                    recognized = true
                    normalized.put(
                        JSONObject()
                            .put("type", "markdown")
                            .put("block_id", "cloud:${block.optString("id", index.toString())}")
                            .put("text", block.optString("text")),
                    )
                }
            }
        }
        if (!recognized) return null
        if (normalized.length() == 0 && fallbackText.isNotBlank()) return null
        return normalized.toString()
    }

    private fun encodePath(value: String): String = urlEncode(value).replace("+", "%20")
    private fun urlEncode(value: String): String = URLEncoder.encode(value, Charsets.UTF_8.name())

    companion object {
        const val ACCOUNT_BASE = "https://account.meoarch.org"
        const val API_BASE = "https://api.meoarch.org"
        const val REDIRECT_URI = "org.meo.ai:/oauth/callback"
    }
}
