import json
import os
import sys
import argparse
from pathlib import Path
from typing import Optional
from datetime import datetime
import uuid
import time

from mcp.server.fastmcp import FastMCP

# Instância FastMCP
mcp = FastMCP("automcp")

# Caminho padrão configurável no start (--path) ou via env
DEFAULT_VERIFAI_PATH: Optional[str] = None

# Controle simples de monotonicidade local para timestamps em ms
_PREV_NOW_MS: int = 0


def _resolve_base_path() -> Optional[Path]:
    base = DEFAULT_VERIFAI_PATH or os.environ.get("VERIFAI_ASSISTANT_DIR")
    return Path(base) if base else None


@mcp.tool()
def get_experts() -> str:
    """Lista os experts disponíveis no VerifAI Assistant.

    Usa o caminho definido ao iniciar o servidor com --path
    ou a variável de ambiente VERIFAI_ASSISTANT_DIR.
    """
    base_dir = _resolve_base_path()
    if not base_dir:
        return (
            "Erro: Caminho do VerifAI Assistant não definido. "
            "Inicie o servidor com --path ou defina VERIFAI_ASSISTANT_DIR."
        )

    experts_file = base_dir / "experts.json"
    if not experts_file.exists():
        return f"Erro: Arquivo experts.json não encontrado em {base_dir}"

    try:
        with open(experts_file, "r", encoding="utf-8") as f:
            experts = json.load(f)

        lines: list[str] = ["Experts disponíveis no VerifAI Assistant:", ""]
        for i, expert in enumerate(experts, 1):
            lines.append(f"{i}. ID: {expert.get('id', 'N/A')}")
            lines.append(f"   Tipo: {expert.get('type', 'N/A')}")
            lines.append(f"   Estado: {expert.get('state', 'N/A')}")
            if expert.get("name"):
                lines.append(f"   Nome: {expert.get('name')}")
            if expert.get("prompt"):
                prompt: str = expert.get("prompt", "")
                lines.append(f"   Prompt: {prompt}")
            lines.append("")

        return "\n".join(lines)

    except Exception as e:  # noqa: BLE001
        return f"Erro ao ler arquivo experts.json: {str(e)}"


@mcp.tool()
def create_expert(name: Optional[str] = None, prompt: Optional[str] = None, confirm: bool = False) -> str:
    """Cria um novo expert no experts.json.

    Se name/prompt não forem informados, o LLM deve perguntar ao usuário.
    Quando confirm=False, retorna uma prévia e pede confirmação.
    Quando confirm=True, grava no arquivo.
    """
    base_dir = _resolve_base_path()
    if not base_dir:
        return (
            "Erro: Caminho do VerifAI Assistant não definido. "
            "Inicie o servidor com --path ou defina VERIFAI_ASSISTANT_DIR."
        )

    experts_file = base_dir / "experts.json"
    if not experts_file.exists():
        return f"Erro: Arquivo experts.json não encontrado em {base_dir}"

    if not name or not prompt:
        missing = []
        if not name:
            missing.append("nome")
        if not prompt:
            missing.append("prompt")
        return (
            "Faltam dados: " + ", ".join(missing) + ". "
            "Por favor forneça name e prompt, e eu retornarei uma prévia para confirmação."
        )

    new_obj = {
        "id": str(uuid.uuid4()),
        "type": "user",
        "state": "enabled",
        "name": name,
        "prompt": prompt,
        "triggerApps": [],
    }

    # Prévia e checagens leves
    try:
        with open(experts_file, "r", encoding="utf-8") as f:
            current = json.load(f)
    except Exception as e:  # noqa: BLE001
        return f"Erro ao ler experts.json: {str(e)}"

    duplicates = [e for e in current if e.get("name") == name]
    dup_note = " (aviso: já existe expert com esse name)" if duplicates else ""

    if not confirm:
        preview = json.dumps(new_obj, ensure_ascii=False, indent=2)
        return (
            "Prévia do expert a ser criado" + dup_note + ":\n\n" + preview +
            "\n\nResponda confirm=true para gravar."
        )

    # Backup e escrita segura
    try:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = experts_file.with_suffix(f".json.bak.{timestamp}")
        with open(backup_path, "w", encoding="utf-8") as bf:
            json.dump(current, bf, ensure_ascii=False, indent=2)

        current.append(new_obj)
        tmp_path = experts_file.with_suffix(".json.tmp")
        with open(tmp_path, "w", encoding="utf-8") as tf:
            json.dump(current, tf, ensure_ascii=False, indent=2)
        os.replace(tmp_path, experts_file)

        return f"Expert criado com sucesso (id={new_obj['id']}). Backup: {backup_path.name}"
    except Exception as e:  # noqa: BLE001
        return f"Erro ao gravar experts.json: {str(e)}"


