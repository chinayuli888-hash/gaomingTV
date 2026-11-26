package cn.gaoming.tv;

import android.os.Build;
import java.io.IOException;
import java.net.HttpURLConnection;
import java.net.InetAddress;
import java.net.Socket;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import javax.net.ssl.HttpsURLConnection;
import javax.net.ssl.SSLSocket;
import javax.net.ssl.SSLSocketFactory;

public final class LegacyTls {
    private static final String TLS_12 = "TLSv1.2";

    private LegacyTls() {}

    public static void configure(HttpURLConnection connection) {
        if (Build.VERSION.SDK_INT < 21 && connection instanceof HttpsURLConnection) {
            HttpsURLConnection https = (HttpsURLConnection) connection;
            https.setSSLSocketFactory(new EnableTls12(https.getSSLSocketFactory()));
        }
    }

    private static final class EnableTls12 extends SSLSocketFactory {
        private final SSLSocketFactory delegate;

        EnableTls12(SSLSocketFactory delegate) {
            this.delegate = delegate;
        }

        @Override public String[] getDefaultCipherSuites() {
            return delegate.getDefaultCipherSuites();
        }

        @Override public String[] getSupportedCipherSuites() {
            return delegate.getSupportedCipherSuites();
        }

        @Override public Socket createSocket() throws IOException {
            return enable(delegate.createSocket());
        }

        @Override public Socket createSocket(Socket socket, String host, int port, boolean autoClose) throws IOException {
            return enable(delegate.createSocket(socket, host, port, autoClose));
        }

        @Override public Socket createSocket(String host, int port) throws IOException {
            return enable(delegate.createSocket(host, port));
        }

        @Override public Socket createSocket(String host, int port, InetAddress local, int localPort) throws IOException {
            return enable(delegate.createSocket(host, port, local, localPort));
        }

        @Override public Socket createSocket(InetAddress host, int port) throws IOException {
            return enable(delegate.createSocket(host, port));
        }

        @Override public Socket createSocket(InetAddress host, int port, InetAddress local, int localPort) throws IOException {
            return enable(delegate.createSocket(host, port, local, localPort));
        }

        private Socket enable(Socket socket) {
            if (socket instanceof SSLSocket) {
                SSLSocket ssl = (SSLSocket) socket;
                List<String> supported = Arrays.asList(ssl.getSupportedProtocols());
                if (supported.contains(TLS_12)) {
                    List<String> enabled = new ArrayList<>(Arrays.asList(ssl.getEnabledProtocols()));
                    enabled.remove("SSLv3");
                    // KitKat's OpenSSL can cap negotiation at TLS 1.0 if TLS 1.1 is disabled.
                    for (String protocol : Arrays.asList("TLSv1.1", TLS_12)) {
                        if (supported.contains(protocol) && !enabled.contains(protocol)) {
                            enabled.add(protocol);
                        }
                    }
                    ssl.setEnabledProtocols(enabled.toArray(new String[0]));
                }
            }
            return socket;
        }
    }
}
