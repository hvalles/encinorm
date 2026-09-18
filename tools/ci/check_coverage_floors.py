"""Gate de pisos de cobertura POR MODULO sobre `coverage json` (D-04/D-06 de Fase 1).

`coverage.py` no soporta `fail_under` por fichero: `[report] fail_under` es un
unico total (verificado en la doc oficial). Este script lee el JSON que produce
`coverage json` y aplica un piso por modulo, de modo que los modulos del seam de
dialectos no puedan esconderse tras la cobertura de SQLite.

Falla CERRADO si un modulo del mapa NO aparece en el reporte: iterar el mapa con
`.get()` haria pasar el gate al borrar el fichero (Pitfall J). Un gate que se
apaga solo no es un gate. Mismo contrato que `tools/ci/check_skips.py`: solo
stdlib, mensajes `FALLO:` a stderr, `raise SystemExit(main(sys.argv))`.

NO hay pisos de adaptador todavia A PROPOSITO: en la corrida equivalente a CI
`oracle.py` mide 16% porque Oracle esta deseleccionado en el job `test`. Un piso
fijado antes de que existan los jobs de motor es una ficcion. Se fijan en la
fase siguiente a partir del primer run verde de `engine-heavy`, cuya cobertura ya
sube al job `coverage`.
"""

import json
import sys

FLOORS: dict[str, float] = {
    # Tiny, puro y critico para la seguridad: la tabla accept/reject es
    # exhaustiva, asi que no hay excusa para menos de 100.
    "encino_orm/dialects/identifiers.py": 100.0,
    # Puro: 6 estrategias x 3 verbos + los caminos de rechazo.
    "encino_orm/dialects/builders.py": 95.0,
    # Objeto de valor puro: casos de `{n}` dispersos/duplicados/malformados.
    "encino_orm/query.py": 95.0,
}


def _norm(path: str) -> str:
    """Normaliza separadores para que el script sea igual en Windows y Linux."""
    return path.replace("\\", "/")


def main(argv: list[str] | None = None) -> int:
    """Devuelve 1 si algun modulo incumple su piso o si el JSON no se puede leer."""
    if argv is None:
        argv = sys.argv
    path = argv[1] if len(argv) > 1 else "coverage.json"
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        # Falla cerrado: un reporte ausente o ilegible no puede convertirse en 0.
        print(f"FALLO: no se pudo leer {path!r}: {exc}", file=sys.stderr)
        return 1

    files = {_norm(key): value for key, value in data.get("files", {}).items()}
    failures = []
    for module, floor in FLOORS.items():
        entry = files.get(module)
        if entry is None:
            failures.append(f"{module}: AUSENTE del reporte (piso {floor}%)")
            continue
        actual = entry["summary"]["percent_covered"]
        if actual < floor:
            failures.append(f"{module}: {actual:.1f}% < piso {floor}%")

    if failures:
        for line in failures:
            print(f"FALLO: {line}", file=sys.stderr)
        return 1
    print(f"OK: {len(FLOORS)} modulo(s) cumplen su piso.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
