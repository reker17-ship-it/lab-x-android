package de.wiehl.stadtduell;

import android.app.Activity;
import android.os.Bundle;
import android.graphics.Color;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import java.io.ByteArrayOutputStream;
import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

public class MainActivity extends Activity {
    private WebView game;
    private static final String ORIGIN = "https://appassets.androidplatform.net/";

    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        getWindow().setStatusBarColor(Color.rgb(9, 23, 20));
        getWindow().setNavigationBarColor(Color.rgb(9, 23, 20));
        game = new WebView(this);
        game.setBackgroundColor(Color.rgb(9, 23, 20));
        game.getSettings().setJavaScriptEnabled(true);
        game.getSettings().setDomStorageEnabled(true);
        game.getSettings().setAllowFileAccess(false);
        game.getSettings().setAllowContentAccess(false);
        game.getSettings().setSupportMultipleWindows(false);
        game.setWebChromeClient(new WebChromeClient());
        game.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                return true;
            }
            @Override public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
                String scheme = request.getUrl().getScheme();
                if ("https".equals(scheme) || "http".equals(scheme)) {
                    return new WebResourceResponse("text/plain", "UTF-8", new ByteArrayInputStream(new byte[0]));
                }
                return null;
            }
        });
        setContentView(game);
        try (InputStream input = getAssets().open("index.html");
             ByteArrayOutputStream output = new ByteArrayOutputStream()) {
            byte[] buffer = new byte[8192];
            int count;
            while ((count = input.read(buffer)) != -1) output.write(buffer, 0, count);
            String html = new String(output.toByteArray(), StandardCharsets.UTF_8);
            game.loadDataWithBaseURL(ORIGIN, html, "text/html", "UTF-8", null);
        } catch (Exception e) {
            game.loadData("<html><body>Das Spiel konnte nicht geladen werden.</body></html>", "text/html", "UTF-8");
        }
    }

    @Override public void onBackPressed() {
        game.evaluateJavascript("(function(){var d=document.querySelector('dialog[open]');if(d){d.close();return true;}return false;})()",
            value -> { if (!"true".equals(value)) finish(); });
    }

    @Override protected void onPause() {
        if (game != null) game.onPause();
        super.onPause();
    }

    @Override protected void onResume() {
        super.onResume();
        if (game != null) game.onResume();
    }

    @Override protected void onDestroy() {
        if (game != null) { game.destroy(); game = null; }
        super.onDestroy();
    }
}
