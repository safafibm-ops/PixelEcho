"""Render/hosted entry point. Exactly one worker preserves in-memory cases."""
import os
import uvicorn


def main():
    try:
        port=int(os.environ.get('PORT','10000'))
        if not 1<=port<=65535:raise ValueError
    except ValueError:
        raise RuntimeError('PORT must be an integer between 1 and 65535.') from None
    # PUBLIC_ORIGIN (or Render's URL) handles HTTPS origins explicitly.
    # Do not trust arbitrary client-supplied forwarding headers.
    uvicorn.run('server:app',host='0.0.0.0',port=port,workers=1,proxy_headers=False)


if __name__=='__main__':
    main()
