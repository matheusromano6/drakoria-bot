# CLAUDE.md - drakoria_bot

Bot do **Drakoria** que roda **dentro do IdleDeck**, no mesmo estilo dos bots do OtxIdle e do Huntera. Projeto NOVO e
SEPARADO: nao misturar com `matheusromano6/otxidle-bot` nem `matheusromano6/huntera-bot` (versoes, releases, config).

## Ponto de partida
- BASE = o bot do OtxIdle (C:\Users\Pichau\otxidle-bot). Leia o CLAUDE.md de la inteiro antes de comecar: tem a arquitetura,
  o processo de release e as licoes de 6 dias de uso real. O do Huntera (C:\Users\Pichau\huntera-bot) e' o modelo mais antigo.
- O que da pra REAPROVEITAR quase igual (so trocar nomes/host): `idledeck.py` (CDP porta 9224, so paginas do jogo),
  `launcher.py` (abrir o IdleDeck com a porta; NUNCA matar o IdleDeck a forca), `updater.py` (botao Atualizar via GitHub
  releases, asset de nome fixo), `paths.py`, `runner.py` (thread), `memory.py`, `credentials.py` (logins com DPAPI),
  `config.py` (merge com padroes), `gui.py` (CustomTkinter + bandeja + log em arquivo + `--iniciar`), build com PyInstaller.
- O que e' ESPECIFICO do jogo e precisa ser mapeado AO VIVO antes de codar: `selectors.py`, `account.py` (leitura de estado
  num unico evaluate + acoes), e as regras do `engine.py`/`tasks.py`.
- Regra de ouro: so agir em paginas do Drakoria; NUNCA tocar nas paginas do OtxIdle/Huntera (os outros bots rodam no mesmo
  IdleDeck/porta). Mapear primeiro SO LENDO; o usuario prefere mapear e depois implementar, com objetividade.

## Checklist de mapeamento (o que o bot do OtxIdle precisou - conferir se existe no Drakoria)
1. Identidade/HUD: nome, level, vocacao, ouro, capacidade (livre e maxima), stamina (caça e treino), party.
2. Estados: caçando / saindo / cidade / treinando / deslogado (tela de personagens) / login / pagina inicial / erro.
3. Ciclo de capacidade: sair da caça -> vender (fluxo completo, confirmacoes) -> voltar pra mesma caça.
4. Caças: lista (nome, level recomendado/minimo, criaturas), busca, iniciar. Ler a lista inteira 1x e guardar (hunts.json).
5. Party: criar, convidar (pelo nome?), aceitar convite, o que acontece quando o lider/membro sai, regra de level.
6. Treino/stamina: como iniciar/encerrar, arma de exercicio, o que acontece com stamina baixa.
7. Telas que travam: novidades/patch notes, avisos, morte, relatorio de caça, recompensa diaria.
8. Quedas: server save, login (o bot NUNCA digita senha de conta real por conta propria: o usuario cadastra na aba Login),
   tela de personagens, desconexao (notificacao), pagina de erro do servidor, tela travada -> recarregar.
9. Extras do jogo: tasks/bestiary/blessings/etc. (so depois do basico rodando).

## Licoes que ja custaram caro no OtxIdle (evitar desde o inicio)
- Textos e seletores do jogo MUDAM com atualizacoes (botao traduzido, campo de busca novo): seletores centralizados e
  regex com variantes; nunca esperar 30s por um botao que pode nao existir.
- Campo de busca: escopar na janela certa (outra janela aberta "roubava" o input); .fill() pode nao disparar o filtro (DIGITAR).
- Ler o estado depois de clicar com espera pela MUDANCA (lista velha = clique na carta errada).
- Estado que precisa sobreviver a reinicio (treino em grupo, bloqueios, logins por personagem) vai pro memory.json.
- Nunca esconder erro de build; conferir que o exe de dist nao esta em uso e que o exe gerado e' novo (icone/horario).
  Build numa pasta separada (release/) e so depois trocar o exe em dist.
- Testes com contas falsas que simulam o jogo; testes NUNCA gravam arquivos reais; nomes reais nao entram nos testes.
- Escolhas do usuario (caça fixa, modo por conta) mandam: o bot nao "corrige" escolhas por conta propria.

