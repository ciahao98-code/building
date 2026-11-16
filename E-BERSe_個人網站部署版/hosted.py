"""Single-owner online entry point. Run behind the hosting provider's HTTPS proxy."""

import base64
import binascii
import hmac
import os
import re
from http.server import ThreadingHTTPServer
from pathlib import Path

import app


class PersonalHandler(app.Handler):
    def setup(self):
        self.request.settimeout(20)
        super().setup()

    def require_login(self):
        authorization = self.headers.get('Authorization', '')
        scheme, _, encoded = authorization.partition(' ')
        supplied = b''
        if scheme.lower() == 'basic' and len(encoded) <= 4096:
            try:
                supplied = base64.b64decode(encoded, validate=True)
            except (ValueError, binascii.Error):
                pass
        if hmac.compare_digest(supplied, self.server.credentials):
            return True
        self.send_response(401)
        self.send_header('WWW-Authenticate', 'Basic realm="E-BERSe Personal", charset="UTF-8"')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', '0')
        self.end_headers()
        return False

    def do_GET(self):
        if self.path == '/healthz':
            self.send_data(200, 'text/plain; charset=utf-8', b'ok')
        elif self.require_login():
            super().do_GET()

    def do_POST(self):
        if self.require_login():
            super().do_POST()


def main():
    email = os.environ.get('EAC_LOGIN_EMAIL', '').strip()
    password = os.environ.get('EAC_LOGIN_PASSWORD', '')
    if not re.fullmatch(r'[^@:\s]+@[^@:\s]+', email) or not email.isascii():
        raise SystemExit('Set EAC_LOGIN_EMAIL to your email address.')
    if len(password) < 16 or len(password.encode('utf-8')) > 512:
        raise SystemExit('Set EAC_LOGIN_PASSWORD to a unique password of at least 16 characters.')
    directory = os.environ.get('EAC_DATA_DIR', '').strip()
    if directory:
        data_path = Path(directory)
        if not data_path.is_dir() or not os.access(data_path, os.W_OK):
            raise SystemExit('EAC_DATA_DIR must be an existing writable directory.')
        app.DRAFT = data_path / 'case_draft.json'
    port = int(os.environ.get('PORT', '10000'))
    with ThreadingHTTPServer(('0.0.0.0', port), PersonalHandler) as server:
        server.credentials = f'{email}:{password}'.encode('utf-8')
        server.serve_forever()


if __name__ == '__main__':
    main()
