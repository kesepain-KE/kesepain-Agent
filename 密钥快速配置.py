from __future__ import annotations

import argparse
import getpass
import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent
USERS_DIR = ROOT_DIR / "users"
TEMP_CACHE_PATH = ROOT_DIR / "core" / "temp" / "cache.json"
TEMP_CACHE_TEMPLATE_PATH = ROOT_DIR / "system" / "start" / "cache.json"
PROVIDER_API_PATH = ROOT_DIR / "provider" / "api.json"
EMPTY_SENTINEL = "/empty"

MAIN_KEY_ENV_MAP = {
    "deepseek": ["DEEPSEEK_API_KEY"],
    "openai": ["OPENAI_API_KEY"],
}

OPTIONAL_KEY_ENV_MAP = {
    "web_search_key": ["TAVILY_API_KEY", "WEB_SEARCH_API_KEY"],
    "weather_public_key": ["WEATHER_PUBLIC_KEY", "QWEATHER_PUBLIC_KEY", "HEFENG_PUBLIC_KEY"],
    "weather_private_key": ["WEATHER_PRIVATE_KEY", "QWEATHER_PRIVATE_KEY", "HEFENG_PRIVATE_KEY"],
}


@dataclass(frozen=True)
class TargetSpec:
    label: str
    arg_name: str
    json_path: tuple[str, ...]
    candidates: tuple[Path, ...]


@dataclass
class PlannedChanges:
    clear: bool = False
    dry_run: bool = False
    quick_mode: bool = False
    user_api_key: str | None = None
    history_zip_key: str | None = None
    weather_public_key: str | None = None
    weather_private_key: str | None = None
    web_search_key: str | None = None
    main_provider: str | None = None
    main_model: str | None = None
    sync_history: bool | None = None
    history_provider: str | None = None
    history_model: str | None = None
    notes: list[str] = field(default_factory=list)


def set_stream_utf8(stream: Any) -> None:
    reconfigure = getattr(stream, "reconfigure", None)
    if callable(reconfigure):
        try:
            reconfigure(encoding="utf-8")
        except Exception:
            pass


set_stream_utf8(sys.stdout)
set_stream_utf8(sys.stderr)
set_stream_utf8(sys.stdin)


def load_json(path: Path) -> dict:
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except json.JSONDecodeError as error:
            raise SystemExit(f"JSON 格式错误: {path} -> {error}") from error
        except OSError as error:
            raise SystemExit(f"读取失败: {path} -> {error}") from error
        if isinstance(data, dict) is False:
            raise SystemExit(f"配置文件根节点必须是对象: {path}")
        return data

    if path == TEMP_CACHE_PATH and TEMP_CACHE_TEMPLATE_PATH.exists():
        return load_json(TEMP_CACHE_TEMPLATE_PATH)
    return {}


def save_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("w", encoding="utf-8") as file:
            json.dump(data, file, ensure_ascii=False, indent=4)
            file.write("\n")
    except OSError as error:
        raise SystemExit(f"写入失败: {path} -> {error}") from error


def get_nested_value(data: dict, keys: tuple[str, ...] | list[str]) -> str:
    current: Any = data
    for key in keys:
        if isinstance(current, dict) is False or key not in current:
            return ""
        current = current[key]
    if isinstance(current, str):
        return current
    if current is None:
        return ""
    return str(current)


def set_nested_value(data: dict, keys: tuple[str, ...] | list[str], value: str) -> None:
    current = data
    for key in keys[:-1]:
        child = current.get(key)
        if isinstance(child, dict) is False:
            child = {}
            current[key] = child
        current = child
    current[keys[-1]] = value


def mask_secret(value: str) -> str:
    text = value.strip()
    if text == "":
        return "(empty)"
    if len(text) <= 8:
        return "*" * len(text)
    return f"{text[:4]}...{text[-4:]}"


def format_value_for_display(json_path: str, value: str) -> str:
    secret_suffixes = ("key", "API_KEY", "public_key", "private_key")
    if any(json_path.endswith(suffix) for suffix in secret_suffixes):
        return mask_secret(value)
    return value if value != "" else "(empty)"


