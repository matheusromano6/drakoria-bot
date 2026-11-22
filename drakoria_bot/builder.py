"""Builder da caça (Escolher Hunt > card > Builder): aplica no Helper as magias e curas que o jogo sugere para cada
personagem. Só clica 'Aplicar no Helper' quando o botao esta habilitado (o jogo mostra 'O Helper já está com este
combo' quando ja esta igual)."""
import time

MEMBERS = ["MRKina", "MRPally", "MRSorc", "MRDruid"]
TABS = ["Magias", "Curas"]


def _pick_hunt(page, hunt):
    # JS direto no card: a grade se redesenha e o clique do Playwright fica bloqueado (igual account.start_hunt)
    page.evaluate("""(name) => { const t = [...document.querySelectorAll('.hw-root .hw-tile')].find(x =>
        (x.querySelector('strong')?.innerText || '').trim().toLowerCase() === name.toLowerCase());
        if (t) { t.scrollIntoView({block: 'center'}); t.querySelector('.hw-tile-main')?.click(); } }""", hunt)
    time.sleep(1.0)


def _open(page):
    page.locator(".hw-root .hw-detail [data-action=build-advisor-open]").first.click()
    time.sleep(1.2)


def _click_visible(locator):
    # o mesmo texto aparece em botoes escondidos (ex.: equipamento): clica no primeiro que esta visivel
    for i in range(locator.count()):
        item = locator.nth(i)
        if item.is_visible():
            item.click()
            return
    raise RuntimeError("nenhum botao visivel")


def apply_for_hunt(page, hunt, log=print):
    """Aplica o combo sugerido de magias e curas em cada personagem. Retorna {personagem: {aba: estado}}."""
    result = {}
    _pick_hunt(page, hunt)
    _open(page)
    for member in MEMBERS:
        result[member] = {}
        _click_visible(page.locator(".tibia-window-body button", has_text=member))
        time.sleep(0.8)
        for tab in TABS:
            _click_visible(page.locator("button", has_text=tab))
            time.sleep(0.8)
            btn = page.locator("button", has_text="Aplicar no Helper").first
            if btn.count() == 0:
                state = "sem botao"
            elif btn.is_enabled():
                btn.click()
                time.sleep(1.5)
                state = "aplicado"
            else:
                state = "ja estava"
            result[member][tab] = state
            log(f"{member} {tab}: {state}")
    return result
