import os
import asyncio
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import random

S3_ENDPOINT_URL = os.environ.get('S3_ENDPOINT_URL')
S3_ACCESS_KEY = os.environ.get('S3_ACCESS_KEY')
S3_SECRET_KEY = os.environ.get('S3_SECRET_KEY')
S3_BUCKET_NAME = os.environ.get('S3_BUCKET_NAME')

if not all([S3_ENDPOINT_URL, S3_ACCESS_KEY, S3_SECRET_KEY, S3_BUCKET_NAME]):
    print("ERRO: Variáveis S3 não configuradas")

try:
    url_parts = S3_ENDPOINT_URL.replace('https://', '').replace('http://', '').split('.')
    OCI_REGION = next(
        (part for part in url_parts if part.startswith(('sa-', 'us-', 'eu-', 'ap-', 'ca-', 'uk-', 'me-'))), 
        'sa-vinhedo-1'
    )
except:
    OCI_REGION = "sa-vinhedo-1"

print(f"🎵 Rádio Casa 13 - Streaming direto")
print(f"S3 Bucket: {S3_BUCKET_NAME} em {OCI_REGION}")

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PLAYLIST = [
    {'storage_key': 'cc/teardrop.mp3', 'titulo': 'Teardrop', 'artista': 'Massive Attack'}
]

# Cliente S3 global
import boto3
from botocore.config import Config

s3_client = boto3.client(
    's3',
    endpoint_url=S3_ENDPOINT_URL,
    aws_access_key_id=S3_ACCESS_KEY,
    aws_secret_access_key=S3_SECRET_KEY,
    config=Config(region_name=OCI_REGION, signature_version='s3v4')
)

async def stream_audio(request: Request):
    """Gera stream de áudio infinito"""
    from urllib.request import urlopen
    
    client_id = id(request)
    print(f"🔌 Cliente conectado: {client_id}")
    
    try:
        while True:
            # Verifica se o cliente ainda está conectado
            if await request.is_disconnected():
                print(f"❌ Cliente desconectado: {client_id}")
                break
            
            # Escolhe música
            track = random.choice(PLAYLIST)
            print(f"▶️  [{client_id}] Tocando: {track['titulo']} - {track['artista']}")
            
            # Gera URL
            url = s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': S3_BUCKET_NAME, 'Key': track['storage_key']},
                ExpiresIn=600
            )
            
            # Stream do arquivo
            try:
                with urlopen(url) as response:
                    bytes_sent = 0
                    while True:
                        # Verifica desconexão novamente
                        if await request.is_disconnected():
                            print(f"❌ Cliente desconectado durante reprodução: {client_id}")
                            return
                        
                        chunk = response.read(8192)
                        if not chunk:
                            break
                        
                        bytes_sent += len(chunk)
                        yield chunk
                        
                        # Pequeno delay para não sobrecarregar
                        await asyncio.sleep(0.01)
                    
                    print(f"✅ [{client_id}] Música completa: {bytes_sent} bytes enviados")
                    
            except Exception as e:
                print(f"❌ Erro no streaming para {client_id}: {e}")
                break
                
    except Exception as e:
        print(f"❌ Erro geral para {client_id}: {e}")
    finally:
        print(f"🔌 Stream encerrado para cliente: {client_id}")

@app.get("/")
def read_root():
    return {
        "radio": "Casa 13",
        "status": "online",
        "stream_url": "/stream",
        "now_playing_url": "/now-playing"
    }

@app.get("/stream")
async def stream(request: Request):
    """Endpoint de streaming de áudio"""
    return StreamingResponse(
        stream_audio(request),
        media_type="audio/mpeg",
        headers={
            "Cache-Control": "no-cache, no-store",
            "Connection": "keep-alive",
            "Accept-Ranges": "none",
            "icy-name": "Rádio Casa 13",
            "icy-description": "Música Livre 24/7",
            "icy-url": "https://radiocasa13-api.duckdns.org",
            "Access-Control-Allow-Origin": "*"
        }
    )

@app.get("/now-playing")
def now_playing():
    """Retorna a música atual"""
    track = random.choice(PLAYLIST)
    return {
        "titulo": track['titulo'],
        "artista": track['artista']
    }
