from __future__ import annotations

import ipaddress
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import uvicorn
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def certificate_directory() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / "WealthFlow" / "dev-certs"
    return Path.home() / ".wealthflow" / "dev-certs"


def ensure_certificate(directory: Path) -> tuple[Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    certificate_path = directory / "localhost-cert.pem"
    key_path = directory / "localhost-key.pem"

    if certificate_path.is_file() and key_path.is_file():
        return certificate_path, key_path

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.now(timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now.replace(tzinfo=None))
        .not_valid_after((now + timedelta(days=365)).replace(tzinfo=None))
        .add_extension(
            x509.SubjectAlternativeName(
                [
                    x509.DNSName("localhost"),
                    x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
                ]
            ),
            critical=False,
        )
        .sign(private_key, hashes.SHA256())
    )

    key_path.write_bytes(
        private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.PKCS8,
            encryption_algorithm=serialization.NoEncryption(),
        )
    )
    certificate_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    return certificate_path, key_path


def main() -> None:
    certificate_path, key_path = ensure_certificate(certificate_directory())
    os.environ["COOKIE_SECURE"] = "true"
    uvicorn.run(
        "main:app",
        host="127.0.0.1",
        port=8443,
        reload=True,
        ssl_certfile=str(certificate_path),
        ssl_keyfile=str(key_path),
    )


if __name__ == "__main__":
    main()