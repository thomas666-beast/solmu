"""Pure-Python Shamir Secret Sharing over GF(p).

p is the RFC 3526 2048-bit MODP prime. Any secret integer must be < p,
so byte chunks must be at most 255 bytes (255 * 8 = 2040 bits < 2048).
All arithmetic is done modulo p.
"""

import secrets

# RFC 3526 2048-bit MODP Group prime, hex form.
PRIME = int(
    "FFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD1"
    "29024E088A67CC74020BBEA63B139B22514A08798E3404DD"
    "EF9519B3CD3A431B302B0A6DF25F14374FE1356D6D51C245"
    "E485B576625E7EC6F44C42E9A637ED6B0BFF5CB6F406B7ED"
    "EE386BFB5A899FA5AE9F24117C4B1FE649286651ECE45B3D"
    "C2007CB8A163BF0598DA48361C55D39A69163FA8FD24CF5F"
    "83655D23DCA3AD961C62F356208552BB9ED529077096966D"
    "670C354E4ABC9804F1746C08CA18217C32905E462E36CE3B"
    "E39E772C180E86039B2783A2EC07A28FB5C55DF06F4C52C9"
    "DE2BCBF6955817183995497CEA956AE515D2261898FA0510"
    "15728E5A8AACAA68FFFFFFFFFFFFFFFF",
    16,
)

MAX_CHUNK_BYTES = 255


def split_secret(secret: int, threshold: int, total: int, prime: int = PRIME):
    """Split an integer secret into `total` shares, any `threshold` of which
    reconstruct it. Returns a list of (x, y) tuples with x in 1..total.
    """
    if threshold < 1 or total < threshold:
        raise ValueError("require 1 <= threshold <= total")
    if not 0 <= secret < prime:
        raise ValueError("secret must be in [0, prime)")

    # a_0 = secret, a_1..a_{t-1} random
    coeffs = [secret] + [secrets.randbelow(prime) for _ in range(threshold - 1)]

    points = []
    for x in range(1, total + 1):
        y = 0
        for c in reversed(coeffs):  # Horner's method
            y = (y * x + c) % prime
        points.append((x, y))
    return points


def lagrange_coeffs_at_zero(xs, prime: int = PRIME):
    """Lagrange basis coefficients for interpolation at x = 0.

    Depends only on the x values, so compute once and reuse for every chunk.
    """
    out = []
    for i, xi in enumerate(xs):
        num = den = 1
        for j, xj in enumerate(xs):
            if i != j:
                num = num * (-xj) % prime
                den = den * (xi - xj) % prime
        out.append(num * pow(den, -1, prime) % prime)
    return out


def reconstruct_secret(points, prime: int = PRIME, coeffs=None) -> int:
    """Reconstruct the secret from (x, y) shares via Lagrange interpolation
    at x = 0. Pass precomputed `coeffs` (from lagrange_coeffs_at_zero) when
    reconstructing many secrets that use the same x values.
    """
    if not points:
        raise ValueError("no points")
    xs = [x for x, _ in points]
    if len(set(xs)) != len(xs):
        raise ValueError("points must have distinct x")
    if coeffs is None:
        coeffs = lagrange_coeffs_at_zero(xs, prime)
    return sum(y * c for (_, y), c in zip(points, coeffs)) % prime
