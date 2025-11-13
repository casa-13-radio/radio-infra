import os
import hashlib
import hmac
import base64
from datetime import datetime
from urllib.request import Request, urlopen
from urllib.error import HTTPError
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware

# --- 1. Configuração S3/OCI ---
S3_ENDPOINT_URL = os.environ.get('S3_ENDPOINT_URL')
S3_ACCESS_KEY = os.environ.get('S3_ACCESS_KEY')
S3_SECRET_KEY = os.environ.get('S3_SECRET_KEY')
S3_BUCKET_NAME = os.environ.get('S3_BUCKET_NAME')

if not all([S3_ENDPOINT_URL, S3_ACCESS_KEY, S3_SECRET_KEY, S3_BUCKET_NAME]):
    print("ERRO CRÍTICO: Variáveis de ambiente S3 não configuradas.")

# Extrai região e host
try:
    url_parts = S3_ENDPOINT_URL.replace('https://', '').replace('http://', '').split('.')
    OCI_REGION = next(
        (part for part in url_parts if part.startswith(('sa-', 'us-', 'eu-', 'ap-', 'ca-', 'uk-', 'me-'))), 
        'sa-vinhedo-1'
    )
    S3_HOST = S3_ENDPOINT_URL.replace('https://', '').replace('http://', '')
except Exception as e:
    OCI_REGION = "sa-vinhedo-1"
    S3_HOST = S3_ENDPOINT_URL.replace('https://', '').replace('http://', '')

print(f"Conectado ao S3 Bucket: {S3_BUCKET_NAME} em {S3_ENDPOINT_URL} (região: {OCI_REGION})")

# --- 2. AWS Signature V4 ---
def sign_v4(method, url, region, service, access_key, secret_key, payload, content_type):
    """Implementa AWS Signature Version 4"""
    
    # Parse URL
    from urllib.parse import urlparse
    parsed = urlparse(url)
    host = parsed.netloc
    canonical_uri = parsed.path
    
    # Timestamp
    t = datetime.utcnow()
    amz_date = t.strftime('%Y%m%dT%H%M%SZ')
    date_stamp = t.strftime('%Y%m%d')
    
    # Payload hash
    payload_hash = hashlib.sha256(payload).hexdigest()
    
    # Canonical request
    canonical_headers = f'host:{host}\nx-amz-content-sha256:{payload_hash}\nx-amz-date:{amz_date}\n'
    signed_headers = 'host;x-amz-content-sha256;x-amz-date'
    canonical_request = f'{method}\n{canonical_uri}\n\n{canonical_headers}\n{signed_headers}\n{payload_hash}'
    
    # String to sign
    algorithm = 'AWS4-HMAC-SHA256'
    credential_scope = f'{date_stamp}/{region}/{service}/aws4_request'
    string_to_sign = f'{algorithm}\n{amz_date}\n{credential_scope}\n{hashlib.sha256(canonical_request.encode()).hexdigest()}'
    
    # Signing key
    def get_signature_key(key, date_stamp, region_name, service_name):
        k_date = hmac.new(('AWS4' + key).encode('utf-8'), date_stamp.encode('utf-8'), hashlib.sha256).digest()
        k_region = hmac.new(k_date, region_name.encode('utf-8'), hashlib.sha256).digest()
        k_service = hmac.new(k_region, service_name.encode('utf-8'), hashlib.sha256).digest()
        k_signing = hmac.new(k_service, b'aws4_request', hashlib.sha256).digest()
        return k_signing
    
    signing_key = get_signature_key(secret_key, date_stamp, region, service)
    signature = hmac.new(signing_key, string_to_sign.encode('utf-8'), hashlib.sha256).hexdigest()
    
    # Authorization header
    authorization_header = f'{algorithm} Credential={access_key}/{credential_scope}, SignedHeaders={signed_headers}, Signature={signature}'
    
    # Headers
    headers = {
        'Host': host,
        'Content-Type': content_type,
        'Content-Length': str(len(payload)),
        'x-amz-content-sha256': payload_hash,
        'x-amz-date': amz_date,
        'Authorization': authorization_header
    }
    
    return headers

def upload_to_oci(bucket, key, data, content_type):
    """Upload para OCI usando AWS Signature V4"""
    url = f"{S3_ENDPOINT_URL}/{bucket}/{key}"
    
    print(f"DEBUG: Enviando PUT para {url}")
    print(f"DEBUG: Content-Length: {len(data)}")
    
    headers = sign_v4(
        method='PUT',
        url=url,
        region=OCI_REGION,
        service='s3',
        access_key=S3_ACCESS_KEY,
        secret_key=S3_SECRET_KEY,
        payload=data,
        content_type=content_type
    )
    
    try:
        req = Request(url, data=data, headers=headers, method='PUT')
        with urlopen(req) as response:
            print(f"✅ Upload bem-sucedido: {response.status}")
            return response.status
    except HTTPError as e:
        error_body = e.read().decode('utf-8')
        raise Exception(f"Upload falhou [{e.code}]: {error_body}")

# --- 3. FastAPI App ---
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def read_root():
    return {"api": "casa-13-radio-api", "status": "online"}

@app.post("/api/v1/tracks")
async def upload_track(
    file: UploadFile = File(...),
    titulo: str = Form(),
    artista: str = Form(),
    tipo_licenca: str = Form(default='cc')
):
    if not file.content_type.startswith('audio/'):
        raise HTTPException(status_code=400, detail="Tipo de arquivo inválido. Apenas áudio.")

    storage_key = f"{tipo_licenca}/{file.filename}"

    try:
        contents = await file.read()
        content_length = len(contents)
        
        print(f"DEBUG: Arquivo recebido - {file.filename}")
        print(f"DEBUG: Content-Type - {file.content_type}")
        print(f"DEBUG: Tamanho - {content_length} bytes")
        print(f"DEBUG: Storage Key - {storage_key}")

        # Upload via HTTP com AWS Signature V4
        upload_to_oci(S3_BUCKET_NAME, storage_key, contents, file.content_type)
        
        print(f"✅ Música salva no S3: {storage_key} ({content_length} bytes)")

    except Exception as e:
        print(f"❌ Erro no upload para S3: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Falha no upload para o S3: {str(e)}")

    return {
        "message": "Música enviada com sucesso!", 
        "storage_key": storage_key,
        "titulo": titulo,
        "artista": artista,
        "size_bytes": content_length
    }

@app.api_route("/api/v1/queue/next", methods=["GET", "HEAD"])
async def get_next_track_for_liquidsoap():
    try:
        import boto3
        from botocore.config import Config
        
        s3_client = boto3.client(
            's3',
            endpoint_url=S3_ENDPOINT_URL,
            aws_access_key_id=S3_ACCESS_KEY,
            aws_secret_access_key=S3_SECRET_KEY,
            config=Config(region_name=OCI_REGION, signature_version='s3v4')
        )
        
        track = {'storage_key': 'cc/teardrop.mp3'}

        if not track:
            return Response(status_code=404, content="Nenhuma música na fila.")

        presigned_url = s3_client.generate_presigned_url(
            'get_object',
            Params={'Bucket': S3_BUCKET_NAME, 'Key': track['storage_key']},
            ExpiresIn=600
        )

        return Response(content=presigned_url, media_type="text/plain")

    except Exception as e:
        print(f"Erro ao gerar URL assinada: {e}")
        return Response(status_code=500, content=f"Erro no servidor da API: {e}")
