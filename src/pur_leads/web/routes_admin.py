"""Admin user and settings routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from pur_leads.repositories.settings import SettingRecord
from pur_leads.repositories.userbots import UserbotAccountRecord
from pur_leads.repositories.web_auth import WebUserRecord
from pur_leads.services.ai_registry import AiRegistryService
from pur_leads.services.settings import DEFAULT_SETTINGS, RawSecretValueError, SettingsService
from pur_leads.services.task_registry import list_task_definitions
from pur_leads.services.userbots import UserbotAccountService
from pur_leads.services.web_auth import (
    AuthError,
    SessionValidationResult,
    UserConflictError,
    WebAuthService,
)
from pur_leads.web.dependencies import current_admin, get_auth_service, get_session

router = APIRouter(prefix="/api")


class TelegramAdminRequest(BaseModel):
    telegram_user_id: str
    telegram_username: str | None = None
    display_name: str | None = None


class UserUpdateRequest(BaseModel):
    status: str | None = None
    display_name: str | None = None


class SettingUpdateRequest(BaseModel):
    value: Any
    value_type: str
    scope: str = "global"
    scope_id: str | None = None
    reason: str | None = None
    description: str | None = None
    requires_restart: bool = False


class UserbotCreateRequest(BaseModel):
    display_name: str
    session_name: str
    session_path: str
    telegram_user_id: str | None = None
    telegram_username: str | None = None
    status: str = "active"
    priority: str = "normal"
    max_parallel_telegram_jobs: int = 1
    flood_sleep_threshold_seconds: int = 60
    make_default: bool = False


class AiModelLimitUpdateRequest(BaseModel):
    raw_limit: int | None = None
    utilization_ratio: float | None = None


class AiModelUpdateRequest(BaseModel):
    display_name: str | None = None
    context_window_tokens: int | None = None
    max_output_tokens: int | None = None
    status: str | None = None


class AiModelProfileUpsertRequest(BaseModel):
    profile_key: str
    display_name: str
    description: str | None = None
    max_input_tokens: int | None = None
    max_output_tokens: int | None = None
    temperature: float | None = None
    thinking_mode: str | None = None
    structured_output_required: bool = True
    status: str = "active"


class AiModelProfileUpdateRequest(BaseModel):
    display_name: str | None = None
    description: str | None = None
    max_input_tokens: int | None = None
    max_output_tokens: int | None = None
    temperature: float | None = None
    thinking_mode: str | None = None
    structured_output_required: bool | None = None
    status: str | None = None


class AiAgentRouteUpsertRequest(BaseModel):
    profile_id: str | None = None
    model_id: str | None = None
    route_role: str
    priority: int = 50
    enabled: bool = True
    max_output_tokens: int | None = None
    temperature: float | None = None
    thinking_enabled: bool = False
    thinking_mode: str | None = None
    structured_output_required: bool | None = None
    account_id: str | None = None


class AiAgentRouteUpdateRequest(BaseModel):
    enabled: bool | None = None
    priority: int | None = None
    max_output_tokens: int | None = None
    temperature: float | None = None
    thinking_enabled: bool | None = None
    thinking_mode: str | None = None
    structured_output_required: bool | None = None


@router.get("/admin/users")
def list_admin_users(
    _validated: SessionValidationResult = Depends(current_admin),
    auth_service: WebAuthService = Depends(get_auth_service),
) -> dict[str, Any]:
    return {"items": [_user_payload(user) for user in auth_service.list_admin_users()]}


@router.post("/admin/users/telegram")
def add_telegram_admin(
    payload: TelegramAdminRequest,
    validated: SessionValidationResult = Depends(current_admin),
    auth_service: WebAuthService = Depends(get_auth_service),
) -> dict[str, Any]:
    try:
        user = auth_service.add_telegram_admin(
            telegram_user_id=payload.telegram_user_id,
            telegram_username=payload.telegram_username,
            display_name=payload.display_name,
            actor=_actor(validated),
            actor_user_id=validated.user.id,
        )
    except UserConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except AuthError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return {"user": _user_payload(user)}


@router.patch("/admin/users/{user_id}")
def update_admin_user(
    user_id: str,
    payload: UserUpdateRequest,
    validated: SessionValidationResult = Depends(current_admin),
    auth_service: WebAuthService = Depends(get_auth_service),
) -> dict[str, Any]:
    try:
        user = auth_service.update_admin_user(
            user_id,
            actor=_actor(validated),
            actor_user_id=validated.user.id,
            status=payload.status,
            display_name=payload.display_name,
            update_display_name="display_name" in payload.model_fields_set,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="User not found") from exc
    except AuthError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"user": _user_payload(user)}


@router.get("/admin/userbots")
def list_userbot_accounts(
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = UserbotAccountService(session)
    return {"items": [_userbot_payload(service, account) for account in service.list_accounts()]}


@router.post("/admin/userbots")
def create_userbot_account(
    payload: UserbotCreateRequest,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    actor = _actor(validated)
    service = UserbotAccountService(session)
    try:
        account = service.create_account(
            display_name=payload.display_name,
            session_name=payload.session_name,
            session_path=payload.session_path,
            actor=actor,
            telegram_user_id=payload.telegram_user_id,
            telegram_username=payload.telegram_username,
            status=payload.status,
            priority=payload.priority,
            max_parallel_telegram_jobs=payload.max_parallel_telegram_jobs,
            flood_sleep_threshold_seconds=payload.flood_sleep_threshold_seconds,
        )
        if payload.make_default:
            SettingsService(session).set(
                "telegram_default_userbot_account_id",
                account.id,
                value_type="string",
                updated_by=actor,
                reason="userbot created as default",
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"userbot": _userbot_payload(service, account)}


@router.get("/admin/ai-registry")
def get_ai_registry(
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = AiRegistryService(session)
    return service.snapshot()


@router.post("/admin/ai-registry/bootstrap-defaults")
def bootstrap_ai_registry_defaults(
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = AiRegistryService(session)
    service.bootstrap_defaults(actor=_actor(validated))
    return service.snapshot()


@router.patch("/admin/ai-model-limits/{limit_id}")
def update_ai_model_limit(
    limit_id: str,
    payload: AiModelLimitUpdateRequest,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = AiRegistryService(session)
    try:
        limit = service.update_model_limit(
            limit_id,
            actor=_actor(validated),
            raw_limit=payload.raw_limit,
            utilization_ratio=payload.utilization_ratio,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="AI model limit not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"limit": limit}


@router.patch("/admin/ai-models/{model_id}")
def update_ai_model(
    model_id: str,
    payload: AiModelUpdateRequest,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = AiRegistryService(session)
    try:
        model = service.update_model_metadata(
            model_id,
            actor=_actor(validated),
            display_name=payload.display_name,
            context_window_tokens=payload.context_window_tokens,
            max_output_tokens=payload.max_output_tokens,
            status=payload.status,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="AI model not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"model": model}


@router.post("/admin/ai-models/{model_id}/profiles")
def upsert_ai_model_profile(
    model_id: str,
    payload: AiModelProfileUpsertRequest,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = AiRegistryService(session)
    try:
        profile = service.upsert_model_profile(
            model_id=model_id,
            profile_key=payload.profile_key,
            actor=_actor(validated),
            display_name=payload.display_name,
            description=payload.description,
            max_input_tokens=payload.max_input_tokens,
            max_output_tokens=payload.max_output_tokens,
            temperature=payload.temperature,
            thinking_mode=payload.thinking_mode,
            structured_output_required=payload.structured_output_required,
            status=payload.status,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="AI model not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"profile": profile}


@router.patch("/admin/ai-model-profiles/{profile_id}")
def update_ai_model_profile(
    profile_id: str,
    payload: AiModelProfileUpdateRequest,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = AiRegistryService(session)
    try:
        profile = service.update_model_profile(
            profile_id,
            actor=_actor(validated),
            display_name=payload.display_name,
            description=payload.description,
            max_input_tokens=payload.max_input_tokens,
            max_output_tokens=payload.max_output_tokens,
            temperature=payload.temperature,
            thinking_mode=payload.thinking_mode,
            structured_output_required=payload.structured_output_required,
            status=payload.status,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="AI model profile not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"profile": profile}


@router.post("/admin/ai-agents/{agent_key}/routes")
def upsert_ai_agent_route(
    agent_key: str,
    payload: AiAgentRouteUpsertRequest,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = AiRegistryService(session)
    try:
        route = service.upsert_agent_route(
            agent_key=agent_key,
            profile_id=payload.profile_id,
            model_id=payload.model_id,
            route_role=payload.route_role,
            actor=_actor(validated),
            account_id=payload.account_id,
            priority=payload.priority,
            enabled=payload.enabled,
            max_output_tokens=payload.max_output_tokens,
            temperature=payload.temperature,
            thinking_enabled=payload.thinking_enabled,
            thinking_mode=payload.thinking_mode,
            structured_output_required=payload.structured_output_required,
        )
    except KeyError as exc:
        raise HTTPException(
            status_code=404, detail="AI agent, model/profile, or account not found"
        ) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"route": route}


@router.patch("/admin/ai-routes/{route_id}")
def update_ai_agent_route(
    route_id: str,
    payload: AiAgentRouteUpdateRequest,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = AiRegistryService(session)
    try:
        route = service.update_agent_route(
            route_id,
            actor=_actor(validated),
            enabled=payload.enabled,
            priority=payload.priority,
            max_output_tokens=payload.max_output_tokens,
            temperature=payload.temperature,
            thinking_enabled=payload.thinking_enabled,
            thinking_mode=payload.thinking_mode,
            structured_output_required=payload.structured_output_required,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="AI agent route not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"route": route}


@router.get("/settings")
def list_settings(
    scope: str | None = None,
    _validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = SettingsService(session)
    records = service.list(scope=scope)
    items = [_setting_payload(record, is_default=False) for record in records]
    if scope in (None, "global"):
        explicit_global_keys = {
            record.key for record in records if record.scope == "global" and record.scope_id == ""
        }
        items.extend(
            _default_setting_payload(key, default)
            for key, default in DEFAULT_SETTINGS.items()
            if key not in explicit_global_keys
        )
    return {"items": sorted(items, key=lambda item: (item["scope"], item["key"]))}


@router.put("/settings/{key}")
def update_setting(
    key: str,
    payload: SettingUpdateRequest,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    service = SettingsService(session)
    try:
        service.set(
            key,
            payload.value,
            value_type=payload.value_type,
            updated_by=_actor(validated),
            scope=payload.scope,
            scope_id=payload.scope_id,
            reason=payload.reason,
            description=payload.description,
            requires_restart=payload.requires_restart,
        )
    except (RawSecretValueError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    record = service.repository.get(key, scope=payload.scope, scope_id=payload.scope_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Setting not found")
    return {"setting": _setting_payload(record, is_default=False)}


@router.delete("/settings/{key}")
def delete_setting(
    key: str,
    scope: str = "global",
    scope_id: str | None = None,
    validated: SessionValidationResult = Depends(current_admin),
    session: Session = Depends(get_session),
) -> dict[str, Any]:
    deleted = SettingsService(session).delete(
        key,
        updated_by=_actor(validated),
        scope=scope,
        scope_id=scope_id,
        reason="reset from web settings",
    )
    if not deleted:
        raise HTTPException(status_code=404, detail="Setting not found")
    default = DEFAULT_SETTINGS.get(key)
    if default is None:
        return {"deleted": True, "setting": None}
    return {"deleted": True, "setting": _default_setting_payload(key, default)}


@router.get("/admin/task-types")
def list_task_types(
    _validated: SessionValidationResult = Depends(current_admin),
) -> dict[str, Any]:
    return {"items": list_task_definitions()}


def _actor(validated: SessionValidationResult) -> str:
    return validated.user.local_username or validated.user.telegram_user_id or validated.user.id


def _user_payload(user: WebUserRecord) -> dict[str, Any]:
    return {
        "id": user.id,
        "telegram_user_id": user.telegram_user_id,
        "telegram_username": user.telegram_username,
        "display_name": user.display_name,
        "auth_type": user.auth_type,
        "local_username": user.local_username,
        "must_change_password": user.must_change_password,
        "role": user.role,
        "status": user.status,
        "created_at": user.created_at,
        "updated_at": user.updated_at,
        "last_login_at": user.last_login_at,
    }


def _setting_payload(record: SettingRecord, *, is_default: bool) -> dict[str, Any]:
    help_payload = _setting_help(record.key)
    return {
        "key": record.key,
        "value": record.value_json,
        "value_type": record.value_type,
        "scope": record.scope,
        "scope_id": record.scope_id,
        "description": record.description,
        "requires_restart": record.requires_restart,
        "is_secret_ref": record.is_secret_ref,
        "updated_by": record.updated_by,
        "updated_at": record.updated_at,
        "is_default": is_default,
        **help_payload,
    }


def _default_setting_payload(key: str, default) -> dict[str, Any]:
    return {
        "key": key,
        "value": default.value,
        "value_type": default.value_type,
        "scope": "global",
        "scope_id": "",
        "description": None,
        "requires_restart": False,
        "is_secret_ref": default.value_type == "secret_ref",
        "updated_by": None,
        "updated_at": None,
        "is_default": True,
        **_setting_help(key),
    }


def _setting_help(key: str) -> dict[str, str]:
    explicit: dict[str, tuple[str, str, str]] = {
        "worker_concurrency": (
            "Воркеры",
            "Сколько рабочих циклов одновременно берет задачи из очереди.",
            "Если ниже доступной емкости ресурсов, система будет недогружать Telegram, LLM и парсеры.",
        ),
        "worker_capacity_global_cap": (
            "Воркеры",
            "Верхний предел рекомендованной параллельности для всего рантайма.",
            "Защищает сервер от слишком большого количества одновременных задач.",
        ),
        "worker_realtime_reserved_slots": (
            "Воркеры",
            "Сколько рабочих слотов резервируется под живые лиды и уведомления.",
            "Не дает bulk-ингесту каталога вытеснить срочные действия оператора.",
        ),
        "worker_retry_base_delay_seconds": (
            "Воркеры",
            "Базовая задержка перед повтором задачи, если внешний сервис не дал свою задержку.",
            "Чем выше значение, тем мягче система реагирует на временные ошибки и блокировки.",
        ),
        "worker_retry_backoff_multiplier": (
            "Воркеры",
            "Множитель экспоненциального роста задержки между повторными попытками.",
            "2.0 означает, что вторая попытка ждет вдвое дольше первой, третья — вчетверо.",
        ),
        "worker_retry_max_delay_seconds": (
            "Воркеры",
            "Максимальная задержка перед повтором задачи.",
            "Ограничивает рост backoff, чтобы временная ошибка не откладывала задачу слишком далеко.",
        ),
        "worker_retry_jitter_mode": (
            "Воркеры",
            "Режим случайного разброса задержки повтора: full, equal или none.",
            "Снижает риск одновременного повторного удара по Telegram или LLM после массовой ошибки.",
        ),
        "catalog_llm_rate_limit_fallback_enabled": (
            "Каталог",
            "Разрешает переключаться на резервный AI-исполнитель каталога при rate limit основной модели.",
            "Если включено, система пробует fallback-модель до откладывания задачи в очередь.",
        ),
        "catalog_quality_idle_validation_enabled": (
            "Каталог",
            "Включает фоновую проверку кандидатов каталога сильной моделью, когда нет другой работы.",
            "Помогает улучшать каталог в простое, не мешая новым лидам, ingest и уведомлениям.",
        ),
        "catalog_quality_idle_batch_size": (
            "Каталог",
            "Сколько кандидатов каталога ставить в очередь за один idle-проход.",
            "Большее значение быстрее загружает сильные модели, но создает больше низкоприоритетных задач.",
        ),
        "catalog_quality_idle_max_active_jobs": (
            "Каталог",
            "Максимум одновременно активных задач фоновой проверки каталога.",
            "0 означает auto по AI-маршруту и лимиту модели; положительное число вручную ограничивает idle-проход.",
        ),
        "catalog_quality_validator_model": (
            "Каталог",
            "Модель по умолчанию для фоновой проверки кандидатов каталога.",
            "Используется idle-планировщиком для дедупликации review jobs и выбора непроверенных кандидатов.",
        ),
        "catalog_quality_validator_profile": (
            "Каталог",
            "Профиль модели по умолчанию для фоновой проверки кандидатов каталога.",
            "Позволяет отдельно учитывать параметры strong-review, например thinking и structured output.",
        ),
        "catalog_quality_validation_statuses": (
            "Каталог",
            "JSON-список статусов кандидатов, которые можно отправлять на фоновую AI-проверку.",
            "По умолчанию проверяются auto_pending, чтобы сильная модель валидировала черновой каталог.",
        ),
        "catalog_quality_weak_source_models": (
            "Каталог",
            "JSON-список моделей, результаты которых считаются первыми кандидатами на перепроверку.",
            "Кандидаты от этих моделей получают приоритет в idle quality pass.",
        ),
        "catalog_quality_auto_apply_enabled": (
            "Каталог",
            "Разрешает будущую автоприменяемую обработку сильных AI-review.",
            "Сейчас reviews только сохраняются; автоприменение оставлено выключенным и требует отдельной логики.",
        ),
        "catalog_quality_auto_apply_min_confidence": (
            "Каталог",
            "Минимальная уверенность для будущего автоприменения strong-model review.",
            "Пока используется как зарезервированная настройка, чтобы не забыть порог при включении автоприменения.",
        ),
        "ai_model_concurrency_utilization_ratio": (
            "AI",
            "Коэффициент использования опубликованных лимитов моделей.",
            "0.8 означает использовать примерно 80% лимита и оставлять запас под всплески и ошибки.",
        ),
        "llm_connect_timeout_seconds": (
            "AI",
            "Сколько секунд ждать установления соединения с LLM-провайдером.",
            "Короткое значение быстро отсеивает сетевые зависания до отправки тяжелого запроса.",
        ),
        "llm_request_timeout_seconds_by_model": (
            "AI",
            "JSON-карта таймаутов ответа по моделям LLM.",
            "Позволяет дать GLM-4-Plus больше времени, а Flash-моделям — короткий предел.",
        ),
        "llm_request_timeout_seconds_by_task": (
            "AI",
            "JSON-карта таймаутов ответа по типам задач.",
            "Задает разные ожидания для каталога, лидов, OCR и других фоновых операций.",
        ),
        "llm_request_timeout_hard_cap_seconds": (
            "AI",
            "Абсолютный верхний предел таймаута одного LLM-запроса.",
            "Защищает worker от слишком долгого удержания соединений и слотов модели.",
        ),
        "llm_circuit_breaker_enabled": (
            "AI",
            "Заготовка circuit breaker для временного отключения деградировавшей связки provider/account/model/task.",
            "Когда будет включено, несколько подряд retryable ошибок будут временно уводить трафик на fallback, а не добивать провайдера.",
        ),
        "llm_circuit_breaker_failure_threshold": (
            "AI",
            "Сколько подряд retryable ошибок открывает circuit breaker.",
            "Низкое значение быстрее защищает систему, высокое реже переключает маршруты из-за случайных сбоев.",
        ),
        "llm_circuit_breaker_recovery_timeout_seconds": (
            "AI",
            "Сколько секунд ждать перед пробной half-open попыткой после открытия circuit breaker.",
            "Определяет, как быстро модель снова попадет в работу после серии ошибок.",
        ),
        "llm_circuit_breaker_half_open_probe_count": (
            "AI",
            "Сколько пробных запросов разрешать в half-open состоянии.",
            "Ограничивает риск повторного каскадного сбоя при восстановлении модели.",
        ),
        "llm_circuit_breaker_scope": (
            "AI",
            "Ключ агрегации circuit breaker: обычно provider_account_model_task.",
            "Позволяет блокировать конкретную модель для конкретной задачи, не отключая весь провайдер.",
        ),
        "llm_circuit_breaker_retryable_errors_only": (
            "AI",
            "Учитывать в circuit breaker только retryable ошибки LLM.",
            "Не дает ошибкам конфигурации и валидации случайно открыть breaker как перегрузку провайдера.",
        ),
        "llm_adaptive_timeout_enabled": (
            "AI",
            "Заготовка адаптивного таймаута по p95 latency.",
            "Когда будет включено, timeout можно будет считать из накопленных метрик или задавать вручную.",
        ),
        "llm_adaptive_timeout_activation_mode": (
            "AI",
            "Когда применять адаптивный timeout: metrics_only, manual_only или metrics_or_manual.",
            "Позволяет включать расчет только после накопления метрик либо принудительно через ручные override.",
        ),
        "llm_adaptive_timeout_min_samples": (
            "AI",
            "Минимум успешных/завершенных измерений latency для расчета p95.",
            "До накопления этого количества система использует статический timeout или ручной override.",
        ),
        "llm_adaptive_timeout_manual_overrides": (
            "AI",
            "JSON-карта ручных timeout override по task/model/profile.",
            "Нужна, чтобы оператор мог включить конкретные значения до накопления достаточной статистики.",
        ),
        "llm_adaptive_timeout_window_hours": (
            "AI",
            "Окно истории latency для расчета p95.",
            "Короткое окно быстрее реагирует на деградацию, длинное стабильнее при редких задачах.",
        ),
        "llm_adaptive_timeout_percentile": (
            "AI",
            "Перцентиль latency для расчета адаптивного timeout.",
            "p95 балансирует между нормальной задержкой и редкими длинными ответами.",
        ),
        "llm_adaptive_timeout_buffer_ratio": (
            "AI",
            "Множитель запаса поверх p95 latency.",
            "1.2 означает p95 плюс 20% буфера, но не выше hard cap.",
        ),
        "llm_adaptive_timeout_min_seconds_by_task": (
            "AI",
            "JSON-карта нижних границ адаптивного timeout по типам задач.",
            "Не дает расчету p95 сделать timeout слишком коротким для тяжелых фоновых задач.",
        ),
        "llm_adaptive_timeout_max_seconds_by_task": (
            "AI",
            "JSON-карта верхних границ адаптивного timeout по типам задач.",
            "Ограничивает рост timeout при хронической деградации модели.",
        ),
        "telegram_read_jobs_per_userbot": (
            "Telegram",
            "Сколько задач чтения истории можно вести одним юзерботом.",
            "Увеличение ускоряет backfill, но повышает риск flood-wait.",
        ),
        "telegram_userbot_circuit_breaker_enabled": (
            "Telegram",
            "Заготовка circuit breaker для юзерботов Telegram.",
            "Когда будет включено, серия flood-wait, auth, banned или сетевых ошибок временно остановит конкретный юзербот/операцию и переключит работу на другие аккаунты.",
        ),
        "telegram_userbot_circuit_breaker_failure_threshold": (
            "Telegram",
            "Сколько подряд ошибок чтения открывает breaker юзербота.",
            "Низкое значение быстрее защищает аккаунт от блокировок, высокое меньше реагирует на единичные сбои.",
        ),
        "telegram_userbot_circuit_breaker_recovery_timeout_seconds": (
            "Telegram",
            "Сколько секунд ждать перед пробной операцией после открытия breaker юзербота.",
            "Задает паузу восстановления после flood-wait, временных блокировок или сетевой деградации.",
        ),
        "telegram_userbot_circuit_breaker_scope": (
            "Telegram",
            "Ключ агрегации breaker для юзербота: обычно userbot_account_operation.",
            "Позволяет остановить чтение одним аккаунтом, не отключая все Telegram-операции системы.",
        ),
        "telegram_userbot_adaptive_limit_enabled": (
            "Telegram",
            "Заготовка адаптивных лимитов чтения для юзерботов.",
            "Когда будет включено, система сможет снижать или повышать параллельность/паузы по истории успешности и flood-wait.",
        ),
        "telegram_userbot_adaptive_limit_activation_mode": (
            "Telegram",
            "Когда применять адаптивные лимиты юзербота: metrics_only, manual_only или metrics_or_manual.",
            "До накопления метрик можно использовать ручные override для конкретного аккаунта или операции.",
        ),
        "telegram_userbot_adaptive_limit_min_samples": (
            "Telegram",
            "Минимум измерений операций юзербота для автоматического расчета лимитов.",
            "До накопления этого количества используются статические настройки или ручной override.",
        ),
        "telegram_userbot_adaptive_limit_manual_overrides": (
            "Telegram",
            "JSON-карта ручных лимитов юзерботов по account/operation.",
            "Позволяет оператору задать безопасные паузы или параллельность до накопления статистики.",
        ),
        "telegram_userbot_adaptive_limit_window_hours": (
            "Telegram",
            "Окно истории для расчета адаптивных лимитов юзербота.",
            "Определяет, за какой период учитывать flood-wait, ошибки и успешные чтения.",
        ),
        "telegram_userbot_adaptive_limit_target_success_ratio": (
            "Telegram",
            "Целевая доля успешных операций юзербота.",
            "Если фактическая успешность ниже цели, будущая логика сможет снижать нагрузку.",
        ),
        "telegram_bot_circuit_breaker_enabled": (
            "Telegram",
            "Заготовка circuit breaker для обычных Telegram-ботов.",
            "Когда будет включено, серия rate-limit, forbidden или сетевых ошибок временно остановит отправку через конкретного бота/чат.",
        ),
        "telegram_bot_circuit_breaker_failure_threshold": (
            "Telegram",
            "Сколько подряд ошибок отправки открывает breaker Telegram-бота.",
            "Защищает уведомления от каскадных повторов при rate-limit или проблемах прав в группе.",
        ),
        "telegram_bot_circuit_breaker_recovery_timeout_seconds": (
            "Telegram",
            "Сколько секунд ждать перед пробной отправкой после открытия breaker бота.",
            "Помогает не добивать Bot API повторными уведомлениями во время rate-limit.",
        ),
        "telegram_bot_circuit_breaker_scope": (
            "Telegram",
            "Ключ агрегации breaker для бота: обычно bot_token_chat_operation.",
            "Позволяет остановить проблемную группу уведомлений, не отключая все остальные маршруты.",
        ),
        "telegram_bot_adaptive_limit_enabled": (
            "Telegram",
            "Заготовка адаптивных лимитов отправки Telegram-ботов.",
            "Когда будет включено, система сможет менять интервалы и параллельность отправки по метрикам или ручным override.",
        ),
        "telegram_bot_adaptive_limit_activation_mode": (
            "Telegram",
            "Когда применять адаптивные лимиты бота: metrics_only, manual_only или metrics_or_manual.",
            "До накопления метрик можно задать ручные лимиты для конкретного бота или группы.",
        ),
        "telegram_bot_adaptive_limit_min_samples": (
            "Telegram",
            "Минимум измерений отправки для автоматического расчета лимитов бота.",
            "До накопления этого количества используются статические настройки или ручной override.",
        ),
        "telegram_bot_adaptive_limit_manual_overrides": (
            "Telegram",
            "JSON-карта ручных лимитов отправки по bot/chat/operation.",
            "Позволяет оператору ограничить проблемный маршрут уведомлений до накопления статистики.",
        ),
        "telegram_bot_adaptive_limit_window_hours": (
            "Telegram",
            "Окно истории для расчета адаптивных лимитов Telegram-бота.",
            "Определяет, за какой период учитывать rate-limit, forbidden и успешные отправки.",
        ),
        "telegram_bot_adaptive_limit_target_success_ratio": (
            "Telegram",
            "Целевая доля успешных отправок Telegram-бота.",
            "Если фактическая успешность ниже цели, будущая логика сможет снижать нагрузку.",
        ),
    }
    if key in explicit:
        group, description, impact = explicit[key]
        return {"group": group, "description": description, "impact": impact}
    if key.startswith("telegram_"):
        return {
            "group": "Telegram",
            "description": "Настройка Telegram-ботов, юзерботов, уведомлений или чтения источников.",
            "impact": "Влияет на доставку уведомлений, доступ к чатам, скорость чтения и риск Telegram-лимитов.",
        }
    if key.startswith(("catalog_", "manual_catalog_")):
        return {
            "group": "Каталог",
            "description": "Настройка наполнения, извлечения или ручной разметки каталога.",
            "impact": "Меняет скорость и строгость появления новых сущностей, терминов и условий в источнике истины.",
        }
    if key.startswith(("lead_", "notify_", "high_value_")):
        return {
            "group": "Лиды",
            "description": "Настройка классификации лидов, уверенности и правил уведомления.",
            "impact": "Меняет чувствительность системы и то, какие события сразу уходят оператору в Telegram.",
        }
    if key.startswith(("ai_", "zai_")):
        return {
            "group": "AI",
            "description": "Настройка AI-провайдеров, лимитов, ключей и контроля параллельности.",
            "impact": "Влияет на доступность LLM/OCR-задач, скорость анализа и защитный запас по лимитам.",
        }
    if key.startswith(("external_page_", "local_parser_")):
        return {
            "group": "Парсинг",
            "description": "Настройка загрузки внешних страниц и локального разбора документов.",
            "impact": "Меняет скорость обработки ссылок и документов из каналов каталога.",
        }
    if key.startswith(("backup_", "restore_")):
        return {
            "group": "Бэкапы",
            "description": "Настройка архивации, проверки и срока хранения резервных копий.",
            "impact": "Влияет на восстановимость системы и занимаемое место на диске.",
        }
    return {
        "group": "Система",
        "description": "Системная настройка, используемая рабочими процессами PUR Leads.",
        "impact": "Изменение влияет на связанные фоновые задачи; проверьте операции после сохранения.",
    }


def _userbot_payload(
    service: UserbotAccountService,
    account: UserbotAccountRecord,
) -> dict[str, Any]:
    return service.public_payload(account)
