# Manifest Q-szabály mentési szolgáltatás

A Manifest Szerkesztő közös Q-szabályait a kiadási repó q_rules.json fájljába mentő kis szolgáltatás. Ez a repó kizárólag a szolgáltatás forrását tartalmazza, üzemi adatot és hozzáférési kulcsot nem.

Indítás: `python q_rules_service.py`. Nincs külső Python-függőség. A `render.yaml` ingyenes, frankfurti példányt ír le, kézi telepítéssel.

A tárhely titkos környezeti változói: `Q_RULES_GITHUB_TOKEN` (a kiadási repóra korlátozott Contents írási jog) és `Q_RULES_ACCESS_KEY` (külön, legalább 32 karakteres mentési kulcs). Egyik érték sem kerülhet Gitbe. A GitHub-kulcs nem kerül a kliensbe.

Kulcsok nélkül a szolgáltatás biztonságosan elindul, de minden mentést visszautasít. `GET /health` a `configured` mezőben jelzi, hogy a mentés be van-e állítva. Ez önmagában nem bizonyítja a GitHub-kulcs írási jogosultságát.

`POST /q-rules`: Bearer mentési kulcs, base/rules/editor JSON-mezők. A szolgáltatás csak a rögzített kiadási repó main ágán lévő q_rules.json fájlt írja. A külön szabályokon végzett változtatásokat összevezeti, eltérő azonos szabálymódosításnál 409-et ad. A GitHub fájl-SHA-jával védi a mentést a párhuzamos felülírástól.
