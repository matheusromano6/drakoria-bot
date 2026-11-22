"""Builder da caça (Escolher Hunt > card > Builder): aplica no Helper as magias e curas que o jogo sugere para cada
personagem. Só clica 'Aplicar no Helper' quando o botao esta habilitado (o jogo mostra 'O Helper já está com este
combo' quando ja esta igual)."""
import time

from . import selectors as S

MEMBERS = ["MRKina", "MRPally", "MRSorc", "MRDruid"]
TABS = ["Magias", "Curas"]


def _pick_hunt(page, hunt, wait=6):
    # a busca da janela Escolher Hunt pode estar com outro nome (ex.: busca antiga 'Rotworm Cave'): digita o nome
    # da caça (mesmo evento 'input' que o digitar do usuario) e so' depois clica no card
    page.evaluate("""([sel, text]) => { const box = document.querySelector(sel); if (!box) return; box.focus(); box.value = text;
        box.dispatchEvent(new Event('input', {bubbles: true})); box.dispatchEvent(new Event('change', {bubbles: true})); }""",
                  [S.PICKER + " " + S.PICKER_SEARCH, hunt])
    end = time.time() + wait
    while True:
        # JS direto no card: a grade se redesenha e o clique do Playwright fica bloqueado (igual account.start_hunt)
        found = page.evaluate("""(name) => { const t = [...document.querySelectorAll('.hw-root .hw-tile')].find(x =>
            (x.querySelector('strong')?.innerText || '').trim().toLowerCase() === name.toLowerCase());
            if (!t) return false; t.scrollIntoView({block: 'center'}); t.querySelector('.hw-tile-main')?.click(); return true; }""", hunt)
        if found:
            break
        if time.time() > end:
            raise RuntimeError(f"caça '{hunt}' não aparece na lista do Builder")
        time.sleep(0.4)
    time.sleep(1.0)


def _open(page):
    _click_visible(page.locator(".hw-root .hw-detail [data-action=build-advisor-open]"), "abrir o Builder da caça")
    time.sleep(1.2)


def _click_visible(locator, what, wait=6):
    # o mesmo texto aparece em botoes escondidos (ex.: equipamento): clica no primeiro que esta visivel.
    # espera a janela se redesenhar (o detalhe da caça demora pra aparecer depois de selecionar)
    end = time.time() + wait
    while True:
        for i in range(locator.count()):
            item = locator.nth(i)
            if item.is_visible():
                item.click()
                return
        if time.time() > end:
            raise RuntimeError(f"{what}: nenhum botão visível")
        time.sleep(0.4)


def _visible_apply(page):
    btn = page.locator("button", has_text="Aplicar no Helper")
    visible = [btn.nth(i) for i in range(btn.count()) if btn.nth(i).is_visible()]
    return visible[0] if visible else None


def _apply_once(page):
    """'Aplicar no Helper' habilitado = o combo ainda nao e' o melhor: clica e CONFERE que ficou desabilitado
    (desabilitado de cara = ja esta o melhor). Tenta de novo 1x se o jogo nao aceitou."""
    for attempt in range(2):
        btn = _visible_apply(page)
        if btn is None:
            return "sem botao"
        if not btn.is_enabled():
            return "ja estava" if attempt == 0 else "aplicado"
        btn.click()
        time.sleep(1.5)
    btn = _visible_apply(page)
    return "nao aplicou" if btn is not None and btn.is_enabled() else "aplicado"


def apply_for_hunt(page, hunt, log=print):
    """Aplica o combo sugerido de magias e curas em cada personagem. Retorna {personagem: {aba: estado}}."""
    result = {}
    _pick_hunt(page, hunt)
    _open(page)
    for member in MEMBERS:
        result[member] = {}
        # os botoes dos personagens da janela Builder sao 'tibia-button small' (o do equipamento da tela e' outro)
        _click_visible(page.locator("button.tibia-button", has_text=member), f"personagem {member}")
        time.sleep(0.8)
        for tab in TABS:
            _click_visible(page.locator("button", has_text=tab), f"aba {tab} de {member}")
            time.sleep(0.8)
            state = _apply_once(page)
            result[member][tab] = state
            log(f"{member} {tab}: {state}")
    return result
