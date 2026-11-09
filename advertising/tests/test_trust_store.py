"""Outbound HTTPS refuses the eMudhra chains distrusted in October 2026."""

import hashlib
import re
import ssl

import certifi
import httplib2.certs
from django.test import SimpleTestCase

# SHA-256 of each root's DER encoding, as `openssl x509 -fingerprint -sha256`
# prints it, lowercased and without colons.
DISTRUSTED_ROOTS = {
    "emSign ECC Root CA - G3": "86a1ecba089c4a8d3bbe2734c612ba341d813e043cf9e8a862cd5c57a36bbe6b",
    "AAA Certificate Services": "d7a7a0fb5d7e2731d771e9484ebcdef71d5f0c3e0a2948782bc83ee0ea699ef4",
}

PEM_BLOCK = re.compile(r"-----BEGIN CERTIFICATE-----.+?-----END CERTIFICATE-----", re.S)


class TrustStoreTests(SimpleTestCase):
    """Eight eMudhra intermediate CAs had private keys recoverable from the
    certificates themselves (CVE-2026-111943), so anyone could mint a
    certificate for any site that those chains would vouch for. They hang off
    the two roots above, and a plain bundle cannot block an intermediate — only
    drop its root — so certifi removed them from 2026.10.19.

    Every outbound call the app makes (httpx to the LSD and Graph, msal via
    requests to Entra, httplib2 in `room_schedules`) verifies against certifi,
    not the OS store, so these tests are the whole of the Python-side defence.
    The OS store is the image's job: the deploy repo's Dockerfile upgrades
    `ca-certificates`.
    """

    databases = []

    def test_certifi_excludes_the_distrusted_roots(self):
        bundled = {
            hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem)).hexdigest()
            for pem in PEM_BLOCK.findall(certifi.contents())
        }
        self.assertTrue(bundled, "parsed no certificates out of certifi's bundle")
        present = [name for name, fingerprint in DISTRUSTED_ROOTS.items() if fingerprint in bundled]
        self.assertEqual(present, [])

    def test_httplib2_verifies_against_certifi(self):
        """httplib2 falls back to its own `cacerts.txt` when certifi is not
        installed: 71 roots, AAA Certificate Services among them, with no fixed
        release. certifi is always present, so the fallback should be
        unreachable; this keeps it that way."""
        self.assertEqual(httplib2.certs.where(), certifi.where())
