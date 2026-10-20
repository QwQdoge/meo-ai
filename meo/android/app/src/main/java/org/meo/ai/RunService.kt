package org.meo.ai

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.IBinder

/**
 * Foreground service that exists only while Meo AI is generating an answer. It
 * does no work itself: it makes Android keep the process and its network alive
 * when you switch to another app, so the answer can finish (and notify you).
 */
class RunService : Service() {
    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val manager = getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(NotificationChannel("running", "Answering", NotificationManager.IMPORTANCE_LOW))
        val notification = Notification.Builder(this, "running")
            .setSmallIcon(android.R.drawable.stat_notify_sync)
            .setContentTitle("Meo AI")
            .setContentText("Writing an answer…")
            .setOngoing(true)
            .build()
        startForeground(1, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        return START_NOT_STICKY
    }

    override fun onBind(intent: Intent?): IBinder? = null
}
