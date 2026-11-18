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

- Cuando no quedan preguntas, o si escribes *perfil*, el bot envía un **enlace de un solo uso**
  (vence en 24 horas) a la página de revisión, donde corriges y confirmas el perfil. El enlace
  se cambia por una cookie firmada que dura 2 horas; en la base solo se guarda el hash.

Pendiente: plantilla de estilo y la fase B (vacantes).

## Cómo funciona

- **API web** (`employer_buddy.main`): recibe el webhook de WhatsApp, valida la firma, guarda el
  mensaje y encola un trabajo. Responde de inmediato, porque Meta reintenta si tarda.
- **Worker** (`employer_buddy.worker`): toma trabajos de la cola (tabla `jobs` en PostgreSQL) y
  hace la parte lenta. Reintenta con espera creciente hasta 5 veces.
- **Claude** (`employer_buddy.ai`): extrae el perfil con salida JSON validada contra
  `profile_schema.py`. Si el modelo declina, usa el respaldo automático del servidor.
- **Página de revisión** (`employer_buddy.web`): `/perfil` y `/api/perfil`. Configura
  `PUBLIC_BASE_URL` y `SESSION_SECRET` fuera de desarrollo; sin ellos la app no arranca.
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
