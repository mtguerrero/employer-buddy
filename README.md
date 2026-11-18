# Employer Buddy

Asistente por WhatsApp que guarda tu trayectoria profesional y, por cada vacante que le envías,
evalúa qué tanto encajas y prepara una hoja de vida ajustada, en español y opcionalmente en inglés.
Tú revisas el resultado y postulas.

## Estado

Fase A (configuración del perfil) en construcción:

- El webhook de WhatsApp recibe mensajes, los guarda y los encola. Solo atiende a los números
  de `ALLOWED_NUMBERS`; los demás se ignoran sin guardar nada.
- Si envías tu HV (PDF, Word o foto) o escribes tu trayectoria, Claude la convierte en el
  **perfil maestro** (solo hechos) y el bot te pregunta, una por una, por los datos que faltan.
- Cada respuesta actualiza el perfil. Se registran los tokens usados por persona.

Pendiente: página de revisión del perfil, plantilla de estilo, y la fase B (vacantes).

## Cómo funciona

- **API web** (`employer_buddy.main`): recibe el webhook de WhatsApp, valida la firma, guarda el
  mensaje y encola un trabajo. Responde de inmediato, porque Meta reintenta si tarda.
- **Worker** (`employer_buddy.worker`): toma trabajos de la cola (tabla `jobs` en PostgreSQL) y
  hace la parte lenta. Reintenta con espera creciente hasta 5 veces.
- **Claude** (`employer_buddy.ai`): extrae el perfil con salida JSON validada contra
  `profile_schema.py`. Si el modelo declina, usa el respaldo automático del servidor.
- **PostgreSQL**: usuarios, mensajes, cola, archivos recibidos, perfil y consumo de tokens. Todas las tablas con datos personales llevan
  `user_id`, para poder abrir el servicio a más personas sin migrar datos.

## Desarrollo

Requisitos: Python 3.13, [uv](https://docs.astral.sh/uv/) y PostgreSQL.

```bash
./scripts/dev-db.sh          # inicia PostgreSQL y crea las bases si no existen
uv sync
cp .env.example .env         # completa los valores de WhatsApp
uv run alembic upgrade head
```

Ejecutar:

```bash
uv run uvicorn employer_buddy.main:app --reload
uv run employer-buddy-worker
```

Pruebas y estilo:

```bash
uv run pytest
uv run ruff check . && uv run ruff format --check .
```

Las pruebas usan la base `employer_buddy_test` y simulan WhatsApp y Claude; no necesitan claves.
