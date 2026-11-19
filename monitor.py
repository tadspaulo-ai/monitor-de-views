"""Monitor de Views: le as estatisticas dos videos do YouTube e do TikTok,
compara com a rodada anterior e envia um relatorio por e-mail (Gmail) e,
opcionalmente, por WhatsApp (CallMeBot).

Configuracao por variaveis de ambiente (segredos do GitHub Actions):
  YT_API_KEY, YT_CHANNEL            -> chave da API e @handle ou ID do canal
  TIKTOK_CLIENT_KEY, TIKTOK_CLIENT_SECRET, TIKTOK_REFRESH_TOKEN
  GMAIL_USER, GMAIL_APP_PASSWORD, EMAIL_TO (opcional; padrao = GMAIL_USER)
  CALLMEBOT_PHONE, CALLMEBOT_APIKEY (opcional, WhatsApp)
  VIRAL_POR_HORA   (padrao 1000)  -> views ganhas em 1 hora para virar alerta
  VIRAL_TOTAL      (padrao 100000)-> total de views para entrar na lista de virais
  MODO_RELATORIO   (padrao "sempre"; "alertas" = so envia quando houver alerta)
"""
import json
import os
import smtplib
import ssl
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone, timedelta
from email.mime.text import MIMEText

ESTADO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "estado.json")
BRT = timezone(timedelta(hours=-3))


def env(nome, padrao=None):
    valor = os.environ.get(nome, "").strip()
    return valor or padrao


def http_json(url, data=None, headers=None, metodo=None):
    req = urllib.request.Request(url, data=data, headers=headers or {}, method=metodo)
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


# ---------------------------------------------------------------- YouTube
def youtube_videos(api_key, canal, limite=500):
    base = "https://www.googleapis.com/youtube/v3/"
    params = {"part": "contentDetails,snippet", "key": api_key}
    if canal.startswith("UC") and len(canal) == 24:
        params["id"] = canal
    else:
        params["forHandle"] = canal if canal.startswith("@") else "@" + canal
    dados = http_json(base + "channels?" + urllib.parse.urlencode(params))
    if not dados.get("items"):
        raise RuntimeError(f"Canal do YouTube nao encontrado: {canal}")
    uploads = dados["items"][0]["contentDetails"]["relatedPlaylists"]["uploads"]

    ids, pagina = [], None
    while len(ids) < limite:
        p = {"part": "contentDetails", "playlistId": uploads, "maxResults": 50, "key": api_key}
        if pagina:
            p["pageToken"] = pagina
        resp = http_json(base + "playlistItems?" + urllib.parse.urlencode(p))
        ids += [i["contentDetails"]["videoId"] for i in resp.get("items", [])]
        pagina = resp.get("nextPageToken")
        if not pagina:
            break

    videos = {}
    for i in range(0, len(ids), 50):
        p = {"part": "snippet,statistics", "id": ",".join(ids[i:i + 50]), "key": api_key}
        for v in http_json(base + "videos?" + urllib.parse.urlencode(p)).get("items", []):
            s = v.get("statistics", {})
            videos["yt:" + v["id"]] = {
                "plataforma": "YouTube",
                "titulo": v["snippet"]["title"],
                "url": f"https://youtu.be/{v['id']}",
                "views": int(s.get("viewCount", 0)),
                "curtidas": int(s.get("likeCount", 0)),
                "comentarios": int(s.get("commentCount", 0)),
            }
    return videos


# ---------------------------------------------------------------- TikTok
def tiktok_access_token(client_key, client_secret, refresh_token):
    corpo = urllib.parse.urlencode({
        "client_key": client_key,
        "client_secret": client_secret,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
    }).encode()
    resp = http_json("https://open.tiktokapis.com/v2/oauth/token/", data=corpo,
                     headers={"Content-Type": "application/x-www-form-urlencoded"})
    if "access_token" not in resp:
        raise RuntimeError(f"TikTok recusou o refresh token: {resp.get('error_description') or resp}")
    if resp.get("refresh_token") and resp["refresh_token"] != refresh_token:
        print("AVISO: o TikTok emitiu um novo refresh token; rode configurar.ps1 de novo se o TikTok parar.")
    return resp["access_token"]


