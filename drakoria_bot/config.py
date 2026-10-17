"""Configuracao do bot (config.json ao lado do .exe). O que nao estiver no arquivo usa o padrao daqui."""
import copy
import json
import os

DIFFICULTIES = ["Fácil", "Normal", "Difícil", "Insano", "Pesadelo", "Inferno", "Impossível"]

DEFAULTS = {
    "cdp_url": "http://127.0.0.1:9224",   # IdleDeck com depuracao remota (mesma porta dos outros bots)
    "poll_seconds": 5,                    # 1 leitura (1 evaluate) a cada N segundos
    # "hunt" = mantem a party caçando | "watch" = so' vigia (relogin, avisos, loot) e nao mexe na caça/treino
    "mode": "hunt",
    "hunt": "",                           # vazio = automatica ('Melhor escolha' do jogo pro level da party)
    "difficulty": "Normal",               # Insano+ pede level (250/450/700/1000)
    "loot": {
        "auto_sell": "auto",              # "auto" = liga se a conta for Premium | "on" | "off"
        "sell_at_items": 30,              # sem Auto Sell: 'Vender tudo agora' com a Loot Pouch nesse numero de itens
        "check_minutes": 30,              # confere 'Proteger drops de boss' (sempre ligado) e o Auto Sell
    },
    # Prey: espaco livre -> criatura da caça (a que mais aparece); senao troca gratis; depois troca paga com OURO
    # ("until_found" = ate achar | "budget" = ate gold_per_day por dia); nao achou -> qualquer uma (tenta de novo em 2h).
    # Nunca gasta cartas (Prey Wildcards) nem Drako Coins.
    "prey": {
        "enabled": True,
        "mode": "budget",
        "gold_per_day": 5000,
        "reserve_gold": 0,                # nunca deixa o ouro abaixo disso trocando lista
        "check_minutes": 10,
        "max_rerolls_per_check": 10,
    },
    # objetivos (aba Objetivos): filas escolhidas pelo usuario. Caça: task ativa -> bestiary -> caça da aba Regras
    "goals": {
        "enabled": True,                  # confere as tasks (tambem as aceitas na mao) e segue a fila
        "tasks": [],                      # nomes das tasks de produto, na ordem
        "bestiary": [],                   # criaturas, na ordem
        "level_over": 10,                 # ate quantos levels acima do recomendado da caça a party pode ir
        "check_minutes": 10,
    },
    "relogin": True,                      # entra sozinho com o login salvo (aba Login) se o jogo deslogar
    "error_reload_seconds": 60,           # pagina de erro/desconectado: recarrega a cada N s
    "unknown_reload_seconds": 120,        # estado desconhecido por mais disso: recarrega
    "cooldown_fail_seconds": 300,         # acao que falhou espera isso antes de tentar de novo
    "bosses": [],                         # (futuro) fila de bosses
}


def _merge(base, extra):
    out = copy.deepcopy(base)
    for key, value in (extra or {}).items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def load(path):
    data = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as file:
            data = json.load(file)
    else:
        save(path, DEFAULTS)
    return _merge(DEFAULTS, data)


def save(path, config):
    with open(path, "w", encoding="utf-8") as file:
        json.dump(config, file, ensure_ascii=False, indent=2)
