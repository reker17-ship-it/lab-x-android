package de.wiehl.stadtduell;

import android.app.Activity;
import android.os.Bundle;
import android.os.Build;
import android.view.WindowInsets;
import android.graphics.Insets;
import android.widget.FrameLayout;
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
                String host = request.getUrl().getHost();
                String path = request.getUrl().getPath();
                if ("https".equals(scheme) && "appassets.androidplatform.net".equals(host)) {
                    if ("/".equals(path) || "/index.html".equals(path)) {
                        try { return new WebResourceResponse("text/html", "UTF-8", getAssets().open("index.html")); }
                        catch (Exception ignored) {}
                    }
                    if ("/online.js".equals(path) || "/peerjs.min.js".equals(path)) {
                        try {
                            return new WebResourceResponse("application/javascript", "UTF-8", getAssets().open(path.substring(1)));
                        } catch (Exception ignored) {}
                    }
                }
                if ("https".equals(scheme) && "0.peerjs.com".equals(host)) return null;
                if ("https".equals(scheme) || "http".equals(scheme)) {
                    return new WebResourceResponse("text/plain", "UTF-8", new ByteArrayInputStream(new byte[0]));
                }
                return null;
            }
        });
        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(Color.rgb(9, 23, 20));
        root.addView(game, new FrameLayout.LayoutParams(-1,-1));
        if (Build.VERSION.SDK_INT >= 30) {
            getWindow().setDecorFitsSystemWindows(false);
            root.setOnApplyWindowInsetsListener((view, insets) -> {
                Insets safe = insets.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout() | WindowInsets.Type.ime());
                view.setPadding(safe.left, safe.top, safe.right, safe.bottom);
                return WindowInsets.CONSUMED;
            });
        }
        setContentView(root);
        root.requestApplyInsets();
        game.loadUrl(ORIGIN+"index.html");
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