## Ambiente deste PC
- Python 3.12 em %LOCALAPPDATA%\Programs\Python\Python312 (fora do PATH: chamar pelo caminho completo), com playwright,
  customtkinter, pillow, pystray, pyinstaller. Git em C:\Program Files\Git\cmd, gh em C:\Program Files\GitHub CLI (logado
  como matheusromano6). Commits com -c user.name="Matheus Romano" -c user.email="matheus.romano@manyminds.com.br".
- Usuario fala portugues.

## A preencher no mapeamento
- URL do jogo / host das paginas no IdleDeck, contas abertas, layout ideal da interface do novo bot.

## Primeira olhada (16/10/2026 ~20:40, ao vivo, so leitura) - Drakoria Idle v1.7, build 2030-online416
- Host: `https://jogo.drakoriaidle.com.br/` (1 aba no IdleDeck; worker `background-combat-worker.js` = combate roda em background).
- DIFERENCA PRINCIPAL: UMA conta (login MRomano) controla a PARTY INTEIRA de 4 numa unica pagina: MRKina (Knight, TANK, lider),
  MRPally (DPS), MRSorc (DPS), MRDruid (SUP), todos lv 8. Sem convite/aceite entre abas: party e' do proprio jogo
  ("Lider da Party: MRKina - Lideranca automatica · Knight preferencial"). O modelo do OtxIdle (1 conta por aba) NAO se aplica.
- HUD (classes estaveis, prefixos `drk-`, `td-`, `tcb-`, `hw-`): topbar ouro `.topbar-gold-balance` (500), Drako Coins
  `.topbar-drako-balance`; painel Party `.td-member` (`.td-member-main` "Nome ROLE Lv 8 · 0% hp mana", `.td-member-bag`);
  Backpack "2/80" (slots), Loot Pouch, Supply Pouch (30). Skills por aba `.td-tab` EK/RP/MS/ED. "Reserva offline hh:mm:ss".
- Menu: `.header-menu-launcher` abre o menu; itens `button.nav-item[data-nav=...]` (hunt, bosses, quests, bestiary, party,
  inventory=Banco, market, city=Loja, guild, ranking, settings, gm). Itens de outras abas do menu ficam hidden: clicar via JS.
  Barra rapida `.quick-access-button` (title "Caçar (tecla 1)" ... "Cyclopedia (tecla 8)").
- Escolher Hunt (`data-nav=hunt`): `section.hunt-picker-window`, fecha com `[aria-label="Fechar a escolha de hunt"]`.
  68 caças; busca `input[aria-label^="Buscar hunt"]` (nome/cidade/criatura/level); filtros `.hw-band` (Todas, Recomendadas,
  1-49...); ordenar select (Melhor para a Party...). Card `.hw-tile` (`.is-selected`/`.is-above`) > `button.hw-tile-main`
  (strong=nome, `.hw-lv` "Lv 5+", `.hw-fit` "Melhor escolha"/"Desafio", tag bonus `.hv-tag`). Detalhe `.hw-detail`:
  criaturas `.hw-creature[title="Ficha: X"]`, level recomendado, recordes, "Maestria do offline" (2.000 abates, 200 sem
  derrota total -> libera caçada offline). INICIAR: `button.hw-start` "Caçada online" (verde) / `.hw-start-offline` (disabled
  ate a maestria). Criatura do Dia `.bc-panel` (XP x2) com a caça dela.
- Personagem (`data-nav=party`, janela Cyclopedia aba Personagem): sub-abas por membro; Atributos: HP, Mana, CAPACIDADE (470
  na Kina), velocidade. Cap e' por personagem; loot vai pra Loot Pouch/backpack da party.
- Loot Pouch (`button[title^="Abrir a Loot Pouch"]`, `.loot-pouch-window`): checkbox "Proteger drops de boss" (on) e
  "AUTO SELL" (off), `.loot-sell-all` "Vender tudo agora", listas "Nao coletar" e "Nao vender". O JOGO JA TEM AUTO SELL:
  provavelmente dispensa o ciclo sair->vender->voltar do OtxIdle (confirmar com o usuario antes de ligar).