def to_relative_text(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT_DIR))
    except ValueError:
        return str(path)


def resolve_target_paths(candidates: tuple[Path, ...] | list[Path]) -> list[Path]:
    candidate_list = list(candidates)
    existing_files = [path for path in candidate_list if path.exists()]
    if existing_files:
        return existing_files
    existing_parents = [path for path in candidate_list if path.parent.exists()]
    if existing_parents:
        return [existing_parents[0]]
    return [candidate_list[0]]


def normalize_secret_arg(value: str | None) -> str | None:
    if value is None:
        return None
    if value == EMPTY_SENTINEL:
        return ""
    return value


def load_provider_catalog() -> dict[str, dict[str, Any]]:
    provider_data = load_json(PROVIDER_API_PATH)
    if provider_data:
        return provider_data
    raise SystemExit(f"缺少 provider 配置: {PROVIDER_API_PATH}")


def get_provider_names(provider_catalog: dict[str, dict[str, Any]]) -> list[str]:
    return sorted(provider_catalog.keys())


def get_default_provider(provider_catalog: dict[str, dict[str, Any]]) -> str:
    provider_names = get_provider_names(provider_catalog)
    if "deepseek" in provider_catalog:
        return "deepseek"
    if provider_names:
        return provider_names[0]
    raise SystemExit("provider/api.json 中没有可用 provider")


def ensure_provider_exists(provider_catalog: dict[str, dict[str, Any]], provider_name: str) -> None:
    if provider_name not in provider_catalog:
        available = ", ".join(get_provider_names(provider_catalog))
        raise SystemExit(f"未知 provider: {provider_name}。可选值: {available}")


def pick_model(
    provider_catalog: dict[str, dict[str, Any]],
    provider_name: str,
    requested_model: str | None,
    current_model: str | None = None,
) -> str:
    ensure_provider_exists(provider_catalog, provider_name)
    models = provider_catalog[provider_name].get("available_models", [])
    if isinstance(models, list) is False or len(models) == 0:
        raise SystemExit(f"provider {provider_name} 没有配置可用模型")
    if requested_model is not None:
        if requested_model not in models:
            raise SystemExit(
                f"provider {provider_name} 不支持模型 {requested_model}。"
                f" 可选值: {', '.join(models)}"
            )
        return requested_model
    if current_model in models:
        return str(current_model)
    return str(models[0])


def get_user_names() -> list[str]:
    if USERS_DIR.exists() is False:
        raise SystemExit(f"users 目录不存在: {USERS_DIR}")
    return sorted(item.name for item in USERS_DIR.iterdir() if item.is_dir())


def select_user_name(requested_name: str | None) -> str:
    user_names = get_user_names()
    if requested_name:
        if requested_name not in user_names:
            raise SystemExit(
                f"用户不存在: {requested_name}。"
                f" 可选用户: {', '.join(user_names) or '(none)'}"
            )
        return requested_name
    if "kesepain" in user_names:
        return "kesepain"
    if len(user_names) == 1:
        return user_names[0]
    raise SystemExit(f"请通过 --user 指定用户。可选用户: {', '.join(user_names) or '(none)'}")


def get_user_config_path(user_name: str) -> Path:
    return USERS_DIR / user_name / "config.json"


def build_targets(user_name: str) -> list[TargetSpec]:
    weather_candidates = (
        ROOT_DIR / "system" / "skills" / "weather" / "run" / "config.json",
        ROOT_DIR / "system" / "skills" / "weather" / "skill_run" / "config.json",
    )
    web_search_candidates = (
        ROOT_DIR / "system" / "skills" / "web_search" / "run" / "config.json",
        ROOT_DIR / "system" / "skills" / "web_search" / "skill_run" / "config.json",
    )
    return [
        TargetSpec(
            label="用户主模型 API key",
            arg_name="user_api_key",
            json_path=("API", "key"),
            candidates=(get_user_config_path(user_name),),
        ),
        TargetSpec(
            label="历史压缩 API key",
            arg_name="history_zip_key",
            json_path=("history_zip", "API_KEY"),
            candidates=(ROOT_DIR / "core" / "config.json",),
        ),
        TargetSpec(
            label="天气技能 public_key",
            arg_name="weather_public_key",
            json_path=("public_key",),
            candidates=weather_candidates,
        ),
        TargetSpec(
            label="天气技能 private_key",
            arg_name="weather_private_key",
            json_path=("private_key",),
            candidates=weather_candidates,
        ),
        TargetSpec(
            label="网络搜索 key",
            arg_name="web_search_key",
            json_path=("key",),
            candidates=web_search_candidates,
        ),
    ]


