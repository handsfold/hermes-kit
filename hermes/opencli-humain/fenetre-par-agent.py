#!/usr/bin/env python3
"""Une fenetre Chrome par session opencli, ouverte en arriere-plan.

Sans ce correctif, toutes les sessions `opencli browser <s>` partagent UNE
fenetre : chaque agent a un onglet, un seul est visible, et chaque commande
remet la fenetre au premier plan. Les agents se volent l'onglet actif, les
captures ratent, le focus de USER saute.

Le correctif touche l'extension (~/.opencli/extension/dist/background.js) :
- le role de fenetre devient "interactive:<session>" (un conteneur par session) ;
- aucun groupe d'onglets (v3) : la fenetre suffit a isoler la session, et
  USER ne veut plus de groupes. Les fenetres des sessions sont notees dans
  chrome.storage.local pour survivre a un redemarrage du service worker ;
- mode par defaut "background" (--window foreground reste possible) ;
- v3.12 : fenetre d'agent sans commande depuis 15 min fermee, page ou pas ;
- v3.13 : fenetre d'agent (et popup de ses pages) notee des sa naissance, plus
  d'orpheline ; GET 127.0.0.1:19826/adopter peut confier des fenetres au balai ;
  idem pour une fenetre faite seulement de message.alibaba.com ou 1688.com ;
  fenetres d'agent memorisees en storage.local (survivent au rechargement) ;
- v3.9 : tout focus d'agent pendant une commande passe par /vol (le compositeur decide) ;
- v3.7 : fenetres d'agent visibles (jamais reduites a la creation), focus rendu
  par l'extension GNOME opencli-discret@poste, rechargement auto si ce fichier change ;
- v3.5 : garde-fou onFocusChanged (reduit la fenetre d'agent qui prend le focus) ;
- v3.4 : fenetre d'arriere-plan creee reduite (state minimized), et toute
  fenetre OpenCLI videe se ferme au lieu de rester en about:blank.

Idempotent. `--retirer` restaure l'original. Recharger l'extension ensuite.
"""
import pathlib
import shutil
import sys

CIBLE = pathlib.Path.home() / ".opencli/extension/dist/background.js"
SAUVEGARDE = CIBLE.with_suffix(".js.orig")
MARQUE = "/* opencli-humain: fenetre-par-agent v3.13 */"
ANCIENNES = ["/* opencli-humain: fenetre-par-agent v3.12 */", "/* opencli-humain: fenetre-par-agent v3.11 */", "/* opencli-humain: fenetre-par-agent v3.10 */", "/* opencli-humain: fenetre-par-agent v3.9 */", "/* opencli-humain: fenetre-par-agent v3.8.1 */", "/* opencli-humain: fenetre-par-agent v3.8 */", "/* opencli-humain: fenetre-par-agent v3.7 */", "/* opencli-humain: fenetre-par-agent v3.6.5 */", "/* opencli-humain: fenetre-par-agent v3.6.4 */", "/* opencli-humain: fenetre-par-agent v3.6.3 */", "/* opencli-humain: fenetre-par-agent v3.6.2 */", "/* opencli-humain: fenetre-par-agent v3.6.1 */", "/* opencli-humain: fenetre-par-agent v3.6.4 */", "/* opencli-humain: fenetre-par-agent v3.6.3 */", "/* opencli-humain: fenetre-par-agent v3.6.2 */", "/* opencli-humain: fenetre-par-agent v3.6.1 */", "/* opencli-humain: fenetre-par-agent v3.6 */", "/* opencli-humain: fenetre-par-agent v3.5 */", "/* opencli-humain: fenetre-par-agent v3.4 */", "/* opencli-humain: fenetre-par-agent v3.3 */", "/* opencli-humain: fenetre-par-agent v3.2 */", "/* opencli-humain: fenetre-par-agent v3.1 */", "/* opencli-humain: fenetre-par-agent v3 */", "/* opencli-humain: fenetre-par-agent */", "/* opencli-humain: fenetre-par-agent v2 */"]