@mcp.tool()
def update_expert(
    id: Optional[str] = None,
    name: Optional[str] = None,
    new_name: Optional[str] = None,
    new_prompt: Optional[str] = None,
    new_state: Optional[str] = None,
    confirm: bool = False,
) -> str:
    """Atualiza um expert existente em experts.json.

    Identificação: por id (preferível) ou por name (se único).
    Atualizações suportadas: new_name, new_prompt, new_state.
    Use confirm=false para prévia; confirm=true para gravar.
    """
    base_dir = _resolve_base_path()
    if not base_dir:
        return (
            "Erro: Caminho do VerifAI Assistant não definido. "
            "Inicie o servidor com --path ou defina VERIFAI_ASSISTANT_DIR."
        )

    experts_file = base_dir / "experts.json"
    if not experts_file.exists():
        return f"Erro: Arquivo experts.json não encontrado em {base_dir}"

    if not id and not name:
        return "Forneça 'id' ou 'name' do expert a ser atualizado."

    try:
        with open(experts_file, "r", encoding="utf-8") as f:
            current = json.load(f)
    except Exception as e:  # noqa: BLE001
        return f"Erro ao ler experts.json: {str(e)}"

    # Encontrar candidato(s)
    matches = []
    if id:
        matches = [i for i, e in enumerate(current) if e.get("id") == id]
    else:
        matches = [i for i, e in enumerate(current) if e.get("name") == name]

    if not matches:
        return "Nenhum expert encontrado com os critérios informados."
    if len(matches) > 1:
        # Ambiguidade por name
        sample = [f"id={current[i].get('id')} name={current[i].get('name')}" for i in matches]
        return (
            "Múltiplos experts encontrados para este nome. Especifique 'id'.\n" + "\n".join(sample)
        )

    idx = matches[0]
    old = dict(current[idx])

    if new_name is None and new_prompt is None and new_state is None:
        return "Nenhuma alteração fornecida. Informe 'new_name', 'new_prompt' ou 'new_state'."

    updated = dict(old)
    if new_name is not None:
        updated["name"] = new_name
    if new_prompt is not None:
        updated["prompt"] = new_prompt
    if new_state is not None:
        if new_state not in {"enabled", "disabled"}:
            return "new_state inválido. Use 'enabled' ou 'disabled'."
        updated["state"] = new_state

    # Prévia
    if not confirm:
        def to_json(o):
            return json.dumps(o, ensure_ascii=False, indent=2)
        diff_lines = [
            "Prévia de atualização (old → new):",
            "OLD:", to_json(old),
            "NEW:", to_json(updated),
            "\nResponda confirm=true para aplicar.",
        ]
        return "\n".join(diff_lines)

    # Backup e escrita
    try:
        timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = experts_file.with_suffix(f".json.bak.{timestamp}")
        with open(backup_path, "w", encoding="utf-8") as bf:
            json.dump(current, bf, ensure_ascii=False, indent=2)

        current[idx] = updated
        tmp_path = experts_file.with_suffix(".json.tmp")
        with open(tmp_path, "w", encoding="utf-8") as tf:
            json.dump(current, tf, ensure_ascii=False, indent=2)
        os.replace(tmp_path, experts_file)
        return f"Expert atualizado com sucesso (id={updated.get('id')}). Backup: {backup_path.name}"
    except Exception as e:  # noqa: BLE001
        return f"Erro ao gravar experts.json: {str(e)}"


