from Crypto.PublicKey import RSA

KEYPAIR_DEFAULT = {
    'bits': 2048,
}


def generate_ssh_keypair(bits=KEYPAIR_DEFAULT['bits']):
    new_key = RSA.generate(bits)
    public_key = new_key.publickey().exportKey("PEM")
    private_key = new_key.exportKey("PEM")
    return private_key, public_key
