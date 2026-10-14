package org.meo.ai.auth

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import org.json.JSONObject
import org.meo.ai.model.OAuthSession
import org.meo.ai.model.PendingOAuth
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

class SecureSessionStore(context: Context) {
    private val prefs = context.getSharedPreferences("meo_ai_secure_session", Context.MODE_PRIVATE)

    fun saveSession(session: OAuthSession) {
        val payload = JSONObject()
            .put("accessToken", session.accessToken)
            .put("refreshToken", session.refreshToken)
            .put("expiresAt", session.expiresAtEpochSeconds)
            .put("userId", session.userId)
            .put("email", session.email)
            .toString()
        prefs.edit().putString(KEY_SESSION, encrypt(payload)).apply()
    }

    fun loadSession(): OAuthSession? {
        val encrypted = prefs.getString(KEY_SESSION, null) ?: return null
        return runCatching {
            val data = JSONObject(decrypt(encrypted))
            OAuthSession(
                accessToken = data.getString("accessToken"),
                refreshToken = data.getString("refreshToken"),
                expiresAtEpochSeconds = data.getLong("expiresAt"),
                userId = data.optString("userId"),
                email = data.optString("email"),
            )
        }.getOrNull()
    }

    fun clearSession() {
        prefs.edit().remove(KEY_SESSION).apply()
    }

    fun savePendingOAuth(value: PendingOAuth) {
        val payload = JSONObject()
            .put("state", value.state)
            .put("verifier", value.verifier)
            .toString()
        prefs.edit().putString(KEY_PENDING, encrypt(payload)).apply()
    }

    fun loadPendingOAuth(): PendingOAuth? {
        val encrypted = prefs.getString(KEY_PENDING, null) ?: return null
        return runCatching {
            val data = JSONObject(decrypt(encrypted))
            PendingOAuth(
                state = data.getString("state"),
                verifier = data.getString("verifier"),
            )
        }.getOrNull()
    }

    fun clearPendingOAuth() {
        prefs.edit().remove(KEY_PENDING).apply()
    }

    private fun encrypt(plainText: String): String {
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.ENCRYPT_MODE, secretKey())
        val ciphertext = cipher.doFinal(plainText.toByteArray(Charsets.UTF_8))
        val envelope = ByteArray(1 + cipher.iv.size + ciphertext.size)
        envelope[0] = cipher.iv.size.toByte()
        cipher.iv.copyInto(envelope, destinationOffset = 1)
        ciphertext.copyInto(envelope, destinationOffset = 1 + cipher.iv.size)
        return Base64.encodeToString(envelope, Base64.NO_WRAP)
    }

    private fun decrypt(encoded: String): String {
        val envelope = Base64.decode(encoded, Base64.NO_WRAP)
        require(envelope.isNotEmpty())
        val ivLength = envelope[0].toInt() and 0xff
        require(ivLength in 12..32 && envelope.size > 1 + ivLength)
        val iv = envelope.copyOfRange(1, 1 + ivLength)
        val ciphertext = envelope.copyOfRange(1 + ivLength, envelope.size)
        val cipher = Cipher.getInstance(TRANSFORMATION)
        cipher.init(Cipher.DECRYPT_MODE, secretKey(), GCMParameterSpec(128, iv))
        return cipher.doFinal(ciphertext).toString(Charsets.UTF_8)
    }

    private fun secretKey(): SecretKey {
        val keyStore = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (keyStore.getKey(KEY_ALIAS, null) as? SecretKey)?.let { return it }

        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        generator.init(
            KeyGenParameterSpec.Builder(
                KEY_ALIAS,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
            )
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build(),
        )
        return generator.generateKey()
    }

    private companion object {
        const val KEY_ALIAS = "org.meo.ai.oauth.session.v1"
        const val TRANSFORMATION = "AES/GCM/NoPadding"
        const val KEY_SESSION = "oauth_session"
        const val KEY_PENDING = "oauth_pending"
    }
}