def get_target_map(user_name: str) -> dict[str, TargetSpec]:
    return {target.arg_name: target for target in build_targets(user_name)}


def get_current_main_profile(user_name: str) -> tuple[str, str, str]:
    data = load_json(get_user_config_path(user_name))
    return (
        get_nested_value(data, ("API", "provider")),
        get_nested_value(data, ("API", "model")),
        get_nested_value(data, ("API", "key")),
    )


def get_current_history_profile() -> tuple[str, str, str, str]:
    data = load_json(ROOT_DIR / "core" / "config.json")
    return (
        get_nested_value(data, ("history_zip", "API")),
        get_nested_value(data, ("history_zip", "model")),
        get_nested_value(data, ("history_zip", "base_url")),
        get_nested_value(data, ("history_zip", "API_KEY")),
    )


def get_current_cache_profile() -> tuple[str, str, str]:
    data = load_json(TEMP_CACHE_PATH)
    return (
        get_nested_value(data, ("API", "provider")),
        get_nested_value(data, ("API", "model")),
        get_nested_value(data, ("API", "key")),
    )


def get_current_target_value(target: TargetSpec) -> tuple[str, str]:
    target_paths = resolve_target_paths(target.candidates)
    primary_path = target_paths[0]
    value = get_nested_value(load_json(primary_path), target.json_path)
    return value, " | ".join(to_relative_text(path) for path in target_paths)


def print_current_summary(user_name: str, provider_catalog: dict[str, dict[str, Any]]) -> None:
    main_provider, main_model, main_key = get_current_main_profile(user_name)
    history_provider, history_model, history_base_url, history_key = get_current_history_profile()
    cache_provider, cache_model, cache_key = get_current_cache_profile()
    target_map = get_target_map(user_name)
    web_search_value, web_search_path = get_current_target_value(target_map["web_search_key"])
    weather_public_value, weather_public_path = get_current_target_value(target_map["weather_public_key"])
    weather_private_value, weather_private_path = get_current_target_value(target_map["weather_private_key"])

    provider_names = ", ".join(get_provider_names(provider_catalog))
    print("\n当前配置概览")
    print(f"- 用户: {user_name}")
    print(f"- 支持的 provider: {provider_names}")
    print(
        f"- 用户主模型: provider={main_provider or '(empty)'}"
        f", model={main_model or '(empty)'}"
        f", key={mask_secret(main_key)}"
    )
    print(
        f"- 当前缓存: provider={cache_provider or '(empty)'}"
        f", model={cache_model or '(empty)'}"
        f", key={mask_secret(cache_key)}"
    )
    print(
        f"- 历史压缩: provider={history_provider or '(empty)'}"
        f", model={history_model or '(empty)'}"
        f", base_url={history_base_url or '(empty)'}"
        f", key={mask_secret(history_key)}"
    )
    print(f"- 网络搜索: {mask_secret(web_search_value)} ({web_search_path})")
    print(f"- 天气 public_key: {mask_secret(weather_public_value)} ({weather_public_path})")
    print(f"- 天气 private_key: {mask_secret(weather_private_value)} ({weather_private_path})")


def prompt_input(label: str, default: str | None = None) -> str:
    prompt = f"{label}"
    if default not in (None, ""):
        prompt += f" [{default}]"
    prompt += ": "
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        raise SystemExit("\n已取消") from None


