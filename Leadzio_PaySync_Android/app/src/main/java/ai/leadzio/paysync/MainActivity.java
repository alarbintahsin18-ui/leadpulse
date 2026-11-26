package ai.leadzio.paysync;

import android.Manifest;
import android.app.Activity;
import android.content.Context;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.os.Build;
import android.os.Bundle;
import android.view.Gravity;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONObject;

import java.io.OutputStreamWriter;
import java.net.HttpURLConnection;
import java.net.URL;

public class MainActivity extends Activity {
    private TextView statusText;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        SharedPreferences prefs = getSharedPreferences("LeadzioPaySync", Context.MODE_PRIVATE);
        String savedUrl = prefs.getString("webhook_url", "https://leadzio.vercel.app/api/sms-sync/receive");
        String savedKey = prefs.getString("sync_key", "LEADZIO-PAYSYNC-2026-8842");

        ScrollView scroll = new ScrollView(this);
        scroll.setBackgroundColor(Color.parseColor("#070B14"));

        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setPadding(60, 110, 60, 80);
        scroll.addView(root);

        TextView badge = new TextView(this);
        badge.setText("● 0% FEE • LIVE SMS AUTO-SYNC");
        badge.setTextColor(Color.parseColor("#34D399"));
        badge.setTextSize(12f);
        badge.setTypeface(Typeface.MONOSPACE, Typeface.BOLD);
        root.addView(badge);

        TextView title = new TextView(this);
        title.setText("Leadzio PaySync");
        title.setTextColor(Color.WHITE);
        title.setTextSize(28f);
        title.setTypeface(null, Typeface.BOLD);
        title.setPadding(0, 12, 0, 8);
        root.addView(title);

        TextView sub = new TextView(this);
        sub.setText("Automatically syncs incoming bKash & Nagad SMS directly to your Leadzio website for instant TrxID verification.");
        sub.setTextColor(Color.parseColor("#94A3B8"));
        sub.setTextSize(14f);
        sub.setPadding(0, 0, 0, 48);
        root.addView(sub);

        TextView lblUrl = new TextView(this);
        lblUrl.setText("Website Webhook URL");
        lblUrl.setTextColor(Color.parseColor("#CBD5E1"));
        lblUrl.setTextSize(13f);
        lblUrl.setTypeface(null, Typeface.BOLD);
        root.addView(lblUrl);

        EditText urlInput = createStyledInput(savedUrl, "https://leadzio.vercel.app/api/sms-sync/receive");
        root.addView(urlInput);

        TextView lblKey = new TextView(this);
        lblKey.setText("Secret PaySync Key");
        lblKey.setTextColor(Color.parseColor("#CBD5E1"));
        lblKey.setTextSize(13f);
        lblKey.setTypeface(null, Typeface.BOLD);
        lblKey.setPadding(0, 28, 0, 0);
        root.addView(lblKey);

        EditText keyInput = createStyledInput(savedKey, "LEADZIO-PAYSYNC-2026-8842");
        root.addView(keyInput);

        Button saveBtn = createStyledButton("Save & Activate Live Sync", "#10B981", "#020617");
        saveBtn.setOnClickListener(v -> {
            prefs.edit()
                    .putString("webhook_url", urlInput.getText().toString().trim())
                    .putString("sync_key", keyInput.getText().toString().trim())
                    .apply();
            requestSmsPermissions();
            statusText.setText("✅ Active! Listening for bKash & Nagad SMS in background...");
            statusText.setTextColor(Color.parseColor("#34D399"));
            Toast.makeText(this, "Leadzio PaySync Activated!", Toast.LENGTH_SHORT).show();
        });
        root.addView(saveBtn);

