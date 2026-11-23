# Ajazz AK980 V2 Manager - control software for the AJAZZ AK980 (V2) PRO keyboard
# Copyright (C) 2026 j0p3s. GPL-3.0-or-later (see LICENSE). Not affiliated with or endorsed by AJAZZ.
"""Interface language for the navigation and page titles (the rest of the interface stays English). Chosen on the System page; applied
the next time the program starts. English is the source text, so a missing translation simply shows the English text."""
LANGUAGES = ('English', 'Português', 'Français', 'Español', 'Türkçe')
_PT = {'Overview': 'Resumo', 'Lighting': 'Iluminação', 'Per-key': 'Por tecla', 'Per-key colours': 'Cores por tecla', 'Reactive': 'Reativo',
       'Keys': 'Teclas', 'Key remapping': 'Remapear teclas', 'Macros': 'Macros', 'Screen': 'Ecrã', 'Live screen': 'Ecrã ao vivo',
       'Profiles': 'Perfis', 'Connection': 'Ligação', 'System': 'Sistema', 'HOME': 'INÍCIO', 'LIGHTING': 'ILUMINAÇÃO',
       'KEYS AND MACROS': 'TECLAS E MACROS', 'DEVICE': 'DISPOSITIVO', 'Manager': 'Gestor'}
_TR = {'Overview': 'Genel Bakış', 'Lighting': 'Aydınlatma', 'Per-key': 'Tuş başına', 'Per-key colours': 'Tuş başına renkler',
       'Reactive': 'Reaktif', 'Keys': 'Tuşlar', 'Key remapping': 'Tuş atama', 'Macros': 'Makrolar', 'Screen': 'Ekran',
       'Live screen': 'Canlı ekran', 'Profiles': 'Profiller', 'Connection': 'Bağlantı', 'System': 'Sistem', 'HOME': 'ANA SAYFA',
       'LIGHTING': 'AYDINLATMA', 'KEYS AND MACROS': 'TUŞLAR VE MAKROLAR', 'DEVICE': 'CİHAZ', 'Manager': 'Yönetici'}
_FR = {'Overview': 'Aperçu', 'Lighting': 'Éclairage', 'Per-key': 'Par touche', 'Per-key colours': 'Couleurs par touche', 'Reactive': 'Réactif',
       'Keys': 'Touches', 'Key remapping': 'Réassignation des touches', 'Macros': 'Macros', 'Screen': 'Écran', 'Live screen': 'Écran en direct',
       'Profiles': 'Profils', 'Connection': 'Connexion', 'System': 'Système', 'HOME': 'ACCUEIL', 'LIGHTING': 'ÉCLAIRAGE',
       'KEYS AND MACROS': 'TOUCHES ET MACROS', 'DEVICE': 'APPAREIL', 'Manager': 'Gestionnaire'}
_ES = {'Overview': 'Resumen', 'Lighting': 'Iluminación', 'Per-key': 'Por tecla', 'Per-key colours': 'Colores por tecla', 'Reactive': 'Reactivo',
       'Keys': 'Teclas', 'Key remapping': 'Reasignar teclas', 'Macros': 'Macros', 'Screen': 'Pantalla', 'Live screen': 'Pantalla en vivo',
       'Profiles': 'Perfiles', 'Connection': 'Conexión', 'System': 'Sistema', 'HOME': 'INICIO', 'LIGHTING': 'ILUMINACIÓN',
       'KEYS AND MACROS': 'TECLAS Y MACROS', 'DEVICE': 'DISPOSITIVO', 'Manager': 'Gestor'}
TABLES = {'Português': _PT, 'Français': _FR, 'Español': _ES, 'Türkçe': _TR}
current = 'English'


def set_language(name):
    global current
    current = name if name in LANGUAGES else 'English'


def tr(text):
    return TABLES.get(current, {}).get(text, text)
