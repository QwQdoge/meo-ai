package org.meo.ai.model

import org.json.JSONArray
import org.json.JSONObject
import java.util.UUID

data class OAuthSession(
    val accessToken: String,
    val refreshToken: String,
    val expiresAtEpochSeconds: Long,
    val userId: String = "",
    val email: String = "",
)

data class PendingOAuth(
    val state: String,
    val verifier: String,
)

data class Conversation(
    val id: String,
    val title: String,
    val updatedAt: String,
)

data class Credential(
    val id: String,
    val provider: String,
    val displayName: String,
    val defaultModel: String,
    val enabled: Boolean,
)

data class AiModel(
    val id: String,
    val name: String,
    val description: String,
)

data class ConsentPreview(
    val requestId: String,
    val payloadSha256: String,
    val expiresAt: String,
    val provider: String,
    val providerName: String,
    val destination: String,
    val model: String,
)

data class UiMessage(
    val id: String = UUID.randomUUID().toString(),
    val role: String,
    val text: String,
    val blocksJson: String = markdownBlocks(text),
) {
    companion object {
        fun user(text: String) = UiMessage(role = "user", text = text, blocksJson = "[]")
        fun assistant(text: String) = UiMessage(role = "assistant", text = text)
    }
}

data class PendingSend(
    val text: String,
    val userPrompt: String,
    val dataCategories: List<String>,
    val consent: ConsentPreview,
)

fun markdownBlocks(text: String): String {
    if (text.isBlank()) return "[]"
    return JSONArray().put(
        JSONObject()
            .put("type", "markdown")
            .put("block_id", "android:${UUID.randomUUID()}")
            .put("text", text),
    ).toString()
}
