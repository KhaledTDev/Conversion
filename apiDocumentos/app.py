"""
API de Conversión de Archivos - Versión Profesional
Autor: Tu Nombre
Versión: 3.0
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

# Configuración inicial
logger = logging.getLogger("uvicorn.error")
locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')  # Configuración multi-idioma

app = FastAPI(
    title="Professional File Converter API",
    max_file_size=100 * 1024 * 1024 * 1024,  # 100 GB
    timeout=7200  # 2 horas
)

# Configuración CORS para dominio personalizado
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Reemplazar con tu dominio específico
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuración de almacenamiento
SSD_PATH = "/mnt/ssd_storage"  # Ruta a tu SSD de 128GB
TEMP_DIR = os.path.join(SSD_PATH, "fileconverter_temp")
os.makedirs(TEMP_DIR, exist_ok=True)

ALLOWED_MIME_TYPES = ['image/', 'application/pdf', 'text/', 'application/']

def get_disk_space():
    """Obtiene espacio disponible en el SSD"""
    total, used, free = shutil.disk_usage(SSD_PATH)
    return free / (1024**3)  # Espacio libre en GB

def cleanup_files(file_paths: List[str]):
    """Eliminación segura de archivos temporales con verificación de espacio"""
    for path in file_paths:
        try:
            if path and os.path.exists(path):
                os.remove(path)
                logger.debug(f"Eliminado: {path}")
        except Exception as e:
            logger.error(f"Error eliminando {path}: {e}")

    # Limpieza adicional si el espacio es menor a 5GB
    if get_disk_space() < 5:
        shutil.rmtree(TEMP_DIR, ignore_errors=True)
        os.makedirs(TEMP_DIR, exist_ok=True)

def validate_file(file: UploadFile):
    """Validación MIME multi-idioma"""
    mime = magic.Magic(mime=True)
    file_type = mime.from_buffer(file.file.read(1024))
    file.file.seek(0)

    if not any(file_type.startswith(allowed) for allowed in ALLOWED_MIME_TYPES):
        raise HTTPException(400, f"Tipo no soportado: {file_type}")

    return file_type

def convert_with_libreoffice(input_path: str, output_format: str) -> str:
    """Conversión de documentos profesional con soporte multi-idioma"""
    base_name = os.path.splitext(os.path.basename(input_path))[0]
    output_file = f"{base_name}.{output_format}"

    cmd = [
        'libreoffice', '--headless', '--convert-to', output_format,
        '--outdir', TEMP_DIR, '--env:UserInstallation=file:///tmp/.libreoffice',
        input_path
    ]

    try:
        # Configuración especial para idiomas RTL (árabe)
        env = os.environ.copy()
        env['LC_ALL'] = 'ar_AE.UTF-8'
        env['LANG'] = 'ar_AE.UTF-8'

        result = subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=3600,  # 1 hora
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
    """Endpoint profesional para conversiones complejas"""
    temp_input = None
    output_path = None

    try:
        # Verificación de espacio en disco
        if get_disk_space() < 10:
            raise HTTPException(507, "Espacio en disco insuficiente")

        # Validación de archivo
        file_type = validate_file(input_file)

        # Guardado temporal con manejo de grandes archivos
        temp_input = os.path.join(TEMP_DIR, input_file.filename)
        with open(temp_input, "wb") as f:
            # Escritura en bloques de 10MB
            while chunk := await input_file.read(10 * 1024 * 1024):
                f.write(chunk)

        # Proceso de conversión multi-idioma
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

        # Verificación final del archivo
        if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            raise RuntimeError("Archivo convertido no válido")

        # Programar limpieza
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
    """Fusión profesional de PDFs multi-idioma"""
    merger = PdfMerger()
    temp_files = []

    try:
        # Verificación de espacio
        if get_disk_space() < len(files) * 0.1:
            raise HTTPException(507, "Espacio en disco insuficiente")

        for file in files:
            if file.content_type != 'application/pdf':
                raise HTTPException(400, "Solo se permiten PDFs")

            temp_path = os.path.join(TEMP_DIR, f"temp_{os.urandom(4).hex()}.pdf")
            with open(temp_path, "wb") as f:
                # Escritura en bloques de 10MB
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
        timeout_keep_alive=7200  # 2 horas
    )