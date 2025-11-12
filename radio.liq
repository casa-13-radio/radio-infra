# Define o caminho dos logs
set("log.file.path", "/var/log/liquidsoap/radio.log")

# Habilita o servidor Telnet para a API poder controlar
set("server.telnet", true)
set("server.telnet.port", 1234)
set("server.telnet.bind_addr", "0.0.0.0") # Ouve em todas as interfaces

# --- Esta é a sua "Fase 1: Bootstrapping" ---
# Pega músicas das suas pastas de Domínio Público e Creative Commons
playlist_dp = playlist(id="playlist_dp", mode="random", "/var/radio/music/dp")
playlist_cc = playlist(id="playlist_cc", mode="random", "/var/radio/music/cc")

# Combina as duas playlists. Toca 3 músicas de CC, depois 1 de DP, e repete.
radio = random(id="radio_main", weights=[3, 1], [playlist_cc, playlist_dp])

# Adiciona um som de emergência caso as playlists fiquem vazias
# Gera um tom de teste (bip) para nunca ficar em silêncio
emergency = single("annotate:title='Rádio Casa 13 - Aguardando músicas':sine(duration=10.)")

# Usa a rádio principal, mas se falhar, usa o som de emergência
radio = fallback(track_sensitive=false, [radio, emergency])

# --- Saída para o Icecast ---
# Envia a música para o servidor Icecast
output.icecast(
  %vorbis, # Codifica em Vorbis (bom e livre)
  id = "main_stream",
  host = "icecast", # O nome do serviço no Docker
  port = 8000,
  # Pega a senha do .env, com fallback para "hackme"
  password = getenv("ICECAST_SOURCE_PASSWORD", "hackme"),
  mount = "/stream",
  radio
)