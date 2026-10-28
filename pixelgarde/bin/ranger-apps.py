#!/usr/bin/env python3
"""Range les applications du Pixel en dossiers sur un ecran d'accueil.

Lit mapping.txt (paquet -> composant), produit le SQL a injecter dans launcher.db.
Chaque application est affectee a exactement un dossier.
"""
import sys, sqlite3, shutil

# Ordre = ordre d'affichage des dossiers sur l'ecran.
CATEGORIES = [
    ("Banque", [
        "com.bbl.mobilebanking", "com.kasikorn.retail.mbanking.wap", "ktbcs.netbank",
        "com.uob.mightyth2", "th.co.truemoney.wallet", "com.beeasy.airpay",
        "com.payoneer.android", "com.paypal.android.p2pmobile", "com.transferwise.android",
        "com.statrys.statrys", "com.aspireapp.sg", "com.airwallex",
        "com.stripe.android.dashboard", "com.rapyd.dev", "com.revenuedepartment.app",
        "com.moremins.moremins", "com.digitalchemy.currencyconverter",
        "com.tribab.tricount.android", "fr.free.moncomptefree", "fr.freemobile.android.vvm",
        "uk.gov.onelogin", "com.google.android.apps.walletnfcrel",
    ]),
    ("Crypto", [
        "com.kraken.invest.app", "com.kraken.pay.app", "com.kraken.trade",
        "com.bitkub", "com.bitazza.android", "io.metamask", "app.phantom",
        "com.solflare.mobile", "com.ledger.live", "com.coingecko.coingeckoapp",
        "com.coinglass.android", "com.coinstats.crypto.portfolio", "com.coinsoho.app",
        "com.dexscreener", "com.debank.meme", "com.geckoterminal.www.twa",
        "net.cryptobubbles", "io.coinmetrics.mobileapp", "com.kastfinance.app",
        "org.toshi", "org.brightid", "org.cryptomator", "com.gmgn.app",
    ]),
    ("Bourse", [
        "atws.app", "com.tradingview.tradingviewapp", "de.traderepublic.app",
        "com.kalodata.kalodata_android", "com.a3.yearlyprogess",
    ]),
    ("Messages", [
        "com.whatsapp", "com.whatsapp.w4b", "org.telegram.messenger",
        "jp.naver.line.android", "com.kakao.talk", "com.tencent.mm",
        "com.discord", "com.facebook.orca", "com.multibyte.esender.jiedian",
        "com.sonetel.sonetel2", "io.heckel.ntfy", "ch.protonmail.android",
        "com.microsoft.office.outlook",
    ]),
    ("Social", [
        "com.facebook.katana", "com.instagram.android", "com.twitter.android",
        "com.snapchat.android", "com.reddit.frontpage", "com.linkedin.android",
        "com.pinterest", "com.ss.android.ugc.trill", "com.skool.skoolcommunities",
        "com.meetup", "com.tinder", "jayraavi.SoloMatch", "com.sdcmedia.swingers.g4",
        "com.giphy.messenger", "com.friend.ios",
    ]),
    ("Voyage", [
        "com.agoda.mobile.consumer", "com.airbnb.android", "com.booking",
        "com.airasia.mobile", "com.NokAir.app", "com.bangkokairways.main",
        "com.traveloka.android", "com.kayak.android", "ctrip.english",
        "com.eventbrite.attendee", "com.viagogo.consumer.viagogo.playstore",
        "co.go12.ticketapp", "com.divessi.ssi", "com.funjumpr.app",
        "com.auroraclimbing.kilterboard",
    ]),
    ("Transport", [
        "com.grabtaxi.passenger", "ee.mtakso.client", "com.waze",
        "io.gbike.gcooter", "app.mobile.one2car", "com.koober.app",
        "th.co.exat.android.exatportal", "th.go.doh.mflow",
        "com.pttor.evstationpluz", "th.evolt.echarge", "com.rabbit_app",
    ]),
    ("Achats", [
        "com.lazada.android", "com.shopee.th", "com.alibaba.aliexpresshd",
        "com.alibaba.intl.android.apps.poseidon", "com.amazon.mShop.android.shopping",
        "com.amazon.sellermobile.android", "com.iherb", "com.privage.foodland",
        "com.linecorp.linemanth", "com.bzbs.burgerking", "com.shopify.arrive",
        "com.fiverr.fiverr", "net.zedge.android", "com.duns.padiapp",
    ]),
    ("Audio", [
        "com.spotify.music", "com.soundcloud.android", "com.aspiro.tidal",
        "com.audible.application", "com.audiobookshelf.app",
        "ak.alizandro.smartaudiobookplayer", "com.hyperionics.avar",
        "com.shazam.android", "org.jellyfin.mobile", "com.splendapps.decibel",
        "com.wo.voice2", "myrecorder.voicerecorder.voicememos.audiorecorder.recordingapp",
        "com.innosq.soundtypeai", "com.Relmtech.RemotePaid",
    ]),
    ("Sante", [
        "com.fitbit.FitbitMobile", "com.ouraring.oura", "com.wakingup.android",
        "org.wakingup.android", "com.ishafoundation.app", "org.sadhguru.miracleofmind",
        "com.projects.ayurythm", "com.pg.oralb.oralbapp", "com.brainbow.peak.app",
        "com.rivuspurus.nbackchallenge", "science.eal.n_backmemorytraining",
        "sudoku.puzzle.free.game.brain", "nl.deckeron.apps.innerfire",
        "com.simyasolutions.ling.universal", "air.com.eu.inove.sss2",
    ]),
    ("Astro", [
        "com.astrology.birthchart", "com.astrology.master", "com.cosmicapps.astrogold",
        "com.kurbetsoft.dreamspell", "com.re.planetaryhours4", "com.vitotechnology.Ephemeris",
        "com.noctuasoftware.stellarium_free", "com.jrustonapps.mymoonphase",
        "moon.free.moonphase.calendar.weather", "by.olion.Moon",
        "horoscopolunar.fasesluna.calendariolunar", "net.wilfinger.aquarius2go",
        "com.gregorio.katun", "com.nilecon.afteryou", "prox.lab.calclock",
    ]),
    ("IA", [
        "com.anthropic.claude", "com.openai.chatgpt", "ai.x.grok",
        "com.google.android.apps.bard", "com.google.android.apps.googleassistant",
        "com.canva.editor", "com.spaceship.ocr.textscanner.imagetotext",
    ]),
    ("Outils", [
        "com.tailscale.ipn", "ch.protonvpn.android", "com.nordvpn.android",
        "me.proton.android.drive", "com.dashlane", "com.azure.authenticator",
        "com.yubico.yubioath", "pl.solidexplorer2", "md.obsidian",
        "com.google.android.keep", "com.readwise", "app.alextran.immich",
        "com.realvnc.viewer.android", "com.google.chromeremotedesktop",
        "org.kde.kdeconnect_tp", "com.soomapps.screenmirroring", "com.zerodev.remote_control",
        "com.llamalab.automate", "com.topjohnwu.magisk", "com.fossor.panels",
        "io.appground.blek", "com.speed.gc.autoclicker.automatictap",
        "com.truedevelopersstudio.automatictap.autoclicker", "com.blogspot.newapphorizons.fakegps",
        "com.bluesharp.TrueWifi", "com.microsoft.appmanager", "host.exp.exponent",
        "com.taoapp.trafficdpro", "com.software.maya", "uni.UNIBB6F75A",
        "co.grey.mobile.android",
    ]),
    ("Services", [
        "com.google.android.apps.adm", "com.google.android.apps.adwords",
        "com.google.android.apps.chromecast.app", "com.google.android.apps.docs.editors.docs",
        "com.google.android.apps.docs.editors.sheets", "com.google.android.apps.magazines",
        "com.google.android.apps.subscriptions.red", "com.google.android.apps.translate",
        "com.google.android.apps.wear.companion", "com.casio.wac_app",
        "com.samsung.android.app.watchmanager", "com.samsung.android.oneconnect",
        "com.sec.android.easyMover", "com.DLT.SmartQueue", "com.doe.dwp",
        "com.truelife.mobile.android.trueiservice", "th.co.the1.the1app",
        "com.ntsuperapp", "com.mgcmobilife.mobilife", "net.mobcup.android",
    ]),
]

