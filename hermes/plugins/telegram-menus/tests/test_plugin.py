"""Tests du plugin telegram-menus avec de faux objets PTB (aucun reseau)."""
import asyncio
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

RACINE = Path(__file__).resolve().parent.parent


def _charger():
    nom = "telegram_vj_essai"
    if nom in sys.modules:
        return sys.modules[nom]
    spec = importlib.util.spec_from_file_location(
        nom, RACINE / "__init__.py", submodule_search_locations=[str(RACINE)])
    mod = importlib.util.module_from_spec(spec)
    sys.modules[nom] = mod
    spec.loader.exec_module(mod)
    return mod


plugin = _charger()
h = sys.modules["telegram_vj_essai.handlers"]
ts = sys.modules["telegram_vj_essai.supp"]


def run(coro):
    return asyncio.run(coro)


class FauxApp:
    def __init__(self):
        self.handlers = []

    def add_handler(self, handler, group=0):
        self.handlers.append((group, handler))


class FauxQuery:
    def __init__(self, data, uid=1):
        self.data = data
        self.from_user = SimpleNamespace(id=uid, full_name="USER", first_name="USER")
        self.message = SimpleNamespace(text="x")
        self.reponses = []
        self.editions = []
        self.marqueurs = []

    async def answer(self, text=None, **kw):
        self.reponses.append(text)

    async def edit_message_text(self, text=None, reply_markup=None, **kw):
        self.editions.append((text, reply_markup))

    async def edit_message_reply_markup(self, reply_markup=None, **kw):
        self.marqueurs.append(reply_markup)


class FauxAdapter:
    name = "telegram"

    def __init__(self, autorise=True):
        self.autorise = autorise
        self.events = []

    @staticmethod
    def _callback_ctx(query):
        return None

    async def _callback_authorized(self, query, cb, refus):
        if not self.autorise:
            await query.answer(text=refus)
        return self.autorise

    def _build_message_event(self, msg, type_):
        return SimpleNamespace(text="", user_id="bot", user_name="bot", message_type=type_,
                               source=SimpleNamespace(user_id="bot", user_name="bot"))

    async def handle_message(self, event):
        self.events.append(event)

    def _effective_update_message(self, update):
        return update.message

    def _should_process_message(self, msg, is_command=False):
        return True

    def _is_user_authorized_from_message(self, msg):
        return self.autorise

    def _log_blocked_user(self, msg):
        self.bloque = True


def _enregistre(adapter):
    app = FauxApp()
    plugin._fabrique(app, adapter)
    return app


def _bouton(app):
    return next(hd for g, hd in app.handlers if hasattr(hd, "pattern"))


def test_handlers_groupe_et_pattern():
    app = _enregistre(FauxAdapter())
    assert len(app.handlers) == 2
    assert all(g == -1 for g, _ in app.handlers)
    cb = _bouton(app)
    for ok in ("menu:root", "supp:x"):
        assert cb.pattern.match(ok)
    for ko in ("me:1", "meg:1", "model:x", "ea:1"):
        assert not cb.pattern.match(ko)


def test_menu_root_dispatch_et_stop():
    from telegram.ext import ApplicationHandlerStop
    ad = FauxAdapter()
    cb = _bouton(_enregistre(ad)).callback
    q = FauxQuery("menu:root")
    with pytest.raises(ApplicationHandlerStop):
        run(cb(SimpleNamespace(callback_query=q), None))
    assert q.editions and q.reponses == [None]


def test_callback_hors_famille_laisse_passer():
    ad = FauxAdapter()
    cb = _bouton(_enregistre(ad)).callback
    q = FauxQuery("zzz:1")
    run(cb(SimpleNamespace(callback_query=q), None))
    assert q.editions == [] and q.reponses == []


def test_garde_refuse_les_deux_familles():
    ad = FauxAdapter(autorise=False)
    for data, refus in (("menu:root", "Pas pour toi."), ("supp:s:0", "Non autorise.")):
        q = FauxQuery(data)
        fonction = {"menu": h.bouton_menu, "supp": h.bouton_supp}[data.split(":")[0]]
        run(fonction(ad, q, data))
        assert q.reponses == [refus] and q.editions == []


def test_garde_echoue_ferme_sans_methodes():
    q = FauxQuery("menu:root")
    run(h.bouton_menu(SimpleNamespace(name="t"), q, "menu:root"))
    assert q.reponses == ["Pas pour toi."] and q.editions == []


def test_supp_confirmation_et_annulation(monkeypatch):
    ts.memoriser([{"id": "abc", "titre": "Ma session"}])
    ad = FauxAdapter()
    q = FauxQuery("supp:s:0")
    run(h.bouton_supp(ad, q, "supp:s:0"))
    assert "Supprimer cette session ?" in q.editions[0][0]
    q = FauxQuery("supp:x")
    run(h.bouton_supp(ad, q, "supp:x"))
    assert q.editions[0][0] == "Annule."
    q = FauxQuery("supp:s:9")
    run(h.bouton_supp(ad, q, "supp:s:9"))
    assert q.reponses == ["Liste perimee. Refais /supp."]