AIDES = MARQUE + r'''
// Fenetre de chaque session, gardee hors du service worker : sans groupe
// d'onglets, c'est le seul moyen de la retrouver apres son redemarrage.
const __fenetresRoles = {};
// v3.12 : storage.local et non plus session, vide a chaque rechargement de
// l'extension (les fenetres d'agent devenaient inconnues, donc jamais nettoyees).
// Efface au demarrage de Chrome, ou les ids de fenetre repartent de 1.
const __fenetresPretes = chrome.storage.local.get("__opencliFenetres")
  .then(r => { if (!__chromeVientDeDemarrer) Object.assign(__fenetresRoles, r.__opencliFenetres || {}); }).catch(() => {});
// Fenetres ouvertes depuis le demarrage du service worker : jamais nettoyees
// (un agent vient de la creer, elle est encore sur about:blank).
const __fenetresNeuves = new Set();
function __noterFenetre(role, id) {
  if (id != null) __fenetresNeuves.add(id);
  if (id == null) delete __fenetresRoles[role]; else __fenetresRoles[role] = id;
  chrome.storage.local.set({ __opencliFenetres: __fenetresRoles }).catch(() => {});
}
function __conteneursParSession(base) {
  return new Proxy(base, {
    get(t, p) {
      if (typeof p === "string" && p.startsWith("interactive:") && !(p in t))
        t[p] = { windowId: __fenetresRoles[p] ?? null, groupId: null, promise: null, groupPromise: null };
      return t[p];
    }
  });
}
function __titresParSession(base) {
  return new Proxy(base, {
    get(t, p) {
      if (typeof p === "string" && p.startsWith("interactive:")) return "OpenCLI · " + p.slice(12);
      return t[p];
    }
  });
}
// Au demarrage : les fenetres OpenCLI restees vides sont fermees, les autres
// sortent de leur groupe d'onglets (heritage des versions 1 et 2).
async function __nettoyerFenetresVides() {
  await __fenetresPretes;
  const groupes = (await chrome.tabGroups.query({}).catch(() => [])).filter(g => (g.title || "").startsWith("OpenCLI"));
  const fenetres = new Set([...groupes.map(g => g.windowId), ...Object.values(__fenetresRoles)]);
  for (const w of fenetres) {
    if (__fenetresNeuves.has(w)) continue;
    if ([...automationSessions.values()].some(s => s.windowId === w)) continue;
    const onglets = await chrome.tabs.query({ windowId: w }).catch(() => []);
    if (onglets.length && onglets.every(o => !o.url || o.url === "about:blank" || o.url.startsWith("chrome://newtab"))) {
      await chrome.windows.remove(w).catch(() => {});
      for (const [role, id] of Object.entries(__fenetresRoles)) if (id === w) __noterFenetre(role, null);
      console.log(`[opencli] fenetre vide fermee ${w}`);
    }
  }
  for (const g of groupes) {
    const onglets = await chrome.tabs.query({ groupId: g.id }).catch(() => []);
    if (onglets.length) await chrome.tabs.ungroup(onglets.map(o => o.id)).catch(() => {});
  }
}
setTimeout(() => { __nettoyerFenetresVides(); }, 5000);
// v3.3 : sous X11, chrome.tabs.create({ active: true }) active la fenetre qui
// recoit l'onglet (Chrome appelle Show, qui l'active si elle est deja visible).
// La fenetre d'automatisation passait devant USER a chaque commande d'adaptateur.
// On cree l'onglet inactif, puis on le rend actif dans sa fenetre seulement.
async function __ongletDiscret(proprietes) {
  const onglet = await chrome.tabs.create({ ...proprietes, active: false });
  if (!proprietes.active || onglet.id == null) return onglet;
  return chrome.tabs.update(onglet.id, { active: true }).catch(() => onglet);
}
// v3.7 (2026-10-07) : les fenetres d'agent restent visibles, derriere celle de USER.
// Reduites (v3.4, v3.5), elles disparaissaient : sans barre des taches sous
// GNOME, USER ne les voyait plus. Mais sous Wayland, Mutter donne le focus a toute
// nouvelle fenetre, et Chrome ne sait pas le rendre (mesure : le clavier restait
// dans la fenetre d'agent). Seul le compositeur le peut : l'extension GNOME
// opencli-discret@poste ecoute 127.0.0.1:19826/vol et reactive la fenetre de USER.
// Repli si elle ne repond pas « pris » : la fenetre d'agent est reduite.
// Exemptees : sessions --window foreground, focus hors commande (USER clique lui-meme).
let __finDerniereCommande = 0;
const __fenetresAvant = new Set();
const __fenetresPopups = new Set();
// v3.8 : chrome.storage.session est vide apres un rechargement de l'extension,
// donc __fenetresRoles aussi. Les baux, eux, sont restaures : on les consulte.
const __estAgent = (id) => Object.values(__fenetresRoles).includes(id) || __fenetresPopups.has(id)
  || [...automationSessions.values()].some(s => s.owned && s.windowId === id)
  || (__neesParAgent.has(id) && __justeNee(id));
const __commandeEnCours = () => activeCommandCounts.size > 0 || Date.now() - __finDerniereCommande < 2500;
const __signal = (q) => fetch("http://127.0.0.1:19826/" + q + "&t=" + Date.now()).catch(() => {});
// v3.8 : seul le focus pris a la naissance d'une fenetre est un vol. En v3.7,
// tout focus pendant une commande l'etait : le clic de USER sur une fenetre
// d'agent au travail la faisait reduire aussitot, impossible de la regarder.
const __neeA = new Map();
// v3.10 : une fenetre d'agent prend le focus 11 ms apres sa naissance, avant
// que son bail la connaisse. __estAgent la ratait, la garde ne demandait rien
// au compositeur et la page restait devant USER (mesure du 2026-10-13 : 1
// ouverture sur 2). Toute fenetre nee dans les 3 s d'un chrome.windows.create
// de l'extension compte donc comme agent. Un Ctrl+N de USER ne passe pas par la.
let __creeA = 0;
let __renduA = 0;
const __neesParAgent = new Set();
const __creerOrig = chrome.windows.create.bind(chrome.windows);
try { chrome.windows.create = (...a) => { __creeA = Date.now(); return __creerOrig(...a); }; } catch (e) {}
chrome.windows.onCreated.addListener((w) => {
  __neeA.set(w.id, Date.now());
  if (Date.now() - __creeA < 3000) { __neesParAgent.add(w.id); __adopter(w.id); }
});
chrome.windows.onRemoved.addListener((id) => { __neesParAgent.delete(id); });
const __justeNee = (id) => Date.now() - (__neeA.get(id) ?? 0) < 4000;
// v3.9 : mesure. Chaque focus pris par une fenetre d'agent est signale (pas
// seulement a la naissance), avec l'action de la commande qui le precede.
const __actions = new Map();
const __actionDe = (id) => {
  for (const [k, s] of automationSessions.entries()) {
    if (s.windowId === id) { const a = __actions.get(k); return a ? k + ":" + a.a + "@" + (Date.now() - a.t) : "aucune"; }
  }
  // Fenetre en naissance : pas encore rattachee a son bail, on prend la commande la plus recente.
  let dernier = null;
  for (const [k, a] of __actions.entries()) if (!dernier || a.t > dernier.a.t) dernier = { k, a };
  return dernier ? "~" + dernier.k + ":" + dernier.a.a + "@" + (Date.now() - dernier.a.t) : "?";
};
chrome.windows.onFocusChanged.addListener((id) => {
  if (id == null || id === chrome.windows.WINDOW_ID_NONE || !__estAgent(id)) return;
  __signal("mesure?w=" + id + "&cmd=" + (__commandeEnCours() ? 1 : 0) + "&nee=" + (Date.now() - (__neeA.get(id) ?? 0)) + "&a=" + encodeURIComponent(__actionDe(id)));
});
// v3.9 : tout focus pris par une fenetre d'agent pendant une commande est soumis
// au compositeur (/vol), qui connait la derniere entree de USER. Reponse « pris » :
// il a rendu la main a la fenetre precedente. Reponse « poste » : USER vient de cliquer
// sur cette fenetre, on n'y touche pas. Sans extension GNOME (pas de reponse),
// repli v3.8 : seule une fenetre nee depuis moins de 4 s est reduite.
chrome.windows.onFocusChanged.addListener(async (id) => {
  if (id == null || id === chrome.windows.WINDOW_ID_NONE) return;
  if (!__estAgent(id) || __fenetresAvant.has(id) || !__commandeEnCours()) return;
  const nee = __justeNee(id);
  // v3.11 : quand le compositeur rend la main (« pris »), il reactive la fenetre
  // precedente. Si c'est une autre fenetre d'agent, elle prenait le focus a son
  // tour, redemandait /vol, et les deux se renvoyaient le premier plan environ
  // 300 fois par seconde tant qu'une commande tournait (mesure du 2026-10-13).
  // Un focus qui suit un « pris » de moins d'1 s vient de nous : on n'y touche pas.
  if (!nee && Date.now() - __renduA < 1000) return;
  const reponse = await fetch("http://127.0.0.1:19826/vol?w=" + id + "&nee=" + (nee ? 1 : 0) + "&t=" + Date.now())
    .then(r => r.ok ? r.text() : "").catch(() => "");
  if (reponse === "pris") __renduA = Date.now();
  if (reponse === "pris" || reponse === "poste") return;
  if (!nee) return;
  await chrome.windows.update(id, { state: "minimized" }).catch(() => {});
  __signal("focus?w=" + id + "&reduite=1");
});
// Fenetre ouverte par une page d'agent (popup, lien en nouvel onglet) : suivie
// comme les autres, laissee visible.
chrome.windows.onCreated.addListener(async (w) => {
  if (!__commandeEnCours() || __estAgent(w.id)) return;
  await new Promise(r => setTimeout(r, 150));
  const onglets = await chrome.tabs.query({ windowId: w.id }).catch(() => []);
  const parent = onglets[0]?.openerTabId != null ? await chrome.tabs.get(onglets[0].openerTabId).catch(() => null) : null;
  if (!parent || !__estAgent(parent.windowId) || __fenetresAvant.has(parent.windowId)) return;
  __fenetresNeuves.add(w.id);
  __fenetresPopups.add(w.id);
  __adopter(w.id);
  __signal("nouvelle?w=" + w.id + "&s=" + w.state);
});
chrome.windows.onRemoved.addListener((id) => { __fenetresPopups.delete(id); __neeA.delete(id); });
// v3.8 : balai des fenetres about:blank. Un agent qui s'arrete sans « close »
// laissait sa fenetre vide 10 min (bail interactif), et USER en voyait 1 ou 2.
// Toutes les 30 s : fenetre d'agent vide (about:blank ou nouvel onglet) et sans
// commande depuis 60 s, bail rendu (la fenetre se ferme). Fenetre inconnue mais
// entierement about:blank depuis 2 passages : fermee aussi (restes d'anciennes versions).
const __vuesVides = new Map();
const __estVide = (o) => !o.url || o.url === "about:blank" || o.url.startsWith("chrome://newtab");
// v3.12 : fenetre d'agent sans commande depuis 15 min = fermee, meme avec une
// page dedans (chaque onglet garde ~300 Mo). Heure de derniere commande par
// fenetre, dans chrome.storage.local : survit au rechargement de l'extension,
// effacee au demarrage de Chrome (les ids de fenetre repartent de 1).
// Une fenetre absente de cette carte n'est jamais touchee : c'est celle de USER.
const __INACTIF_MS = 15 * 60 * 1000;
let __activite = {};
var __chromeVientDeDemarrer = false;
chrome.runtime.onStartup.addListener(() => {
  __chromeVientDeDemarrer = true;
  __activite = {};
  for (const k of Object.keys(__fenetresRoles)) delete __fenetresRoles[k];
  chrome.storage.local.remove(["__opencliActivite", "__opencliFenetres"]).catch(() => {});
});
// Pages que des agents rouvrent seuls (demande de USER, 2026-10-16) : une fenetre
// faite uniquement de ces pages suit la meme regle de 15 min, sans focus de USER.
const __PAGES_AGENT = /(^|\.)(message\.alibaba\.com|1688\.com)$/;
const __pagesAgentSeules = (f) => (f.tabs || []).length > 0
  && f.tabs.every(o => { try { return __PAGES_AGENT.test(new URL(o.url).host); } catch { return false; } });
const __activitePrete = chrome.storage.local.get("__opencliActivite")
  .then(r => { if (!__chromeVientDeDemarrer) __activite = r.__opencliActivite || {}; }).catch(() => {});
const __sauverActivite = () => chrome.storage.local.set({ __opencliActivite: __activite }).catch(() => {});
// v3.13 : une fenetre d'agent perdait sa marque quand son bail finissait sans
// la fermer, ou quand c'etait une popup de ses pages (Reddit, Discord : 3
// orphelines le 2026-10-16). Elle entre donc dans la carte des sa naissance.
function __adopter(id) { __activitePrete.then(() => { if (!(id in __activite)) { __activite[id] = Date.now(); __sauverActivite(); } }); }
setInterval(async () => {
  const fenetres = await chrome.windows.getAll({ populate: true }).catch(() => []);
  const vivantes = new Set(fenetres.map(f => f.id));
  for (const id of [...__vuesVides.keys()]) if (!vivantes.has(id)) __vuesVides.delete(id);
  await __activitePrete;
  const maintenant = Date.now();
  let change = false;
  // v3.13 : orphelines d'avant, designees a la main (ids separes par des virgules).
  // Personne n'ecoute ce port en temps normal : la requete echoue, rien ne change.
  const aAdopter = await fetch("http://127.0.0.1:19826/adopter?t=" + maintenant).then(r => r.ok ? r.text() : "").catch(() => "");
  for (const id of aAdopter.split(",").map(Number)) if (vivantes.has(id) && !(id in __activite)) { __activite[id] = 1; change = true; }
  for (const id of Object.keys(__activite)) if (!vivantes.has(Number(id))) { delete __activite[id]; change = true; }
  // Fenetre liee a un onglet de USER (opencli browser bind) : jamais dans la carte.
  const liees = new Set([...automationSessions.values()].filter(s => !s.owned).map(s => s.windowId));
  for (const [k, s] of automationSessions.entries()) {
    if (!s.owned || s.windowId == null || !vivantes.has(s.windowId)) continue;
    const t = activeCommandCounts.has(k) ? maintenant : (__actions.get(k)?.t ?? 0);
    if (t > (__activite[s.windowId] ?? 0)) { __activite[s.windowId] = t; change = true; }
  }
  for (const f of fenetres) {
    if (liees.has(f.id)) continue;
    const suivie = f.id in __activite;
    if (!suivie && (__estAgent(f.id) || __pagesAgentSeules(f))) { __activite[f.id] = maintenant; change = true; }
    else if (suivie && f.focused) { __activite[f.id] = maintenant; change = true; }
  }
  if (change) __sauverActivite();
  for (const f of fenetres) {
    const derniere = __activite[f.id];
    if (!derniere || liees.has(f.id) || f.focused || maintenant - derniere < __INACTIF_MS) continue;
    const baux = [...automationSessions.entries()].filter(([, s]) => s.windowId === f.id);
    if (baux.some(([k]) => activeCommandCounts.has(k))) continue;
    for (const [k] of baux) await releaseLease(k, "inactive 15 min").catch(() => {});
    await chrome.windows.remove(f.id).catch(() => {});
    for (const [role, id] of Object.entries(__fenetresRoles)) if (id === f.id) __noterFenetre(role, null);
    delete __activite[f.id];
    __sauverActivite();
    vivantes.delete(f.id);
    const hotes = (f.tabs || []).map(o => { try { return new URL(o.url).host || "blank"; } catch { return "?"; } });
    __signal("balai?w=" + f.id + "&agent=1&inactive=1&baux=" + baux.length + "&onglets=" + encodeURIComponent(hotes.join(",")));
  }
  for (const f of fenetres) {
    if (!vivantes.has(f.id)) continue;
    const onglets = f.tabs || [];
    const vide = onglets.length === 0 || onglets.every(__estVide);
    if (!vide) { __vuesVides.delete(f.id); continue; }
    if (__neeA.has(f.id) && Date.now() - __neeA.get(f.id) < 20000) continue;
    if (__estAgent(f.id) || __fenetresAvant.has(f.id)) {
      const baux = [...automationSessions.entries()].filter(([, s]) => s.windowId === f.id);
      if (baux.some(([k]) => activeCommandCounts.has(k))) continue;
      const calme = baux.every(([k, s]) => !s.idleDeadlineAt || Date.now() - (s.idleDeadlineAt - getIdleTimeout(k)) > 60000);
      if (!calme) continue;
      for (const [k] of baux) await releaseLease(k, "fenetre vide").catch(() => {});
      await chrome.windows.remove(f.id).catch(() => {});
      for (const [role, id] of Object.entries(__fenetresRoles)) if (id === f.id) __noterFenetre(role, null);
      __signal("balai?w=" + f.id + "&agent=1&baux=" + baux.length);
    } else if (onglets.length && onglets.every(o => o.url === "about:blank") && !f.focused) {
      const n = (__vuesVides.get(f.id) ?? 0) + 1;
      __vuesVides.set(f.id, n);
      if (n < 2) continue;
      await chrome.windows.remove(f.id).catch(() => {});
      __signal("balai?w=" + f.id + "&agent=0");
    }
  }
}, 30000);
// Inventaire au demarrage, pour le diagnostic (hotes seulement, jamais d'URL complete).
setTimeout(async () => {
  const fenetres = await chrome.windows.getAll({ populate: true }).catch(() => []);
  for (const f of fenetres) {
    const hotes = (f.tabs || []).map(o => { try { return o.url === "about:blank" ? "blank" : new URL(o.url).host || o.url.slice(0, 12); } catch { return "?"; } });
    const baux = [...automationSessions.values()].filter(s => s.windowId === f.id).map(s => s.session);
    __signal("inventaire?w=" + f.id + "&etat=" + f.state + "&agent=" + (__estAgent(f.id) ? 1 : 0) + "&baux=" + encodeURIComponent(baux.join(",")) + "&onglets=" + encodeURIComponent(hotes.join(",")));
  }
}, 3000);
// v3.6 : rechargement automatique. Apres ce script ou une mise a jour d'opencli,
// le fichier change sur disque : l'extension se recharge des qu'aucune commande
// n'est en vol. Plus de clic a faire dans chrome://extensions.
const __urlScript = chrome.runtime.getURL("dist/background.js");
const __texteAuDemarrage = fetch(__urlScript, { cache: "no-store" }).then(r => r.text()).catch(() => null);
__signal("demarrage?v=3.13");
setInterval(async () => {
  if (activeCommandCounts.size > 0) return;
  const avant = await __texteAuDemarrage;
  const maintenant = await fetch(__urlScript, { cache: "no-store" }).then(r => r.text()).catch(() => null);
  if (avant && maintenant && maintenant.length > 1000 && avant !== maintenant) chrome.runtime.reload();
}, 20000);
'''