def intent(comp):
    pkg = comp.split('/')[0]
    return (f"#Intent;action=android.intent.action.MAIN;"
            f"category=android.intent.category.LAUNCHER;launchFlags=0x10200000;"
            f"package={pkg};component={comp};end")

def main():
    src, dst, ecran = sys.argv[1], sys.argv[2], int(sys.argv[3])
    comp = dict(l.split('\t') for l in open('mapping.txt').read().splitlines() if '\t' in l)

    classees = set()
    for _, pkgs in CATEGORIES:
        classees.update(pkgs)
    restantes = [p for p in comp if p not in classees]

    shutil.copy(src, dst)
    db = sqlite3.connect(dst)
    c = db.cursor()
    c.execute("SELECT MAX(_id) FROM favorites")
    uid = (c.fetchone()[0] or 0) + 100

    cats = [(n, [p for p in pkgs if p in comp]) for n, pkgs in CATEGORIES]
    if restantes:
        cats.append(("Divers", restantes))

    total, case = 0, 0
    for nom, pkgs in cats:
        if not pkgs:
            continue
        fid = uid; uid += 1
        cx, cy = case % 4, case // 4
        case += 1
        c.execute("INSERT INTO favorites (_id,title,intent,container,screen,cellX,cellY,"
                  "spanX,spanY,itemType,profileId,rank,restored) VALUES (?,?,NULL,-100,?,?,?,1,1,2,0,0,0)",
                  (fid, nom, ecran, cx, cy))
        for r, p in enumerate(pkgs):
            c.execute("INSERT INTO favorites (_id,title,intent,container,screen,cellX,cellY,"
                      "spanX,spanY,itemType,profileId,rank,restored) VALUES (?,?,?,?,0,0,0,1,1,0,0,?,0)",
                      (uid, p.split('.')[-1][:20], intent(comp[p]), fid, r))
            uid += 1; total += 1
        print(f"{nom:12} {len(pkgs):3} apps")
    db.commit(); db.close()
    print(f"---\n{len(cats)} dossiers, {total} apps placees sur l'ecran {ecran}")

main()
