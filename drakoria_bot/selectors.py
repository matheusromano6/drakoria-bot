"""TODOS os seletores/textos do Drakoria (mapeados ao vivo em 16/10/2026, build 2030-online416).
O jogo muda textos com atualizacoes: preferir classes estaveis e regex com variantes."""

GAME_HOST = "drakoriaidle.com.br"

# cena central: a classe diz o estado
SCENE = "main.content > section"
SCENE_HUNTING = "spatial-battle-stage"          # caçando
SCENE_HOUSE = "house-scene"                     # na house (treino no dummy)
SCENE_CITY = "city-temple-scene"                # Thais / parado

# menu (itens escondidos por aba: clicar via JS)
NAV = "button.nav-item[data-nav='{}']"          # hunt, bosses, party, city, inventory...

# cidade
CITY_GO = "button.cp-btn-go"                    # "Caçar em <hunt>"
CITY_DEST = ".cp-dest"                          # title "Próximo destino: X · Mundo · Level N+"

# escolher hunt
PICKER = "section.hunt-picker-window"
PICKER_CLOSE = "[aria-label='Fechar a escolha de hunt']"
PICKER_SEARCH = "input[aria-label^='Buscar hunt']"
PICKER_BAND_ALL = ".hw-band"                    # 1o = Todas
PICKER_TILE = ".hw-tile"
PICKER_TILE_MAIN = "button.hw-tile-main"
PICKER_BEST = ".hw-fit.fit-best"                # "Melhor escolha" do jogo pro level da party
PICKER_START = "button.hw-start:not(.hw-start-offline)"   # "Caçada online"

# preparar caçada (dificuldade)
DIFF_WINDOW = ".hcd-window"
DIFF_OPTION = ".hcd-option"                     # texto comeca com o nome (Fácil/Normal/Difícil/Insano...)
DIFF_CONFIRM = ".hcd-confirm"                   # "Entrar na caçada"

# caçando
HUNT_EXIT = "button.cp-btn.danger"              # title "Retornar para Thais"
HUNT_TRACKER_ROW = ".bestiary-tracker-row"      # title "Troll: 4 de 250 kills · faltam 246..."
HUNT_DIFFICULTY = ".world-hunt-difficulty-control"
HUNT_DETAILS = "button.cp-btn[title='Detalhes das criaturas']"   # abre .creature-window.is-hunt com o NOME da caça
HUNT_DETAILS_WINDOW = ".creature-window.is-hunt"

# house / treino
HOUSE_STOP = ".house-hud-btn.danger"            # "Parar" (title "Parar treino"); parado vira "Treinar" (.primary)
HOUSE_LEAVE = "button[title='Sair da house']"    # parado na house -> Thais

# loot pouch
LOOT_OPEN = "button[title^='Abrir a Loot Pouch']"
LOOT_WINDOW = ".loot-pouch-window"
LOOT_SELL_ALL = ".loot-sell-all"                # "Vender tudo agora"
LOOT_PROTECT_LABEL = "Proteger drops de boss"
LOOT_AUTOSELL_LABEL = "Auto Sell"

# janelas que aparecem sozinhas
OFFLINE_REPORT = ".op-window"                   # "Sua Party continuou treinando"
OFFLINE_COLLECT = ".op-collect"                 # "Coletar e continuar"
# botoes "inofensivos" pra fechar avisos/relatorios/morte
DISMISS_TEXT = r"^(Coletar e continuar|Continuar|OK|Ok|Fechar|Entendi|Confirmar)$"

# tasks de produto (Cyclopedia > Tasks). Ate 2 ativas; aceitar/entregar sem confirmacao (entregar: ainda nao visto)
TASKS_OPEN = ".quick-access-button[title^='Tasks']"
TASKS_LIST = ".tibia-tasks-list"
TASK_ROW = ".tibia-tasks-list .tibia-task-row"   # classes: claimed / accepted / locked
TASK_ACCEPT_TEXT = "Aceitar"
TASK_ACTIVE = ".tibia-tasks-active .tibia-task-active"

# cyclopedia / bestiary
CYCLOPEDIA_OPEN = ".quick-access-button[title^='Cyclopedia']"
CYCLOPEDIA_TAB = ".cyclopedia-tab"
BESTIARY_TAB_TEXT = "Bestiário"
BESTIARY_CLASS = ".bestiary-class-tile"          # 'Vermes 3 / 74' (conhecidas / total)

# prey (2 espacos liberados; 3 e 4 = Drako Shop). NUNCA: Comprar cartas / Sortear bonus / Escolher entre todas
PREY_OPEN = ".drk-prey-topbar"
PREY_WINDOW = ".drk-prey-window"
PREY_SLOT = ".drk-prey-slot"                    # state-selection / state-active / state-locked
PREY_CREATURE = "button.drk-prey-creature"      # title = criatura
PREY_CONFIRM = ".drk-prey-confirm"
PREY_TOOL = ".drk-prey-tool"
PREY_REROLL_TEXT = "Trocar lista"
PREY_OPTION = ".drk-prey-option"
PREY_RELEASE_TEXT = "Liberar o espaço"
PREY_ASK = ".drk-prey-ask"                      # confirmacao 'Trocar a lista do espaço N por X gold?'
PREY_ASK_PAY = ".drk-prey-ask button.green"     # 'Pagar 3.000 gold'
PREY_ASK_CANCEL = ".drk-prey-ask button:not(.green)"   # 'Cancelar'

# login (pagina inicial do site)
LOGIN_OPEN_TEXT = r"^(Entrar|Já tenho conta)$"
LOGIN_SUBMIT_TEXT = r"Entrar no jogo"
LOGIN_PASSWORD = "input[type=password]"

# nunca clicar
NEVER = [".online-logout-top-button", ".training-offline-menu-item", ".logout-menu-item", "[data-nav='gm']"]

WINDOW_CLOSE = (".tibia-window-controls button, .tibia-window button[title='Fechar'], "
                ".workspace-window button[title='Fechar'], .workspace-window [aria-label='Fechar']")
