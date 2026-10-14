package org.meo.ai

import android.content.Intent
import android.net.Uri
import android.util.Base64
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import org.meo.ai.auth.SecureSessionStore
import org.meo.ai.model.AiModel
import org.meo.ai.model.ConsentPreview
import org.meo.ai.model.Conversation
import org.meo.ai.model.Credential
import org.meo.ai.model.OAuthSession
import org.meo.ai.model.PendingOAuth
import org.meo.ai.model.PendingSend
import org.meo.ai.model.UiMessage
import org.meo.ai.model.markdownBlocks
import org.meo.ai.network.ApiException
import org.meo.ai.network.MeoApiClient
import java.security.MessageDigest
import java.security.SecureRandom
import java.time.Instant
import java.util.UUID
import java.util.concurrent.Executors

data class MeoUiState(
    val signedIn: Boolean = false,
    val loading: Boolean = false,
    val streaming: Boolean = false,
    val email: String = "",
    val conversations: List<Conversation> = emptyList(),
    val currentConversationId: String? = null,
    val messages: List<UiMessage> = emptyList(),
    val credentials: List<Credential> = emptyList(),
    val selectedCredentialId: String? = null,
    val models: List<AiModel> = emptyList(),
    val selectedModelId: String? = null,
    val pendingSend: PendingSend? = null,
    val error: String? = null,
)

class MeoController(private val activity: MainActivity) {
    private val sessionStore = SecureSessionStore(activity)
    private val client = MeoApiClient()
    private val executor = Executors.newSingleThreadExecutor()

    var state by mutableStateOf(MeoUiState())
        private set

    init {
        if (sessionStore.loadSession() != null) bootstrap()
    }

    fun signIn() {
        val clientId = BuildConfig.MEO_OAUTH_CLIENT_ID.trim()
        if (clientId.isBlank()) {
            state = state.copy(error = "Android OAuth client is not configured yet.")
            return
        }
        val verifier = randomUrlSafe(48)
        val challenge = base64Url(
            MessageDigest.getInstance("SHA-256").digest(verifier.toByteArray(Charsets.US_ASCII)),
        )
        val oauthState = randomUrlSafe(24)
        sessionStore.savePendingOAuth(PendingOAuth(oauthState, verifier))
        val authorize = Uri.parse("${MeoApiClient.ACCOUNT_BASE}/v1/auth/oauth2/authorize")
            .buildUpon()
            .appendQueryParameter("client_id", clientId)
            .appendQueryParameter("redirect_uri", MeoApiClient.REDIRECT_URI)
            .appendQueryParameter("response_type", "code")
            .appendQueryParameter("scope", "openid email profile meo:read meo:write")
            .appendQueryParameter("resource", MeoApiClient.API_BASE)
            .appendQueryParameter("state", oauthState)
            .appendQueryParameter("code_challenge", challenge)
            .appendQueryParameter("code_challenge_method", "S256")
            .build()
        activity.startActivity(Intent(Intent.ACTION_VIEW, authorize))
    }

    fun handleOAuthCallback(uri: Uri?) {
        if (uri == null || uri.scheme != "org.meo.ai" || uri.path != "/oauth/callback") return
        val error = uri.getQueryParameter("error")
        if (!error.isNullOrBlank()) {
            sessionStore.clearPendingOAuth()
            state = state.copy(error = "Sign-in was not completed: $error")
            return
        }
        val code = uri.getQueryParameter("code").orEmpty()
        val returnedState = uri.getQueryParameter("state").orEmpty()
        val pending = sessionStore.loadPendingOAuth()
        if (code.isBlank() || pending == null || returnedState != pending.state) {
            sessionStore.clearPendingOAuth()
            state = state.copy(error = "The sign-in callback could not be verified.")
            return
        }
        state = state.copy(loading = true, error = null)
        executor.execute {
            try {
                val exchanged = client.exchangeCode(
                    BuildConfig.MEO_OAUTH_CLIENT_ID,
                    code,
                    pending.verifier,
                )
                val (userId, email) = client.userInfo(exchanged.accessToken)
                val session = exchanged.copy(userId = userId, email = email)
                sessionStore.saveSession(session)
                sessionStore.clearPendingOAuth()
                loadProductState(session)
            } catch (cause: Throwable) {
                postFailure(cause)
            }
        }
    }

    fun signOut() {
        sessionStore.clearSession()
        sessionStore.clearPendingOAuth()
        state = MeoUiState()
    }

    fun newChat() {
        state = state.copy(
            currentConversationId = null,
            messages = emptyList(),
            pendingSend = null,
            error = null,
        )
    }