        Button testBtn = createStyledButton("Test Connection to Website", "#1E293B", "#38BDF8");
        testBtn.setOnClickListener(v -> {
            String u = urlInput.getText().toString().trim();
            String k = keyInput.getText().toString().trim();
            statusText.setText("⏳ Testing connection...");
            statusText.setTextColor(Color.parseColor("#FBBF24"));
            new Thread(() -> {
                try {
                    URL url = new URL(u);
                    HttpURLConnection conn = (HttpURLConnection) url.openConnection();
                    conn.setRequestMethod("POST");
                    conn.setConnectTimeout(10000);
                    conn.setDoOutput(true);
                    conn.setRequestProperty("Content-Type", "application/json");
                    conn.setRequestProperty("X-PaySync-Key", k);

                    JSONObject payload = new JSONObject();
                    payload.put("sender", "bKash");
                    payload.put("message", "Connection Ping Test from Leadzio PaySync App");
                    payload.put("device", Build.MANUFACTURER + " " + Build.MODEL);

                    OutputStreamWriter out = new OutputStreamWriter(conn.getOutputStream(), "UTF-8");
                    out.write(payload.toString());
                    out.flush();
                    out.close();

                    int code = conn.getResponseCode();
                    conn.disconnect();
                    runOnUiThread(() -> {
                        if (code == 200) {
                            statusText.setText("✅ Connected Successfully! Website is receiving from this phone.");
                            statusText.setTextColor(Color.parseColor("#34D399"));
                        } else {
                            statusText.setText("⚠️ Server responded HTTP " + code + ". Check URL & Key.");
                            statusText.setTextColor(Color.parseColor("#F87171"));
                        }
                    });
                } catch (Exception e) {
                    runOnUiThread(() -> {
                        statusText.setText("❌ Connection failed: " + e.getMessage());
                        statusText.setTextColor(Color.parseColor("#F87171"));
                    });
                }
            }).start();
        });
        root.addView(testBtn);

        statusText = new TextView(this);
        statusText.setText("Status: Ready. Tap 'Save & Activate' and allow SMS permission.");
        statusText.setTextColor(Color.parseColor("#94A3B8"));
        statusText.setTextSize(13f);
        statusText.setPadding(0, 36, 0, 0);
        statusText.setGravity(Gravity.CENTER);
        root.addView(statusText);

        setContentView(scroll);
        requestSmsPermissions();
    }

    private EditText createStyledInput(String value, String hint) {
        EditText et = new EditText(this);
        et.setText(value);
        et.setHint(hint);
        et.setTextColor(Color.WHITE);
        et.setHintTextColor(Color.parseColor("#64748B"));
        et.setTextSize(14f);
        et.setTypeface(Typeface.MONOSPACE);
        et.setPadding(36, 32, 36, 32);
        GradientDrawable bg = new GradientDrawable();
        bg.setColor(Color.parseColor("#111827"));
        bg.setCornerRadius(28f);
        bg.setStroke(2, Color.parseColor("#334155"));
        et.setBackground(bg);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        lp.setMargins(0, 12, 0, 0);
        et.setLayoutParams(lp);
        return et;
    }

    private Button createStyledButton(String text, String bgHex, String textHex) {
        Button btn = new Button(this);
        btn.setText(text);
        btn.setAllCaps(false);
        btn.setTextColor(Color.parseColor(textHex));
        btn.setTextSize(15f);
        btn.setTypeface(null, Typeface.BOLD);
        btn.setPadding(36, 36, 36, 36);
        GradientDrawable bg = new GradientDrawable();
        bg.setColor(Color.parseColor(bgHex));
        bg.setCornerRadius(28f);
        btn.setBackground(bg);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(
                LinearLayout.LayoutParams.MATCH_PARENT, LinearLayout.LayoutParams.WRAP_CONTENT);
        lp.setMargins(0, 28, 0, 0);
        btn.setLayoutParams(lp);
        return btn;
    }

    private void requestSmsPermissions() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
            if (checkSelfPermission(Manifest.permission.RECEIVE_SMS) != PackageManager.PERMISSION_GRANTED
                    || checkSelfPermission(Manifest.permission.READ_SMS) != PackageManager.PERMISSION_GRANTED) {
                requestPermissions(new String[]{
                        Manifest.permission.RECEIVE_SMS,
                        Manifest.permission.READ_SMS
                }, 101);
            }
        }
    }
}