- Loja (`data-nav=city`, `.cs-window`) e' so COMPRA (armas, Loja Magica, Treinamento, Cripta, Bigorna, Promotion).
- Treino: estava "Treinando no dummy" na house Seawatch: HUD `.house-hud-btn.danger` "Parar" (title "Parar treino"),
  `.house-hud-tool` Dummy/Decorar, exercise weapons `.house-exercise-slot` por membro (EK/RP/MS/ED, 1.5x, `.empty`).
  Menu: `.training-online-menu-item` "Treino Online (na house 1.5x/2.5x)", `.training-offline-menu-item` "Treino Offline".
- ATENCAO: clicar `.training-offline-menu-item` (Claude, 20:48) DESLOGOU a conta -> pagina inicial com modal de login
  (Usuario preenchido "MRomano", senha vazia, "Lembrar meu acesso", "Entrar no jogo", Google). Treino Offline = sair e treinar
  offline. NUNCA clicar nele no mapeamento. Login: o usuario faz (ou cadastra na aba Login do bot).
- Aviso de atualizacao: banner "Atualização do Drakoria - O jogo vai salvar seu progresso e atualizar em N s" + "Atualizar
  agora"; passou sozinho sem recarregar visivelmente.
- `.tcb-button.online-logout-top-button` "Salvar e sair da conta" - nunca clicar. Conta tem menu GameMaster (`data-nav=gm`): nao tocar.
- Ainda NAO mapeado: tela caçando (HUD de caça, como sair), stamina (parece ser "Reserva offline" + Premium), morte/derrota
  total, Helper (`.helper-menu-item`, potions/runas/rotacao), Banco, tasks (Cyclopedia > Tasks).

## Segunda olhada (16/10/2026 ~20:55, ao vivo, depois do relogin do usuario)
- Ao entrar: modal `.op-window` "Sua Party continuou treinando · Progresso offline" (tempo, skills ganhas) com
  `.op-collect` "Coletar e continuar" e "Fechamento automático em Ns" (fecha sozinho). O treino offline continuou com a conta fora.
- ESTADOS pela `main.content > section` (classe): cidade/parado = `city-temple-scene ... city-temple-idle-stage`
  (Thais); caçando = `spatial-battle-stage ... phase-engage`; treino na house = HUD `.house-hud-*` "Treinando no dummy".
- Cidade: barra `.cp-toolbar`: `.cp-dest` (title "Próximo destino: Troll Cave · Mundo · Level 5+"), `button.cp-btn-go`
  (title "Caçar em <hunt>") = caçar na ultima/escolhida; `.cp-btn[title="Escolher Hunt"]`, `[title="Ver criaturas"]`.
- INICIAR CAÇA: `.cp-btn-go` (ou `.hw-start` no Escolher Hunt) -> modal `.hcd-window` "Prepare sua caçada": dificuldade
  `.hcd-option` (Fácil/Normal/Difícil livres; Insano 250+, Pesadelo 450+, Inferno 700+, Impossível 1000+ = level), info
  (criaturas no mapa, "Volta em 90 s" respawn) -> `.hcd-confirm` "Entrar na caçada" (Cancelar). Entra em ~2s.
- Caçando: `.world-hunt-difficulty-control` "Normal 4/70 ativas ALTERAR"; `.cp-btn[title="Detalhes das criaturas"]`,
  `[title="Trocar Hunt"]`, `.cp-btn.danger[title="Retornar para Thais"]` = SAIR da caça (nao testado ainda).
  Rastreador `.bestiary-tracker-row` (title "Troll: 4 de 250 kills · faltam 246").
  Sessao (painel esquerdo): XP da Party/h, Kills/h, Valor gerado/h, Lucro/h. Troll Cave lv8: ~97k XP/h party.
  OURO entra direto no topo (500 -> 581); LOOT vai pra Loot Pouch (slots), nao enche a backpack.
- Barras de magia por membro `.hunt-helper-slot` (6 por voc, todas `.empty` = so ataque basico); preset do Helper
  `.abp-save` "Salvar" / `.abp-gear`. Configuracao do jogo: o bot nao deve mexer sem decisao do usuario.
- Helper (`button[title^="Abrir o Helper"]`, `.helper-window`): presets 1-5 `.hlp-preset`, membros `.hlp-member`
  (role-tank/dps/support), abas `.hlp-tab` Curas/Combo/Combate/Equip./Suporte; curas por HP% (Wound Cleansing), pocoes
  (Small Health / Mana Potion por %), Remover Paralyze.
