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

data class CloudSettings(
    val version: Int,
    val personalInstructions: String,
    val memoryEnabled: Boolean,
)

data class CloudMemory(
    val id: String,
    val version: Int,
    val kind: String,
    val content: String,
    val enabled: Boolean,
)

data class RemoteAgentRun(
    val id: String,
    val deviceId: String,
    val status: String,
    val projectId: String?,
)

data class CloudProject(
    val id: String,
    val name: String,
    val description: String,
)

/** Account-owned plugin metadata; this is not an executable native MCP connection. */
data class AccountPlugin(
    val id: String,
    val name: String,
    val description: String,
    val kind: String,
    val enabled: Boolean,
    val skillCount: Int,
    val grantedReadTools: List<String>,
)

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
    val cloudSettings: CloudSettings? = null,
    val cloudMemories: List<CloudMemory> = emptyList(),
    val archivedMemories: Boolean = false,
    val remoteAgentRuns: List<RemoteAgentRun> = emptyList(),
    val remoteAgentRunsBusy: Boolean = false,
    val remoteAgentRunsError: String? = null,
    val projects: List<CloudProject> = emptyList(),
    val projectsBusy: Boolean = false,
    val projectsError: String? = null,
    val selectedProjectId: String? = null,
    val plugins: List<AccountPlugin> = emptyList(),
    val pluginsBusy: Boolean = false,
    val pluginsError: String? = null,
    val personalizationBusy: Boolean = false,
    val personalizationError: String? = null,
    val memoryCreatedSerial: Int = 0,
)

