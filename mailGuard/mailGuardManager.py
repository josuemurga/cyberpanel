import json
import socket

AGENT_SOCKET = '/run/mailguard-agent.sock'


def _call_agent(payload, timeout=45):
    """Envía un comando al agente Mail Guard via Unix socket."""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect(AGENT_SOCKET)
            s.sendall(json.dumps(payload).encode() + b'\n')
            data = b''
            while True:
                chunk = s.recv(65536)
                if not chunk:
                    break
                data += chunk
                if b'\n' in data:
                    break
        return json.loads(data.decode())
    except FileNotFoundError:
        return {'status': 0, 'error': 'Agente Mail Guard no disponible (socket no encontrado)'}
    except Exception as e:
        return {'status': 0, 'error': str(e)}


def get_stats(hours=168):
    resp = _call_agent({'cmd': 'stats', 'hours': int(hours)})
    if not resp.get('status'):
        return None, resp.get('error', 'Error desconocido')
    return resp['data'], None


def get_queue():
    resp = _call_agent({'cmd': 'queue'})
    if not resp.get('status'):
        return None, resp.get('error', 'Error desconocido')
    return resp['data'], None


def block_user(username):
    resp = _call_agent({'cmd': 'block', 'user': username})
    if not resp.get('status'):
        return False, resp.get('error', 'Error desconocido')
    return True, resp.get('data', 'Bloqueado')


def unblock_user(username):
    resp = _call_agent({'cmd': 'unblock', 'user': username})
    if not resp.get('status'):
        return False, resp.get('error', 'Error desconocido')
    return True, resp.get('data', 'Desbloqueado')


def delete_queue(queue_ids):
    resp = _call_agent({'cmd': 'delete_queue', 'ids': queue_ids})
    if not resp.get('status'):
        return False, resp.get('error', 'Error desconocido')
    return True, resp.get('data', 'Eliminado')


def flush_bounces():
    resp = _call_agent({'cmd': 'flush_bounces'})
    if not resp.get('status'):
        return False, resp.get('error', 'Error desconocido')
    return True, resp.get('data', 'Limpieza lista')


def force_ipv4():
    resp = _call_agent({'cmd': 'force_ipv4'})
    if not resp.get('status'):
        return False, resp.get('error', 'Error desconocido')
    return True, resp.get('data', 'Aplicado')