    fun openConversation(id: String) {
        if (state.streaming || state.loading) return
        state = state.copy(loading = true, error = null)
        executor.execute {
            try {
                val session = ensureFreshSession()
                val messages = client.listMessages(session.accessToken, id)
                post {
                    state = state.copy(
                        loading = false,
                        currentConversationId = id,
                        messages = messages,
                    )
                }
            } catch (cause: Throwable) {
                postFailure(cause)
            }
        }
    }

    fun selectCredential(id: String) {
        if (state.streaming) return
        val credential = state.credentials.firstOrNull { it.id == id } ?: return
        state = state.copy(
            selectedCredentialId = id,
            models = emptyList(),
            selectedModelId = credential.defaultModel.takeIf { it.isNotBlank() },
            loading = true,
            error = null,
        )
        executor.execute {
            try {
                val session = ensureFreshSession()
                val models = client.listModels(session.accessToken, id)
                val selected = when {
                    credential.defaultModel.isNotBlank() -> credential.defaultModel
                    models.isNotEmpty() -> models.first().id
                    else -> null
                }
                post {
                    state = state.copy(
                        loading = false,
                        models = models,
                        selectedModelId = selected,
                    )
                }
            } catch (cause: Throwable) {
                postFailure(cause)
            }
        }
    }

    fun selectModel(id: String) {
        if (!state.streaming) state = state.copy(selectedModelId = id, error = null)
    }

    fun beginSend(text: String) {
        val clean = text.trim()
        if (clean.isBlank() || state.streaming || state.pendingSend != null) return
        val credentialId = state.selectedCredentialId
        val model = state.selectedModelId
        if (credentialId.isNullOrBlank()) {
            state = state.copy(error = "Add or select an AI connection first.")
            return
        }
        if (model.isNullOrBlank()) {
            state = state.copy(error = "Choose a model first.")
            return
        }
        val prompt = conversationPrompt(state.messages, clean)
        val categories = if (state.messages.isEmpty()) {
            listOf("chat_text")
        } else {
            listOf("chat_text", "conversation_context")
        }
        state = state.copy(loading = true, error = null)
        executor.execute {
            try {
                val session = ensureFreshSession()
                val preview = client.prepareInference(
                    accessToken = session.accessToken,
                    clientId = BuildConfig.MEO_OAUTH_CLIENT_ID,
                    credentialId = credentialId,
                    model = model,
                    userPrompt = prompt,
                    dataCategories = categories,
                )
                post {
                    state = state.copy(
                        loading = false,
                        pendingSend = PendingSend(clean, prompt, categories, preview),
                    )
                }
            } catch (cause: Throwable) {
                postFailure(cause)
            }
        }
    }

    fun cancelPendingSend() {
        state = state.copy(pendingSend = null)
    }

    fun confirmPendingSend() {
        val pending = state.pendingSend ?: return
        val credentialId = state.selectedCredentialId ?: return
        val model = state.selectedModelId ?: return
        val existingConversationId = state.currentConversationId
        val assistantId = UUID.randomUUID().toString()
        state = state.copy(pendingSend = null, streaming = true, loading = false, error = null)

        executor.execute {
            var conversationId = existingConversationId
            val output = StringBuilder()
            try {
                val session = ensureFreshSession()
                if (conversationId == null) {
                    val conversation = client.createConversation(session.accessToken, titleFor(pending.text))
                    conversationId = conversation.id
                    post {
                        state = state.copy(
                            currentConversationId = conversation.id,
                            conversations = listOf(conversation) + state.conversations.filterNot { it.id == conversation.id },
                        )
                    }
                }
                val id = requireNotNull(conversationId)
                client.appendMessage(session.accessToken, id, "user", pending.text)
                post {
                    state = state.copy(
                        messages = state.messages + UiMessage.user(pending.text) +
                            UiMessage(id = assistantId, role = "assistant", text = "", blocksJson = "[]"),
                    )
                }

                client.streamInference(
                    accessToken = session.accessToken,
                    clientId = BuildConfig.MEO_OAUTH_CLIENT_ID,
                    credentialId = credentialId,
                    model = model,
                    userPrompt = pending.userPrompt,
                    dataCategories = pending.dataCategories,
                    consent = pending.consent,
                ) { delta ->
                    output.append(delta)
                    val snapshot = output.toString()
                    post {
                        state = state.copy(
                            messages = state.messages.map { message ->
                                if (message.id == assistantId) {
                                    message.copy(text = snapshot, blocksJson = markdownBlocks(snapshot))
                                } else {
                                    message
                                }
                            },
                        )
                    }
                }

                val finalText = output.toString().trim()
                if (finalText.isBlank()) throw ApiException(502, "empty_response", "AI returned an empty response")
                client.appendMessage(session.accessToken, id, "assistant", finalText)
                val conversations = client.listConversations(session.accessToken)
                post {
                    state = state.copy(
                        streaming = false,
                        conversations = conversations,
                    )
                }
            } catch (cause: Throwable) {
                post {
                    state = state.copy(streaming = false, loading = false, error = readableError(cause))
                }
            }
        }
    }

