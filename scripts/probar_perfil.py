"""Prueba la extracción del perfil con Claude, sin WhatsApp ni base de datos.

Uso:
    uv run python scripts/probar_perfil.py ruta/a/tu_hv.pdf

Necesita ANTHROPIC_API_KEY en el archivo .env. Acepta PDF, DOCX, JPG o PNG.
"""

import json
import mimetypes
import sys
from pathlib import Path

from employer_buddy.ai import ClaudeProfileAI
from employer_buddy.config import get_settings
from employer_buddy.documents import DOCX, to_source


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    path = Path(sys.argv[1]).expanduser()
    if not path.is_file():
        sys.exit(
            f"No encontré el archivo: {path}\nTip: arrastra el archivo a la terminal para pegar su ruta."
        )
    mime = DOCX if path.suffix.lower() == ".docx" else mimetypes.guess_type(path.name)[0] or ""
    source = to_source(path.read_bytes(), mime)

    result = ClaudeProfileAI(get_settings()).extract(source, None)
    print(json.dumps(result.update.profile.model_dump(), ensure_ascii=False, indent=2))
    print("\nPreguntas para completar el perfil:")
    for question in result.update.questions:
        print(f"- {question}")
    print(f"\nTokens: {result.input_tokens} de entrada, {result.output_tokens} de salida")


if __name__ == "__main__":
    main()