REMPLACEMENTS = [
    # v3 : plus aucun groupe d'onglets, pour aucun role.
    ('  if (role === "automation") return null;',
     '  return null; /* opencli-humain : aucun groupe d onglets */'),
    ('  container.windowId = win.id;\n  await persistRuntimeState();',
     '  container.windowId = win.id;\n  __noterFenetre(role, win.id);\n  await persistRuntimeState();'),
    ('const CONTAINER_TAB_GROUP_TITLE = {',
     'const CONTAINER_TAB_GROUP_TITLE = __titresParSession({'),
    ('  automation: "OpenCLI Adapter"\n};',
     '  automation: "OpenCLI Adapter"\n});'),
    ('const ownedContainers = {\n'
     '  interactive: { windowId: null, groupId: null, promise: null, groupPromise: null },\n'
     '  automation: { windowId: null, groupId: null, promise: null, groupPromise: null }\n'
     '};',
     'const ownedContainers = __conteneursParSession({\n'
     '  interactive: { windowId: null, groupId: null, promise: null, groupPromise: null },\n'
     '  automation: { windowId: null, groupId: null, promise: null, groupPromise: null }\n'
     '});'),
    ('  return getSurfaceFromKey(key) === "browser" ? "interactive" : "automation";',
     '  return getSurfaceFromKey(key) === "browser" ? "interactive:" + getSessionFromKey(key) : "automation";'),
    ('  return sessionOverrides.get(key)?.windowMode ?? (getOwnedWindowRole(key) === "interactive" ? "foreground" : "background");',
     '  return sessionOverrides.get(key)?.windowMode ?? "background";'),
    ('  return role === "automation" ? [] : [CONTAINER_TAB_GROUP_TITLE.interactive];',
     '  return role === "automation" ? [] : [CONTAINER_TAB_GROUP_TITLE[role]];'),
    # Session fermee et derniere de sa fenetre : on ferme la fenetre au lieu
    # de la garder vide pour une reutilisation qui n'arrive jamais (1 fenetre
    # par nom de session).
    ('      } else {\n        try {\n          const tab = await chrome.tabs.update(tabId, { url: BLANK_PAGE, active: true });',
     '      } else if (true) { /* v3.4 : toute fenetre OpenCLI vide se ferme */\n'
     '        const conteneur = ownedContainers[getOwnedWindowRole(leaseKey)];\n'
     '        conteneur.windowId = null; conteneur.groupId = null; conteneur.promise = null; conteneur.groupPromise = null;\n'
     '        __noterFenetre(getOwnedWindowRole(leaseKey), null);\n'
     '        await chrome.windows.remove(session.windowId).catch(() => chrome.tabs.remove(tabId).catch(() => {}));\n'
     '        console.log(`[opencli] Closed session window ${session.windowId} (session=${session.session}, ${reason})`);\n'
     '      } else {\n        try {\n          const tab = await chrome.tabs.update(tabId, { url: BLANK_PAGE, active: true });'),
    # v3.3 : onglets crees sans activer la fenetre (voir __ongletDiscret).
    ('    tab = await chrome.tabs.create({ windowId, url: targetUrl, active: true });',
     '    tab = await __ongletDiscret({ windowId, url: targetUrl, active: true });'),
    ('  const newTab = await chrome.tabs.create({ windowId: scopedWindowId, url: BLANK_PAGE, active: true });',
     '  const newTab = await __ongletDiscret({ windowId: scopedWindowId, url: BLANK_PAGE, active: true });'),
    ('      let tab = await chrome.tabs.create({ windowId, url: cmd.url ?? BLANK_PAGE, active: true });',
     '      let tab = await __ongletDiscret({ windowId, url: cmd.url ?? BLANK_PAGE, active: true });'),
    # v3.6 : la creation reduite de v3.4 est retiree. L'original cree deja
    # la fenetre sans focus en arriere-plan (focused: mode === "foreground").
    # v3.5 : repere la fin d'une commande et les fenetres demandees en avant-plan.
    ('  try {\n    switch (cmd.action) {',
     '  __actions.set(leaseKey, { a: cmd.action + (cmd.op ? ":" + cmd.op : "") + (cmd.cdpMethod ? ":" + cmd.cdpMethod : ""), t: Date.now() });\n  try {\n    switch (cmd.action) {'),
    ('    const remaining = (activeCommandCounts.get(leaseKey) ?? 1) - 1;',
     '    __finDerniereCommande = Date.now();\n    const remaining = (activeCommandCounts.get(leaseKey) ?? 1) - 1;'),
    ('  if (mode !== "foreground") return;\n  const updateWindow = chrome.windows.update;',
     '  if (mode !== "foreground") return;\n  __fenetresAvant.add(windowId);\n  const updateWindow = chrome.windows.update;'),
]