def prompt_secret(label: str, current_value: str, path_text: str, required: bool = False) -> str | None:
    print(f"\n{label}")
    print(f"位置: {path_text}")
    print(f"当前值: {mask_secret(current_value)}")
    if required:
        print(f"请输入新值。输入 {EMPTY_SENTINEL} 清空。")
    else:
        print(f"输入新值，直接回车保持当前值，输入 {EMPTY_SENTINEL} 清空。")
    try:
        value = getpass.getpass("新值: ").strip()
    except (EOFError, KeyboardInterrupt):
        raise SystemExit("\n已取消") from None
    if value == "":
        if required:
            print("该项不能为空，请重新输入。")
            return prompt_secret(label, current_value, path_text, required=True)
        return None
    if value == EMPTY_SENTINEL:
        return ""
    return value


def prompt_yes_no(label: str, default: bool = True) -> bool:
    suffix = " [Y/n]: " if default else " [y/N]: "
    try:
        value = input(label + suffix).strip().lower()
    except (EOFError, KeyboardInterrupt):
        raise SystemExit("\n已取消") from None
    if value == "":
        return default
    if value in ("y", "yes", "1"):
        return True
    if value in ("n", "no", "0"):
        return False
    print("请输入 y 或 n。")
    return prompt_yes_no(label, default=default)


def prompt_provider_choice(
    provider_catalog: dict[str, dict[str, Any]],
    default_provider: str,
) -> str:
    providers = get_provider_names(provider_catalog)
    print("\n可选 provider:")
    for index, provider_name in enumerate(providers, start=1):
        marker = " (默认)" if provider_name == default_provider else ""
        print(f"{index}. {provider_name}{marker}")
    value = prompt_input("选择 provider（编号或名称）", default_provider)
    if value == "":
        return default_provider
    if value.isdigit():
        selected_index = int(value) - 1
        if 0 <= selected_index < len(providers):
            return providers[selected_index]
    if value in provider_catalog:
        return value
    print("输入无效，请重新选择。")
    return prompt_provider_choice(provider_catalog, default_provider)


def prompt_model_choice(
    provider_catalog: dict[str, dict[str, Any]],
    provider_name: str,
    default_model: str,
) -> str:
    models = provider_catalog[provider_name]["available_models"]
    print(f"\n{provider_name} 可选模型:")
    for index, model_name in enumerate(models, start=1):
        marker = " (默认)" if model_name == default_model else ""
        print(f"{index}. {model_name}{marker}")
    value = prompt_input("选择 model（编号或名称）", default_model)
    if value == "":
        return default_model
    if value.isdigit():
        selected_index = int(value) - 1
        if 0 <= selected_index < len(models):
            return str(models[selected_index])
    if value in models:
        return value
    print("输入无效，请重新选择。")
    return prompt_model_choice(provider_catalog, provider_name, default_model)


def get_first_env_value(names: list[str]) -> tuple[str, str] | None:
    for name in names:
        value = os.getenv(name, "").strip()
        if value != "":
            return value, name
    return None


def choose_env_provider(
    provider_catalog: dict[str, dict[str, Any]],
    preferred_provider: str | None,
    fallback_provider: str,
) -> tuple[str, str, str] | None:
    candidates: dict[str, tuple[str, str]] = {}
    for provider_name, env_names in MAIN_KEY_ENV_MAP.items():
        if provider_name not in provider_catalog:
            continue
        value_and_name = get_first_env_value(env_names)
        if value_and_name is not None:
            candidates[provider_name] = value_and_name

    if not candidates:
        return None

    if preferred_provider and preferred_provider in candidates:
        value, env_name = candidates[preferred_provider]
        return preferred_provider, value, env_name

    if fallback_provider in candidates:
        value, env_name = candidates[fallback_provider]
        return fallback_provider, value, env_name

    provider_name = sorted(candidates.keys())[0]
    value, env_name = candidates[provider_name]
    return provider_name, value, env_name


