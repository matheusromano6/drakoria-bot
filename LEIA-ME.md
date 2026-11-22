# Drakoria Bot

Bot do **Drakoria Idle** que roda dentro do **IdleDeck**. Uma conta controla a party inteira (4 personagens).

## Como usar
1. Extraia `DrakoriaBot.exe` numa pasta própria (ele grava `config.json`, `memory.json`, `credentials.json` e `logs/` ao lado).
2. Abra o IdleDeck com o Drakoria logado (se ele não estiver com a depuração remota, o bot pede pra reabrir).
3. Abra o `DrakoriaBot.exe` e clique em **Iniciar**.

## Abas
- **Painel**: estado (caçando, cidade, house...), os 4 membros, XP/h e lucro/h e, por conta: ouro, Loot Pouch, alvo,
  Auto Sell e as duas preys ativas. Os últimos eventos aparecem embaixo.
- **Auto Boss**: todo dia às 00:01 o bot inicia a fila de bosses (Menu > Aventura > Bosses) e acompanha o último
  da fila; quando ele termina, as contas voltam à caça ou ao treino sozinhas.
- **Regras**: modo (caçar sempre / só vigiar), caça (automática = "Melhor escolha" do jogo, ou uma fixa), dificuldade,
  Auto Sell (automático = liga se for Premium) e com quantos itens vender quando não houver Auto Sell.
  "Proteger drops de boss" fica sempre ligado.
- **Market**: compras e vendas automáticas (com limites), e a aba Imbuements: escolha personagem, equipamento,
  imbuement, nível e como conseguir os materiais (automático, só caçar ou só comprar). O bot aplica, reaplica quando
  acaba e junta os materiais antes. Os materiais escolhidos nunca são vendidos.
- **Login**: usuário e senha para o relogin automático. A senha fica criptografada pelo Windows e só abre neste PC.

Os eventos completos ficam em `logs/` ao lado do exe (um arquivo por dia).

O botão **Atualizar** baixa a versão nova do GitHub e reinicia o bot.