def tiktok_videos(access_token, limite=500):
    campos = "id,title,video_description,share_url,view_count,like_count,comment_count,share_count"
    url = "https://open.tiktokapis.com/v2/video/list/?fields=" + campos
    videos, cursor = {}, None
    while len(videos) < limite:
        corpo = {"max_count": 20}
        if cursor:
            corpo["cursor"] = cursor
        resp = http_json(url, data=json.dumps(corpo).encode(), metodo="POST", headers={
            "Authorization": "Bearer " + access_token,
            "Content-Type": "application/json",
        })
        erro = resp.get("error", {})
        if erro.get("code") not in (None, "ok"):
            raise RuntimeError(f"Erro do TikTok: {erro.get('message') or erro}")
        dados = resp.get("data", {})
        for v in dados.get("videos", []):
            titulo = v.get("title") or v.get("video_description") or "(sem titulo)"
            videos["tt:" + v["id"]] = {
                "plataforma": "TikTok",
                "titulo": titulo.strip().splitlines()[0][:90],
                "url": v.get("share_url", ""),
                "views": int(v.get("view_count", 0)),
                "curtidas": int(v.get("like_count", 0)),
                "comentarios": int(v.get("comment_count", 0)),
                "compartilhamentos": int(v.get("share_count", 0)),
            }
        if not dados.get("has_more"):
            break
        cursor = dados.get("cursor")
    return videos


# ---------------------------------------------------------------- Relatorio
def fmt(n):
    return f"{n:,}".replace(",", ".")


def montar_relatorio(atuais, anteriores, por_hora, total_viral, erros):
    agora = datetime.now(BRT).strftime("%d/%m/%Y %H:%M")
    for chave, v in atuais.items():
        antes = anteriores.get(chave, {}).get("views")
        v["ganho"] = v["views"] - antes if antes is not None else None

    subindo = sorted([v for v in atuais.values() if v["ganho"] and v["ganho"] >= por_hora],
                     key=lambda v: v["ganho"], reverse=True)
    virais = sorted([v for v in atuais.values() if v["views"] >= total_viral],
                    key=lambda v: v["views"], reverse=True)
    top_hora = sorted([v for v in atuais.values() if v["ganho"]],
                      key=lambda v: v["ganho"], reverse=True)[:5]

    linhas = [f"Monitor de Views - {agora} (horario de Brasilia)", ""]
    for plat in ("YouTube", "TikTok"):
        vs = [v for v in atuais.values() if v["plataforma"] == plat]
        if vs:
            ganho = sum(v["ganho"] or 0 for v in vs)
            linhas.append(f"{plat}: {len(vs)} videos, {fmt(sum(v['views'] for v in vs))} views no total"
                          f" (+{fmt(ganho)} na ultima hora)")
    linhas.append("")

    if subindo:
        linhas.append(f"ALERTA - VIRALIZANDO AGORA (+{fmt(por_hora)} views/hora ou mais):")
        for v in subindo:
            linhas.append(f"  [{v['plataforma']}] +{fmt(v['ganho'])}/h | {fmt(v['views'])} views | {v['titulo']}")
            linhas.append(f"      {v['url']}")
        linhas.append("")

    if top_hora:
        linhas.append("Os que mais cresceram na ultima hora:")
        for v in top_hora:
            linhas.append(f"  [{v['plataforma']}] +{fmt(v['ganho'])} | {fmt(v['views'])} views | {v['titulo']}")
        linhas.append("")

    if virais:
        linhas.append(f"Seus virais (mais de {fmt(total_viral)} views):")
        for v in virais[:15]:
            linhas.append(f"  [{v['plataforma']}] {fmt(v['views'])} views | {fmt(v['curtidas'])} curtidas | {v['titulo']}")
            linhas.append(f"      {v['url']}")
        linhas.append("")

    if not anteriores:
        linhas.append("Primeira rodada: a partir da proxima hora o relatorio mostra quanto cada video cresceu.")
    for e in erros:
        linhas.append("PROBLEMA: " + e)

    assunto = f"🔥 {len(subindo)} video(s) viralizando" if subindo else "Relatorio de views"
    resumo_whats = None
    if subindo:
        partes = [f"[{v['plataforma']}] +{fmt(v['ganho'])}/h - {v['titulo'][:50]}" for v in subindo[:5]]
        resumo_whats = "Monitor de Views: viralizando agora!\n" + "\n".join(partes)
    return assunto, "\n".join(linhas), bool(subindo), resumo_whats


