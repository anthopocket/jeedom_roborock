#!/usr/bin/env python3
import sys, os, json, argparse, asyncio

SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
VENV_LIB   = os.path.join(SCRIPT_DIR, 'venv', 'lib')
if os.path.isdir(VENV_LIB):
    for pyver in sorted(os.listdir(VENV_LIB)):
        sp = os.path.join(VENV_LIB, pyver, 'site-packages')
        if os.path.isdir(sp):
            sys.path.insert(0, sp)
            break

from roborock.web_api import RoborockApiClient

CODE_PIPE    = '/tmp/roborock/code_pipe'
CLIENT_STATE = '/tmp/roborock/auth_state'
RESULT_FILE  = '/tmp/roborock/auth_result'

async def request_code(email, base_url):
    if os.path.exists(CODE_PIPE):
        os.remove(CODE_PIPE)
    if os.path.exists(RESULT_FILE):
        os.remove(RESULT_FILE)

    c = RoborockApiClient(username=email, base_url=base_url or None)
    country      = await c.country
    country_code = await c.country_code
    resolved_url = await c.base_url

    if country and country_code:
        await asyncio.wait_for(c.request_code_v4(), timeout=30)
        use_v4 = True
    else:
        await asyncio.wait_for(c.request_code(), timeout=30)
        use_v4 = False

    # Ecrit le state pour signaler que le code a ete envoye
    with open(CLIENT_STATE, 'w') as f:
        json.dump({
            'email':        email,
            'base_url':     str(resolved_url) if resolved_url else (base_url or ''),
            'country':      country or '',
            'country_code': str(country_code) if country_code else '',
            'use_v4':       use_v4,
        }, f)

    # Attend que le code arrive dans CODE_PIPE (max 120 secondes)
    for _ in range(240):
        await asyncio.sleep(0.5)
        if os.path.exists(CODE_PIPE):
            with open(CODE_PIPE) as f:
                code = f.read().strip()
            os.remove(CODE_PIPE)
            if os.path.exists(CLIENT_STATE):
                os.remove(CLIENT_STATE)
            # Valide avec la MEME instance
            if use_v4 and country and country_code:
                ud = await asyncio.wait_for(
                    c.code_login_v4(code, country=country, country_code=int(country_code)),
                    timeout=30)
            else:
                ud = await asyncio.wait_for(c.code_login(code), timeout=30)
            result = json.dumps(ud.as_dict())
            # Ecrit le resultat pour que codeLogin ajax le lise
            with open(RESULT_FILE, 'w') as f:
                f.write(result)
            print(result)
            return

    raise Exception("Timeout: code non recu en 120 secondes")

async def pass_login(email, password, base_url):
    c = RoborockApiClient(username=email, base_url=base_url or None)
    try:
        ud = await asyncio.wait_for(c.pass_login(password), timeout=30)
    except TypeError:
        ud = await asyncio.wait_for(c.pass_login(email, password), timeout=30)
    result = json.dumps(ud.as_dict())
    with open(RESULT_FILE, 'w') as f:
        f.write(result)
    print(result)

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--action',   required=True)
    p.add_argument('--email',    default='')
    p.add_argument('--code',     default='')
    p.add_argument('--password', default='')
    p.add_argument('--baseurl',  default='')
    args = p.parse_args()
    try:
        if args.action == 'request_code':
            asyncio.run(request_code(args.email, args.baseurl))
        elif args.action == 'pass_login':
            asyncio.run(pass_login(args.email, args.password, args.baseurl))
    except Exception as e:
        # Ecrit l'erreur dans RESULT_FILE pour que l'ajax la lise
        with open(RESULT_FILE, 'w') as f:
            f.write(json.dumps({'error': str(e)}))
        print(f"Erreur: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()