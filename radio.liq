# /radio-infra/radio.liq
settings.server.telnet := true
settings.server.telnet.port := 1234
settings.server.telnet.bind_addr := "0.0.0.0"

# 1. Primeiro, definimos uma FUNÇÃO que sabe como pedir uma música.
def get_next_song_from_api()
  # Ela retorna um *objeto* de requisição
  request.create("http://api:3000/api/v1/queue/next")
end

# 2. Agora, dizemos ao request.dynamic para usar aquela FUNÇÃO.
radio = request.dynamic(
  id="api_playlist",
  get_next_song_from_api
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
