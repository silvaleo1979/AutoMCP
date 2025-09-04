# AutoMCP

MCP para gerenciamento de experts e histórico do VerifAI Assistant.

## Função disponível

### get_experts
Lista todos os experts disponíveis no VerifAI Assistant.

**Parâmetros:**
- `verifai_path` (string): Caminho para o diretório do VerifAI Assistant

**Exemplo de uso:**
```json
{
  "verifai_path": "C:\\Users\\silva\\AppData\\Roaming\\VerifAI Assistant"
}
```

## Instalação

```bash
pip install -r requirements.txt
```

## Execução

```bash
python -m automcp.server
```
