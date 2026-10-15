"""Guardas deterministas: intención, PII contextual y permisos del simulador."""
from __future__ import annotations
import re
import unicodedata

ABSTENCION = 'No puedo responder con los datos disponibles.'
EMAIL = re.compile(r'\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b', re.I)
PHONE = re.compile(r'(?<!\d)(?:\+593[ -]?0?[ -]?9(?:[ -]?\d){8}|09(?:[ -]?\d){8})(?!\d)')
CEDULA = re.compile(r'(?i)(\b(?:cedula|cédula|identificacion|identificación|dni)\s*(?:es|:|=)?\s*)(\d{10})(?!\d)')
SECRET = re.compile(r'\b(?:sk-(?:proj-)?[A-Za-z0-9_-]{16,}|AKIA[A-Z0-9]{16}|ghp_[A-Za-z0-9]{30,})\b|(?i:api[_ -]?key|password|contraseña|token)\s*[=:]\s*[^\s,;]{8,}')

def normalizar(text: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFKD', text.casefold()) if not unicodedata.combining(c))

def redactar(text: str) -> str:
    text = EMAIL.sub('[CORREO]', text)
    text = PHONE.sub('[TELEFONO]', text)
    text = CEDULA.sub(lambda m: m[1] + '[CEDULA]', text)
    # A bare Ecuadorian ID is treated as PII only with a valid province prefix;
    # quantities, UUIDs and ISO dates are preserved.
    text = re.sub(r'(?<![\w.-])(?:0[1-9]|1\d|2[0-4])\d{8}(?![\w.-])', '[CEDULA]', text)
    return SECRET.sub('[SECRETO]', text)

def mask(data=None, **kwargs):
    if isinstance(data, str): return redactar(data)
    if isinstance(data, dict): return {k: mask(v) for k, v in data.items()}
    if isinstance(data, (list, tuple)): return [mask(x) for x in data]
    return data

def inyeccion(text: str, version: str = 'v2') -> bool:
    n = normalizar(text)
    if version == 'v1':
        return bool(re.search(r'ignore all previous|ignora (?:tus|las) instrucciones', n))
    # An explanation of attacks or a negative instruction is legitimate.
    if re.search(r'^(?:no ejecutes|no borres)', n) and not re.search(r'[;.!?].*(?:ignora|revela|borra|elimina|extrae|envia)', n): return False
    patterns = [r'(?:ignora|olvida|omite|desobedece|ignore|forget).{0,65}(?:instruccion|regla|restriccion|instruction)',
                r'(?:sin|no tuvieras).{0,12}(?:reglas|restricciones)',
                r'(?:muestra|revela|imprime|print|traduce|dame|envia|extrae).{0,90}(?:system prompt|prompt del sistema|reglas internas|clave|secret|token|kubeconfig)',
                r'(?:borra|elimina|destruye|ejecuta|ejecutar).{0,90}(?:kubectl.*delete|namespace|base de datos|tabla de ventas)',
                r'kubectl\s+(?:-n\s+\S+\s+)?delete\b']
    return any(re.search(p, n) for p in patterns)

def entrada(text: str, version='v2') -> dict:
    if len(text) > 6000: return {'decision':'bloquear','texto':ABSTENCION,'motivo':'longitud'}
    if inyeccion(text, version): return {'decision':'bloquear','texto':ABSTENCION,'motivo':'inyeccion'}
    safe = redactar(text)
    return {'decision':'redactar' if safe != text else 'pasar','texto':safe,'motivo':'pii' if safe != text else 'ok'}

def salida(text: str, version="v2") -> dict:
    if SECRET.search(text): return {'decision':'bloquear','texto':ABSTENCION,'motivo':'secreto'}
    if version == 'v2' and text.strip().startswith(ABSTENCION) and text.strip() != ABSTENCION:
        return {'decision':'redactar','texto':ABSTENCION,'motivo':'abstencion_canonica'}
    safe = redactar(text)
    return {'decision':'redactar' if safe != text else 'pasar','texto':safe,'motivo':'pii' if safe != text else 'ok'}

def validar_entrada(text):
    r=entrada(text); return r['decision'] != 'bloquear', r['texto']

def validar_salida(text):
    r=salida(text); return r['decision'] != 'bloquear', r['texto']

def permitir_reinicio(namespace, deployment, approved=False):
    allowed = approved is True and namespace == 'payments' and deployment == 'checkout-api'
    return {'decision':'pasar' if allowed else 'bloquear', 'motivo':'reinicio_simulado_aprobado' if allowed else 'requiere_aprobacion_y_allowlist'}
