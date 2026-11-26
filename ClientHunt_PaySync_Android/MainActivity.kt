package ai.clienthunt.paysync

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.os.Bundle
import android.widget.Button
import android.widget.EditText
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat

/**
 * ClientHunt PaySync — Native Android Companion App
 * Enter your Website Webhook URL & Secret Sync Key from /admin once,
 * grant SMS permission, and every bKash/Nagad payment verifies automatically!
 */
class MainActivity : AppCompatActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        val prefs = getSharedPreferences("PaySyncPrefs", Context.MODE_PRIVATE)

        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL
            setPadding(56, 96, 56, 56)
            setBackgroundColor(0xFF0B0F19.toInt())
        }

        val title = TextView(this).apply {
            text = "⚡ ClientHunt PaySync"
            textSize = 24f
            setTextColor(0xFF34D399.toInt())
        }

        val subtitle = TextView(this).apply {
            text = "Direct bKash & Nagad Live SMS Auto-Payment Sync (0% Fee)\n"
            textSize = 14f
            setTextColor(0xFF9CA3AF.toInt())
        }

        val urlInput = EditText(this).apply {
            hint = "https://yourdomain.com/api/sms-sync/receive"
            setText(prefs.getString("webhook_url", "https://yourdomain.com/api/sms-sync/receive"))
            setTextColor(0xFFFFFFFF.toInt())
            setHintTextColor(0xFF6B7280.toInt())
        }

        val keyInput = EditText(this).apply {
            hint = "Paste Secret PaySync Key from /admin"
            setText(prefs.getString("sync_key", ""))
            setTextColor(0xFFFFFFFF.toInt())
            setHintTextColor(0xFF6B7280.toInt())
        }

        val saveBtn = Button(this).apply {
            text = "Save & Activate Live SMS Sync"
            setOnClickListener {
                prefs.edit()
                    .putString("webhook_url", urlInput.text.toString().trim())
                    .putString("sync_key", keyInput.text.toString().trim())
                    .apply()
                requestSmsPermissions()
                Toast.makeText(this@MainActivity, "✅ Live bKash & Nagad Sync Activated!", Toast.LENGTH_LONG).show()
            }
        }

        layout.addView(title)
        layout.addView(subtitle)
        layout.addView(urlInput)
        layout.addView(keyInput)
        layout.addView(saveBtn)
        setContentView(layout)

        requestSmsPermissions()
    }

    private fun requestSmsPermissions() {
        val perms = arrayOf(Manifest.permission.RECEIVE_SMS, Manifest.permission.READ_SMS)
        val missing = perms.filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }
        if (missing.isNotEmpty()) {
            ActivityCompat.requestPermissions(this, missing.toTypedArray(), 101)
        }
    }
}