- Tasks (quick-access "Tasks (tecla 3)", Cyclopedia > Tasks = `.workspace-window`): "Tasks de Creature Products" = COLETAR
  ITENS (ex. Cabelos de Troll: 100 Bunch Of Troll Hair, Troll Cave Lv5+, 5.000 ouro + 5.000 XP cada? +10 TP). Lista
  `.tibia-tasks-list > .tibia-task-row`, filtros Todas/Disponíveis/Ativas/Concluídas, botao `.tibia-button.small.green`
  "Aceitar" (ou "Requer Lv N" disabled). Ate 2 ativas; 40 no total; itens pedidos ficam protegidos da venda automatica.
  Resumo: Task Points, Tasks ativas 0/2, Prontas para entregar, Concluidas 0/40.
- STAMINA: nao existe stamina de caça visivel (nada com "stamina" no DOM). Limite visto = "Reserva offline" (Premium Ouro:
  ate 12h, carrega +2h por 1h online; os 15 min iniciais de cada saida nao gastam) - usada pela caçada/treino offline.
- Workspace (Cyclopedia etc.) NAO e' `.tibia-window`: `.workspace-window`; fechar todas as janelas precisa cobrir as duas.
- Deixado CAÇANDO em Troll Cave (Normal) as 20:55 pelo mapeamento (antes estava treinando no dummy).
- Falta ver: "Retornar para Thais" (sair), Loot Pouch cheia / Auto Sell em uso, morte/derrota total, Treino Online na house
  (como iniciar/parar o dummy), Banco, tela de login automatica (Lembrar meu acesso).

