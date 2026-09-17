"""Gate de tests omitidos sobre el JUnit-XML (CI-02).

Un unico test omitido en el job de motores requeridos es un gate roto: el job
deselecciona los motores opcionales con `-m "not optional_engine"`, asi que
cualquier `skipped > 0` que quede en el XML es un skip NO marcado. Ver
`.planning/phases/01-safety-net-ci-gates-test-infrastructure/01-RESEARCH.md`,
seccion "Pattern 2".
"""

import sys
import xml.etree.ElementTree as ET


def total_skipped(path: str) -> int:
    """Suma el atributo `skipped` de todos los `<testsuite>` del XML."""
    root = ET.parse(path).getroot()
    # pytest puede emitir varios <testsuite> (uno por clase/fichero); se suman
    # todos porque cualquiera de ellos puede esconder un skip no marcado.
    return sum(int(ts.get("skipped", 0)) for ts in root.iter("testsuite"))


def main(argv: list[str] | None = None) -> int:
    """Devuelve 1 si hay algun test omitido o si el XML no se puede leer."""
    if argv is None:
        argv = sys.argv
    path = argv[1] if len(argv) > 1 else "junit.xml"
    try:
        skipped = total_skipped(path)
    except (OSError, ET.ParseError) as exc:
        # Falla cerrado: un XML ausente o ilegible no puede convertirse en un 0.
        print(f"FALLO: no se pudo leer el JUnit-XML {path!r}: {exc}", file=sys.stderr)
        return 1
    if skipped:
        print(
            f"FALLO: {skipped} test(s) omitidos. Un skip en CI es un gate roto.",
            file=sys.stderr,
        )
        return 1
    print("OK: 0 tests omitidos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
