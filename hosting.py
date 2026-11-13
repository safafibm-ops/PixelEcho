"""Explicit public origin support without trusting arbitrary forwarded hosts."""
from urllib.parse import urlsplit


def canonical_origin(value):
    try:
        parsed=urlsplit(value)
        if (parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password
                or parsed.path not in ('','/') or parsed.query or parsed.fragment):
            return None
        host=parsed.hostname.casefold()
        if ':' in host:host=f'[{host}]'
        port=parsed.port
        if port and port != (443 if parsed.scheme=='https' else 80):host+=f':{port}'
        return f'{parsed.scheme}://{host}'
    except (ValueError,TypeError):
        return None


def deployment_settings(environment):
    supplied=(environment.get('PUBLIC_ORIGIN') or environment.get('RENDER_EXTERNAL_URL') or '').strip()
    public=canonical_origin(supplied) if supplied else ''
    if supplied and not public:
        raise RuntimeError('PUBLIC_ORIGIN or RENDER_EXTERNAL_URL must be a valid HTTP(S) origin without credentials, path, query or fragment.')
    allowed=['127.0.0.1','localhost','testserver']
    if public:
        host=urlsplit(public).hostname
        if host not in allowed:allowed.append(host)
    return public,allowed


def same_origin(origin, request_base_url, public_origin):
    expected=public_origin or canonical_origin(request_base_url)
    actual=canonical_origin(origin)
    return bool(actual and expected and actual==expected)