def apply_env_defaults(
    plan: PlannedChanges,
    provider_catalog: dict[str, dict[str, Any]],
    current_provider: str,
) -> None:
    chosen_main = choose_env_provider(provider_catalog, plan.main_provider, current_provider)
    if chosen_main is not None:
        provider_name, key_value, env_name = chosen_main
        plan.main_provider = provider_name
        if plan.quick_mode and plan.sync_history is None:
            plan.sync_history = True
        if plan.user_api_key is None:
            plan.user_api_key = key_value
            plan.notes.append(f"用户主模型 API key 来自环境变量 {env_name}")
        if plan.main_model is None:
            plan.main_model = pick_model(provider_catalog, provider_name, None, None)
        if plan.quick_mode and plan.sync_history is not False and plan.history_zip_key is None:
            plan.history_zip_key = key_value
            plan.notes.append(f"历史压缩 API key 来自环境变量 {env_name}")

    for field_name, env_names in OPTIONAL_KEY_ENV_MAP.items():
        if getattr(plan, field_name) is not None:
            continue
        value_and_name = get_first_env_value(env_names)
        if value_and_name is None:
            continue
        key_value, env_name = value_and_name
        setattr(plan, field_name, key_value)
        plan.notes.append(f"{field_name} 来自环境变量 {env_name}")


def set_value_for_path(
    file_cache: dict[Path, dict],
    updates: list[tuple[Path, str, str]],
    path: Path,
    json_path: tuple[str, ...],
    new_value: str,
) -> None:
    data = file_cache.setdefault(path, load_json(path))
    current_value = get_nested_value(data, json_path)
    if current_value == new_value:
        return
    set_nested_value(data, json_path, new_value)
    updates.append((path, ".".join(json_path), new_value))


def set_value_for_paths(
    file_cache: dict[Path, dict],
    updates: list[tuple[Path, str, str]],
    paths: list[Path],
    json_path: tuple[str, ...],
    new_value: str,
) -> None:
    for path in paths:
        set_value_for_path(file_cache, updates, path, json_path, new_value)