## v1.0.0 (16/10/2026) - decisoes do usuario e estrutura
- Usuario: sem stamina no jogo -> sem ida pro treino por enquanto; tasks depois; dificuldades acima de Difícil so com
  level 250+ (mostrar todas). Level das caças e' pra 1 char: com 4 da pra ir em mais fortes (so' informacao, o bot nao usa).
  Lista de hunts toda carregada (`drakoria_bot/data/hunts.json`, 68) e de bosses (`data/bosses.json`, 81: nome, level,
  categoria Bane/Archfoe/Nemesis/Reward Boss, HP, local) pra fila de bosses no futuro (`config.bosses`).
  Venda: Premium tem Auto Sell; free precisa 'Vender tudo agora'. SEMPRE garantir 'Proteger drops de boss' ligado.
  Auto Sell 'auto' = liga se a conta for Premium (Boosts > Conta "Premium Ouro").
  Interface: simples, leve, objetiva: abas Painel / Regras / Login / Log, janela 440x580, destaque dourado (#e0a526),
  icone "D" dourado. Relogin automatico com 1 login (DPAPI em credentials.json).
- Estrutura: `selectors.py`, `account.py` (READ_JS = 1 evaluate -> State; acoes start_hunt/best_hunt/stop_training/
  loot_settings/sell_all/login/reload/dismiss_popups), `engine.py` (1 acao por tick: erro -> login -> avisos -> loot ->
  caça), `hunts.py` (identify: caça atual pelas criaturas do rastreador, a tela de caça nao mostra o nome), `config.py`,
  `memory.py`, `gui.py`, e copiados do OtxIdle: idledeck/launcher/updater/paths/runner/credentials.
- `python -m drakoria_bot --status` le sem agir (validado: house, Premium, 4 membros lv 8). Testes: 39 ok.
- Validado ao vivo so leitura: seletores da Loot Pouch (checkboxes por label, `.loot-sell-all`) e fechar janela.
- AINDA NAO validado com o bot rodando: start_hunt pela busca, stop_training ('Parar' na house), sell_all (confirmacao?),
  login (form da pagina inicial), troca de caça estando caçando, best_hunt.
- Conta em treino na house + modo 'Caçar sempre' -> o bot PARA o treino e vai caçar (modo 'Só vigiar' nao mexe).

## Teste ao vivo do bot (17/10/2026 00:32)
- 'Parar' na house so' para o treino: a party FICA na house (botao vira `.house-hud-btn.primary` "Treinar"). Fase nova
  `house_idle` -> `button[title='Sair da house']` -> Thais em ~5s. v1.0.1.
- VALIDADO: Loot Pouch conferida (protecao de boss + Auto Sell ligados, Premium) -> parar treino -> sair da house ->
  busca 'Troll Cave' (digitando) -> Caçada online -> Normal -> Entrar na caçada -> caçando; identify() reconheceu
  a caça pelo rastreador; best_hunt = 'Troll Cave' pro lv 8.
- Ainda NAO visto: sell_all (conta free), login automatico, troca de caça estando caçando.

## Prey (17/10/2026, ao vivo)
- Abre por `.drk-prey-topbar` (ou menu `.drk-prey-menu-item`): `.drk-prey-window` "Bonus contra uma criatura, para a Party
  inteira". 4 espacos `.drk-prey-slot` (`state-selection` / `state-active` / `state-locked`): 1 e 2 liberados; 3 e 4 so pela
  Drako Shop (2.750 / 5.000 Drako Coins). Tempo so corre CAÇANDO online (Bosses/Endless nao contam; "Pausado · fora da caça").
- Escolha: lista de 9 criaturas por espaco (`button.drk-prey-creature[title=Nome]`) -> clicar seleciona -> `.drk-prey-confirm`
  "Confirmar" (sem confirmacao extra). Bonus sorteado (dano, defesa, XP ou loot, 1-10 estrelas). Fica 2:00:00 de caça.
  Escolhido por Claude 17/10 ~01:10 (Troll Cave): espaco 1 Young Troll (Dano reduzido +12%), espaco 2 Troll (Loot +13%).
- Ativo: texto "Prey ativo / <criatura> / <bonus +N%> / ... / h:mm:ss / Pausado · fora da caça". Ferramentas `.drk-prey-tool`:
  "Trocar lista" (gratis 1 por espaco por dia, renova a meia-noite; `.drk-prey-free`), "Sortear bonus" (1 carta),
  "Escolher entre todas" (5 cartas). "Quando o tempo acabar": radios `.drk-prey-option` Liberar o espaco (padrao) /
  Renovar sorteando (1 carta) / Travar (5 cartas).
- Cartas = Prey Wildcards (0/250), compradas na Drako Shop com DRAKO COINS (5 = 250 coins ... 50 = 1.900), NAO com ouro.
  O bot NUNCA gasta Drako Coins. Custo da troca de lista depois da gratis do dia: ainda nao visto (provavel ouro).
- Troll Cave: espaco 1 tinha Spider/Young Troll, espaco 2 Troll/Rat (as listas sao sorteadas por espaco).

## v1.1.0 - Prey automatica (17/10/2026, regra do usuario)
- So' caçando e com a caça identificada, a cada 10 min: abre a Prey (read_prey), e em cada espaco LIVRE (state-selection):
  criatura da caça na lista -> escolhe a que mais aparece (abates no rastreador); senao 'Trocar lista' gratis; depois troca
  paga com OURO: modo 'budget' (ate prey.gold_per_day por dia, gasto em memory.json prey_spent) ou 'until_found'
  (sem limite diario, respeita reserve_gold); ate 10 trocas por checagem; nao achou -> escolhe a 1a da lista (libera em
  2h de caça e o bot tenta de novo). Ao escolher marca 'Liberar o espaço' no fim. NUNCA cartas/Drako Coins; preço
  desconhecido = nao paga. Espaco ativo nao e' trocado.
- Validado ao vivo: read_prey (2 ativos, Trocar lista gratis). prey_choose usa os mesmos seletores da escolha manual.
- Ainda NAO visto: preço da troca paga (texto do botao depois da gratis), confirmacao da troca.
- Espacos da Prey (usuario 17/10): free = 1, Premium = 2, +1 comprado na Drako Shop = 3 (4 = mais um). read_prey ignora
  `state-locked`, entao serve pra qualquer quantidade. Conta free ainda nao vista ao vivo (supondo espaco 2 `state-locked`).

## Tasks e Bestiary (17/10/2026, so leitura)
- Tasks: Cyclopedia > aba `.cyclopedia-tab` 'Tasks' (quick-access 'Tasks (tecla 3)'). So existem 'Tasks de Creature Products'
  (entregar ITENS), 51 no total (`drakoria_bot/data/tasks.json`: nome, criatura, local, level, item, quantidade, ouro/XP por
  unidade, TP). Ate 2 ativas. Itens pedidos ficam protegidos do Auto Sell ate a entrega; contam Loot Pouch, mochila, Supply
  Pouch e Banco. Cancelar libera a vaga e nao tira itens. Resumo: Task Points, Tasks ativas n/2, Prontas para entregar,
  Concluidas n/51. Linha `.tibia-task-row` (classes `claimed` = concluida '✓ Concluída', `locked` = 'Requer Lv N'
  disabled), botao `.tibia-button.small.green` 'Aceitar'. Botao de ENTREGAR ainda NAO visto (nenhuma ativa).
  'Cabelos de Troll' ja concluida pelo usuario. 17 tasks citam locais que NAO estao nas 68 caças (Nibelor, Nargor,
  Cyclopolis..., criaturas como Winter Wolf, Werefox) -> o bot so consegue fazer as 34 cuja criatura esta numa caça.
- Bestiary: Cyclopedia > 'Bestiário': 1.269 criaturas em 22 classes `.bestiary-class-tile` ('Humanoides 2 / 123'),
  busca 'Buscar criatura, classe ou local', toggle `.bestiary-tracker-option` (rastreador na caça). Criatura
  `.bestiary-creature` (`complete` / `unknown` = '?', sem nome). DESCONHECIDAS nao aparecem nem na busca.
  Conhecida: title 'Troll · 760 / 250 kills'; detalhe: Total Kills, meta, Charm Points (5), HP/XP, resistencias, loot,
  Localizacao (texto do Tibia, nao e' a caça do jogo). Meta de abates tambem no rastreador da caça ('X de N kills · faltam').
  Usuario ja completou Troll e Young Troll (6 conhecidas, 4 completas, 16 charm points).
- ACEITAR (17/10 01:50, Claude, pedido do usuario): 'Restos de Rotworm' -> 'Aceitar' sem confirmacao. Linha vira
  `.tibia-task-row.accepted` ('Ativa' + `.tibia-task-cancel` 'Cancelar', title 'Desistir desta Task. Os produtos continuam
  com você.'). Painel 'Tasks ativas': `.tibia-tasks-active > .tibia-task-active` (item · criatura, 'have / need',
  `.tibia-progress`, `.tibia-task-reward`, acoes `.tibia-task-active-actions`). Resumo 'Tasks ativas 1 / 2'.

## v1.2.0 - Objetivos: tasks e bestiary (17/10/2026)
- Aba Objetivos: 'Até N levels acima do recomendado' (goals.level_over, padrao 10) + listas de marcar: Tasks (so as 34
  com criatura numa caça; ✓ concluida, ▶ ativa) e Bestiary (204 criaturas das caças, com a caça mais facil; ✓ completa).
  A ordem da lista e' a fila. Prioridade da caça (goals.goal_hunt): task ativa nao pronta -> 1a criatura do bestiary nao
  completa -> caça da aba Regras. Caça escolhida = a mais facil com a criatura e recomendado <= level + level_over.
- A cada 10 min (sempre, tambem pra tasks aceitas na mao): read_tasks -> entrega as prontas -> aceita as proximas da fila
  (disponiveis e alcançaveis) ate 2 ativas. Progresso da ativa: linha 'have / need' (ex. '0 / 250').
- Bestiary: abates/meta vem do rastreador da caça (title 'X: a de N kills') -> memory.json 'bestiary'; completa -> proxima.
- deliver_task: clica o botao da task ativa que nao e' Cancelar (+ confirma se pedir). AINDA NAO VALIDADO ao vivo.
- Ao vivo 17/10 ~02:10: party lv 19 caçando; goal_hunt com a task de Rotworm ativa -> 'Rotworms'.

## v1.2.1 - ao vivo 17/10 ~20:05
- O rastreador da caça mostra as TASKS ativas (`.task-tracker`, 'TASKS 1/2 · Lump Of Dirt 0/250') quando ha task: some o
  rastreador de bestiary -> identify() falha. Caça atual por `button.cp-btn[title='Detalhes das criaturas']` ->
  `.creature-window.is-hunt` (titulo = nome da caça), lido 1x por caçada (Engine.hunt_known). Monstros sao so' canvas.
- VALIDADO: party em 'Ghoul e Skeleton' com task de Rotworm ativa -> bot leu a caça, trocou DIRETO da tela de caça pra
  Rotworms (Escolher Hunt funciona caçando). Prey so' e' escolhida quando ja esta na caça desejada (Engine._settled).
- Troca de lista PAGA: botao 'Trocar lista 3k gold' (title 'Trocar a lista: 3.000 gold (a troca grátis volta à
  meia-noite)') -> caixa `.drk-prey-ask` 'Trocar a lista do espaço 2 por 3.000 gold?' com Cancelar / `button.green`
  'Pagar 3.000 gold'. O bot so' paga se o preço <= o que decidiu; senao Cancela. parse_reroll: preço antes de 'grátis'.
- Slot que acabou: 'Escolha a nova criatura: o bônus guardado continua' (bonus fica pra proxima criatura).
- Janela comum esquecida aberta (detalhes) virava 'aviso' em loop: agora dismiss so' clica visivel e fecha o resto.

## v1.3.0 - dificuldade por objetivo + bestiary pela Cyclopedia (17/10/2026, usuario)
- Aba Objetivos: cada task/criatura MARCADA ganha seletor de dificuldade (Padrão = a da aba Regras; Fácil..Impossível).
  goals.difficulty {task ou criatura: dificuldade}. goal_hunt devolve (caça, motivo, chave). Caçando a caça certa em
  outra dificuldade (2 leituras) -> start_hunt de novo na mesma caça com a dificuldade do objetivo.
- Bestiary pela Cyclopedia (a cada goals.bestiary_minutes=30, com fila de bestiary): quick-access 'Cyclopedia' ->
  `.cyclopedia-tab` Bestiário -> cada `.bestiary-class-tile` com conhecidas > 0 -> titles `.bestiary-creature`
  'Rotworm · 421 / 500 kills' -> Voltar. Necessario porque com task ativa o rastreador da caça mostra so' as tasks.
  Validado ao vivo 17/10: 8 criaturas lidas (Rotworm 489/500, Ghoul 1050/500...).
- ENTREGA VALIDADA 17/10 ~20:30: task pronta = `.tibia-task-active.ready` (linha 'have / need · pronta para entregar')
  com `.tibia-button.small.green` 'Entregar' -> deliver_task: entrega na hora, SEM confirmacao; TP 10 -> 20, Concluidas
  2/51, linha vira 'done'. Leitura do progresso aceita o sufixo '· pronta para entregar'.

## Marketplace (20/10/2026, so leitura, pelo navegador do app logado)
- Menu `data-nav=market` -> janela 'Marketplace' (abas Market, Minhas Ofertas, Historico, Caixa do Mercado, Favoritos &
  Alertas). Dados por API REST JSON em `/api/v1/market/...` que EXIGE LOGIN (sem cookie: 401 AUTH_REQUIRED).
  Rotas vistas: overview (carteira, config: ofertas 10 dias, taxa de execucao 10%, 20 ofertas por conta, MANUAL_ACCEPTANCE),
  items?page=&limit=&sort=volume (1.443 itens: lowestSell, highestBuy, buyQuantity, sellQuantity, npcBuy/npcSell, categoria,
  level, vocacoes, tier), items/<id> (item + buyOffers + sellOffers + statistics {windowDays 30, trades, daily}), 
  drako-coins/orderbook (compra/venda de Drako Coin em ouro), watchlist, alerts, me/assets|orders|history|deliveries,
  events (stream continuo: nao usar fetch simples). Catalogo estatico: /System/Marketplace/data/market-tibia-catalog.json.
  Icones: /assets/items/<categoria>/<Nome>.gif. Hunt Analyzer tambem usa precos (hunt-analyzer-market-prices.js).
- Caminho sugerido: fetch DENTRO da aba logada via CDP (page.evaluate) - sem abrir janela nem clicar; guardar em SQLite e
  mostrar num painel local (modelo: matheusromano6/baiakidle/market: api/scanner/store/server/dashboard).

## Marketplace - compra sem clique VALIDADA (20/10/2026 ~22:17, autorizada pelo usuario: Rope Belt 1x, max 10 p/ testes)
- Itens de imbuement: categoria 'Imbuement Materials' (71 itens; so ~6 com oferta em 20/10, mercado novo).
- items/<id>.statistics: windowDays 30, trades {vwap, min, max, quantity, trades, volume}, sellOffers/buyOffers {average,
  min, max, offers}, daily [{day, vwap_price_gold, minimum/maximum_price_gold, quantity_traded, trades_count, gold_volume}].
  Ofertas: id, side SELL/BUY, unitPriceGold, remainingQuantity, status ACTIVE/PARTIAL, mine, version, expiresAt.
- Rotas de escrita (marketplace-ui.js): POST orders/{id}/accept {quantity, instanceId:null, expectedVersion: order.version,
  deviceId, clientBuild}; POST me/deliveries/{id}/claim {deviceId, clientBuild}; claim-all; orders (criar); orders/{id}/cancel;
  wallet/withdraw; watchlist; alerts. Header 'Idempotency-Key'. NAO chamar a URL crua: o jogo usa authoritativeMutation()
  = game.stop(); game.save(); client.flushRequired(); request; adoptServerSave(payload.save); game.replaceState(); start.
  Chamar a API por fora do save deixaria o save local sobrescrever a compra.
- Instancia viva: import('/System/Marketplace/marketplace-ui.js?build=...') -> MarketplaceUI.prototype (classe compartilhada);
  embrulhar os metodos do prototype guardando 'this' em window.__drkMarket; o jogo so' chama ao ABRIR o Marketplace
  (nav data-nav=market) -> abrir 1x por carga da pagina (~0,8s) e fechar. Depois: m.authoritativeMutation(path, body).
  m.client.deviceId / m.client.clientBuild ('v1.7.2030-online416'). Hook some ao recarregar a aba.
- Teste: 1 Rope Belt a 25.000 (oferta mais barata): ouro 58.181.857 -> 58.156.857; entrega 'PENDING' na Caixa do Mercado ->
  claim -> 'Entrega coletada no Banco' (assets mostra a rope belt). Jogo seguiu rodando, ouro do topo consistente.

## v1.4.0 - Market (20/10/2026)
- drakoria_bot/market/: api.py (fetch/hook/authoritativeMutation pela aba logada), analysis.py (puro), store.py (SQLite
  market.db: snapshot, daily, purchase, alert), watcher.py (a cada 5 min: categorias -> detalhe dos itens com oferta ou
  observados -> avalia -> historico -> alerta 1x por oferta/preço/qualidade -> compra se chave geral + regra do item).
- Preço justo = min(VWAP janela, VWAP recente = ultimo terço dos dias), do diario LIMPO (dias fora de 1/3..3x a mediana
  descartados). Qualidade: boa 15% / muito boa 25% / excelente 40% de desconto; tendencia <= -10% derruba 1 nivel.
- Compra: chave geral market.auto_buy (padrao OFF) + regra {watch, buy, max_price, quantity} por item (nome minusculo).
  Sem max_price usa 20% abaixo do justo; sem justo nao compra. Limites: quantidade total (compras do bot), orçamento
  diario, reserva de ouro, ofertas mais baratas primeiro; erro para o ciclo. Resgata a entrega pro Banco.
- Aba Market: tabela (Item, Menor, Justo, Desc., À venda, Qualidade; ★ observado, $ compra), regra do item selecionado,
  chave geral, orçamento/dia, reserva. Aviso: balao da bandeja + bipe.
- Dados reais 20/10: Rope Belt justo 25k (queda 43k->25k), Protective Charm justo ~39,4k (sem o negocio a 1 gold),
  Silencer Claws 20k, Peacock Feather Fan sem historico. Nenhuma oportunidade no momento.
- ATENCAO sessao unica: logar no navegador do app DESLOGOU a aba do IdleDeck (20/10). Usar so' o IdleDeck com o bot.
- 20/10: as 4 paginas do Huntera no IdleDeck nao respondiam ao CDP -> connect_over_cdp do Playwright travava (todos os
  bots). A pagina do Drakoria respondia. MarketApi (wrapper Python) ainda NAO rodou ao vivo no IdleDeck por isso; os
  scripts JS dele foram validados no navegador do app (hook em pagina recem-carregada: 0,9s; leitura; compra; resgate).
- v1.4.1 (20/10 19:40): Pool.open loga 'Conectando ao IdleDeck...' e desiste em 45s (CONNECT_TIMEOUT_MS) com mensagem
  clara. Antes o bot ficava mudo em 'Conectando...' com as abas do Huntera travadas. Usuario abriu a v1.4.0 de
  Downloads\DrakoriaBot-windows com a v1.3.0 de release\ ainda aberta (2 bots): fechar o antigo.
