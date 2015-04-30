from Crypto.PublicKey import RSA
from functools import wraps
from flask import abort, g

KEYPAIR_DEFAULT = {
    'bits': 2048,
}


def generate_ssh_keypair(bits=KEYPAIR_DEFAULT['bits']):
    new_key = RSA.generate(bits)
    public_key = new_key.publickey().exportKey(format="OpenSSH")
    private_key = new_key.exportKey(format="PEM")
    return private_key, public_key


def requires_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not g.user.is_admin:
            abort(403)
        return f(*args, **kwargs)

    return decorated