# --- Helpers para history.json ---

def _history_path() -> Optional[Path]:
    base_dir = _resolve_base_path()
    return (base_dir / "history.json") if base_dir else None


def _load_history() -> tuple[Optional[dict], Optional[str]]:
    path = _history_path()
    if not path:
        return None, (
            "Erro: Caminho do VerifAI Assistant não definido. "
            "Inicie o servidor com --path ou defina VERIFAI_ASSISTANT_DIR."
        )
    if not path.exists():
        return None, f"Erro: Arquivo history.json não encontrado em {path.parent}"
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data, None
    except Exception as e:  # noqa: BLE001
        return None, f"Erro ao ler history.json: {str(e)}"


def _safe_message_text(msg: dict) -> str:
    if not isinstance(msg, dict):
        return ""
    if isinstance(msg.get("text"), str):
        return msg["text"]
    content = msg.get("content")
    if isinstance(content, str):
        return content
    # Alguns formatos trazem content como lista/dict estruturado; retornar JSON compacto
    try:
        return json.dumps(content, ensure_ascii=False)[:2000]
    except Exception:  # noqa: BLE001
        return ""


def _parse_order(order: str) -> tuple[str, bool]:
    # Retorna (chave, reverse)
    if not order:
        return "lastModified", True
    reverse = order.startswith("-")
    key = order[1:] if reverse else order
    if key not in {"lastModified", "createdAt", "title"}:
        key = "lastModified"
    return key, reverse or (key in {"lastModified", "createdAt"})


@mcp.tool()
def get_folders() -> str:
    """Lista pastas do history.json com id, name e qtd_chats."""
    data, err = _load_history()
    if err:
        return err
    folders = data.get("folders") or []
    lines = ["Folders:", ""]
    for f in folders:
        fid = f.get("id")
        name = f.get("name")
        count = len(f.get("chats") or [])
        lines.append(f"- id={fid} | name={name} | qtd_chats={count}")
    if len(lines) == 2:
        lines.append("(sem pastas)")
    return "\n".join(lines)


@mcp.tool()
def get_chats(folder_id: Optional[str] = None, limit: int = 20, offset: int = 0, order: str = "-lastModified") -> str:
    """Lista chats (globais ou por pasta) com paginação.

    order: 'lastModified' | 'createdAt' | 'title' (prefixe com '-' para desc)
    """
    data, err = _load_history()
    if err:
        return err
    chats = data.get("chats") or []

    if folder_id:
        folders = data.get("folders") or []
        match = next((f for f in folders if f.get("id") == folder_id), None)
        if not match:
            return f"Folder não encontrado: {folder_id}"
        chat_ids = set(match.get("chats") or [])
        chats = [c for c in chats if c.get("uuid") in chat_ids]

    key, reverse = _parse_order(order)

    # Ordenação determinística com desempates estáveis
    if key in ("lastModified", "createdAt"):
        def key_tuple(c: dict):
            lm = c.get("lastModified") or 0
            ca = c.get("createdAt") or 0
            uid = c.get("uuid") or ""
            if key == "lastModified":
                primary, secondary = lm, ca
            else:
                primary, secondary = ca, lm
            # reverse=True => desc: usar negativos para evitar 'reverse'
            if reverse:
                return (-int(primary), -int(secondary), uid)
            return (int(primary), int(secondary), uid)
        chats.sort(key=key_tuple)
    else:
        # title: ordenar por título insensitive; desempate por lastModified desc, uuid asc
        def key_tuple(c: dict):
            title = (c.get("title") or "").lower()
            lm = c.get("lastModified") or 0
            uid = c.get("uuid") or ""
            if reverse:
                return (title, -int(lm), uid)
            return (title, int(lm), uid)
        chats.sort(key=key_tuple)

    page = chats[offset: offset + max(0, limit)]
    lines = [
        f"Chats (total={len(chats)} offset={offset} limit={limit} order={order}):",
        "",
    ]
    for c in page:
        lines.append(
            (
                f"- uuid={c.get('uuid')} | title={c.get('title')} | "
                f"createdAt={c.get('createdAt')} | lastModified={c.get('lastModified')} | "
                f"engine={c.get('engine')} | model={c.get('model')} | messages={len(c.get('messages') or [])}"
            )
        )
    if len(page) == 0:
        lines.append("(sem resultados nesta página)")
    return "\n".join(lines)


