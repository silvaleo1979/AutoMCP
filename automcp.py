import json
import os
import sys
import argparse
from pathlib import Path
from typing import Optional
from datetime import datetime
import uuid

from mcp.server.fastmcp import FastMCP

# Instância FastMCP
mcp = FastMCP("automcp")

# Caminho padrão configurável no start (--path) ou via env
DEFAULT_VERIFAI_PATH: Optional[str] = None


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
