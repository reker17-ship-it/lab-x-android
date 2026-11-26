# Eigener Online-Dienst – Deploymentplan, nicht bereitgestellt

Ziel: eigener HTTPS/WSS PeerServer mit stabiler Domain und dokumentierter Datenverarbeitung. Der aktuelle Test nutzt PeerJS Cloud. Keine Kosten oder Hosting-Verträge wurden ausgelöst.

1. Anbieter mit geeigneter Region, Auftragsverarbeitung und Kosten auswählen.
2. PeerServer in einer fest gepinnten, geprüften Version deployen; TLS über Reverse Proxy, WebSocket-Upgrades und Rate-Limits, Monitoring und kurze Log-Aufbewahrung konfigurieren.
3. Für Netzwerke ohne direkte WebRTC-Verbindung eigenen oder vertraglich geprüften TURN-Dienst mit kurzlebigen Zugangsdaten einrichten. Niemals permanente TURN-Geheimnisse in die App schreiben.
4. App auf tatsächlichen Host, Port und Pfad umstellen, HTTPS-Hostliste in MainActivity anpassen. Verwendete STUN/TURN-Endpunkte und Datensicherheitsangaben überprüfen.
5. Tests mit verschiedenen WLAN-/Mobilfunknetzen, Reconnect und Lasttest durchführen. Kein Produktionsversprechen vor bestandenen Tests.