@mcp.tool()
def get_chat(uuid: str, include_messages: bool = False, msg_limit: int = 20, msg_offset: int = 0) -> str:
    """Retorna detalhes de um chat. Mensagens opcionais com paginação."""
    data, err = _load_history()
    if err:
        return err
    chats = data.get("chats") or []
    chat = next((c for c in chats if c.get("uuid") == uuid), None)
    if not chat:
        return f"Chat não encontrado: {uuid}"

    lines = [
        f"uuid={chat.get('uuid')}",
        f"title={chat.get('title')}",
        f"createdAt={chat.get('createdAt')}",
        f"lastModified={chat.get('lastModified')}",
        f"engine={chat.get('engine')}",
        f"model={chat.get('model')}",
        f"messages_total={len(chat.get('messages') or [])}",
    ]

    if include_messages:
        msgs = chat.get("messages") or []
        page = msgs[msg_offset: msg_offset + max(0, msg_limit)]
        lines.append("")
        lines.append(f"Messages (offset={msg_offset} limit={msg_limit}):")
        for i, m in enumerate(page, msg_offset + 1):
            role = m.get("role")
            text = _safe_message_text(m)
            if text and len(text) > 2000:
                text = text[:2000] + "..."
            lines.append(f"[{i}] role={role} type={m.get('type')} createdAt={m.get('createdAt')}")
            if text:
                lines.append(text)
                lines.append("")
    return "\n".join(lines)