def test_supp_suppression(monkeypatch):
    ts.memoriser([{"id": "abc", "titre": "Ma session"}])
    appels = []
    monkeypatch.setattr(ts, "_supprimer", lambda i: appels.append(i) or {"ok": True})
    q = FauxQuery("supp:del:0")
    run(h.bouton_supp(FauxAdapter(), q, "supp:del:0"))
    assert appels == ["abc"]
    assert "Session supprimee" in q.editions[0][0]
    assert ts.cible(0) is None


def test_effort_passe_par_handle_message():
    ad = FauxAdapter()
    q = FauxQuery("menu:e:1")
    run(h.bouton_menu(ad, q, "menu:e:1"))
    ev = ad.events[0]
    assert ev.text.startswith("/reasoning ") and "--global" not in ev.text
    assert ev.user_id == "1" and ev.source.user_id == "1"
    assert q.marqueurs, "clavier redessine avec la coche"
    q = FauxQuery("menu:eg:1")
    run(h.bouton_menu(ad, q, "menu:eg:1"))
    assert ad.events[1].text.endswith("--global")


def test_commande_menu_depuis_categorie():
    ad = FauxAdapter()
    cmd, _d = h.tm.categories()[0][1][0]
    q = FauxQuery("menu:x:0:0")
    run(h.bouton_menu(ad, q, "menu:x:0:0"))
    assert ad.events[0].text == f"/{cmd}"


def test_commande_garde_refuse():
    from telegram.ext import ApplicationHandlerStop  # noqa: F401
    ad = FauxAdapter(autorise=False)
    app = _enregistre(ad)
    cmd = next(hd for g, hd in app.handlers if not hasattr(hd, "pattern"))
    msg = SimpleNamespace(text="/menu")
    envoyes = []

    async def reply(*a, **k):
        envoyes.append(a)
    msg.reply_text = reply
    run(cmd.callback(SimpleNamespace(message=msg), None))
    assert envoyes == [] and getattr(ad, "bloque", False)


def test_commande_menu_envoie_et_stop():
    from telegram.ext import ApplicationHandlerStop
    ad = FauxAdapter()
    cmd = next(hd for g, hd in _enregistre(ad).handlers if not hasattr(hd, "pattern"))
    envoyes = []

    async def reply(texte, reply_markup=None):
        envoyes.append((texte, reply_markup))
    msg = SimpleNamespace(text="/menu@mon_bot", reply_text=reply)
    with pytest.raises(ApplicationHandlerStop):
        run(cmd.callback(SimpleNamespace(message=msg), None))
    assert envoyes and envoyes[0][1] is not None


def test_register_enregistre_les_commandes():
    appels = []
    ctx = SimpleNamespace(
        register_telegram_handler=lambda f: appels.append(("tg", f)),
        register_command=lambda nom, fn, **k: appels.append((nom, fn)))
    plugin.register(ctx)
    assert [a[0] for a in appels] == ["tg", "menu", "supp"]
    assert "Commandes par categorie" in plugin._texte_menu("")


def test_banc_liste_et_erreur():
    ad = FauxAdapter()
    q = FauxQuery("menu:b:mod")
    run(h.bouton_menu(ad, q, "menu:b:mod"))
    assert q.editions[0][0] == "Modifier quelle question ?"
    q = FauxQuery("menu:b:d:zz")
    run(h.bouton_menu(ad, q, "menu:b:d:zz"))
    assert q.reponses == ["Element introuvable."]


def _fausse_config(monkeypatch, priorite, mode):
    """Remet le module du coeur dans un etat neuf avec une config choisie."""
    from hermes_cli import commands_platforms as cp
    monkeypatch.setattr(cp, "_telegram_command_menu_config", lambda: {
        "max_commands": 20, "priority_mode": mode, "priority": list(priorite)})
    return cp


@pytest.mark.parametrize("mode", ["replace", "prepend"])
def test_tete_de_liste_ordre_et_doublons(monkeypatch, mode):
    cp = _fausse_config(monkeypatch, ["personality", "new"], mode)
    assert plugin._tete_de_liste() is True
    assert plugin._tete_de_liste() is True  # idempotent : pas d'empilement
    cfg = cp._telegram_command_menu_config()
    assert cfg["priority"] == ["menu", "supp", "personality", "new"]
    assert cfg["priority_mode"] == mode


def test_tete_de_liste_dans_le_vrai_menu(monkeypatch):
    cp = _fausse_config(monkeypatch, ["personality", "new"], "replace")
    monkeypatch.setattr("hermes_cli.plugins.get_plugin_commands", lambda: {
        n: {"description": n, "args_hint": ""} for n in ("menu", "supp", "zzz")})
    plugin._tete_de_liste()
    ordre = [c for c, _d in cp.telegram_menu_commands(max_commands=100)[0]]
    assert ordre[:2] == ["menu", "supp"]