    fun clearError() {
        if (state.error != null) state = state.copy(error = null)
    }

    fun close() {
        executor.shutdownNow()
    }

    private fun bootstrap() {
        state = state.copy(loading = true)
        executor.execute {
            try {
                loadProductState(ensureFreshSession())
            } catch (cause: Throwable) {
                sessionStore.clearSession()
                post {
                    state = MeoUiState(error = readableError(cause))
                }
            }
        }
    }

    private fun loadProductState(initialSession: OAuthSession) {
        var session = initialSession
        if (session.userId.isBlank() || session.email.isBlank()) {
            val (userId, email) = client.userInfo(session.accessToken)
            session = session.copy(userId = userId, email = email)
            sessionStore.saveSession(session)
        }
        val conversations = client.listConversations(session.accessToken)
        val credentials = client.listCredentials(session.accessToken)
        val firstCredential = credentials.firstOrNull()
        val models = firstCredential?.let {
            runCatching { client.listModels(session.accessToken, it.id) }.getOrDefault(emptyList())
        }.orEmpty()
        val selectedModel = when {
            firstCredential?.defaultModel?.isNotBlank() == true -> firstCredential.defaultModel
            models.isNotEmpty() -> models.first().id
            else -> null
        }
        post {
            state = MeoUiState(
                signedIn = true,
                loading = false,
                email = session.email,
                conversations = conversations,
                credentials = credentials,
                selectedCredentialId = firstCredential?.id,
                models = models,
                selectedModelId = selectedModel,
            )
        }
    }

    private fun ensureFreshSession(): OAuthSession {
        val existing = sessionStore.loadSession() ?: throw ApiException(401, "signed_out", "Sign in again")
        if (existing.expiresAtEpochSeconds > Instant.now().epochSecond + 90) return existing
        val refreshed = client.refreshTokens(BuildConfig.MEO_OAUTH_CLIENT_ID, existing.refreshToken)
            .copy(userId = existing.userId, email = existing.email)
        sessionStore.saveSession(refreshed)
        return refreshed
    }

    private fun conversationPrompt(messages: List<UiMessage>, current: String): String {
        if (messages.isEmpty()) return current
        val selected = ArrayDeque<String>()
        var used = current.length + 16
        for (message in messages.asReversed()) {
            if (message.text.isBlank()) continue
            val prefix = if (message.role == "assistant") "Assistant: " else "User: "
            val line = prefix + message.text
            if (used + line.length + 2 > 38_000) break
            selected.addFirst(line)
            used += line.length + 2
        }
        return "Conversation so far:\n${selected.joinToString("\n\n")}\n\nUser: $current"
    }

    private fun titleFor(text: String): String {
        return text.replace(Regex("\\s+"), " ").trim().take(72).ifBlank { "New chat" }
    }

    private fun postFailure(cause: Throwable) {
        post {
            state = state.copy(loading = false, streaming = false, error = readableError(cause))
        }
    }

    private fun readableError(cause: Throwable): String {
        return when (cause) {
            is ApiException -> when (cause.status) {
                401 -> "Your Meo Account session expired. Sign in again."
                403 -> "This account or OAuth client is not allowed to do that."
                409 -> "That AI confirmation expired or was already used. Try sending again."
                428 -> "Fresh confirmation is required before sending data to the AI provider."
                429 -> "Too many requests. Try again shortly."
                else -> cause.message ?: cause.code
            }
            else -> cause.message ?: "Meo AI could not complete the request."
        }
    }

    private fun post(block: () -> Unit) {
        activity.runOnUiThread(block)
    }

    private fun randomUrlSafe(byteCount: Int): String {
        val bytes = ByteArray(byteCount)
        SecureRandom().nextBytes(bytes)
        return base64Url(bytes)
    }

    private fun base64Url(bytes: ByteArray): String {
        return Base64.encodeToString(bytes, Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING)
    }
}
