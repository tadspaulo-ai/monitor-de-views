"""Exporta os dados publicos de todos os videos do canal para youtube_videos.json
(usado para analisar o que da mais views). Usa YT_API_KEY e YT_CHANNEL."""
import json
import os
import urllib.parse
import urllib.request

KEY, CANAL = os.environ["YT_API_KEY"].strip(), os.environ["YT_CHANNEL"].strip()
BASE = "https://www.googleapis.com/youtube/v3/"


def get(rec, **p):
    p["key"] = KEY
    with urllib.request.urlopen(BASE + rec + "?" + urllib.parse.urlencode(p), timeout=60) as r:
        return json.loads(r.read().decode())


p = {"part": "contentDetails,snippet,statistics"}
if CANAL.startswith("UC") and len(CANAL) == 24:
    p["id"] = CANAL
else:
    p["forHandle"] = CANAL if CANAL.startswith("@") else "@" + CANAL
canal = get("channels", **p)["items"][0]
uploads = canal["contentDetails"]["relatedPlaylists"]["uploads"]

ids, tok = [], None
while True:
    q = {"part": "contentDetails", "playlistId": uploads, "maxResults": 50}
    if tok:
        q["pageToken"] = tok
    r = get("playlistItems", **q)
    ids += [i["contentDetails"]["videoId"] for i in r["items"]]
    tok = r.get("nextPageToken")
    if not tok:
        break

videos = []
for i in range(0, len(ids), 50):
    r = get("videos", part="snippet,statistics,contentDetails,status,topicDetails", id=",".join(ids[i:i + 50]))
    for v in r["items"]:
        s, sn, cd = v.get("statistics", {}), v["snippet"], v["contentDetails"]
        videos.append({
            "id": v["id"],
            "titulo": sn["title"],
            "descricao": sn.get("description", "")[:300],
            "tags": sn.get("tags", []),
            "categoria": sn.get("categoryId"),
            "publicado_utc": sn["publishedAt"],
            "duracao": cd["duration"],
            "views": int(s.get("viewCount", 0)),
            "curtidas": int(s.get("likeCount", 0)),
            "comentarios": int(s.get("commentCount", 0)),
            "topicos": v.get("topicDetails", {}).get("topicCategories", []),
        })

with open("youtube_videos.json", "w", encoding="utf-8") as f:
    json.dump({"canal": {"titulo": canal["snippet"]["title"],
                         "inscritos": canal["statistics"].get("subscriberCount"),
                         "views_total": canal["statistics"].get("viewCount")},
               "videos": videos}, f, ensure_ascii=False, indent=1)
print(f"{len(videos)} videos exportados")