@mcp.tool()
def search_history(
    query: str,
    in_: str = "both",
    date_from: Optional[str] = None,
    date_to: Optional[str] = None,
    engine: Optional[str] = None,
    model: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> str:
    """Busca por título e/ou mensagens com filtros básicos e paginação.

    in_: 'titles' | 'messages' | 'both'
    date_from/date_to: ISO (YYYY-MM-DD ou YYYY-MM-DDTHH:MM); compara createdAt/lastModified (ms epoch)
    """
    data, err = _load_history()
    if err:
        return err
    chats = data.get("chats") or []

    # Normalizar query
    q = (query or "").strip()
    if not q:
        return "Informe um termo de busca em 'query'."
    ql = q.lower()

    # Datas
    def to_epoch_ms(s: Optional[str]) -> Optional[int]:
        if not s:
            return None
        try:
            # aceitar 'YYYY-MM-DD' ou 'YYYY-MM-DDTHH:MM'
            if "T" in s:
                from datetime import datetime
                dt = datetime.fromisoformat(s)
            else:
                from datetime import datetime
                dt = datetime.fromisoformat(s + "T00:00:00")
            return int(dt.timestamp() * 1000)
        except Exception:  # noqa: BLE001
            return None

    from_ms = to_epoch_ms(date_from)
    to_ms = to_epoch_ms(date_to)

    def match_chat(c: dict) -> tuple[bool, Optional[str]]:
        if engine and c.get("engine") != engine:
            return False, None
        if model and c.get("model") != model:
            return False, None
        ca = c.get("createdAt") or 0
        lm = c.get("lastModified") or 0
        if from_ms is not None and lm < from_ms and ca < from_ms:
            return False, None
        if to_ms is not None and ca > to_ms and lm > to_ms:
            return False, None
        scope = in_.lower() if in_ else "both"
        # títulos
        if scope in ("titles", "both"):
            title = (c.get("title") or "").lower()
            if ql in title:
                return True, None
        # mensagens
        if scope in ("messages", "both"):
            for m in (c.get("messages") or []):
                text = _safe_message_text(m).lower()
                if ql in text:
                    # retornar trecho curto do primeiro match
                    snippet = _safe_message_text(m)
                    if len(snippet) > 200:
                        snippet = snippet[:200] + "..."
                    return True, snippet
        return False, None

    results: list[tuple[dict, Optional[str]]] = []
    for c in chats:
        ok, snip = match_chat(c)
        if ok:
            results.append((c, snip))

    # Ordenar por lastModified desc padrão
    results.sort(key=lambda t: t[0].get("lastModified") or 0, reverse=True)

    page = results[offset: offset + max(0, limit)]
    lines = [
        f"Resultados (total={len(results)} offset={offset} limit={limit}):",
        "",
    ]
    for c, snip in page:
        lines.append(
            f"- uuid={c.get('uuid')} | title={c.get('title')} | lastModified={c.get('lastModified')} | model={c.get('model')}"
        )
        if snip:
            lines.append(f"  snippet: {snip}")
    if len(page) == 0:
        lines.append("(sem resultados)")
    return "\n".join(lines)


# --- Helpers adicionais ---

DEFAULT_ENGINE = "anthropic"
DEFAULT_MODEL = "claude-sonnet-4-20250514"

def _now_ms() -> int:
    """Retorna epoch em milissegundos com garantia de monotonicidade local.

    Usa time.time_ns() // 1_000_000 e, em caso de empate com a última
    chamada no mesmo processo, soma +1 ms.
    """
    global _PREV_NOW_MS
    now_ms = time.time_ns() // 1_000_000
    if now_ms <= _PREV_NOW_MS:
        now_ms = _PREV_NOW_MS + 1
    _PREV_NOW_MS = now_ms
    return now_ms


def _write_history_atomic(updated: dict, target: Path) -> Optional[str]:
    try:
        from datetime import datetime
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = target.with_suffix(f".json.bak.{ts}")
        with open(backup, "w", encoding="utf-8") as bf:
            json.dump(updated, bf, ensure_ascii=False, indent=2)
        tmp = target.with_suffix(".json.tmp")
        with open(tmp, "w", encoding="utf-8") as tf:
            json.dump(updated, tf, ensure_ascii=False, indent=2)
        os.replace(tmp, target)
        return None
    except Exception as e:  # noqa: BLE001
        return str(e)


@mcp.tool()
def create_folder(name: str, confirm: bool = False) -> str:
    """Cria uma pasta em history.json (id=uuid4, chats=[])."""
    name_norm = (name or "").strip()
    if not name_norm:
        return "O campo 'name' é obrigatório."

    data, err = _load_history()
    if err:
        return err

    folders = data.get("folders") or []
    now = _now_ms()
    folder_obj = {
        "id": str(uuid.uuid4()),
        "name": " ".join(name_norm.split()),
        "chats": [],
        "createdAt": now,
        "lastModified": now,
    }

    warn = ""
    if any((f.get("name") or "") == folder_obj["name"] for f in folders):
        warn = "\n(aviso: já existe pasta com esse nome)"

    if not confirm:
        return (
            "Prévia da pasta a ser criada:" + warn + "\n\n" +
            json.dumps(folder_obj, ensure_ascii=False, indent=2) +
            "\n\nResponda confirm=true para gravar."
        )

    # Persistir
    history_path = _history_path()
    data.setdefault("folders", folders)
    folders.append(folder_obj)
    errw = _write_history_atomic(data, history_path)
    if errw:
        return f"Erro ao gravar history.json: {errw}"
    return f"Folder criado com sucesso (id={folder_obj['id']})."


@mcp.tool()
def create_chat(
    title: str,
    engine: Optional[str] = None,
    model: Optional[str] = None,
    folder_id: Optional[str] = None,
    initial_messages: Optional[list[dict]] = None,
    disableStreaming: bool = False,
    tools: Optional[list] = None,
    locale: Optional[str] = None,
    docrepo: Optional[str] = None,
    confirm: bool = False,
) -> str:
    """Cria um chat em history.json e opcionalmente vincula a uma pasta."""
    title_norm = (title or "").strip()
    engine_norm = ((engine or DEFAULT_ENGINE) or "").strip().lower()
    model_norm = ((model or DEFAULT_MODEL) or "").strip()

    if not title_norm:
        return "O campo 'title' é obrigatório."
    if not engine_norm:
        return "Engine inválido após aplicar padrão."
    if not model_norm:
        return "Model inválido após aplicar padrão."

    data, err = _load_history()
    if err:
        return err

    chats = data.get("chats") or []
    folders = data.get("folders") or []

    folder_ref = None
    if folder_id:
        folder_ref = next((f for f in folders if f.get("id") == folder_id), None)
        if not folder_ref:
            return f"Folder não encontrado: {folder_id}"

    now = _now_ms()
    chat_uuid = str(uuid.uuid4())

    # Montar mensagens a partir de initial_messages
    built_messages: list[dict] = []
    for msg in (initial_messages or []):
        if not isinstance(msg, dict):
            return "Cada mensagem inicial deve ser um objeto com 'role' e 'text'/'content'."
        role = (msg.get("role") or "").strip().lower()
        text = (msg.get("text") or msg.get("content") or "")
        if role not in {"system", "user", "assistant"}:
            return "Cada mensagem inicial deve ter role em {'system','user','assistant'}."
        built_messages.append({
            "role": role,
            "type": "text",
            "attachments": [],
            "uuid": str(uuid.uuid4()),
            "engine": engine_norm,
            "model": model_norm,
            "createdAt": _now_ms(),
            "expert": None,
            "deepResearch": False,
            "toolCalls": [],
            "usage": None,
            "transient": False,
            "uiOnly": False,
            "content": text,
        })

    chat_obj = {
        "uuid": chat_uuid,
        "title": title_norm if len(title_norm) <= 512 else title_norm[:512],
        "createdAt": now,
        "lastModified": now,
        "engine": engine_norm,
        "model": model_norm,
        "disableStreaming": bool(disableStreaming),
        "tools": tools or [],
        "locale": locale if locale else None,
        "docrepo": docrepo if docrepo else None,
        "messages": built_messages,
    }

    if not confirm:
        preview_lines = [
            "Prévia do chat a ser criado:",
            json.dumps(chat_obj, ensure_ascii=False, indent=2),
        ]
        if folder_ref:
            preview_lines.append(f"Será vinculado à pasta: {folder_ref.get('name')} (id={folder_ref.get('id')})")
        preview_lines.append("\nResponda confirm=true para gravar.")
        return "\n\n".join(preview_lines)

    # Persistir
    history_path = _history_path()
    data.setdefault("chats", chats)
    chats.append(chat_obj)

    if folder_ref:
        folder_ref.setdefault("chats", [])
        if chat_uuid not in folder_ref["chats"]:
            folder_ref["chats"].append(chat_uuid)
        folder_ref["lastModified"] = max(int(folder_ref.get("lastModified") or 0), now)

    errw = _write_history_atomic(data, history_path)
    if errw:
        return f"Erro ao gravar history.json: {errw}"
    if folder_ref:
        return f"Chat criado com sucesso (uuid={chat_uuid}) e vinculado à pasta {folder_ref.get('name')}."
    return f"Chat criado com sucesso (uuid={chat_uuid})."


def main() -> None:
    global DEFAULT_VERIFAI_PATH

    parser = argparse.ArgumentParser(description="AutoMCP (FastMCP)")
    parser.add_argument("extra", nargs="*", help=argparse.SUPPRESS)  # ignora args posicionais do host
    parser.add_argument("--path", dest="verifai_path", type=str, help="Diretório do VerifAI Assistant")
    parser.add_argument("--test", action="store_true", help="Executa get_experts localmente e sai")
    args, _ = parser.parse_known_args()

    DEFAULT_VERIFAI_PATH = args.verifai_path or os.environ.get("VERIFAI_ASSISTANT_DIR")

    if args.test:
        print(get_experts())
        return

    # Executa o servidor via STDIO
    mcp.run()


if __name__ == "__main__":
    main()