def apply_plan(
    user_name: str,
    plan: PlannedChanges,
    provider_catalog: dict[str, dict[str, Any]],
) -> bool:
    target_map = get_target_map(user_name)
    file_cache: dict[Path, dict] = {}
    updates: list[tuple[Path, str, str]] = []

    user_config_path = get_user_config_path(user_name)
    cache_path = TEMP_CACHE_PATH
    main_provider_now, main_model_now, _ = get_current_main_profile(user_name)
    history_provider_now, history_model_now, _, _ = get_current_history_profile()

    fallback_provider = main_provider_now or get_default_provider(provider_catalog)
    desired_main_provider = plan.main_provider or fallback_provider
    desired_main_model = pick_model(
        provider_catalog,
        desired_main_provider,
        plan.main_model,
        main_model_now if main_provider_now == desired_main_provider else None,
    )

    history_fallback_provider = history_provider_now or desired_main_provider
    if plan.sync_history is True and plan.history_provider is None:
        desired_history_provider = desired_main_provider
    else:
        desired_history_provider = plan.history_provider or history_fallback_provider

    desired_history_model = pick_model(
        provider_catalog,
        desired_history_provider,
        plan.history_model,
        history_model_now if history_provider_now == desired_history_provider else None,
    )

    main_profile_should_change = (
        plan.main_provider is not None
        or plan.main_model is not None
        or (plan.quick_mode and plan.user_api_key is not None)
    )
    if main_profile_should_change:
        set_value_for_path(file_cache, updates, user_config_path, ("API", "provider"), desired_main_provider)
        set_value_for_path(file_cache, updates, user_config_path, ("API", "model"), desired_main_model)
        set_value_for_path(file_cache, updates, cache_path, ("API", "provider"), desired_main_provider)
        set_value_for_path(file_cache, updates, cache_path, ("API", "model"), desired_main_model)

    if plan.clear:
        set_value_for_path(file_cache, updates, user_config_path, ("API", "key"), "")
        set_value_for_path(file_cache, updates, cache_path, ("API", "key"), "")
        for target in target_map.values():
            set_value_for_paths(
                file_cache,
                updates,
                resolve_target_paths(target.candidates),
                target.json_path,
                "",
            )
    else:
        if plan.user_api_key is not None:
            set_value_for_path(file_cache, updates, user_config_path, ("API", "key"), plan.user_api_key)
            set_value_for_path(file_cache, updates, cache_path, ("API", "key"), plan.user_api_key)

        if plan.history_zip_key is not None:
            set_value_for_path(
                file_cache,
                updates,
                ROOT_DIR / "core" / "config.json",
                ("history_zip", "API_KEY"),
                plan.history_zip_key,
            )

        if plan.weather_public_key is not None:
            target = target_map["weather_public_key"]
            set_value_for_paths(
                file_cache,
                updates,
                resolve_target_paths(target.candidates),
                target.json_path,
                plan.weather_public_key,
            )

        if plan.weather_private_key is not None:
            target = target_map["weather_private_key"]
            set_value_for_paths(
                file_cache,
                updates,
                resolve_target_paths(target.candidates),
                target.json_path,
                plan.weather_private_key,
            )

        if plan.web_search_key is not None:
            target = target_map["web_search_key"]
            set_value_for_paths(
                file_cache,
                updates,
                resolve_target_paths(target.candidates),
                target.json_path,
                plan.web_search_key,
            )

    history_profile_should_change = (
        plan.history_provider is not None
        or plan.history_model is not None
        or (plan.sync_history is True and plan.user_api_key is not None)
    )
    if history_profile_should_change:
        history_config_path = ROOT_DIR / "core" / "config.json"
        history_base_url = str(provider_catalog[desired_history_provider]["base_url"])
        set_value_for_path(file_cache, updates, history_config_path, ("history_zip", "API"), desired_history_provider)
        set_value_for_path(file_cache, updates, history_config_path, ("history_zip", "model"), desired_history_model)
        set_value_for_path(file_cache, updates, history_config_path, ("history_zip", "base_url"), history_base_url)
        if plan.sync_history is True and plan.user_api_key is not None and plan.history_zip_key is None:
            set_value_for_path(
                file_cache,
                updates,
                history_config_path,
                ("history_zip", "API_KEY"),
                plan.user_api_key,
            )

    if updates:
        unique_updates = []
        printed = set()
        for path, json_path, value in updates:
            key = (path, json_path)
            if key in printed:
                continue
            printed.add(key)
            unique_updates.append((path, json_path, value))

        if plan.dry_run:
            print("\n预览模式：以下改动将会写入，但当前未落盘")
        else:
            saved_paths = set()
            for path, _, _ in unique_updates:
                if path not in saved_paths:
                    save_json(path, file_cache[path])
                    saved_paths.add(path)
            print("\n已写入以下配置")

        for path, json_path, value in unique_updates:
            print(f"- {to_relative_text(path)} -> {json_path} = {format_value_for_display(json_path, value)}")

        if plan.dry_run:
            print(f"\n共预览 {len(unique_updates)} 个字段变更。")
        else:
            print(f"\n共更新 {len(unique_updates)} 个字段。")
        return True

    print("\n没有检测到需要写入的改动。")
    return False


def build_plan_from_args(
    args: argparse.Namespace,
    user_name: str,
    provider_catalog: dict[str, dict[str, Any]],
) -> PlannedChanges:
    main_provider_now, _, _ = get_current_main_profile(user_name)
    plan = PlannedChanges(clear=args.clear, dry_run=args.dry_run, quick_mode=args.quick)
    plan.main_provider = args.provider
    plan.main_model = args.model
    plan.sync_history = args.sync_history
    plan.history_provider = args.history_provider
    plan.history_model = args.history_model
    plan.user_api_key = normalize_secret_arg(args.user_api_key)
    plan.history_zip_key = normalize_secret_arg(args.history_zip_key)
    plan.weather_public_key = normalize_secret_arg(args.weather_public_key)
    plan.weather_private_key = normalize_secret_arg(args.weather_private_key)
    plan.web_search_key = normalize_secret_arg(args.web_search_key)

    if plan.quick_mode and plan.sync_history is None:
        plan.sync_history = True

    if args.from_env:
        apply_env_defaults(plan, provider_catalog, main_provider_now or get_default_provider(provider_catalog))

    if plan.quick_mode and plan.main_provider is None and plan.user_api_key is not None:
        plan.main_provider = main_provider_now or get_default_provider(provider_catalog)
    if plan.quick_mode and plan.main_model is None and plan.main_provider is not None:
        _, current_model, _ = get_current_main_profile(user_name)
        plan.main_model = pick_model(
            provider_catalog,
            plan.main_provider,
            None,
            current_model if main_provider_now == plan.main_provider else None,
        )
    return plan