def enviar_email(usuario, senha, para, assunto, texto):
    msg = MIMEText(texto, "plain", "utf-8")
    msg["Subject"], msg["From"], msg["To"] = assunto, usuario, para
    with smtplib.SMTP_SSL("smtp.gmail.com", 465, context=ssl.create_default_context(), timeout=60) as s:
        s.ehlo()
        # usa so AUTH PLAIN: o login() padrao tenta outro metodo depois de uma recusa,
        # o Gmail derruba a conexao e o motivo real (ex.: senha errada) se perde
        s.user, s.password = usuario, senha
        s.auth("PLAIN", s.auth_plain)
        s.sendmail(usuario, [para], msg.as_string())


def enviar_whatsapp(telefone, apikey, texto):
    url = "https://api.callmebot.com/whatsapp.php?" + urllib.parse.urlencode(
        {"phone": telefone, "text": texto, "apikey": apikey})
    urllib.request.urlopen(url, timeout=60).read()


# ---------------------------------------------------------------- Main
def main():
    anteriores = {}
    if os.path.exists(ESTADO):
        with open(ESTADO, encoding="utf-8") as f:
            anteriores = json.load(f).get("videos", {})

    atuais, erros = {}, []
    if env("YT_API_KEY") and env("YT_CHANNEL"):
        try:
            atuais.update(youtube_videos(env("YT_API_KEY"), env("YT_CHANNEL")))
        except Exception as e:  # noqa: BLE001
            erros.append(f"YouTube: {e}")
    if env("TIKTOK_REFRESH_TOKEN"):
        try:
            token = tiktok_access_token(env("TIKTOK_CLIENT_KEY"), env("TIKTOK_CLIENT_SECRET"),
                                        env("TIKTOK_REFRESH_TOKEN"))
            atuais.update(tiktok_videos(token))
        except Exception as e:  # noqa: BLE001
            erros.append(f"TikTok: {e}")

    assunto, texto, tem_alerta, whats = montar_relatorio(
        atuais, anteriores, int(env("VIRAL_POR_HORA", "1000")), int(env("VIRAL_TOTAL", "100000")), erros)
    print(texto)

    # guarda so os numeros necessarios para a proxima comparacao (antes de enviar,
    # para que uma falha no envio nao apague o historico)
    salvar = {k: {"views": v["views"]} for k, v in atuais.items()}
    for k, v in anteriores.items():  # nao perde o historico se uma plataforma falhar
        salvar.setdefault(k, v)
    with open(ESTADO, "w", encoding="utf-8") as f:
        json.dump({"atualizado": datetime.now(timezone.utc).isoformat(), "videos": salvar}, f, indent=1)

    falhou = not atuais and bool(erros)
    if env("MODO_RELATORIO", "sempre") == "sempre" or tem_alerta or erros:
        if env("GMAIL_USER") and env("GMAIL_APP_PASSWORD"):
            try:
                enviar_email(env("GMAIL_USER"), env("GMAIL_APP_PASSWORD"),
                             env("EMAIL_TO", env("GMAIL_USER")), assunto, texto)
                print("E-mail enviado.")
            except smtplib.SMTPException as e:
                print(f"ERRO NO E-MAIL: o Gmail recusou o login ({type(e).__name__}: {e}). "
                      "Confira se GMAIL_USER e o endereco completo e se GMAIL_APP_PASSWORD e uma senha de app.")
                falhou = True
    if whats and env("CALLMEBOT_PHONE") and env("CALLMEBOT_APIKEY"):
        try:
            enviar_whatsapp(env("CALLMEBOT_PHONE"), env("CALLMEBOT_APIKEY"), whats)
            print("WhatsApp enviado.")
        except Exception as e:  # noqa: BLE001
            print(f"ERRO NO WHATSAPP: {e}")

    if falhou:
        sys.exit(1)


if __name__ == "__main__":
    main()