class MeoController(private val activity: MainActivity) {
    val devicePreferences = DevicePreferences(activity)
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
        if (state.loading || state.streaming || state.pendingSend != null) return
        state = state.copy(
            currentConversationId = null,
            messages = emptyList(),
            pendingSend = null,
            error = null,
        )
    }

    fun openConversation(id: String) {
        if (state.streaming || state.loading || state.pendingSend != null) return
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
        if (state.streaming || state.loading || state.pendingSend != null) return
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
        if (!state.streaming && !state.loading && state.pendingSend == null)
            state = state.copy(selectedModelId = id, error = null)
    }

    fun beginSend(text: String) {
        val clean = text.trim()
        if (clean.isBlank() || state.loading || state.streaming || state.pendingSend != null) return
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
        // The shared Chat API owns conversation context; never stitch history here.
        val categories = if (state.messages.isEmpty()) {
            listOf("chat_text")
        } else {
            listOf("chat_text", "conversation_context")
        }
        state = state.copy(loading = true, error = null)
        val initialConversationId = state.currentConversationId
        executor.execute {
            try {
                val session = ensureFreshSession()
                val conversationId = initialConversationId ?: run {
                    val conversation = client.createConversation(session.accessToken, titleFor(clean))
                    post {
                        state = state.copy(
                            currentConversationId = conversation.id,
                            conversations = listOf(conversation) +
                                state.conversations.filterNot { it.id == conversation.id },
                        )
                    }
                    conversation.id
                }
                val preview = client.prepareInference(
                    accessToken = session.accessToken,
                    clientId = BuildConfig.MEO_OAUTH_CLIENT_ID,
                    credentialId = credentialId,
                    model = model,
                    userPrompt = clean,
                    dataCategories = categories,
                    conversationId = conversationId,
                )
                post {
                    state = state.copy(
                        loading = false,
                        pendingSend = PendingSend(clean, clean, categories, preview),
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
            val output = StringBuilder()
            try {
                val session = ensureFreshSession()
                val id = requireNotNull(existingConversationId) { "Create a conversation before consent." }
                // Persist only after streaming: inserting the user message here
                // changes server context and invalidates the approved payload hash.
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
                    userPrompt = pending.text,
                    dataCategories = pending.dataCategories,
                    conversationId = id,
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
                client.appendMessage(session.accessToken, id, "user", pending.text)
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

    fun hasRemoteAgentCloud(): Boolean = client.remoteAgentCloudConfigured()

    /** A cloud run remains owned by the server; this method never dispatches an
     * AgentRun, opens a shell or retries a previous side effect.
     */
    fun loadRemoteAgentRuns() {
        if (!state.signedIn || state.remoteAgentRunsBusy) return
        val actor = state.email
        state = state.copy(remoteAgentRunsBusy = true, remoteAgentRunsError = null)
        executor.execute {
            try {
                val rows = client.listRecentAgentRuns(ensureFreshSession().accessToken)
                val idPattern = Regex("^[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[1-8][a-fA-F0-9]{3}-[89abAB][a-fA-F0-9]{3}-[a-fA-F0-9]{12}$")
                val validStatuses = setOf("queued", "dispatching", "running",
                    "awaiting_approval", "cancel_requested", "cancelled", "completed", "failed")
                val runs = buildList {
                    for (index in 0 until rows.length()) {
                        val row = rows.optJSONObject(index) ?: continue
                        val id = row.optString("id")
                        val deviceId = row.optString("device_id")
                        val status = row.optString("status")
                        if (!idPattern.matches(id) || deviceId.isBlank() || status !in validStatuses) continue
                        val projectId = row.optString("project_id").takeIf { idPattern.matches(it) }
                        add(RemoteAgentRun(id, deviceId.take(120), status, projectId))
                    }
                }
                post { if (state.signedIn && state.email == actor)
                    state = state.copy(remoteAgentRuns = runs, remoteAgentRunsBusy = false,
                        remoteAgentRunsError = null) }
            } catch (cause: Throwable) {
                post { if (state.signedIn && state.email == actor)
                    state = state.copy(remoteAgentRunsBusy = false,
                        remoteAgentRunsError = readableError(cause)) }
            }
        }
    }

    private val projectIdPattern = Regex("^[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[1-8][a-fA-F0-9]{3}-[89abAB][a-fA-F0-9]{3}-[a-fA-F0-9]{12}$")

    private fun cloudProject(row: org.json.JSONObject): CloudProject? {
        val id = row.optString("id")
        val name = row.optString("name").trim()
        if (!projectIdPattern.matches(id) || name.isBlank()) return null
        return CloudProject(id, name, row.optString("description"))
    }

    fun selectProject(id: String) {
        if (state.projects.any { it.id == id }) state = state.copy(selectedProjectId = id)
    }

    fun loadProjects() {
        if (!state.signedIn || state.projectsBusy) return
        val actor = state.email
        state = state.copy(projectsBusy = true, projectsError = null)
        executor.execute {
            try {
                val rows = client.listProjects(ensureFreshSession().accessToken)
                val projects = buildList {
                    for (index in 0 until rows.length()) {
                        rows.optJSONObject(index)?.let { row -> cloudProject(row)?.let { add(it) } }
                    }
                }
                post {
                    if (state.signedIn && state.email == actor)
                        state = state.copy(projects = projects, projectsBusy = false, projectsError = null)
                }
            } catch (cause: Throwable) {
                post { if (state.signedIn && state.email == actor)
                    state = state.copy(projectsBusy = false, projectsError = readableError(cause)) }
            }
        }
    }

    fun createProject(name: String) {
        val normalized = name.trim()
        if (!state.signedIn || state.projectsBusy || normalized.isEmpty() || normalized.length > 160) return
        val actor = state.email
        state = state.copy(projectsBusy = true, projectsError = null)
        executor.execute {
            try {
                val project = cloudProject(client.createProject(ensureFreshSession().accessToken, normalized))
                    ?: throw IllegalStateException("Invalid Project API response")
                post { if (state.signedIn && state.email == actor)
                    state = state.copy(projects = listOf(project) + state.projects.filter { it.id != project.id },
                        selectedProjectId = project.id, projectsBusy = false, projectsError = null) }
            } catch (cause: Throwable) {
                post { if (state.signedIn && state.email == actor)
                    state = state.copy(projectsBusy = false, projectsError = readableError(cause)) }
            }
        }
    }

    fun renameProject(id: String, name: String) {
        val normalized = name.trim()
        if (!state.signedIn || state.projectsBusy || state.projects.none { it.id == id } ||
            normalized.isEmpty() || normalized.length > 160) return
        val actor = state.email
        state = state.copy(projectsBusy = true, projectsError = null)
        executor.execute {
            try {
                val project = cloudProject(client.renameProject(ensureFreshSession().accessToken, id, normalized))
                    ?: throw IllegalStateException("Invalid Project API response")
                if (project.id != id) throw IllegalStateException("Unexpected project identity")
                post { if (state.signedIn && state.email == actor)
                    state = state.copy(projects = state.projects.map { if (it.id == id) project else it },
                        projectsBusy = false, projectsError = null) }
            } catch (cause: Throwable) {
                post { if (state.signedIn && state.email == actor)
                    state = state.copy(projectsBusy = false, projectsError = readableError(cause)) }
            }
        }
    }

    /** Fetch the same account-scoped plugin inventory used on the web.
     * Only metadata, enabled Skill counts and safe grant names are displayed.
     * Tool execution/credentials remain owned by Meo API or the local broker.
     */
    fun loadAccountPlugins() {
        if (!state.signedIn || state.pluginsBusy) return
        state = state.copy(pluginsBusy = true, pluginsError = null)
        executor.execute {
            try {
                val token = ensureFreshSession().accessToken
                val rows = client.listAccountPlugins(token)
                val grants = client.listAccountPluginGrants(token)
                val grantNames = mutableMapOf<String, MutableList<String>>()
                for (index in 0 until grants.length()) {
                    val item = grants.optJSONObject(index) ?: continue
                    val pluginId = item.optString("pluginId")
                    val name = item.optString("toolName")
                    if (pluginId.isNotBlank() && name.isNotBlank())
                        grantNames.getOrPut(pluginId) { mutableListOf() }.add(name)
                }
                val plugins = buildList {
                    for (index in 0 until rows.length()) {
                        val row = rows.optJSONObject(index) ?: continue
                        val id = row.optString("id")
                        if (id.isBlank()) continue
                        add(AccountPlugin(
                            id = id,
                            name = row.optString("name"),
                            description = row.optString("description"),
                            kind = row.optString("kind"),
                            enabled = row.optBoolean("enabled", false),
                            skillCount = row.optInt("skillCount", 0),
                            grantedReadTools = grantNames[id].orEmpty(),
                        ))
                    }
                }
                post { state = state.copy(plugins = plugins, pluginsBusy = false, pluginsError = null) }
            } catch (cause: Throwable) {
                // Keep the last known list for display, but never mark it live.
                post { state = state.copy(pluginsBusy = false, pluginsError = readableError(cause)) }
            }
        }
    }

    /** Cloud settings are account state; Compose owns only their native presentation. */
    fun loadPersonalization(archived: Boolean = false) {
        if (state.personalizationBusy || state.streaming || state.pendingSend != null) return
        state = state.copy(personalizationBusy = true, personalizationError = null)
        executor.execute {
            try {
                val token = ensureFreshSession().accessToken
                val row = client.getAiSettings(token)
                val items = client.listPersonalMemories(token, archived)
                val settings = CloudSettings(
                    version = row.optInt("version", 0),
                    personalInstructions = row.optString("personalInstructions"),
                    memoryEnabled = row.optBoolean("memoryEnabled", true),
                )
                val memories = buildList {
                    for (index in 0 until items.length()) {
                        val item = items.optJSONObject(index) ?: continue
                        add(CloudMemory(
                            id = item.optString("id"),
                            version = item.optInt("version", 1),
                            kind = item.optString("kind", "fact"),
                            content = item.optString("content"),
                            enabled = item.optBoolean("enabled", true),
                        ))
                    }
                }
                post {
                    state = state.copy(
                        cloudSettings = settings, cloudMemories = memories,
                        archivedMemories = archived, personalizationBusy = false,
                    )
                }
            } catch (cause: Throwable) { personalizationFailure(cause) }
        }
    }

    fun savePersonalization(instructions: String, memoryEnabled: Boolean) {
        val current = state.cloudSettings ?: return
        if (state.personalizationBusy) return
        state = state.copy(personalizationBusy = true, personalizationError = null)
        executor.execute {
            try {
                val token = ensureFreshSession().accessToken
                val row = client.saveAiSettings(token, current.version, instructions, memoryEnabled)
                post {
                    state = state.copy(
                        cloudSettings = CloudSettings(
                            row.optInt("version", current.version + 1),
                            row.optString("personalInstructions"),
                            row.optBoolean("memoryEnabled", true),
                        ),
                        personalizationBusy = false,
                    )
                }
            } catch (cause: Throwable) { personalizationFailure(cause) }
        }
    }

    fun addPersonalMemory(content: String) {
        if (content.isBlank() || state.personalizationBusy) return
        state = state.copy(personalizationBusy = true, personalizationError = null)
        executor.execute {
            try {
                val token = ensureFreshSession().accessToken
                client.addPersonalMemory(token, "fact", content.trim())
                post {
                    state = state.copy(
                        personalizationBusy = false,
                        memoryCreatedSerial = state.memoryCreatedSerial + 1,
                    )
                }
                post { loadPersonalization() }
            } catch (cause: Throwable) { personalizationFailure(cause) }
        }
    }

    fun changePersonalMemory(
        item: CloudMemory, content: String? = null,
        enabled: Boolean? = null, archived: Boolean? = null,
    ) {
        if (state.personalizationBusy) return
        state = state.copy(personalizationBusy = true, personalizationError = null)
        val viewArchived = state.archivedMemories
        executor.execute {
            try {
                val token = ensureFreshSession().accessToken
                client.updatePersonalMemory(token, item.id, item.version, enabled, archived, content)
                post { state = state.copy(personalizationBusy = false) }
                post { loadPersonalization(viewArchived) }
            } catch (cause: Throwable) { personalizationFailure(cause) }
        }
    }

    fun deletePersonalMemory(item: CloudMemory) {
        if (state.personalizationBusy) return
        state = state.copy(personalizationBusy = true, personalizationError = null)
        val viewArchived = state.archivedMemories
        executor.execute {
            try {
                val token = ensureFreshSession().accessToken
                client.deletePersonalMemory(token, item.id)
                post { state = state.copy(personalizationBusy = false) }
                post { loadPersonalization(viewArchived) }
            } catch (cause: Throwable) { personalizationFailure(cause) }
        }
    }

    private fun personalizationFailure(cause: Throwable) {
        val description = if (cause is ApiException && cause.status == 409)
            "Changes were made elsewhere. Reload settings before trying again."
        else readableError(cause)
        post { state = state.copy(personalizationBusy = false, personalizationError = description) }
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
