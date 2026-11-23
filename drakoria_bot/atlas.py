"""Atlas Celestial: monta a build combinada (12/11/2026) nos personagens da conta, pelo motor do jogo (sem janela).

Mesma logica do tools/atlas_build.py: a build vai pela VOCACAO e usa os pontos LIVRES de cada personagem, na ordem de
PRIORITY, respeitando o ouro (reserva). plan(page, apply=False) so simula; apply=True grava no Atlas.
"""
import json

# Caminhos pelo NOME do losango (o jogo muda as posicoes por vocacao: no Knight a Ressonancia de Soul fica no setor
# 'party', nas outras em 'assalto:1'). O script acha o caminho de cada nome no Atlas do personagem.
# L1 = XP da party (todos), L2 = dano da wave (so existe no Knight). A = principal, B e C = secundarios.
LEGADO = {"L1": ["Ressonância de Soul", "Legado · XP da party (Ressonância de Soul → Legado de Drakoria)"],
          "L2": ["Varredura", "Legado · Dano da wave (Varredura → Matilha)"]}
BUILD = {
    "knight": {"A": ["Sangue de Titã", "Vigor (+vida → Imortal)"],
               "B": ["Mestre do Escudo", "Muralha (shielding → Rocha)"],
               "C": ["Pele de Pedra", "Couraça (proteção → Bastião de Drakoria)"],
               # 14/11: o Atlas do Knight perdeu a Ressonancia/Varredura; no lugar, dano de magia (as waves morrem nas magias)
               "D": ["Magias Pesadas", "Guerra (dano de magia → Senhor da Guerra)"]},
    "paladin": {"A": ["Primeira Flecha", "Arqueiro (dano Physical → Avatar do Arqueiro)"],
                "B": ["Mira Firme", "Cadência (velocidade do ataque → Chuva de Projéteis)"],
                "C": ["Força do Caçador", "Força (dano → Último Suspiro)"]},
    "sorcerer": {"A": ["Ignição", "Chamas (dano Fire → Avatar das Chamas)"],
                 "B": ["Ruptura Arcana", "Convergência (crítico Fire → Apoteose)"],
                 "C": ["Potência Arcana", "Poder (dano → Fênix)"]},
    "druid": {"A": ["Prece Viva", "Cura (+cura → Grande Restauração)"],
              "B": ["Reserva Espiritual", "Fluxo (menos mana → Fonte Eterna)"],
              "C": ["Fúria Ancestral", "Ciclo (recarga das ultimates → Renascer)"]},
}
# Prioridade (igual para todas): cada caminho tem a 1a metade (ate o losango) e a 2a (ate o no final). Caminho que nao
# existe na vocacao (L2 fora do Knight) e' pulado.
PRIORITY = [("A", 1), ("L1", 1), ("L2", 1), ("D", 1), ("A", 2), ("B", 1), ("B", 2), ("L1", 2), ("L2", 2), ("D", 2),
            ("C", 1), ("C", 2)]

