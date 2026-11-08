#!/usr/bin/env python3
"""Small read-only MCP client. Python 3.9+, no third-party dependencies."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import sys
import urllib.request

ENDPOINT = 'https://mcp.openboostai.com/mcp-servers/openboost-all-mcp'
SCHEMAS = Path(__file__).resolve().parents[1] / 'references/tool-schemas.json'


def credential():
    key = os.getenv('OPENBOOST_SECRET_KEY')
    if key:
        return key
    path = Path(os.getenv('CODEX_HOME', str(Path.home() / '.codex'))) / 'config.toml'
    text = path.read_text()
    try:
        import tomllib
    except ImportError:
        # Narrow fallback for Python 3.9/3.10: only our literal header table.
        match = re.search(r'^\[mcp_servers\.openboost-all-mcp\.http_headers\]\s*\n([^\[]*)', text, re.M)
        value = re.search(r'^\s*[\"\']?secret-key[\"\']?\s*=\s*"([^"\n]+)"\s*$', match.group(1), re.M) if match else None
        if not value:
            raise ValueError('Set OPENBOOST_SECRET_KEY or configure the literal secret-key header in Codex.')
        return value.group(1)
    server = tomllib.loads(text)['mcp_servers']['openboost-all-mcp']
    if server.get('url') != ENDPOINT:
        raise ValueError('Configured endpoint does not match OpenBoost.')
    if 'secret-key' in server.get('env_http_headers', {}):
        return os.environ[server['env_http_headers']['secret-key']]
    return server['http_headers']['secret-key']


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('Redirect refused; credential was not forwarded.')


class Client:
    def __init__(self, key):
        self.headers = {'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream', 'secret-key': key}
        self.opener = urllib.request.build_opener(NoRedirect)
        self.counter = 0

    def rpc(self, method, params=None, notification=False):
        self.counter += 1
        payload = {'jsonrpc': '2.0', 'method': method}
        if params is not None:
            payload['params'] = params
        if not notification:
            payload['id'] = self.counter
        req = urllib.request.Request(ENDPOINT, json.dumps(payload).encode(), self.headers)
        with self.opener.open(req, timeout=45) as response:
            session = response.headers.get('Mcp-Session-Id')
            if session:
                self.headers['Mcp-Session-Id'] = session
            if notification:
                return {}
            if 'text/event-stream' in response.headers.get('Content-Type', ''):
                data = []
                result = None
                for raw in response:
                    line = raw.decode().rstrip('\r\n')
                    if line.startswith('data:'):
                        data.append(line[5:].lstrip())
                    elif not line and data:
                        candidate = json.loads('\n'.join(data))
                        data = []
                        if candidate.get('id') == payload['id']:
                            result = candidate
                            break
                if result is None:
                    raise ValueError('MCP stream ended without matching response.')
            else:
                result = json.load(response)
        if result.get('error'):
            raise ValueError('MCP RPC error: ' + json.dumps(result['error'], ensure_ascii=False))
        return result['result']

    def start(self):
        result = self.rpc('initialize', {'protocolVersion': '2024-11-05', 'capabilities': {}, 'clientInfo': {'name': 'openboost-parasite-radar', 'version': '1.0.0'}})
        self.headers['MCP-Protocol-Version'] = result['protocolVersion']
        self.rpc('notifications/initialized', notification=True)


def validate(args, schema):
    if not isinstance(args, dict):
        raise ValueError('Arguments must be a JSON object.')
    props = schema.get('properties', {})
    missing = set(schema.get('required', [])) - args.keys()
    unknown = args.keys() - props.keys()
    if missing or unknown:
        raise ValueError('Missing: %s; unknown: %s' % (sorted(missing), sorted(unknown)))
    types = {'string': str, 'integer': int, 'number': (int, float), 'boolean': bool, 'array': list, 'object': dict}
    for k, v in args.items():
        typ = props[k].get('type')
        if typ in types and (not isinstance(v, types[typ]) or (typ in ('number', 'integer') and isinstance(v, bool))):
            raise ValueError('Incorrect type for ' + k + ': expected ' + typ)


def unpack(result):
    """Preserve raw MCP result; decode JSON strings only for inspection."""
    values = []
    for block in result.get('content', []):
        if block.get('type') != 'text':
            continue
        value = block.get('text')
        for _ in range(5):
            if not isinstance(value, str):
                break
            try:
                value = json.loads(value)
            except ValueError:
                break
        values.append(value)
    return values[0] if len(values) == 1 else values


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    s = sub.add_parser('schema'); s.add_argument('tool', nargs='?')
    s.add_argument('--live', action='store_true', help='Read current server schemas')
    c = sub.add_parser('call'); c.add_argument('tool'); c.add_argument('--args', required=True, help='JSON file path')
    c.add_argument('--out', required=True, help='New raw evidence JSON path; never overwritten')
    opts = parser.parse_args()
    local = {t['name']: t for t in json.loads(SCHEMAS.read_text())['tools']}
    if opts.tool and opts.tool not in local:
        raise ValueError('Tool not in this skill read-only allowlist.')
    if opts.command == 'schema' and not opts.live:
        print(json.dumps(local.get(opts.tool, list(local)), ensure_ascii=False, indent=2)); return
    if opts.command == 'call':
        out = Path(opts.out)
        if out.exists():
            raise ValueError('Evidence output already exists; use a fresh path.')
        arguments = json.loads(Path(opts.args).read_text())
        validate(arguments, local[opts.tool]['inputSchema'])
    key = credential()
    client = Client(key); client.start()
    if opts.command == 'schema':
        result = client.rpc('tools/list')
        tools = result.get('tools', [])
        while result.get('nextCursor'):
            result = client.rpc('tools/list', {'cursor': result['nextCursor']})
            tools.extend(result.get('tools', []))
        selected = [t for t in tools if t['name'] in local and (not opts.tool or t['name'] == opts.tool)]
        print(json.dumps(selected, ensure_ascii=False, indent=2).replace(key, '[REDACTED]')); return
    result = client.rpc('tools/call', {'name': opts.tool, 'arguments': arguments})
    record = {'tool': opts.tool, 'arguments': arguments, 'retrieved_at': dt.datetime.now(dt.timezone.utc).isoformat(), 'result': result, 'payload': unpack(result)}
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('x') as f:
        f.write(json.dumps(record, ensure_ascii=False, indent=2).replace(key, '[REDACTED]'))
    print(json.dumps({'saved': str(out.resolve()), 'mcp_is_error': bool(result.get('isError')), 'note': 'Inspect nested business code, dates and empty data before using as evidence.'}))
    if result.get('isError'):
        sys.exit(2)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        message = str(exc)
        try:
            message = message.replace(credential(), '[REDACTED]')
        except Exception:
            pass
        print(type(exc).__name__ + ': ' + message, file=sys.stderr)
        sys.exit(1)