def main():
    if not CIBLE.exists():
        sys.exit(f"introuvable : {CIBLE}")
    texte = CIBLE.read_text()
    if "--retirer" in sys.argv:
        if not SAUVEGARDE.exists():
            sys.exit("pas de sauvegarde, rien a retirer")
        shutil.copy2(SAUVEGARDE, CIBLE)
        print("original restaure, recharger l'extension")
        return
    if MARQUE in texte:
        print("deja applique")
        return
    ancienne = any(m in texte for m in ANCIENNES)
    if ancienne:
        if not SAUVEGARDE.exists():
            sys.exit("ancienne version appliquee sans sauvegarde, mise a niveau impossible")
        texte = SAUVEGARDE.read_text()
        print("ancienne version remplacee par la courante")
    # Ancres que l'editeur a retirees : le code vise n'existe plus, rien a corriger.
    # 1.0.26 : getOwnedContainerGroupTitles supprimee (plus de recherche de groupe par titre).
    facultatives = {'  return role === "automation" ? [] : [CONTAINER_TAB_GROUP_TITLE.interactive];'}
    absentes = [a for a, _ in REMPLACEMENTS if a in facultatives and texte.count(a) == 0]
    for a in absentes:
        print("ancre retiree par l'editeur, ignoree :", a.strip()[:70])
    manquants = [a for a, _ in REMPLACEMENTS if a not in absentes and texte.count(a) != 1]
    if manquants:
        sys.exit("extension changee, correctif a revoir. Introuvable :\n" + "\n".join(m[:80] for m in manquants))
    if not ancienne:
        shutil.copy2(CIBLE, SAUVEGARDE)
    for avant, apres in REMPLACEMENTS:
        texte = texte.replace(avant, apres)
    CIBLE.write_text(AIDES + texte)
    print("applique, recharger l'extension (chrome://extensions, OpenCLI, bouton recharger)")


if __name__ == "__main__":
    main()
