# /radio-infra/radio.liq
settings.server.telnet := true
settings.server.telnet.port := 1234
settings.server.telnet.bind_addr := "0.0.0.0"

# O CORAÇÃO DA FASE 2
# Pergunta para a API (http://api:3000) qual música tocar
radio = request.dynamic(
  id="api_playlist",
  request.create("http://api:3000/api/v1/queue/next")
)

radio = fallback(track_sensitive=false, [radio, blank()])

output.icecast(
  %vorbis, 
  id = "main_stream",
  host = "icecast",
  port = 8000,
  password = environment.get("ICECAST_SOURCE_PASSWORD"), 
  mount = "/stream",
  radio
)