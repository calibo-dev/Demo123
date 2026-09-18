import logging
import os

from dotenv import load_dotenv

load_dotenv()

from latest_ai_development.secrets_manager import SecretsManager

logger = logging.getLogger("uvicorn.error")
_TRACING_INITIALIZED = False


def get_tracing_backend() -> str:
    """Return the normalized tracing backend name."""
    value = os.getenv("TRACING_BACKEND", "CREWAI")
    logger.info(f"Tracing backend: {value}")
    return value.strip().upper() or "CREWAI"


def _resolve_langsmith_api_key() -> str | None:
    api_key = os.getenv("LANGSMITH_API_KEY")
    if api_key:
        return api_key

    secret_name = os.getenv("LANGSMITH_API_KEY_SECRET")
    if not secret_name:
        return None

    return SecretsManager().get_secret(secret_name)


def _instrument_openinference_sdk(instrumentor_cls, tracer_provider) -> None:
    try:
        instrumentor = instrumentor_cls()
        if getattr(instrumentor, "is_instrumented_by_opentelemetry", False):
            logger.debug("%s already instrumented; skipping", instrumentor_cls.__name__)
            return

        instrumentor.instrument(tracer_provider=tracer_provider)
        logger.info("%s OpenTelemetry instrumentation enabled", instrumentor_cls.__name__)
    except Exception as exc:
        logger.debug("%s OpenTelemetry instrumentation skipped | error=%s", instrumentor_cls.__name__, exc)


def _instrument_provider_openinference(provider: str, tracer_provider) -> None:
    provider = (provider or "").strip().upper()

    try:
        if provider in {"OPENAI", "AZUREAI"}:
            from openinference.instrumentation.openai import OpenAIInstrumentor

            _instrument_openinference_sdk(OpenAIInstrumentor, tracer_provider)
            return

        if provider == "GEMINIAI":
            from openinference.instrumentation.google_genai import GoogleGenAIInstrumentor

            _instrument_openinference_sdk(GoogleGenAIInstrumentor, tracer_provider)
            return

        if provider == "ANTHROPICAI":
            from openinference.instrumentation.anthropic import AnthropicInstrumentor

            _instrument_openinference_sdk(AnthropicInstrumentor, tracer_provider)
            return
    except ImportError as exc:
        logger.debug(
            "OpenInference instrumentation for PROVIDER=%s unavailable | error=%s",
            provider,
            exc,
        )
        return

    logger.debug("No provider-specific OpenInference instrumentation for PROVIDER=%s", provider)


def _instrument_crewai_openinference(tracer_provider) -> None:
    try:
        from openinference.instrumentation.crewai import CrewAIInstrumentor
    except ImportError as exc:
        logger.debug("CrewAI OpenTelemetry instrumentation unavailable | error=%s", exc)
        return

    _instrument_openinference_sdk(CrewAIInstrumentor, tracer_provider)


def initialize_langsmith_tracing() -> None:
    global _TRACING_INITIALIZED

    if _TRACING_INITIALIZED or get_tracing_backend() != "LANGSMITH":
        return

    logger.info("langsmith tracing initialized")
    try:
        # Disable CrewAI's anonymous telemetry when LangSmith is the selected backend.
        os.environ["CREWAI_DISABLE_TELEMETRY"] = "true"

        api_key = _resolve_langsmith_api_key()
        if not api_key:
            raise ValueError(
                "TRACING_BACKEND is LANGSMITH but LANGSMITH_API_KEY or "
                "LANGSMITH_API_KEY_SECRET is not configured."
            )

        os.environ["LANGSMITH_API_KEY"] = api_key

        from langsmith.integrations.otel import OtelSpanProcessor
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.trace import ProxyTracerProvider

        tracer_provider = trace.get_tracer_provider()
        if isinstance(tracer_provider, ProxyTracerProvider):
            tracer_provider = TracerProvider()
            trace.set_tracer_provider(tracer_provider)

        tracer_provider.add_span_processor(
            OtelSpanProcessor(api_key=api_key, project=os.getenv("LANGSMITH_PROJECT"))
        )

        _instrument_crewai_openinference(tracer_provider)
        _instrument_provider_openinference(os.getenv("PROVIDER"), tracer_provider)

        _TRACING_INITIALIZED = True
        logger.info(
            "LangSmith tracing enabled | project=%s",
            os.getenv("LANGSMITH_PROJECT") or "not set",
        )
    except Exception as e:
        os.environ["TRACING_BACKEND"] = "CREWAI"
        logger.warning(
            "LangSmith tracing initialization failed; falling back to CrewAI tracing | error=%s",
            e,
        )