def prompt_optional_target_value(target: TargetSpec) -> str | None:
    current_value, path_text = get_current_target_value(target)
    return prompt_secret(target.label, current_value, path_text)


def run_interactive_full_edit(user_name: str) -> PlannedChanges:
    plan = PlannedChanges()
    target_map = get_target_map(user_name)
    for field_name in (
        "user_api_key",
        "history_zip_key",
        "web_search_key",
        "weather_public_key",
        "weather_private_key",
    ):
        value = prompt_optional_target_value(target_map[field_name])
        if value is not None:
            setattr(plan, field_name, value)
    return plan


def run_interactive_quick_setup(
    user_name: str,
    provider_catalog: dict[str, dict[str, Any]],
) -> PlannedChanges:
    current_provider, current_model, current_key = get_current_main_profile(user_name)
    default_provider = current_provider or get_default_provider(provider_catalog)
    provider_name = prompt_provider_choice(provider_catalog, default_provider)
    default_model = pick_model(
        provider_catalog,
        provider_name,
        None,
        current_model if current_provider == provider_name else None,
    )
    model_name = prompt_model_choice(provider_catalog, provider_name, default_model)

    main_path = to_relative_text(get_user_config_path(user_name))
    main_key = prompt_secret("用户主模型 API key", current_key, main_path, required=True)
    if main_key is None:
        raise SystemExit("快速配置必须提供主模型 API key")

    plan = PlannedChanges(
        quick_mode=True,
        user_api_key=main_key,
        main_provider=provider_name,
        main_model=model_name,
        sync_history=prompt_yes_no("是否同步同一套 provider / model / key 到历史压缩配置", default=True),
    )

    if prompt_yes_no("是否继续配置网络搜索和天气密钥", default=False):
        target_map = get_target_map(user_name)
        web_search_value = prompt_optional_target_value(target_map["web_search_key"])
        if web_search_value is not None:
            plan.web_search_key = web_search_value
        weather_public_value = prompt_optional_target_value(target_map["weather_public_key"])
        if weather_public_value is not None:
            plan.weather_public_key = weather_public_value
        weather_private_value = prompt_optional_target_value(target_map["weather_private_key"])
        if weather_private_value is not None:
            plan.weather_private_key = weather_private_value

    plan.dry_run = prompt_yes_no("先预览改动而不写入文件", default=False)
    return plan


def run_interactive_env_import(
    user_name: str,
    provider_catalog: dict[str, dict[str, Any]],
) -> PlannedChanges | None:
    current_provider, _, _ = get_current_main_profile(user_name)
    plan = PlannedChanges(quick_mode=True, sync_history=True)
    apply_env_defaults(plan, provider_catalog, current_provider or get_default_provider(provider_catalog))

    if (
        plan.user_api_key is None
        and plan.history_zip_key is None
        and plan.web_search_key is None
        and plan.weather_public_key is None
        and plan.weather_private_key is None
    ):
        print("\n没有找到可导入的环境变量。")
        print("已尝试的主模型环境变量: DEEPSEEK_API_KEY, OPENAI_API_KEY")
        print("已尝试的附加环境变量: TAVILY_API_KEY, WEATHER_PUBLIC_KEY, WEATHER_PRIVATE_KEY 等")
        return None

    print("\n将从环境变量导入以下配置")
    for note in plan.notes:
        print(f"- {note}")
    plan.dry_run = prompt_yes_no("先预览改动而不写入文件", default=False)
    return plan


