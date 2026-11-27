# Freigabe-Checkliste

Technischer Kandidat: API 36, Java/WebView, Android ab 6 (API 23), eigene stilisierte Stadtgrafik statt Foto, separates Paket de.reker17.wiehl.stadtduell.

## Build
- Debug-APK zum Testen, unsigned Release-AAB zur weiteren Vorbereitung.
- AAB vor Upload mit einem dauerhaften Upload-Schlüssel signieren. Schlüssel und Passwort privat sichern, niemals in Git oder öffentliche Artefakte laden. Google Play App Signing einrichten.
- Release-Paketname vor erster Einreichung endgültig bestätigen.
- Dieser Branch befindet sich im bestehenden öffentlichen Repository; vor Vermarktung privates Repository einrichten. Bereits öffentlich zugänglicher Code ist nicht rückwirkend geheim.

## Tests
- Lokales Duell: Würfeln, kaufen, passen, Miete, Ereignisse, Ausbau, alle zwölf Runden, Sieger, Neustart, Speicherstand nach App-Neustart.
- Kleine und große Android-Bildschirme, Tastatur, Zurück-Taste, aktuelle Android System WebView, Android 16 Systemleisten.
- Online: zwei reale Geräte im WLAN und in unterschiedlichen Mobilfunknetzen, falscher Code, Wiederbeitritt, Verbindungsabbruch, beiderseitige Zugkontrolle, Spielende.
- Server: PeerJS Cloud ist ein Testdienst ohne nachgewiesene Verfügbarkeitsgarantie für dieses Projekt. Produktionsdienst und ggf. TURN-Relay erst nach Betreiberwahl, Datenschutzprüfung, TLS, Missbrauchsschutz, Monitoring und Lasttest einsetzen.
- Noch keine kommerzielle Freigabe. Store-Text für Online-Modus erst nach Praxistest ergänzen.

## Anbieter
- Play Console Konto und Identitätsprüfung, einmalige Gebühr, Zahlungsprofil für kostenpflichtige App, gegebenenfalls Gewerbe/Steuer/Verbraucherpflichten.
- Bei neuem Privatkonto: 12 kontinuierlich teilnehmende Tester über mindestens 14 Tage für geschlossenen Test, dann Produktionszugang beantragen.
- Datenschutz-URL und Impressum finalisieren; Data Safety, Zielgruppe, IARC-Altersbewertung, Werbung (nein), App-Zugang, Preis, Verfügbarkeit.
- Store-Grafiken: 512x512 Icon und 1024x500 Feature-Grafik werden im Build erzeugt; mindestens zwei echte Screenshots bereitstellen.
- Produktionsfreigabe erst nach Tests, Rechteprüfung, Datenschutzerklärung, signiertem AAB und Genehmigung des Inhabers.