PLAN_JS = r"""([build, legado, priority, apply, reserve]) => {
  const g = window.__drkMarket.game;
  // Pontos gratis (do Redistribuir/migracao) nao custam gold; cada ponto pago custa 1M. O ouro e' um so para a conta:
  // e' usado por inteiro pelo primeiro que precisar; o que sobra passa para o proximo, sem sobrar metade a cada rodada.
  let wallet = Math.max(0, Number(g.char.gold || 0) - reserve);
  const members = g.partyMembers();
  return members.map((m, index) => {
    // o gold sobrando passa todo para o proximo: antes cada um recebia metade do que restava e a cada rodada
    // sobrava metade, por isso precisava executar varias vezes
    const share = wallet;
    const def = g.soulTreeDefinition(m);
    const voc = String(def.vocation || m.vocationName || '').toLowerCase().replace(/^(elite|royal|master|elder)\s+/, '');
    const b = build[voc];
    const sum = g.soulTreeSummary(m);
    const out = {name: m.name, vocation: voc, available: sum.available, spent: sum.spent, done: []};
    if (!b) { out.skip = 'vocacao sem build'; return out; }
    const norm = t => String(t || '').normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase().trim();
    const node = id => def.nodes.find(n => n.id === id);
    // nome do losango -> [setor, caminho, 'a'|'b', rotulo]
    const lanes = {}; const missing = [];
    for (const [key, [name, label]] of Object.entries(Object.assign({}, legado, b))) {
      const n = def.nodes.find(x => /:5[ab]$/.test(x.id) && norm(x.name) === norm(name));
      if (n) { const [s, l, r] = n.id.split(':'); lanes[key] = [s, Number(l), r.slice(1), label]; }
      else if (key === 'A') missing.push(name);  // so o principal e' obrigatorio; o resto a vocacao pode nao ter
    }
    if (missing.length) { out.skip = 'nao achei no Atlas: ' + missing.join(', '); return out; }
    const current = Object.assign({}, (g.soulTreeState ? g.soulTreeState(m).nodes : m.soulTree.nodes) || {});
    const dr = Object.assign({}, current);
    const free = Math.min(sum.available, Number(sum.freePoints || 0));
    let left = Math.min(sum.available, free + Math.floor(share / 1e6));
    const budget = left;
    out.free = free;
    // sobe `id` ate `target`, nivel por nivel, enquanto houver ponto; devolve se chegou
    const raise = (id, target) => {
      const n = node(id); if (!n) return false;
      while ((dr[id] || 0) < target) { if (left < n.cost) return false; dr[id] = (dr[id] || 0) + 1; left -= n.cost; added.push(id); }
      return true;
    };
    const added = [];  // ordem em que os niveis entraram (para desfazer do fim se o jogo disser que nao cabe)
    let stopped = false;
    for (const [key, half] of priority) {
      if (stopped) break;
      if (!lanes[key]) continue;
      const [s, l, c, label] = lanes[key];
      const p = s + ':' + l + ':';
      dr[s + ':portal'] = 1;
      const steps = half === 1 ? [[p+'2',5],[p+'3',5],[p+'4',5],[p+'5'+c,1]] : [[p+'6',5],[p+'7',5],[p+'8',1]];
      for (const [id, target] of steps) { if (!raise(id, target)) { stopped = true; break; } }
      out.done.push(label + (half === 1 ? ' — até o losango' : ' — até o final') + (stopped ? ' (parcial)' : ''));
    }
    // sobra: pequenos do caminho principal ate o nivel 10
    // (A, depois XP da party, B, L2 e C), para nao deixar ponto parado
    for (const key of ['A', 'L1', 'D', 'B', 'L2', 'C']) {
      if (!lanes[key]) continue;
      const [ms, ml] = lanes[key];
      for (const ring of ['2', '3', '6', '7', '7s1', '7s2']) {
        const id = ms + ':' + ml + ':' + ring;
        const n = node(id);
        if (!n || n.maxRank < 10) continue;
        if ((dr[id] || 0) >= 5 || ring.startsWith('7s') && (dr[ms + ':' + ml + ':7'] || 0) >= 5) raise(id, n.maxRank);
      }
    }
    const changed = Object.keys(dr).some(id => (dr[id] || 0) !== (current[id] || 0));
    if (!changed) {
      out.skip = budget < sum.available ? 'sem gold para os pontos pagos (só tem ' + free + ' grátis)' : 'sem pontos livres para o próximo passo';
      return out;
    }
    // o jogo cobra coisas que a conta acima nao ve (portais/pontes): tira os ultimos niveis ate o plano caber
    let pv = g.previewSoulTreePlan(m.id, dr);
    while (!pv.canApply && added.length && (pv.affordableSoul === false || pv.affordableGold === false)) {
      const id = added.pop();
      dr[id] -= 1; if (!dr[id]) delete dr[id];
      pv = g.previewSoulTreePlan(m.id, dr);
    }
    const why = pv.msg || (pv.affordableGold === false ? 'gold insuficiente' : pv.affordableSoul === false ? 'pontos insuficientes' : '');
    Object.assign(out, {ok: pv.canApply, msg: why, soul: pv.totalSoul, gold: pv.totalGold, left: pv.availableSoulAfter,
                        limited: budget < sum.available});
    if (pv.canApply) wallet -= Number(pv.totalGold || 0);
    if (apply && pv.canApply) {
      const r = g.applySoulTreePlan(m.id, dr);
      out.applied = !!r.ok;
      out.applyMsg = r.msg || '';
    }
    return out;
  });
}"""



def run(page, reserve_gold, apply=False):
    """Simula (apply=False) ou aplica o Atlas de todos os personagens da conta. Devolve as linhas por personagem.
    Precisa do motor do jogo capturado (window.__drkMarket.game): quem chama faz o hook antes."""
    return page.evaluate(PLAN_JS, [BUILD, LEGADO, PRIORITY, bool(apply), int(reserve_gold)])


def summary(rows):
    """Texto curto por personagem (pra log)."""
    out = []
    for r in rows:
        if r.get("skip"):
            out.append(f"{r['name']}: pulado ({r['skip']})")
        elif r.get("applied") is not None:
            out.append(f"{r['name']}: {'APLICADO' if r['applied'] else 'FALHOU ' + (r.get('applyMsg') or '')}")
        else:
            out.append(f"{r['name']}: " + ("pronto para aplicar" if r.get("ok") else "nao da: " + (r.get("msg") or "")))
    return out
