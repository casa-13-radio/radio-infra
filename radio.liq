
# Habilita o servidor Telnet (sintaxe nova)
settings.server.telnet := true
settings.server.telnet.port := 1234
settings.server.telnet.bind_addr := "0.0.0.0"

# --- Esta é a sua "Fase 1: Bootstrapping" ---
playlist_dp = playlist(id="playlist_dp", mode="random", "/var/radio/music/dp")
playlist_cc = playlist(id="playlist_cc", mode="random", "/var/radio/music/cc")

# Combina as duas playlists
radio = random(id="radio_main", weights=[3, 1], [playlist_cc, playlist_dp])

# Adiciona silêncio como fallback
radio = fallback(track_sensitive=false, [radio, blank()])

# --- Saída para o Icecast ---
output.icecast(
  %vorbis, 
  id = "main_stream",
  host = "icecast",
  port = 8000,
  password = environment.get("ICECAST_SOURCE_PASSWORD"),
  mount = "/stream",
  radio
)