"""
API de Conversión de Archivos - Versión Profesional
Autor: Tu Nombre
Versión: 3.1.1 (Solucionado error de despliegue)
"""

import os
import tempfile
import logging
import shutil
import locale
from typing import List
from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import pdf2image
from PIL import Image
from PyPDF2 import PdfMerger
import magic
import subprocess

# 1. Configuración inicial
logger = logging.getLogger("uvicorn.error")
locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')

# 2. Crear instancia de FastAPI primero
app = FastAPI(
    title="Professional File Converter API",
    description="API modificada para usar almacenamiento principal del sistema",
    max_file_size=100 * 1024 * 1024 * 1024,  # 100 GB
    timeout=7200  # 2 horas
)

# 3. Configuración CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["enciclopediaislamica.com"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 4. Configuración de almacenamiento
TEMP_DIR = os.path.join(tempfile.gettempdir(), "fileconverter_temp")
os.makedirs(TEMP_DIR, exist_ok=True)

ALLOWED_MIME_TYPES = ['image/', 'application/pdf', 'text/', 'application/']

def get_disk_space():
    total, used, free = shutil.disk_usage(TEMP_DIR)
    return free / (1024**3)

def cleanup_files(file_paths: List[str]):
    for path in file_paths:
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except Exception as e:
            logger.error(f"Error eliminando {path}: {e}")
    
    if get_disk_space() < 5:
        shutil.rmtree(TEMP_DIR, ignore_errors=True)
        os.makedirs(TEMP_DIR, exist_ok=True)

def validate_file(file: UploadFile):
    mime = magic.Magic(mime=True)
    file_type = mime.from_buffer(file.file.read(1024))
    file.file.seek(0)

    if not any(file_type.startswith(allowed) for allowed in ALLOWED_MIME_TYPES):
        raise HTTPException(400, f"Tipo no soportado: {file_type}")

    return file_type

def convert_with_libreoffice(input_path: str, output_format: str) -> str:
    base_name = os.path.splitext(os.path.basename(input_path))[0]
    output_file = f"{base_name}.{output_format}"

    cmd = [
        'libreoffice', '--headless', '--convert-to', output_format,
        '--outdir', TEMP_DIR, '--env:UserInstallation=file:///tmp/.libreoffice',
        input_path
    ]

    try:
        env = os.environ.copy()
        env['LC_ALL'] = 'ar_AE.UTF-8'
        env['LANG'] = 'ar_AE.UTF-8'

        result = subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=3600,
            env=env
        )

        output_path = os.path.join(TEMP_DIR, output_file)

        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise RuntimeError("Error en conversión de documento")

        return output_path

    except subprocess.CalledProcessError as e:
        error_msg = e.stderr.decode('utf-8', errors='replace').strip()
        logger.error(f"Error LibreOffice: {error_msg}")
        raise RuntimeError(f"Fallo de conversión: {error_msg}")

@app.post("/convert/")
async def convert_file(
    background_tasks: BackgroundTasks,
    input_file: UploadFile = File(...),
    output_format: str = "pdf"
):
    temp_input = None
    output_path = None

    try:
        if get_disk_space() < 10:
            raise HTTPException(507, "Espacio en disco insuficiente")

        file_type = validate_file(input_file)

        temp_input = os.path.join(TEMP_DIR, input_file.filename)
        with open(temp_input, "wb") as f:
            while chunk := await input_file.read(10 * 1024 * 1024):
                f.write(chunk)

        if file_type.startswith('application/'):
            output_path = convert_with_libreoffice(temp_input, output_format)
        elif file_type.startswith('image/'):
            output_path = os.path.join(TEMP_DIR, f"converted_{os.urandom(4).hex()}.{output_format}")
            with Image.open(temp_input) as img:
                img.save(output_path, optimize=True, quality=95)
        elif file_type == 'application/pdf' and output_format in ['png', 'jpg']:
            output_path = os.path.join(TEMP_DIR, f"converted_{os.urandom(4).hex()}.{output_format}")
            images = pdf2image.convert_from_path(temp_input, strict=False)
            if not images:
                raise RuntimeError("No se pudieron extraer imágenes del PDF")
            images[0].save(output_path, optimize=True, quality=95)
        else:
            raise HTTPException(400, "Conversión no soportada")

        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise RuntimeError("Archivo convertido no válido")

        background_tasks.add_task(cleanup_files, [temp_input, output_path])

        return FileResponse(
            output_path,
            media_type='application/octet-stream',
            filename=os.path.basename(output_path))
    
    except Exception as e:
        cleanup_files([temp_input, output_path])
        logger.error(f"Error en conversión: {str(e)}")
        raise HTTPException(500, f"Error en conversión: {str(e)}")

@app.post("/merge-pdfs/")
async def merge_pdfs(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...)
):
    merger = PdfMerger()
    temp_files = []

    try:
        if get_disk_space() < len(files) * 0.1:
            raise HTTPException(507, "Espacio en disco insuficiente")

        for file in files:
            if file.content_type != 'application/pdf':
                raise HTTPException(400, "Solo se permiten PDFs")

            temp_path = os.path.join(TEMP_DIR, f"temp_{os.urandom(4).hex()}.pdf")
            with open(temp_path, "wb") as f:
                while chunk := await file.read(10 * 1024 * 1024):
                    f.write(chunk)
            temp_files.append(temp_path)
            merger.append(temp_path)

        output_path = os.path.join(TEMP_DIR, f"merged_{os.urandom(4).hex()}.pdf")
        merger.write(output_path)
        merger.close()

        background_tasks.add_task(cleanup_files, [*temp_files, output_path])
        return FileResponse(output_path, media_type='application/pdf', filename="merged.pdf")

    except Exception as e:
        cleanup_files(temp_files)
        logger.error(f"Error fusionando PDFs: {str(e)}")
        raise HTTPException(500, f"Error en fusión: {str(e)}")

# 5. Punto de entrada para Gunicorn
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
