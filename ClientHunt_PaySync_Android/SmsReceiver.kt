package ai.clienthunt.paysync

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.os.Build
import android.provider.Telephony
import org.json.JSONObject
import java.io.OutputStreamWriter
import java.net.HttpURLConnection
import java.net.URL
import kotlin.concurrent.thread

/**
 * Listens silently in the background for incoming bKash & Nagad SMS
 * and pushes them instantaneously to your ClientHunt AI website.
 */
class SmsReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != Telephony.Sms.Intents.SMS_RECEIVED_ACTION) return

        val messages = Telephony.Sms.Intents.getMessagesFromIntent(intent)
        if (messages.isEmpty()) return

        val sender = messages[0].displayOriginatingAddress ?: ""
        val fullBody = messages.joinToString("") { it.displayMessageBody ?: "" }

        val sLow = sender.lowercase()
        val bLow = fullBody.lowercase()
        val isPaymentSms = (
            sLow.contains("bkash") || sLow.contains("nagad") ||
            bLow.contains("trxid") || bLow.contains("txnid") ||
            bLow.contains("have received tk") || bLow.contains("money received")
        )
        if (!isPaymentSms) return

        val prefs = context.getSharedPreferences("PaySyncPrefs", Context.MODE_PRIVATE)
        val webhookUrl = prefs.getString("webhook_url", "")?.trim() ?: ""
        val syncKey = prefs.getString("sync_key", "")?.trim() ?: ""
        if (webhookUrl.isEmpty() || syncKey.isEmpty()) return

        thread {
            try {
                val url = URL(webhookUrl)
                val conn = url.openConnection() as HttpURLConnection
                conn.requestMethod = "POST"
                conn.connectTimeout = 10000
                conn.readTimeout = 10000
                conn.doOutput = true
                conn.setRequestProperty("Content-Type", "application/json")
                conn.setRequestProperty("X-PaySync-Key", syncKey)

                val payload = JSONObject().apply {
                    put("sender", sender)
                    put("message", fullBody)
                    put("device", "${Build.MANUFACTURER} ${Build.MODEL}")
                }

                OutputStreamWriter(conn.outputStream).use { it.write(payload.toString()) }
                conn.responseCode
                conn.disconnect()
            } catch (e: Exception) {
                e.printStackTrace()
            }
        }
    }
}