def run_interactive_menu(
    user_name: str,
    provider_catalog: dict[str, dict[str, Any]],
) -> PlannedChanges | None:
    print_current_summary(user_name, provider_catalog)
    print("\n请选择操作")
    print("1. 快速配置主模型（推荐）")
    print("2. 从环境变量导入")
    print("3. 逐项编辑所有密钥")
    print("4. 清空脚本管理的所有密钥")
    choice = prompt_input("输入序号，直接回车退出")
    if choice == "":
        print("已退出。")
        return None
    if choice == "1":
        return run_interactive_quick_setup(user_name, provider_catalog)
    if choice == "2":
        return run_interactive_env_import(user_name, provider_catalog)
    if choice == "3":
        plan = run_interactive_full_edit(user_name)
        plan.dry_run = prompt_yes_no("先预览改动而不写入文件", default=False)
        return plan
    if choice == "4":
        return PlannedChanges(clear=True, dry_run=prompt_yes_no("先预览改动而不写入文件", default=False))
    print("输入无效。")
    return run_interactive_menu(user_name, provider_catalog)


def has_direct_change_request(args: argparse.Namespace) -> bool:
    return any(
        [
            args.clear,
            args.from_env,
            args.user_api_key is not None,
            args.history_zip_key is not None,
            args.weather_public_key is not None,
            args.weather_private_key is not None,
            args.web_search_key is not None,
            args.provider is not None,
            args.model is not None,
            args.sync_history is not None,
            args.history_provider is not None,
            args.history_model is not None,
        ]
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="快速写入、同步或清空本地密钥配置。")
    parser.add_argument("--user", help="目标用户目录名，默认自动选择 kesepain 或唯一用户")
    parser.add_argument("--show", action="store_true", help="显示当前配置概览")
    parser.add_argument("--dry-run", action="store_true", help="只预览将写入的改动，不落盘")
    parser.add_argument("--quick", action="store_true", help="启用快速配置模式")
    parser.add_argument("--from-env", action="store_true", help="从常见环境变量导入密钥")
    parser.add_argument("--clear", action="store_true", help="清空脚本管理的所有密钥字段")
    parser.add_argument("--non-interactive", action="store_true", help="仅使用命令行参数，不进入交互模式")
    parser.add_argument("--provider", help="主模型 provider，例如 deepseek 或 openai")
    parser.add_argument("--model", help="主模型 model，例如 deepseek-chat")
    parser.add_argument(
        "--sync-history",
        dest="sync_history",
        action="store_true",
        help="将主模型 provider / model / key 同步到历史压缩配置",
    )
    parser.add_argument(
        "--no-sync-history",
        dest="sync_history",
        action="store_false",
        help="快速模式下不自动同步历史压缩配置",
    )
    parser.add_argument("--history-provider", help="单独指定历史压缩使用的 provider")
    parser.add_argument("--history-model", help="单独指定历史压缩使用的 model")
    parser.add_argument("--main-key", "--user-api-key", dest="user_api_key", help="写入 users/<user>/config.json 的 API.key")
    parser.add_argument("--history-key", "--history-zip-key", dest="history_zip_key", help="写入 core/config.json 的 history_zip.API_KEY")
    parser.add_argument("--weather-public-key", help="写入天气技能配置的 public_key")
    parser.add_argument("--weather-private-key", help="写入天气技能配置的 private_key")
    parser.add_argument("--web-search-key", help="写入网络搜索配置的 key")
    parser.set_defaults(sync_history=None)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    provider_catalog = load_provider_catalog()
    user_name = select_user_name(args.user)
    direct_change_requested = has_direct_change_request(args)

    if args.show:
        print_current_summary(user_name, provider_catalog)
        if direct_change_requested is False and args.quick is False:
            return

    if args.non_interactive:
        plan = build_plan_from_args(args, user_name, provider_catalog)
        if direct_change_requested is False:
            print("未提供任何新值，未写入文件。")
            return
    else:
        if direct_change_requested is False:
            if args.quick:
                plan = run_interactive_quick_setup(user_name, provider_catalog)
            else:
                plan = run_interactive_menu(user_name, provider_catalog)
                if plan is None:
                    return
        else:
            plan = build_plan_from_args(args, user_name, provider_catalog)

    for note in plan.notes:
        print(f"- {note}")
    apply_plan(user_name, plan, provider_catalog)


if __name__ == "__main__":
    main()
