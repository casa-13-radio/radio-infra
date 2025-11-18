import os
import asyncio
import hashlib
import hmac
from datetime import datetime
from urllib.request import Request as URLRequest, urlopen
from urllib.error import HTTPError
from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException
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

# Lista de músicas (atualiza dinamicamente conforme uploads)
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

# Funções de upload (AWS Signature V4)
def sign_v4(method, url, region, service, access_key, secret_key, payload, content_type, extra_headers=None):
    from urllib.parse import urlparse
    parsed = urlparse(url)
    host = parsed.netloc
    canonical_uri = parsed.path
    
    t = datetime.utcnow()
    amz_date = t.strftime('%Y%m%dT%H%M%SZ')
    date_stamp = t.strftime('%Y%m%d')
    
    payload_hash = hashlib.sha256(payload).hexdigest()
    
    headers_to_sign = {
        'host': host,
        'x-amz-content-sha256': payload_hash,
        'x-amz-date': amz_date
    }
    
    if extra_headers:
        for k, v in extra_headers.items():
            headers_to_sign[k.lower()] = v
    
    sorted_header_keys = sorted(headers_to_sign.keys())
    canonical_headers = '\n'.join([f'{k}:{headers_to_sign[k]}' for k in sorted_header_keys]) + '\n'
    signed_headers = ';'.join(sorted_header_keys)
    
    canonical_request = f'{method}\n{canonical_uri}\n\n{canonical_headers}\n{signed_headers}\n{payload_hash}'
    
    algorithm = 'AWS4-HMAC-SHA256'
    credential_scope = f'{date_stamp}/{region}/{service}/aws4_request'
    string_to_sign = f'{algorithm}\n{amz_date}\n{credential_scope}\n{hashlib.sha256(canonical_request.encode()).hexdigest()}'
    
    def get_signature_key(key, date_stamp, region_name, service_name):
        k_date = hmac.new(('AWS4' + key).encode('utf-8'), date_stamp.encode('utf-8'), hashlib.sha256).digest()
        k_region = hmac.new(k_date, region_name.encode('utf-8'), hashlib.sha256).digest()
        k_service = hmac.new(k_region, service_name.encode('utf-8'), hashlib.sha256).digest()
        k_signing = hmac.new(k_service, b'aws4_request', hashlib.sha256).digest()
        return k_signing
    
    signing_key = get_signature_key(secret_key, date_stamp, region, service)
    signature = hmac.new(signing_key, string_to_sign.encode('utf-8'), hashlib.sha256).hexdigest()
    
    authorization_header = f'{algorithm} Credential={access_key}/{credential_scope}, SignedHeaders={signed_headers}, Signature={signature}'
    
    headers = {
        'Host': host,
        'Content-Type': content_type,
        'Content-Length': str(len(payload)),
        'x-amz-content-sha256': payload_hash,
        'x-amz-date': amz_date,
        'Authorization': authorization_header
    }
    
    if extra_headers:
        headers.update(extra_headers)
    
    return headers

def upload_to_oci(bucket, key, data, content_type):
    url = f"{S3_ENDPOINT_URL}/{bucket}/{key}"
    
    print(f"DEBUG: Upload para {url}")
    
    extra_headers = {'x-amz-acl': 'public-read'}
    
    headers = sign_v4(
        method='PUT',
        url=url,
        region=OCI_REGION,
        service='s3',
        access_key=S3_ACCESS_KEY,
        secret_key=S3_SECRET_KEY,
        payload=data,
        content_type=content_type,
        extra_headers=extra_headers
    )
    
    try:
        # Usa URLRequest (urllib) em vez de Request (FastAPI)
        req = URLRequest(url, data)
        req.get_method = lambda: 'PUT'
        
        # Adiciona cada header
        for key, value in headers.items():
            req.add_header(key, value)
        
        with urlopen(req) as response:
            print(f"✅ Upload bem-sucedido: {response.status}")
            return response.status
    except HTTPError as e:
        error_body = e.read().decode('utf-8')
        raise Exception(f"Upload falhou [{e.code}]: {error_body}")

async def stream_audio(request: Request):
    """Gera stream de áudio infinito"""
    from urllib.request import urlopen
    
    client_id = id(request)
    print(f"🔌 Cliente conectado: {client_id}")
    
    try:
        while True:
            if await request.is_disconnected():
                print(f"❌ Cliente desconectado: {client_id}")
                break
            
            track = random.choice(PLAYLIST)
            print(f"▶️  [{client_id}] Tocando: {track['titulo']} - {track['artista']}")
            
            url = s3_client.generate_presigned_url(
                'get_object',
                Params={'Bucket': S3_BUCKET_NAME, 'Key': track['storage_key']},
                ExpiresIn=600
            )
            
            try:
                with urlopen(url) as response:
                    bytes_sent = 0
                    while True:
                        if await request.is_disconnected():
                            print(f"❌ Cliente desconectado durante reprodução: {client_id}")
                            return
                        
                        chunk = response.read(8192)
                        if not chunk:
                            break
                        
                        bytes_sent += len(chunk)
                        yield chunk
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
        "upload_url": "/api/v1/tracks",
        "playlist_size": len(PLAYLIST)
    }

@app.post("/api/v1/tracks")
async def upload_track(
    file: UploadFile = File(...),
    titulo: str = Form(),
    artista: str = Form(),
    tipo_licenca: str = Form(default='cc')
):
    """Upload de música para o S3"""
    if not file.content_type.startswith('audio/'):
        raise HTTPException(status_code=400, detail="Tipo de arquivo inválido. Apenas áudio.")

    storage_key = f"{tipo_licenca}/{file.filename}"

    try:
        contents = await file.read()
        content_length = len(contents)
        
        print(f"📤 Upload: {file.filename} ({content_length} bytes)")

        upload_to_oci(S3_BUCKET_NAME, storage_key, contents, file.content_type)
        
        # Adiciona à playlist
        PLAYLIST.append({
            'storage_key': storage_key,
            'titulo': titulo,
            'artista': artista
        })
        
        print(f"✅ Música adicionada à playlist: {titulo} - {artista}")
        print(f"📻 Playlist agora tem {len(PLAYLIST)} música(s)")

    except Exception as e:
        print(f"❌ Erro no upload: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Falha no upload: {str(e)}")

    return {
        "message": "Música enviada com sucesso!", 
        "storage_key": storage_key,
        "titulo": titulo,
        "artista": artista,
        "size_bytes": content_length,
        "playlist_size": len(PLAYLIST)
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
            "Access-Control-Allow-Origin": "*"
        }
    )

@app.get("/playlist")
def get_playlist():
    """Retorna a playlist completa"""
    return {
        "total": len(PLAYLIST),
        "tracks": PLAYLIST
    }

@app.get("/now-playing")
def now_playing():
    """Retorna a música atual"""
    track = random.choice(PLAYLIST)
    return {
        "titulo": track['titulo'],
        "artista": track['artista']
    }
