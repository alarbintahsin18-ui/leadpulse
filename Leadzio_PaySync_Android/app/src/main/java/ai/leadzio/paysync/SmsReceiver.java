package ai.leadzio.paysync;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.os.Build;
import android.provider.Telephony;
import android.telephony.SmsMessage;

import org.json.JSONObject;

import java.io.OutputStreamWriter;
import java.net.HttpURLConnection;
import java.net.URL;

public class SmsReceiver extends BroadcastReceiver {
    @Override
    public void onReceive(Context context, Intent intent) {
        if (!Telephony.Sms.Intents.SMS_RECEIVED_ACTION.equals(intent.getAction())) {
            return;
        }
        SmsMessage[] messages = Telephony.Sms.Intents.getMessagesFromIntent(intent);
        if (messages == null || messages.length == 0) {
            return;
        }

        String sender = messages[0].getDisplayOriginatingAddress();
        if (sender == null) sender = "";
        StringBuilder bodyBuilder = new StringBuilder();
        for (SmsMessage m : messages) {
            if (m.getDisplayMessageBody() != null) {
                bodyBuilder.append(m.getDisplayMessageBody());
            }
        }
        final String finalSender = sender;
        final String fullBody = bodyBuilder.toString();

        String combined = (finalSender + " " + fullBody).toLowerCase();
        boolean isPaymentSms = combined.contains("bkash") || combined.contains("nagad")
                || combined.contains("trxid") || combined.contains("txnid")
                || combined.contains("received tk") || combined.contains("money received");
        if (!isPaymentSms) return;

        SharedPreferences prefs = context.getSharedPreferences("LeadzioPaySync", Context.MODE_PRIVATE);
        final String webhookUrl = prefs.getString("webhook_url", "https://leadzio.vercel.app/api/sms-sync/receive").trim();
        final String syncKey = prefs.getString("sync_key", "LEADZIO-PAYSYNC-2026-8842").trim();
        if (webhookUrl.isEmpty() || syncKey.isEmpty()) return;

        new Thread(() -> {
            try {
                URL url = new URL(webhookUrl);
                HttpURLConnection conn = (HttpURLConnection) url.openConnection();
                conn.setRequestMethod("POST");
                conn.setConnectTimeout(12000);
                conn.setReadTimeout(12000);
                conn.setDoOutput(true);
                conn.setRequestProperty("Content-Type", "application/json");
                conn.setRequestProperty("X-PaySync-Key", syncKey);

                JSONObject payload = new JSONObject();
                payload.put("sender", finalSender);
                payload.put("message", fullBody);
                payload.put("device", Build.MANUFACTURER + " " + Build.MODEL);

                OutputStreamWriter out = new OutputStreamWriter(conn.getOutputStream(), "UTF-8");
                out.write(payload.toString());
                out.flush();
                out.close();

                conn.getResponseCode();
                conn.disconnect();
            } catch (Exception e) {
                e.printStackTrace();
            }
        }).start();
    }
}
